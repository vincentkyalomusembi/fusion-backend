"""Load the Nairobi exposure CSV into the PostgreSQL locations table."""
import csv
from pathlib import Path
import sys

from dotenv import load_dotenv
from sqlalchemy.dialects.postgresql import insert

load_dotenv()
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import engine
from app.models.location import Location


CSV_PATH = Path(__file__).resolve().parents[1] / "data" / "exposure_nairobi_with_hazard.csv"
NUMERIC_COLUMNS = {
    "lat",
    "lon",
    "floor_area_m2",
    "cost_per_m2_kes",
    "tiv_kes",
    "hazard_score_common",
    "hazard_score_occasional",
    "hazard_score_moderate",
    "hazard_score_severe",
    "hazard_score_extreme",
    "hazard_severity",
}


def load_rows() -> list[dict]:
    with CSV_PATH.open(newline="", encoding="utf-8") as csv_file:
        rows = list(csv.DictReader(csv_file))
    for row in rows:
        for column in NUMERIC_COLUMNS:
            row[column] = float(row[column])
        row["synthetic"] = row["synthetic"].strip().lower() == "true"
    return rows


def main() -> None:
    if engine is None:
        raise RuntimeError("DATABASE_URL must be set")

    rows = load_rows()
    statement = insert(Location).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=[Location.loc_id],
        set_={column.name: getattr(statement.excluded, column.name)
              for column in Location.__table__.columns if column.name != "loc_id"},
    )
    with engine.begin() as connection:
        connection.execute(statement)
    print(f"Imported {len(rows)} locations from {CSV_PATH.name}")


if __name__ == "__main__":
    main()
