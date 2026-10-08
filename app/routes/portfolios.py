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
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db, engine
from app.models.portfolio import Portfolio, PortfolioPreviewRecord
from app.schemas.portfolio import (
    PortfolioEmailRequest,
    PortfolioEmailResponse,
    PortfolioRead,
    PortfolioUploadRead,
    RecordEditBatch,
)
from app.services.brevo_service import send_portfolio_csv
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


@router.post("", response_model=PortfolioUploadRead, status_code=202)
async def upload_portfolio(
    background_tasks: BackgroundTasks,
    name: str = Form(min_length=1, max_length=160),
    file: UploadFile = File(...),
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
