"""Upsert flood-affected area hotspots from the bundled CSV."""
import csv
from pathlib import Path
import sys

from dotenv import load_dotenv
from sqlalchemy.dialects.postgresql import insert

load_dotenv()
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import engine
from app.models.hotspot import Hotspot


CSV_PATH = Path(__file__).resolve().parents[1] / "data" / "nairobi_hotspots_geocoded.csv"


def load_rows() -> list[dict[str, str | float]]:
    with CSV_PATH.open(newline="", encoding="utf-8") as csv_file:
        rows = list(csv.DictReader(csv_file))
    required = {"name", "lat", "lon"}
    if rows and not required.issubset(rows[0]):
        raise ValueError("Hotspot CSV must contain name, lat, and lon columns")
    return [
        {"name": row["name"].strip(), "lat": float(row["lat"]), "lon": float(row["lon"])}
        for row in rows
    ]


def main() -> None:
    if engine is None:
        raise RuntimeError("DATABASE_URL must be set")
    rows = load_rows()
    if not rows:
        print("No hotspots to import")
        return
    statement = insert(Hotspot).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=[Hotspot.name],
        set_={"lat": statement.excluded.lat, "lon": statement.excluded.lon},
    )
    with engine.begin() as connection:
        connection.execute(statement)
    print(f"Imported {len(rows)} hotspots from {CSV_PATH.name}")


if __name__ == "__main__":
    main()
