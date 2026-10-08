from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.hotspot import Hotspot
from app.schemas.hotspot import HotspotCreate, HotspotRead, HotspotUploadResult

router = APIRouter(prefix="/hotspots", tags=["hotspots"])


@router.get("", response_model=list[HotspotRead])
def list_hotspots(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[Hotspot]:
    try:
        statement = select(Hotspot).order_by(Hotspot.name).offset(offset).limit(limit)
        return list(db.scalars(statement).all())
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Unable to query hotspots") from exc


@router.post("/bulk", response_model=HotspotUploadResult)
def upload_hotspots(
    hotspots: list[HotspotCreate], db: Session = Depends(get_db)
) -> HotspotUploadResult:
    """Create or update hotspots by name from a JSON array."""
    names = [hotspot.name.strip() for hotspot in hotspots]
    if any(not name for name in names):
        raise HTTPException(status_code=422, detail="Hotspot names cannot be blank")
    if len(set(names)) != len(names):
        raise HTTPException(status_code=422, detail="Each hotspot name must be unique in the upload")

    try:
        existing = {
            row.name: row
            for row in db.scalars(select(Hotspot).where(Hotspot.name.in_(names))).all()
        } if names else {}
        created = 0
        updated = 0
        for item, name in zip(hotspots, names):
            row = existing.get(name)
            if row is None:
                db.add(Hotspot(name=name, lat=item.lat, lon=item.lon))
                created += 1
            else:
                row.lat = item.lat
                row.lon = item.lon
                updated += 1
        db.commit()
        return HotspotUploadResult(received=len(hotspots), created=created, updated=updated)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="Unable to save hotspots") from exc
