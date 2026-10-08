"""Compute loss analytics from a confirmed portfolio's hazard predictions.

Return-period tiers and their annualised rate assumptions
(events per year, i.e. 1 / return_period_years):
    common      1-in-5    → 0.200
    occasional  1-in-20   → 0.050
    moderate    1-in-50   → 0.020
    severe      1-in-100  → 0.010
    extreme     1-in-250  → 0.004

Expected Annual Loss (EAL) per tier is approximated as:
    EAL_tier = hazard_score_tier × tiv_kes × annual_rate

The exceedance curve is built from the five tier loss totals ordered by
return period (ascending probability of exceedance).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.database import engine
from app.models.portfolio import Portfolio, PortfolioPreviewRecord, PortfolioResults
from app.services.portfolio_etl import EXPOSURE_FIELDS, HAZARD_FIELDS, get_portfolio_table

# (tier_field, return_period_years, annual_rate)
TIERS: list[tuple[str, int, float]] = [
    ("hazard_score_common",     5,   0.200),
    ("hazard_score_occasional", 20,  0.050),
    ("hazard_score_moderate",   50,  0.020),
    ("hazard_score_severe",     100, 0.010),
    ("hazard_score_extreme",    250, 0.004),
]
TOP_N = 10


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


def compute_and_store_results(portfolio: Portfolio, db: Session) -> PortfolioResults:
    rows = (
        _rows_from_confirmed(portfolio.table_name)
        if portfolio.status == "confirmed"
        else _rows_from_preview(portfolio.id, db)
    )
    if not rows:
        raise ValueError("No rows available to compute results")

    total_tiv = 0.0
    tier_losses: dict[str, float] = {field: 0.0 for field, _, _ in TIERS}

    for row in rows:
        tiv = float(row.get("tiv_kes") or 0)
        total_tiv += tiv
        for field, _, rate in TIERS:
            score = float(row.get(field) or 0)
            tier_losses[field] += score * tiv * rate

    eal_total = sum(tier_losses.values())

    exceedance_curve = []
    for field, rp, rate in TIERS:
        gross_loss = sum(float(row.get(field) or 0) * float(row.get("tiv_kes") or 0) for row in rows)
        exceedance_curve.append({
            "return_period_years": rp,
            "annual_exceedance_probability": round(rate, 4),
            "loss_kes": round(gross_loss, 2),
        })

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
        "eal_common_kes": round(tier_losses["hazard_score_common"], 2),
        "eal_occasional_kes": round(tier_losses["hazard_score_occasional"], 2),
        "eal_moderate_kes": round(tier_losses["hazard_score_moderate"], 2),
        "eal_severe_kes": round(tier_losses["hazard_score_severe"], 2),
        "eal_extreme_kes": round(tier_losses["hazard_score_extreme"], 2),
        "eal_total_kes": round(eal_total, 2),
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
