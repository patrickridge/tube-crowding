"""Append the current live crowding reading for a set of stations to a monthly CSV.

Run by .github/workflows/log-live.yml every 15 minutes; the CSVs live on the `data` branch.
Locally:  python -m scripts.log_live OUTPUT_DIR
"""

import csv
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from tube.client import TflClient, TflError
from tube.config import app_key_from_env

STATIONS = [
    # The 16 busy stations the app uses for the network factor
    "940GZZLUKSX", "940GZZLUOXC", "940GZZLUWLO", "940GZZLULVT", "940GZZLUBNK", "940GZZLUVIC",
    "940GZZLULSQ", "940GZZLUCYF", "940GZZLUSTD", "940GZZLUBXN", "940GZZLUCPC", "940GZZLUEBY",
    "940GZZLUMDN", "940GZZLUWWL", "940GZZLUHOH", "940GZZLUWIM",
    # Event venues: Wembley Park, North Greenwich (O2), Earl's Court
    "940GZZLUWYP", "940GZZLUNGW", "940GZZLUECT",
    # Mid-size and quiet stations
    "940GZZLUAGL", "940GZZLUBLM", "940GZZLUCWR", "940GZZLUGPK", "940GZZLUEUS", "940GZZLULNB",
    "940GZZLUPAC", "940GZZLUHBN", "940GZZLUWPL", "940GZZLUTCR", "940GZZLURVY",
]  # fmt: skip
FIELDS = ["fetched_utc", "naptan_id", "time_local", "live"]


def main(out_dir: Path) -> None:
    client = TflClient(app_key_from_env())
    fetched = datetime.now(UTC)
    rows = []
    for naptan in STATIONS:
        try:
            reading = client.live(naptan)
        except TflError as err:
            print(f"{naptan}: {err}")
            continue
        if reading is not None:
            rows.append(
                [fetched.isoformat(timespec="seconds"), naptan, reading.time_local.isoformat(), reading.value]
            )
        time.sleep(0.2)  # be gentle; 30 calls take about 10 seconds

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{fetched:%Y-%m}.csv"
    new_file = not path.exists()
    with path.open("a", newline="") as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(FIELDS)
        writer.writerows(rows)
    print(f"Wrote {len(rows)} readings to {path}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("live-data"))
