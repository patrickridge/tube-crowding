"""Build data/links.csv from TfL's NUMBAT workbook: people per train on every stretch of line.

Download the five NBT25*_Outputs.xlsx files (MON, TWT, FRI, SAT, SUN) from
https://crowding.data.tfl.gov.uk (NUMBAT/NUMBAT 2025/) into raw/, then run from the repo root:
python -m scripts.build_links
Needs openpyxl (in requirements-dev.txt).
"""

import csv
import re
from collections import defaultdict
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
DAY_TYPES = ["MON", "TWT", "FRI", "SAT", "SUN"]  # TWT = a typical Tuesday to Thursday
OUT = ROOT / "data" / "links.csv"
LINES = {  # NUMBAT name -> name shown in the app
    "Bakerloo": "Bakerloo",
    "Central": "Central",
    "District": "District",
    "Elizabeth Line": "Elizabeth line",
    "H&C and Circle": "Circle / Hammersmith & City",
    "Jubilee": "Jubilee",
    "Metropolitan": "Metropolitan",
    "Northern": "Northern",
    "Piccadilly": "Piccadilly",
    "Victoria": "Victoria",
    "Waterloo & City": "Waterloo & City",
}


def read_sheet(workbook, name: str) -> tuple[list[str], dict[str, tuple]]:
    rows = workbook[name].iter_rows(values_only=True)
    next(rows), next(rows)  # title and blank row
    header = list(next(rows))
    return header, {r[0]: r for r in rows if r[0]}


# Platform or line tags that split one station into several nodes, e.g. "Kennington (Bank)".
TAG = re.compile(r" \((Edgware|High Barnet|Bank|Charing Cross|Bak|DIS|H&C)\)$")


def clean(station: str) -> str:
    """'Balham LU' -> 'Balham', 'Paddington TfL' -> 'Paddington', 'Kennington (Bank)' -> 'Kennington'."""
    for suffix in (" LU", " EL", " NR", " LO", " TfL"):
        station = station.removesuffix(suffix)
    return TAG.sub("", station.strip())


def build_day(day: str) -> tuple[list[int], list[list]]:
    workbook = openpyxl.load_workbook(ROOT / "raw" / f"NBT25{day}_Outputs.xlsx", read_only=True)
    header, loads = read_sheet(workbook, "Link_Loads")
    _, trains = read_sheet(workbook, "Link_Frequencies")
    bands = [i for i, h in enumerate(header) if isinstance(h, str) and len(h) == 9 and h[4] == "-"]

    # Sum people and trains per stretch, so merged platforms give a fair per-train figure.
    people = defaultdict(lambda: [0.0] * len(bands))
    services = defaultdict(lambda: [0.0] * len(bands))
    for link, load in loads.items():
        line, freq = LINES.get(load[1]), trains.get(link)
        if line is None or freq is None or "fast" in load[6] + load[9]:
            continue  # Metropolitan fast services: use the all-stations trains instead
        key = (line, load[2], clean(load[6]), clean(load[9]))
        for j, i in enumerate(bands):
            people[key][j] += load[i] or 0
            services[key][j] += freq[i] or 0

    rows = []
    for key, total in people.items():
        per_train = [round(p / t) if t else "" for p, t in zip(total, services[key], strict=True)]
        rows.append([day, *key, *per_train])
    return [header[i][:4] for i in bands], rows


def main() -> None:
    rows = []
    for day in DAY_TYPES:
        times, day_rows = build_day(day)
        rows += day_rows
    with OUT.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["day", "line", "dir", "from", "to", *times])
        writer.writerows(rows)
    print(f"Wrote {len(rows)} links to {OUT}")


if __name__ == "__main__":
    main()
