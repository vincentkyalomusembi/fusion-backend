from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    table_name: Mapped[str] = mapped_column(String(63), nullable=False, unique=True)
    access_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dropped_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PortfolioResults(Base):
    __tablename__ = "portfolio_results"

    portfolio_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("portfolios.id", ondelete="CASCADE"), primary_key=True
    )
    total_tiv_kes: Mapped[float] = mapped_column(Float, nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    eal_common_kes: Mapped[float] = mapped_column(Float, nullable=False)
    eal_occasional_kes: Mapped[float] = mapped_column(Float, nullable=False)
    eal_moderate_kes: Mapped[float] = mapped_column(Float, nullable=False)
    eal_severe_kes: Mapped[float] = mapped_column(Float, nullable=False)
    eal_extreme_kes: Mapped[float] = mapped_column(Float, nullable=False)
    eal_total_kes: Mapped[float] = mapped_column(Float, nullable=False)
    exceedance_curve: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    top_locations: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    building_losses: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    insurance_curve: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    insurance_program: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PortfolioPreviewRecord(Base):
    __tablename__ = "portfolio_preview_records"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "loc_id", name="uq_portfolio_preview_loc"),
        UniqueConstraint("portfolio_id", "record_hash", name="uq_portfolio_preview_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    portfolio_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    loc_id: Mapped[str] = mapped_column(String(64), nullable=False)
    record_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    record_data: Mapped[dict] = mapped_column(JSON, nullable=False)
