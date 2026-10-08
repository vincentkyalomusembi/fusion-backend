"""Compute loss analytics from a confirmed portfolio's hazard predictions.

Uses the real CAT pipeline (CAT_model.post_processing_pipeline) which applies
JRC/Huizinga damage curves per construction class instead of a simple
hazard_score × tiv approximation.

Expected Annual Loss (EAL) per tier:
    EAL_tier = sum(Loss_tier across all buildings) × annual_rate
    where Loss = damage_ratio(housing_class, hazard_score) × tiv_kes
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.database import engine
from app.models.portfolio import Portfolio, PortfolioPreviewRecord, PortfolioResults
from app.services.portfolio_etl import EXPOSURE_FIELDS, HAZARD_FIELDS, get_portfolio_table
from CAT_model.post_processing_pipeline import RETURN_PERIOD_YEARS, build_losses, ep_curve

# annual rate = 1 / return_period_years
_ANNUAL_RATE = {tier: 1 / rp for tier, rp in RETURN_PERIOD_YEARS.items()}
TOP_N = 10

# Map from portfolio row field names → pipeline column names
_FIELD_MAP = {
    "loc_id": "Loc_id",
    "lat": "Lat",
    "lon": "Lon",
    "housing_class": "Housing_class",
    "floor_area_m2": "floor_area_m2",
    "cost_per_m2_kes": "cost_per_m2_kes",
    "tiv_kes": "TIV",
    "hazard_score_common": "Hazard_score_common",
    "hazard_score_occasional": "Hazard_score_occasional",
    "hazard_score_moderate": "Hazard_score_moderate",
    "hazard_score_severe": "Hazard_score_severe",
    "hazard_score_extreme": "Hazard_score_extreme",
}


def _rows_from_confirmed(table_name: str) -> list[dict[str, Any]]:
    if engine is None:
        raise RuntimeError("DATABASE_URL must be set")
    table = get_portfolio_table(table_name)
    fields = (*EXPOSURE_FIELDS, *HAZARD_FIELDS)
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(select(*(table.c[f] for f in fields))).mappings()]


def _rows_from_preview(portfolio_id: str, db: Session) -> list[dict[str, Any]]:
    staged = db.scalars(
        select(PortfolioPreviewRecord)
        .where(PortfolioPreviewRecord.portfolio_id == portfolio_id)
    ).all()
    return [row.record_data for row in staged]


def _to_pipeline_df(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Rename portfolio row keys to the column names the CAT pipeline expects."""
    df = pd.DataFrame(rows).rename(columns=_FIELD_MAP)
    # Ensure numeric types
    for col in ("Lat", "Lon", "floor_area_m2", "cost_per_m2_kes", "TIV"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def compute_and_store_results(portfolio: Portfolio, db: Session) -> PortfolioResults:
    rows = (
        _rows_from_confirmed(portfolio.table_name)
        if portfolio.status == "confirmed"
        else _rows_from_preview(portfolio.id, db)
    )
    if not rows:
        raise ValueError("No rows available to compute results")

    # ── Run the real CAT pipeline ────────────────────────────────────────────
    scored_df = _to_pipeline_df(rows)
    losses_df = build_losses(scored_df)          # one row per building per return period
    curve_df = ep_curve(losses_df)               # aggregated EP curve

    total_tiv = float(scored_df["TIV"].sum())

    # EAL per tier = total loss at that return period × annual rate
    eal_by_tier: dict[str, float] = {}
    for tier, rp in RETURN_PERIOD_YEARS.items():
        tier_total = float(losses_df.loc[losses_df["Tier"] == tier, "Loss"].sum())
        eal_by_tier[tier] = round(tier_total * _ANNUAL_RATE[tier], 2)
    eal_total = round(sum(eal_by_tier.values()), 2)

    # Exceedance curve from the pipeline output
    exceedance_curve = [
        {
            "return_period_years": int(row["ReturnPeriod"]),
            "annual_exceedance_probability": round(float(row["ExceedanceProbability"]), 6),
            "loss_kes": round(float(row["TotalLoss"]), 2),
        }
        for _, row in curve_df.iterrows()
    ]

    # Top 10 locations by (hazard_severity × tiv)
    top_locations = sorted(
        [
            {
                "loc_id": row.get("loc_id"),
                "lat": row.get("lat"),
                "lon": row.get("lon"),
                "tiv_kes": row.get("tiv_kes"),
                "hazard_severity": row.get("hazard_severity"),
            }
            for row in rows
            if row.get("hazard_severity") is not None
        ],
        key=lambda r: (r["hazard_severity"] or 0) * (r["tiv_kes"] or 0),
        reverse=True,
    )[:TOP_N]

    result_data = {
        "portfolio_id": portfolio.id,
        "total_tiv_kes": round(total_tiv, 2),
        "total_rows": len(rows),
        "eal_common_kes": eal_by_tier.get("common", 0.0),
        "eal_occasional_kes": eal_by_tier.get("occasional", 0.0),
        "eal_moderate_kes": eal_by_tier.get("moderate", 0.0),
        "eal_severe_kes": eal_by_tier.get("severe", 0.0),
        "eal_extreme_kes": eal_by_tier.get("extreme", 0.0),
        "eal_total_kes": eal_total,
        "exceedance_curve": exceedance_curve,
        "top_locations": top_locations,
        "computed_at": datetime.now(timezone.utc),
    }

    stmt = pg_insert(PortfolioResults).values(**result_data)
    stmt = stmt.on_conflict_do_update(
        index_elements=["portfolio_id"],
        set_={k: v for k, v in result_data.items() if k != "portfolio_id"},
    )
    db.execute(stmt)
    db.commit()
    return db.get(PortfolioResults, portfolio.id)
