"""Load the static station list (see scripts/build_stations.py)."""
from __future__ import annotations

import csv
from pathlib import Path

from tube.models import Station

STATIONS_CSV = Path(__file__).resolve().parent.parent / "data" / "stations.csv"


def load_stations(path: Path = STATIONS_CSV) -> list[Station]:
    """Stations sorted by name, with labels made unique for the picker."""
    with path.open(newline="") as f:
        stations = [
            Station(row["naptan_id"], row["name"], tuple(filter(None, row["lines"].split(";"))))
            for row in csv.DictReader(f)
        ]
    return sorted(stations, key=lambda s: s.label)
