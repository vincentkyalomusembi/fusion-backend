from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.auth import AuthResponse, Credentials, RefreshRequest, RefreshResponse, UserRead
from app.services.auth_service import (
    create_access_token,
    create_refresh_token,
    get_current_user,
    hash_password,
    revoke_refresh_token,
    rotate_refresh_token,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["authentication"])


def _response_for(user: User, db: Session) -> AuthResponse:
    try:
        access_token, expires_in = create_access_token(user.id)
        refresh_token = create_refresh_token(user.id, db)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return AuthResponse(
        access_token=access_token,
        expires_in=expires_in,
        refresh_token=refresh_token,
        user=user,
    )


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def sign_up(credentials: Credentials, db: Session = Depends(get_db)) -> AuthResponse:
    email = str(credentials.email).strip().lower()
    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    user = User(email=email, password_hash=hash_password(credentials.password))
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists") from exc
    return _response_for(user, db)


@router.post("/signin", response_model=AuthResponse)
def sign_in(credentials: Credentials, db: Session = Depends(get_db)) -> AuthResponse:
    email = str(credentials.email).strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return _response_for(user, db)


@router.post("/refresh", response_model=RefreshResponse)
def refresh(body: RefreshRequest, db: Session = Depends(get_db)) -> RefreshResponse:
    """
    Exchange a valid refresh token for a new access token + rotated refresh token.
    The old refresh token is immediately invalidated.
    """
    user, new_refresh_token = rotate_refresh_token(body.refresh_token, db)
    try:
        access_token, expires_in = create_access_token(user.id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return RefreshResponse(
        access_token=access_token,
        expires_in=expires_in,
        refresh_token=new_refresh_token,
    )


@router.post("/signout", status_code=status.HTTP_204_NO_CONTENT)
def sign_out(body: RefreshRequest, db: Session = Depends(get_db)) -> None:
    """
    Revoke the refresh token. The access token will naturally expire in 45 min.
    Send the refresh token in the request body to invalidate the session.
    """
    revoke_refresh_token(body.refresh_token, db)


@router.get("/me", response_model=UserRead)
def current_user(user: User = Depends(get_current_user)) -> User:
    return user
