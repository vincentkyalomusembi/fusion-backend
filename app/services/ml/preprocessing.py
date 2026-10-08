import pandas as pd

# Only geographic features are valid hazard model inputs.
# Flood risk depends on where a building sits (elevation, proximity to rivers),
# NOT on its size or value.  Financial fields (floor_area_m2, cost_per_m2_kes,
# tiv_kes) and housing_class belong in the damage calculation, not here.
MODEL_FEATURES = ("lat", "lon")


def prepare_hazard_features(records: list[dict]) -> pd.DataFrame:
    """Build the feature frame in the exact order expected by the trained pipeline.

    Extra keys in each record (housing_class, tiv_kes, etc.) are silently
    ignored — only lat and lon are extracted.
    """
    missing = [
        index for index, row in enumerate(records)
        if any(row.get(field) is None for field in MODEL_FEATURES)
    ]
    if missing:
        raise ValueError(f"Records have missing model features at batch indexes {missing[:20]}")
    return pd.DataFrame.from_records(records, columns=MODEL_FEATURES)
