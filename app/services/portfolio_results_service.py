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
from app.config import settings
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

    deductible = max(0.0, settings.insurance_per_building_deductible_kes)
    per_building_limit = max(0.0, settings.insurance_per_building_limit_kes)
    quota_share = min(1.0, max(0.0, settings.insurance_quota_share))
    cat_attachment = max(0.0, settings.catastrophe_excess_attachment_kes)
    cat_limit = max(0.0, settings.catastrophe_excess_limit_kes)

    # Preserve the CAT model's building-level damage ratio and loss, then apply
    # the insurance program consistently at each return period.
    detailed_losses: list[dict[str, Any]] = []
    for _, row in losses_df.iterrows():
        gross_loss = max(0.0, float(row["Loss"]))
        insured_loss = min(max(gross_loss - deductible, 0.0), per_building_limit)
        quota_share_net = insured_loss * quota_share
        detailed_losses.append({
            "loc_id": str(row["Loc_id"]),
            "lat": round(float(row["Lat"]), 6),
            "lon": round(float(row["Lon"]), 6),
            "housing_class": str(row["Housing_class"]),
            "tiv_kes": round(float(row["TIV"]), 2),
            "tier": str(row["Tier"]),
            "return_period_years": int(row["ReturnPeriod"]),
            "hazard_score": round(float(row["Hazard_score"]), 6),
            "damage_ratio": round(float(row["DamageRatio"]), 6),
            "damage_percent": round(float(row["DamagePercent"]), 4),
            "gross_loss_kes": round(gross_loss, 2),
            "insured_loss_kes": round(insured_loss, 2),
            "quota_share_net_loss_kes": round(quota_share_net, 2),
        })

    insurance_curve: list[dict[str, Any]] = []
    for _, curve_row in curve_df.iterrows():
        return_period = int(curve_row["ReturnPeriod"])
        period_losses = [
            item for item in detailed_losses if item["return_period_years"] == return_period
        ]
        gross_loss = sum(item["gross_loss_kes"] for item in period_losses)
        insured_loss = sum(item["insured_loss_kes"] for item in period_losses)
        net_loss = sum(item["quota_share_net_loss_kes"] for item in period_losses)
        catastrophe_excess_loss = min(max(insured_loss - cat_attachment, 0.0), cat_limit)
        insurance_curve.append({
            "return_period_years": return_period,
            "annual_exceedance_probability": round(float(curve_row["ExceedanceProbability"]), 6),
            "ground_up_loss_kes": round(gross_loss, 2),
            "gross_loss_kes": round(insured_loss, 2),
            "quota_share_net_loss_kes": round(net_loss, 2),
            "catastrophe_excess_loss_kes": round(catastrophe_excess_loss, 2),
            "buildings_affected": int(curve_row["BuildingsAffected"]),
        })

    insurance_program = {
        "per_building_deductible_kes": round(deductible, 2),
        "per_building_limit_kes": round(per_building_limit, 2),
        "quota_share": round(quota_share, 6),
        "catastrophe_excess_attachment_kes": round(cat_attachment, 2),
        "catastrophe_excess_limit_kes": round(cat_limit, 2),
    }

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

    # Top buildings by worst-case ground-up loss across return periods.
    top_by_location: dict[str, dict[str, Any]] = {}
    for item in detailed_losses:
        current = top_by_location.setdefault(item["loc_id"], {
            "loc_id": item["loc_id"], "lat": item["lat"], "lon": item["lon"],
            "tiv_kes": item["tiv_kes"], "max_damage_ratio": 0.0,
            "max_ground_up_loss_kes": 0.0,
        })
        current["max_damage_ratio"] = max(current["max_damage_ratio"], item["damage_ratio"])
        current["max_ground_up_loss_kes"] = max(current["max_ground_up_loss_kes"], item["gross_loss_kes"])
    top_locations = sorted(top_by_location.values(), key=lambda row: row["max_ground_up_loss_kes"], reverse=True)[:TOP_N]

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
        "building_losses": detailed_losses,
        "insurance_curve": insurance_curve,
        "insurance_program": insurance_program,
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
