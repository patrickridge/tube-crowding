"""Regenerate data/stations.csv from the TfL StopPoint API.

The station list changes rarely, so we ship it as a static file: autocomplete is then
instant and costs no API calls. Run:  python scripts/build_stations.py
"""
import csv
from pathlib import Path

import requests

OUT = Path(__file__).resolve().parent.parent / "data" / "stations.csv"


def clean_name(name: str) -> str:
    for suffix in (" Underground Station", "-Underground"):
        name = name.removesuffix(suffix)
    return name.strip()


def main() -> None:
    resp = requests.get("https://api.tfl.gov.uk/StopPoint/Mode/tube", timeout=60)
    resp.raise_for_status()
    rows = []
    for stop in resp.json()["stopPoints"]:
        # Crowding data is keyed on the tube station NaPTAN (940GZZLU...), not hubs or platforms.
        if stop.get("stopType") != "NaptanMetroStation" or not stop["naptanId"].startswith("940GZZLU"):
            continue
        tube_ids = {
            line_id
            for group in stop.get("lineModeGroups", [])
            if group.get("modeName") == "tube"
            for line_id in group.get("lineIdentifier", [])
        }
        lines = sorted(line["name"] for line in stop.get("lines", []) if line["id"] in tube_ids)
        rows.append((stop["naptanId"], clean_name(stop["commonName"]), ";".join(lines)))
    rows.sort(key=lambda r: r[1])
    with OUT.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["naptan_id", "name", "lines"])
        writer.writerows(rows)
    print(f"Wrote {len(rows)} stations to {OUT}")


if __name__ == "__main__":
    main()
