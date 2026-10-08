import csv
import hashlib
import hmac
import io
import tempfile
import uuid
from pathlib import Path
import secrets
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db, engine
from app.models.portfolio import Portfolio, PortfolioPreviewRecord, PortfolioResults
from app.models.user import User
from app.schemas.portfolio import (
    ChatRequest,
    ChatResponse,
    ExplainResponse,
    PortfolioEmailRequest,
    PortfolioEmailResponse,
    PortfolioRead,
    PortfolioResultsRead,
    PortfolioUploadRead,
    RecordEditBatch,
    ReportRequest,
    ReportResponse,
)
from app.services.auth_service import JWT_ALGORITHM, bearer_scheme, get_current_user
from app.services.brevo_service import send_portfolio_csv
from app.services.llm.action_recommender import recommend_actions
from app.services.llm.client import chat as llm_chat
from app.services.llm.result_explainer import explain_results
from app.services.ml.predictor import predict_hazard_scores
from app.services.portfolio_etl import (
    EXPOSURE_FIELDS,
    HAZARD_FIELDS,
    exposure_record_hash,
    get_portfolio_table,
    make_table_name,
    process_portfolio,
    publish_portfolio,
)
from app.services.portfolio_results_service import compute_and_store_results

router = APIRouter(prefix="/portfolios", tags=["portfolios"])
UPLOAD_DIR = Path(tempfile.gettempdir()) / "fusion_portfolio_uploads"
UPLOAD_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
ALLOWED_SUFFIXES = {".csv", ".pdf", ".docx"}
PREDICTABLE_STATUSES = {"completed", "completed_with_warnings", "predicted", "prediction_failed"}


def _get_portfolio(db: Session, portfolio_id: str, access_token: str) -> Portfolio:
    portfolio = db.get(Portfolio, portfolio_id)
    if portfolio is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    token_hash = hashlib.sha256(access_token.encode("utf-8")).hexdigest()
    if not hmac.compare_digest(token_hash, portfolio.access_token_hash):
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return portfolio


def _optional_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> int | None:
    """Extract user_id from JWT if present; return None if missing or invalid."""
    if credentials is None or credentials.scheme.lower() != "bearer" or not settings.jwt_secret:
        return None
    try:
        import jwt
        payload = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
        user_id = int(payload["sub"])
        return user_id if db.get(User, user_id) is not None else None
    except Exception:
        return None


def _get_results_or_compute(portfolio: Portfolio, db: Session) -> PortfolioResults:
    existing = db.get(PortfolioResults, portfolio.id)
    if existing is not None:
        return existing
    if portfolio.status not in {"predicted", "confirmed", *PREDICTABLE_STATUSES}:
        raise HTTPException(status_code=409, detail="Run hazard prediction before viewing results")
    try:
        return compute_and_store_results(portfolio, db)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Results computation failed: {exc}") from exc


# ── List (authenticated) ──────────────────────────────────────────────────────

@router.get("", response_model=list[PortfolioRead])
def list_portfolios(
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Portfolio]:
    """List all portfolios belonging to the signed-in user, newest first."""
    try:
        return list(
            db.scalars(
                select(Portfolio)
                .where(Portfolio.user_id == current_user.id)
                .order_by(Portfolio.created_at.desc())
                .offset(offset)
                .limit(limit)
            ).all()
        )
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Unable to query portfolios") from exc


# ── Upload ────────────────────────────────────────────────────────────────────

@router.post("", response_model=PortfolioUploadRead, status_code=202)
async def upload_portfolio(
    background_tasks: BackgroundTasks,
    name: str = Form(min_length=1, max_length=160),
    file: UploadFile = File(...),
    user_id: int | None = Depends(_optional_user_id),
    db: Session = Depends(get_db),
) -> Portfolio:
    filename = Path(file.filename or "upload").name
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=415, detail="Upload a CSV, PDF, or DOCX file")
    name = name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Portfolio name cannot be blank")

    UPLOAD_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    portfolio_id = str(uuid.uuid4())
    access_token = secrets.token_urlsafe(32)
    temporary_path = UPLOAD_DIR / f"{portfolio_id}{suffix}"
    max_bytes = max(1, settings.portfolio_upload_max_mb) * 1024 * 1024
    size = 0
    try:
        with temporary_path.open("wb") as destination:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(status_code=413, detail="Uploaded file exceeds the configured size limit")
                destination.write(chunk)
        if size == 0:
            raise HTTPException(status_code=422, detail="Uploaded file is empty")

        portfolio = Portfolio(
            id=portfolio_id,
            name=name,
            table_name=make_table_name(name, portfolio_id),
            access_token_hash=hashlib.sha256(access_token.encode("utf-8")).hexdigest(),
            original_filename=filename[:255],
            status="queued",
            total_rows=0,
            dropped_rows=0,
            user_id=user_id,
        )
        db.add(portfolio)
        db.commit()
        db.refresh(portfolio)
        background_tasks.add_task(process_portfolio, portfolio.id, str(temporary_path))
        return PortfolioUploadRead(
            **PortfolioRead.model_validate(portfolio).model_dump(),
            access_token=access_token,
        )
    except HTTPException:
        temporary_path.unlink(missing_ok=True)
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        temporary_path.unlink(missing_ok=True)
        raise HTTPException(status_code=503, detail="Unable to create portfolio") from exc
    except Exception as exc:
        db.rollback()
        temporary_path.unlink(missing_ok=True)
        raise HTTPException(status_code=503, detail="Unable to start portfolio processing") from exc
    finally:
        await file.close()


# ── Status / preview / edit / predict / confirm / export / email ──────────────

@router.get("/{portfolio_id}/status", response_model=PortfolioRead)
def portfolio_status(
    portfolio_id: str,
    access_token: str = Header(alias="X-Portfolio-Token"),
    db: Session = Depends(get_db),
) -> Portfolio:
    return _get_portfolio(db, portfolio_id, access_token)


@router.get("/{portfolio_id}/preview")
def preview_portfolio(
    portfolio_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    access_token: str = Header(alias="X-Portfolio-Token"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    portfolio = _get_portfolio(db, portfolio_id, access_token)
    if engine is None:
        raise HTTPException(status_code=503, detail="Database is not configured")
    try:
        if portfolio.status == "confirmed":
            table = get_portfolio_table(portfolio.table_name)
            with engine.connect() as connection:
                total = connection.execute(select(func.count()).select_from(table)).scalar_one()
                statement = (
                    select(*(table.c[field] for field in (*EXPOSURE_FIELDS, *HAZARD_FIELDS)))
                    .order_by(table.c.loc_id).offset(offset).limit(limit)
                )
                records = [dict(row) for row in connection.execute(statement).mappings().all()]
        else:
            total = db.scalar(
                select(func.count()).select_from(PortfolioPreviewRecord)
                .where(PortfolioPreviewRecord.portfolio_id == portfolio_id)
            ) or 0
            staged = db.scalars(
                select(PortfolioPreviewRecord)
                .where(PortfolioPreviewRecord.portfolio_id == portfolio_id)
                .order_by(PortfolioPreviewRecord.loc_id).offset(offset).limit(limit)
            ).all()
            records = [row.record_data for row in staged]
        return {
            "portfolio_id": portfolio.id,
            "portfolio_name": portfolio.name,
            "status": portfolio.status,
            "total": total,
            "dropped_rows": portfolio.dropped_rows,
            "limit": limit,
            "offset": offset,
            "records": records,
        }
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Unable to load portfolio preview") from exc


@router.patch("/{portfolio_id}/preview")
def edit_portfolio_preview(
    portfolio_id: str,
    changes: RecordEditBatch,
    access_token: str = Header(alias="X-Portfolio-Token"),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    portfolio = _get_portfolio(db, portfolio_id, access_token)
    if portfolio.status not in PREDICTABLE_STATUSES:
        raise HTTPException(status_code=409, detail="Wait for extraction to finish before editing")
    try:
        updated = 0
        for edit in changes.records:
            values = edit.model_dump(exclude_unset=True)
            loc_id = values.pop("loc_id")
            if not values:
                continue
            for required in ("lat", "lon", "housing_class", "floor_area_m2", "cost_per_m2_kes", "tiv_kes"):
                if required in values and values[required] is None:
                    raise HTTPException(status_code=422, detail=f"{required} cannot be null")
            staged = db.scalar(
                select(PortfolioPreviewRecord).where(
                    PortfolioPreviewRecord.portfolio_id == portfolio_id,
                    PortfolioPreviewRecord.loc_id == loc_id,
                )
            )
            if staged is None:
                continue
            record_data = dict(staged.record_data)
            record_data.update(values)
            record_data.update({field: None for field in HAZARD_FIELDS})
            staged.record_data = record_data
            staged.record_hash = exposure_record_hash(record_data)
            updated += 1
        if updated != len(changes.records):
            raise HTTPException(status_code=404, detail="One or more location IDs were not found")
        db.commit()
        if portfolio.status == "predicted":
            portfolio.status = "completed"
            db.commit()
        return {"updated": updated}
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="Unable to update portfolio preview") from exc


@router.post("/{portfolio_id}/predict")
def predict_portfolio(
    portfolio_id: str,
    access_token: str = Header(alias="X-Portfolio-Token"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    portfolio = _get_portfolio(db, portfolio_id, access_token)
    if portfolio.status not in PREDICTABLE_STATUSES:
        raise HTTPException(status_code=409, detail="Portfolio extraction must finish before prediction")
    if engine is None:
        raise HTTPException(status_code=503, detail="Database is not configured")
    try:
        portfolio.status = "predicting"
        db.commit()
        updated = 0
        cursor = ""
        while True:
            batch = db.scalars(
                select(PortfolioPreviewRecord)
                .where(
                    PortfolioPreviewRecord.portfolio_id == portfolio_id,
                    PortfolioPreviewRecord.loc_id > cursor,
                )
                .order_by(PortfolioPreviewRecord.loc_id)
                .limit(500)
            ).all()
            if not batch:
                break
            predictions = predict_hazard_scores([dict(row.record_data) for row in batch])
            for row, scores in zip(batch, predictions):
                record_data = dict(row.record_data)
                record_data.update({field: float(score) for field, score in zip(HAZARD_FIELDS, scores)})
                row.record_data = record_data
            cursor = batch[-1].loc_id
            updated += len(batch)
            db.commit()
        portfolio.status = "predicted"
        db.commit()
        return {"portfolio_id": portfolio.id, "predicted": updated, "status": portfolio.status}
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        portfolio.status = "prediction_failed"
        portfolio.error = str(exc)[:2000]
        db.commit()
        raise HTTPException(status_code=422, detail=f"Hazard prediction failed: {exc}") from exc


@router.post("/{portfolio_id}/confirm", response_model=PortfolioRead, status_code=202)
def confirm_portfolio(
    portfolio_id: str,
    background_tasks: BackgroundTasks,
    access_token: str = Header(alias="X-Portfolio-Token"),
    db: Session = Depends(get_db),
) -> Portfolio:
    portfolio = _get_portfolio(db, portfolio_id, access_token)
    if portfolio.status == "confirmed":
        return portfolio
    if portfolio.status not in {"predicted", "confirmation_failed", "publishing"}:
        raise HTTPException(status_code=409, detail="Run hazard prediction before confirming the portfolio")
    if portfolio.status != "publishing":
        portfolio.status = "publishing"
        portfolio.error = None
        db.commit()
        db.refresh(portfolio)
    background_tasks.add_task(publish_portfolio, portfolio.id)
    return portfolio


@router.get("/{portfolio_id}/export.csv")
def export_portfolio_csv(
    portfolio_id: str,
    access_token: str = Header(alias="X-Portfolio-Token"),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    portfolio = _get_portfolio(db, portfolio_id, access_token)
    if portfolio.status != "confirmed":
        raise HTTPException(status_code=409, detail="Confirm the portfolio before exporting")
    if engine is None:
        raise HTTPException(status_code=503, detail="Database is not configured")
    table = get_portfolio_table(portfolio.table_name)
    fields = (*EXPOSURE_FIELDS, *HAZARD_FIELDS)

    def generate():
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(fields)
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)
        with engine.connect() as connection:
            result = connection.execution_options(stream_results=True).execute(
                select(*(table.c[field] for field in fields)).order_by(table.c.loc_id)
            )
            while rows := result.fetchmany(1000):
                for row in rows:
                    writer.writerow(row)
                yield buffer.getvalue()
                buffer.seek(0)
                buffer.truncate(0)

    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{portfolio.table_name}.csv"'},
    )


@router.post("/{portfolio_id}/email", response_model=PortfolioEmailResponse)
def email_portfolio_csv(
    portfolio_id: str,
    request: PortfolioEmailRequest,
    access_token: str = Header(alias="X-Portfolio-Token"),
    db: Session = Depends(get_db),
) -> PortfolioEmailResponse:
    portfolio = _get_portfolio(db, portfolio_id, access_token)
    if portfolio.status != "confirmed":
        raise HTTPException(status_code=409, detail="Approve the portfolio before emailing its CSV")
    if engine is None:
        raise HTTPException(status_code=503, detail="Database is not configured")

    table = get_portfolio_table(portfolio.table_name)
    fields = (*EXPOSURE_FIELDS, *HAZARD_FIELDS)
    buffer = io.BytesIO()
    text_buffer = io.TextIOWrapper(buffer, encoding="utf-8", newline="", write_through=True)
    writer = csv.writer(text_buffer)
    writer.writerow(fields)
    max_bytes = max(1, settings.portfolio_email_max_mb) * 1024 * 1024
    try:
        with engine.connect() as connection:
            result = connection.execution_options(stream_results=True).execute(
                select(*(table.c[field] for field in fields)).order_by(table.c.loc_id)
            )
            while rows := result.fetchmany(500):
                writer.writerows(rows)
                text_buffer.flush()
                if buffer.tell() > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail="CSV is too large to attach to email; download it from the export endpoint",
                    )
        csv_bytes = buffer.getvalue()
        message_id = send_portfolio_csv(
            request.email,
            portfolio.name,
            f"{portfolio.table_name}.csv",
            csv_bytes,
        )
        return PortfolioEmailResponse(sent=True, message_id=message_id)
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Unable to read the approved portfolio") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Brevo could not send the portfolio email") from exc
    finally:
        text_buffer.detach()


# ── Results ───────────────────────────────────────────────────────────────────

@router.get("/{portfolio_id}/results", response_model=PortfolioResultsRead)
def get_portfolio_results(
    portfolio_id: str,
    access_token: str = Header(alias="X-Portfolio-Token"),
    db: Session = Depends(get_db),
) -> PortfolioResults:
    """Return loss totals and exceedance curve. Computes and caches on first call."""
    portfolio = _get_portfolio(db, portfolio_id, access_token)
    return _get_results_or_compute(portfolio, db)


# ── AI features ───────────────────────────────────────────────────────────────

@router.post("/{portfolio_id}/explain", response_model=ExplainResponse)
def explain_portfolio(
    portfolio_id: str,
    access_token: str = Header(alias="X-Portfolio-Token"),
    db: Session = Depends(get_db),
) -> ExplainResponse:
    """Generate a plain-language explanation of the portfolio's risk results."""
    portfolio = _get_portfolio(db, portfolio_id, access_token)
    results = _get_results_or_compute(portfolio, db)
    results_dict = {
        "total_tiv_kes": results.total_tiv_kes,
        "total_rows": results.total_rows,
        "eal_common_kes": results.eal_common_kes,
        "eal_occasional_kes": results.eal_occasional_kes,
        "eal_moderate_kes": results.eal_moderate_kes,
        "eal_severe_kes": results.eal_severe_kes,
        "eal_extreme_kes": results.eal_extreme_kes,
        "eal_total_kes": results.eal_total_kes,
        "exceedance_curve": results.exceedance_curve,
        "top_locations": results.top_locations,
    }
    try:
        explanation = explain_results(portfolio.name, results_dict)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ExplainResponse(explanation=explanation)


@router.post("/{portfolio_id}/chat", response_model=ChatResponse)
def chat_portfolio(
    portfolio_id: str,
    request: ChatRequest,
    access_token: str = Header(alias="X-Portfolio-Token"),
    db: Session = Depends(get_db),
) -> ChatResponse:
    """Answer questions about the portfolio using its results as context."""
    portfolio = _get_portfolio(db, portfolio_id, access_token)
    results = _get_results_or_compute(portfolio, db)

    system = (
        f"You are a flood risk analyst assistant for the portfolio '{portfolio.name}'. "
        f"Total Insured Value: KES {results.total_tiv_kes:,.0f}. "
        f"Expected Annual Loss: KES {results.eal_total_kes:,.0f}. "
        f"Locations: {results.total_rows}. "
        "Answer questions concisely using only the data provided. "
        "Do not invent figures."
    )
    messages = [{"role": "system", "content": system}] + [
        {"role": m.role, "content": m.content} for m in request.messages
    ]
    try:
        reply = llm_chat(messages, max_tokens=512)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ChatResponse(reply=reply)


@router.put("/{portfolio_id}/report", response_model=ReportResponse)
def generate_report(
    portfolio_id: str,
    request: ReportRequest,
    access_token: str = Header(alias="X-Portfolio-Token"),
    db: Session = Depends(get_db),
) -> ReportResponse:
    """Generate a full narrative report and action recommendations."""
    portfolio = _get_portfolio(db, portfolio_id, access_token)
    results = _get_results_or_compute(portfolio, db)
    results_dict = {
        "total_tiv_kes": results.total_tiv_kes,
        "total_rows": results.total_rows,
        "eal_common_kes": results.eal_common_kes,
        "eal_occasional_kes": results.eal_occasional_kes,
        "eal_moderate_kes": results.eal_moderate_kes,
        "eal_severe_kes": results.eal_severe_kes,
        "eal_extreme_kes": results.eal_extreme_kes,
        "eal_total_kes": results.eal_total_kes,
        "exceedance_curve": results.exceedance_curve,
        "top_locations": results.top_locations,
    }
    try:
        report = explain_results(request.title or portfolio.name, results_dict)
        actions = recommend_actions(portfolio.name, results_dict)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ReportResponse(report=report, actions=actions)
