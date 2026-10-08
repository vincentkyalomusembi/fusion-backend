import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.refresh_token import RefreshToken
from app.models.user import User

password_hash = PasswordHash.recommended()
JWT_ALGORITHM = "HS256"
bearer_scheme = HTTPBearer(auto_error=False)


# ── Passwords ─────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


# ── Access token (short-lived JWT, stateless) ─────────────────────────────────

def create_access_token(user_id: int) -> tuple[str, int]:
    if not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET is not configured")
    expires_in = settings.jwt_access_token_minutes * 60
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    token = jwt.encode(
        {"sub": str(user_id), "iat": datetime.now(timezone.utc), "exp": expires_at},
        settings.jwt_secret,
        algorithm=JWT_ALGORITHM,
    )
    return token, expires_in


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired access token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None or credentials.scheme.lower() != "bearer" or not settings.jwt_secret:
        raise unauthorized
    try:
        payload = jwt.decode(
            credentials.credentials, settings.jwt_secret, algorithms=[JWT_ALGORITHM]
        )
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError) as exc:
        raise unauthorized from exc
    user = db.get(User, user_id)
    if user is None:
        raise unauthorized
    return user


# ── Refresh token (long-lived, stored as hash, rotated on every use) ──────────

def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create_refresh_token(user_id: int, db: Session) -> str:
    """Generate a refresh token, persist its hash, and return the raw value."""
    raw = secrets.token_urlsafe(48)
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_days)
    db.add(RefreshToken(user_id=user_id, token_hash=_hash_token(raw), expires_at=expires_at))
    db.commit()
    return raw


def rotate_refresh_token(raw_token: str, db: Session) -> tuple[User, str]:
    """
    Validate the incoming refresh token, revoke it, issue a new one.

    Raises 401 if the token is unknown, revoked, or expired.
    Raises 401 with a reuse-detection hint if the token was already revoked
    (possible token theft — all tokens for that user are invalidated).
    """
    token_hash = _hash_token(raw_token)
    record = db.query(RefreshToken).filter_by(token_hash=token_hash).first()

    if record is None:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if record.revoked:
        # Possible replay attack — nuke every token for this user
        db.execute(delete(RefreshToken).where(RefreshToken.user_id == record.user_id))
        db.commit()
        raise HTTPException(
            status_code=401,
            detail="Refresh token already used. All sessions have been revoked for security.",
        )

    if record.expires_at < datetime.now(timezone.utc):
        db.delete(record)
        db.commit()
        raise HTTPException(status_code=401, detail="Refresh token has expired, please sign in again")

    user = db.get(User, record.user_id)
    if user is None:
        db.delete(record)
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    # Revoke the used token and issue a fresh one (rotation)
    record.revoked = True
    db.commit()
    new_raw = create_refresh_token(user.id, db)
    return user, new_raw


def revoke_refresh_token(raw_token: str, db: Session) -> None:
    """Mark a refresh token as revoked (signout)."""
    token_hash = _hash_token(raw_token)
    record = db.query(RefreshToken).filter_by(token_hash=token_hash).first()
    if record and not record.revoked:
        record.revoked = True
        db.commit()


def purge_expired_tokens(db: Session) -> int:
    """Delete all expired tokens. Call periodically from a background job."""
    result = db.execute(
        delete(RefreshToken).where(RefreshToken.expires_at < datetime.now(timezone.utc))
    )
    db.commit()
    return result.rowcount
