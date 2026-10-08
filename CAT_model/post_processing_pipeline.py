"""Nairobi flood loss pipeline.

    input table (Loc_id, Lat, Lon, Housing_class, floor_area_m2, cost_per_m2_kes, TIV)
        │
        ▼  score_hazard()      -- app.services.ml.predictor (lat/lon only), one row in -> 5 tier scores out
    scored table (+ Hazard_score_common .. Hazard_score_extreme)
        │
        ▼  build_losses()      -- melt to 5 rows/building, damage_ratio(), loss = ratio * TIV
    Losses table (one row per building per return period)  <- the single table everything else reads from
        │
        ├─▶ ep_curve()         -- portfolio total loss by return period + exceedance probability
        └─▶ (UI reads Losses directly for 4ii/4iii: filter by ReturnPeriod, no extra backend logic needed)

NOTE ON SCOPE: the hazard model itself (feature set, zero cutoff, tier ordering) is owned by
app.services.ml - score_hazard() goes through predict_hazard_scores() so the API and this pipeline
can never disagree on model path, input features or output checks. This pipeline only needs the
model's OUTPUT shape (5 tier scores, in common..extreme order) to stay stable.

Imports are package-absolute, so run/import from the repo root (as uvicorn does):
    from CAT_model.post_processing_pipeline import run
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.services.ml.predictor import HAZARD_SCORE_FIELDS, predict_hazard_scores
from CAT_model.vulnerability import CLASSES, damage_ratio

# ---------------------------------------------------------------------------
# Return-period mapping - FULL reversal from the original plan, confirmed in-thread:
# extreme (the strict/rare tier) is the frequent, low-return-period event; common (the lenient/
# frequent tier) is the rare, high-return-period event. Every downstream consumer (EP curve,
# the return-period filter, the map filter) reads this same table - it is defined exactly once.
# ---------------------------------------------------------------------------
RETURN_PERIOD_YEARS = {
    "extreme": 10,
    "severe": 20,
    "moderate": 50,
    "occasional": 100,
    "common": 250,
}
TIERS_BY_RETURN_PERIOD = sorted(RETURN_PERIOD_YEARS, key=RETURN_PERIOD_YEARS.get)  # [extreme..common]

# Input column -> model's expected column. The hazard model only takes location - housing class
# and TIV are used in the damage/loss step, not for hazard scoring.
_MODEL_INPUT_RENAME = {"Lat": "lat", "Lon": "lon"}
# Same order as predictor.HAZARD_SCORE_FIELDS, renamed to this pipeline's column convention.
_HAZARD_OUTPUT_COLUMNS = ["H" + f[1:] for f in HAZARD_SCORE_FIELDS]
REQUIRED_INPUT_COLUMNS = ["Loc_id", "Lat", "Lon", "Housing_class", "floor_area_m2", "cost_per_m2_kes", "TIV"]
_NUMERIC_INPUT_COLUMNS = ["Lat", "Lon", "floor_area_m2", "cost_per_m2_kes", "TIV"]


class PipelineInputError(ValueError):
    """Raised for anything wrong with the caller's input table - missing columns, unknown
    housing classes, nulls in a required field. Always carries a message naming the exact
    rows/columns at fault, per the 'reject with a clear message' requirement."""


def _ids(df: pd.DataFrame, mask: pd.Series) -> str:
    bad_ids = df.loc[mask, "Loc_id"].tolist()
    return f"{bad_ids[:20]}{' ...' if len(bad_ids) > 20 else ''}"


def _validate_input(df: pd.DataFrame):
    missing_cols = [c for c in REQUIRED_INPUT_COLUMNS if c not in df.columns]
    if missing_cols:
        raise PipelineInputError(f"Input table is missing required column(s): {missing_cols}")
    null_rows = df[REQUIRED_INPUT_COLUMNS].isna().any(axis=1)
    if null_rows.any():
        raise PipelineInputError(
            f"{null_rows.sum()} row(s) have a missing value in a required column - "
            f"Loc_id(s): {_ids(df, null_rows)}"
        )
    for col in _NUMERIC_INPUT_COLUMNS:
        non_numeric = pd.to_numeric(df[col], errors="coerce").isna()
        if non_numeric.any():
            raise PipelineInputError(f"Column {col!r} must be numeric - bad Loc_id(s): {_ids(df, non_numeric)}")
    non_positive_tiv = pd.to_numeric(df["TIV"]) <= 0
    if non_positive_tiv.any():
        raise PipelineInputError(f"TIV must be greater than 0 - bad Loc_id(s): {_ids(df, non_positive_tiv)}")
    unknown = sorted(set(df["Housing_class"]) - set(CLASSES))
    if unknown:
        raise PipelineInputError(
            f"Unknown Housing_class value(s) {unknown} - not in vulnerability.CLASSES {CLASSES}. "
            f"Every row must use one of the classes the damage curves were built for."
        )
    dupes = df["Loc_id"][df["Loc_id"].duplicated()].unique().tolist()
    if dupes:
        raise PipelineInputError(f"Duplicate Loc_id value(s), must be unique: {dupes[:20]}")


# ---------------------------------------------------------------------------
# Step 1 - hazard scoring
# ---------------------------------------------------------------------------
def score_hazard(df: pd.DataFrame) -> pd.DataFrame:
    """Returns a COPY of df with the five Hazard_score_* columns appended (Hazard_severity is
    also produced by the model but dropped immediately - UI decision, not used anywhere downstream).

    predict_hazard_scores() checks the output shape and that every row keeps
    common >= occasional >= moderate >= severe >= extreme, raising ValueError otherwise."""
    _validate_input(df)
    records = df[list(_MODEL_INPUT_RENAME)].astype(float).rename(columns=_MODEL_INPUT_RENAME).to_dict("records")
    raw = np.asarray(predict_hazard_scores(records))
    out = df.copy()
    for i, col in enumerate(_HAZARD_OUTPUT_COLUMNS):
        out[col] = raw[:, i]
    out = out.drop(columns=["Hazard_severity"])  # not used anywhere downstream - UI decision to not show it
    return out


# ---------------------------------------------------------------------------
# Steps 2-3 - melt to one row per (building, return period), damage ratio, loss
# ---------------------------------------------------------------------------
def build_losses(scored_df: pd.DataFrame) -> pd.DataFrame:
    """One row per building per tier (5x the input row count). This is the single table the
    EP curve, the return-period filter, and the map all read from - no further joins needed."""
    tier_cols = {t: f"Hazard_score_{t}" for t in RETURN_PERIOD_YEARS}
    missing = [c for t, c in tier_cols.items() if c not in scored_df.columns]
    if missing:
        raise PipelineInputError(f"scored_df is missing hazard-score column(s): {missing} - run score_hazard() first.")

    long = scored_df.melt(
        id_vars=["Loc_id", "Lat", "Lon", "Housing_class", "TIV"],
        value_vars=list(tier_cols.values()),
        var_name="_tier_col", value_name="Hazard_score",
    )
    tier_name_by_col = {v: k for k, v in tier_cols.items()}
    long["Tier"] = long["_tier_col"].map(tier_name_by_col)
    long["ReturnPeriod"] = long["Tier"].map(RETURN_PERIOD_YEARS)
    long = long.drop(columns=["_tier_col"])

    long["DamageRatio"] = np.nan  # 0-1, see docstring note on ratio vs percent below
    for cls, group in long.groupby("Housing_class"):
        long.loc[group.index, "DamageRatio"] = damage_ratio(cls, group["Hazard_score"].to_numpy())
    # DamagePercent exists ONLY for display - every loss calculation below uses DamageRatio (0-1).
    long["DamagePercent"] = long["DamageRatio"] * 100
    long["Loss"] = long["DamageRatio"] * long["TIV"]  # ratio, not percent - 100x bug otherwise

    long = long.sort_values(["Loc_id", "ReturnPeriod"]).reset_index(drop=True)
    return long[["Loc_id", "Lat", "Lon", "Housing_class", "TIV", "Tier", "ReturnPeriod",
                "Hazard_score", "DamageRatio", "DamagePercent", "Loss"]]


# ---------------------------------------------------------------------------
# 4(i) - EP curve. 4(ii)/4(iii) need no separate function: the UI filters `losses` by
# ReturnPeriod directly for both the portfolio total and the per-building map.
# ---------------------------------------------------------------------------
def ep_curve(losses: pd.DataFrame) -> pd.DataFrame:
    """Portfolio loss by return period, ascending (10yr -> 250yr), i.e. loss increases down the table.
    ExceedanceProbability is the annual chance of an event at least this severe (1 / ReturnPeriod),
    which is what turns the loss-per-return-period table into an EP curve."""
    curve = (
        losses.groupby("ReturnPeriod", as_index=False)
        .agg(TotalLoss=("Loss", "sum"), MeanLoss=("Loss", "mean"), BuildingsAffected=("Loss", lambda s: (s > 0).sum()))
        .sort_values("ReturnPeriod")
        .reset_index(drop=True)
    )
    curve.insert(1, "ExceedanceProbability", 1 / curve["ReturnPeriod"])
    if not curve["TotalLoss"].is_monotonic_increasing:
        import warnings
        warnings.warn(
            "EP curve is not monotonically increasing with return period - loss should always "
            "grow as the event gets rarer. Check the RETURN_PERIOD_YEARS mapping and the "
            "hazard model's output before trusting this curve.", stacklevel=2,
        )
    return curve


def run(input_df: pd.DataFrame) -> dict:
    """Runs the full pipeline. Returns {'scored': ..., 'losses': ..., 'ep_curve': ...}."""
    scored = score_hazard(input_df)
    losses = build_losses(scored)
    curve = ep_curve(losses)
    return {"scored": scored, "losses": losses, "ep_curve": curve}
