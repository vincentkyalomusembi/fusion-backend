from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.location import Location
from app.schemas.location import LocationRead

router = APIRouter(prefix="/locations", tags=["locations"])


@router.get("", response_model=list[LocationRead])
def list_locations(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[Location]:
    try:
        statement = select(Location).order_by(Location.loc_id).offset(offset).limit(limit)
        return list(db.scalars(statement).all())
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Unable to query locations") from exc


@router.get("/{loc_id}", response_model=LocationRead)
def get_location(loc_id: str, db: Session = Depends(get_db)) -> Location:
    try:
        location = db.get(Location, loc_id)
        if location is None:
            raise HTTPException(status_code=404, detail="Location not found")
        return location
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Unable to query locations") from exc
