"""Santander Cycles: nearby docks and a rough door-to-door bike time. No Streamlit, no network.

Dock data comes from TfL's BikePoint API (live counts of bikes and free spaces at each dock).
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

COORDS_CSV = Path(__file__).resolve().parent.parent / "data" / "station_coords.csv"

WALK_RADIUS_M = 500  # about a 6-minute walk
WALK_KMH = 4.8
HIRE_KMH = 15  # a typical pace on a heavy hire bike in city traffic
OWN_BIKE_KMH = 18
ROUTE_FACTOR = 1.3  # roads are longer than a straight line


@dataclass(frozen=True)
class Place:
    name: str
    naptan_id: str
    lat: float
    lon: float


@dataclass(frozen=True)
class Dock:
    name: str
    lat: float
    lon: float
    bikes: int  # all bikes, including e-bikes
    ebikes: int
    spaces: int


def load_places(path: Path = COORDS_CSV) -> dict[str, Place]:
    with path.open(newline="") as f:
        return {
            row["name"]: Place(row["name"], row["naptan_id"], float(row["lat"]), float(row["lon"]))
            for row in csv.DictReader(f)
        }


def parse_docks(raw: Any) -> list[Dock]:
    """Turn TfL's BikePoint response into docks, skipping any entry that's missing a count."""
    docks = []
    for point in raw if isinstance(raw, list) else []:
        try:
            props = {p["key"]: p["value"] for p in point["additionalProperties"]}
            docks.append(
                Dock(
                    name=point["commonName"],
                    lat=float(point["lat"]),
                    lon=float(point["lon"]),
                    bikes=int(props["NbBikes"]),
                    ebikes=int(props.get("NbEBikes", 0)),
                    spaces=int(props["NbEmptyDocks"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return docks


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Straight-line distance on the Earth's surface (haversine formula)."""
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearby(docks: list[Dock], place: Place, radius_m: float = WALK_RADIUS_M) -> list[tuple[Dock, float]]:
    """Docks within walking distance of a station, nearest first."""
    found = [(dock, distance_m(place.lat, place.lon, dock.lat, dock.lon)) for dock in docks]
    return sorted([(d, m) for d, m in found if m <= radius_m], key=lambda pair: pair[1])


def minutes(metres: float, kmh: float) -> float:
    return metres / 1000 / kmh * 60


def own_bike_minutes(origin: Place, dest: Place) -> float:
    return minutes(ROUTE_FACTOR * distance_m(origin.lat, origin.lon, dest.lat, dest.lon), OWN_BIKE_KMH)


@dataclass(frozen=True)
class BikeTrip:
    start: Dock | None  # nearest dock with a bike, if any
    end: Dock | None  # nearest dock with a free space, if any
    bikes_nearby: int
    ebikes_nearby: int
    spaces_nearby: int
    docks_at_start: int  # docks within walking distance, whatever they hold
    docks_at_end: int
    minutes: float | None  # walk + ride + walk; None if there's no bike or no space


def hire_trip(docks: list[Dock], origin: Place, dest: Place) -> BikeTrip:
    """Door-to-door time by Santander Cycle, using the nearest dock with a bike and the nearest
    dock with a free space."""
    near_start, near_end = nearby(docks, origin), nearby(docks, dest)
    start = next(((d, m) for d, m in near_start if d.bikes > 0), None)
    end = next(((d, m) for d, m in near_end if d.spaces > 0), None)
    total = None
    if start and end:
        ride = ROUTE_FACTOR * distance_m(start[0].lat, start[0].lon, end[0].lat, end[0].lon)
        total = minutes(start[1], WALK_KMH) + minutes(ride, HIRE_KMH) + minutes(end[1], WALK_KMH)
    return BikeTrip(
        start=start[0] if start else None,
        end=end[0] if end else None,
        bikes_nearby=sum(d.bikes for d, _ in near_start),
        ebikes_nearby=sum(d.ebikes for d, _ in near_start),
        spaces_nearby=sum(d.spaces for d, _ in near_end),
        docks_at_start=len(near_start),
        docks_at_end=len(near_end),
        minutes=total,
    )
