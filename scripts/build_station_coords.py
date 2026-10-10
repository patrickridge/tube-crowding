"""Build data/station_coords.csv: a TfL stop ID and map position for every station in links.csv.

Run from the repo root:  python -m scripts.build_station_coords
"""

import csv
from pathlib import Path

import requests

from tube.config import app_key_from_env
from tube.seats import load_links, stations

OUT = Path(__file__).resolve().parent.parent / "data" / "station_coords.csv"

# Names in TfL's passenger-count data that don't match its stop list. Where the app treats two
# stations as one (Edgware Road, Hammersmith), the busier one is used.
ALIASES = {
    "Bank and Monument": "940GZZLUBNK",
    "Battersea Power Station": "940GZZBPSUST",
    "Burnham": "910GBNHAM",
    "Edgware Road": "940GZZLUERC",
    "Hammersmith": "940GZZLUHSD",
    "Langley": "910GLANGLEY",
    "Shepherd's Bush": "940GZZLUSBC",
}


def clean(name: str) -> str:
    for suffix in (" Underground Station", " Rail Station", " (Elizabeth line)", "-Underground"):
        name = name.replace(suffix, "")
    return name.strip()


def main() -> None:
    params = {"app_key": key} if (key := app_key_from_env()) else {}
    resp = requests.get(
        "https://api.tfl.gov.uk/StopPoint/Mode/tube,elizabeth-line", params=params, timeout=60
    )
    resp.raise_for_status()
    by_name: dict[str, dict] = {}
    by_id: dict[str, dict] = {}
    for stop in resp.json()["stopPoints"]:
        if stop.get("stopType") not in ("NaptanMetroStation", "NaptanRailStation"):
            continue
        by_id[stop["naptanId"]] = stop
        # Prefer the Underground entry when a name appears twice (e.g. Paddington).
        name = clean(stop["commonName"])
        if name not in by_name or stop["naptanId"].startswith("940"):
            by_name[name] = stop

    rows, missing = [], []
    for name in stations(load_links()):
        stop = by_id.get(ALIASES[name]) if name in ALIASES else by_name.get(name)
        if stop is None:
            missing.append(name)
            continue
        rows.append([name, stop["naptanId"], round(stop["lat"], 6), round(stop["lon"], 6)])

    with OUT.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "naptan_id", "lat", "lon"])
        writer.writerows(rows)
    print(f"Wrote {len(rows)} stations to {OUT}; no match for {missing}")


if __name__ == "__main__":
    main()
