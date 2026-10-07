from sqlalchemy import Boolean, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Location(Base):
    __tablename__ = "locations"

    loc_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    housing_class: Mapped[str] = mapped_column(String(64), nullable=False)
    floor_area_m2: Mapped[float] = mapped_column(Float, nullable=False)
    cost_per_m2_kes: Mapped[float] = mapped_column(Float, nullable=False)
    tiv_kes: Mapped[float] = mapped_column(Float, nullable=False)
    synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    hazard_score_common: Mapped[float] = mapped_column(Float, nullable=False)
    hazard_score_occasional: Mapped[float] = mapped_column(Float, nullable=False)
    hazard_score_moderate: Mapped[float] = mapped_column(Float, nullable=False)
    hazard_score_severe: Mapped[float] = mapped_column(Float, nullable=False)
    hazard_score_extreme: Mapped[float] = mapped_column(Float, nullable=False)
    hazard_severity: Mapped[float] = mapped_column(Float, nullable=False)
