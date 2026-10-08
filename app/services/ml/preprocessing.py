import pandas as pd


MODEL_FEATURES = (
    "lat", "lon", "housing_class", "floor_area_m2", "cost_per_m2_kes", "tiv_kes",
)


def prepare_hazard_features(records: list[dict]) -> pd.DataFrame:
    """Build the feature frame in the exact order expected by the trained pipeline."""
    missing = [
        index for index, row in enumerate(records)
        if any(row.get(field) is None for field in MODEL_FEATURES)
    ]
    if missing:
        raise ValueError(f"Records have missing model features at batch indexes {missing[:20]}")
    return pd.DataFrame.from_records(records, columns=MODEL_FEATURES)
