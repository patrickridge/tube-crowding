"""Will I get a seat? Pure functions over data/links.csv (built by scripts/build_links.py).

Each link is one stretch of line in one direction, with the typical number of people on each
train leaving that stretch's first station, per 15-minute band (TfL NUMBAT 2025), for one of
five day types: MON, TWT (Tuesday to Thursday), FRI, SAT and SUN.
"""

from __future__ import annotations

import csv
import math
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from tube.models import SLOTS_PER_DAY, slot_label

LINKS_CSV = Path(__file__).resolve().parent.parent / "data" / "links.csv"


@dataclass(frozen=True)
class Train:
    seats: int
    capacity: int  # seated + standing


# Seats and total capacity per train, from TfL's rolling stock information sheets.
TRAINS = {
    "Bakerloo": Train(268, 851),
    "Central": Train(272, 1047),
    "Circle / Hammersmith & City": Train(256, 1045),
    "District": Train(256, 1045),
    "Elizabeth line": Train(454, 1500),
    "Jubilee": Train(234, 964),
    "Metropolitan": Train(306, 1176),
    "Northern": Train(248, 752),
    "Piccadilly": Train(228, 798),
    "Victoria": Train(288, 986),
    "Waterloo & City": Train(136, 506),
}


DAY_TYPES = ("MON", "TWT", "TWT", "TWT", "FRI", "SAT", "SUN")  # by datetime.weekday()


@dataclass(frozen=True)
class Link:
    day: str
    line: str
    origin: str
    dest: str
    per_train: tuple[float, ...]  # indexed by slot from 00:00; NaN when no trains run


def load_links(path: Path = LINKS_CSV) -> list[Link]:
    links = []
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            per_train = [math.nan] * SLOTS_PER_DAY
            for slot in range(SLOTS_PER_DAY):
                value = row[slot_label(slot).replace(":", "")]
                per_train[slot] = float(value) if value else math.nan
            links.append(Link(row["day"], row["line"], row["from"], row["to"], tuple(per_train)))
    return links


def for_weekday(links: list[Link], weekday: int) -> list[Link]:
    """Links for the day type that covers a weekday (0 = Monday)."""
    return [link for link in links if link.day == DAY_TYPES[weekday]]


def stations(links: list[Link], line: str) -> list[str]:
    return sorted({name for link in links if link.line == line for name in (link.origin, link.dest)})


def route(links: list[Link], line: str, origin: str, dest: str) -> list[Link] | None:
    """Fewest-stops path from origin to dest on one line (breadth-first search)."""
    outgoing: dict[str, list[Link]] = {}
    for link in links:
        if link.line == line:
            outgoing.setdefault(link.origin, []).append(link)
    came_by: dict[str, Link | None] = {origin: None}
    queue = deque([origin])
    while queue:
        here = queue.popleft()
        if here == dest:
            path = []
            while came_by[here] is not None:
                path.append(came_by[here])
                here = came_by[here].origin
            return path[::-1]
        for link in outgoing.get(here, []):
            if link.dest not in came_by:
                came_by[link.dest] = link
                queue.append(link.dest)
    return None


# ---------- how full is the train? ----------

# My thresholds, not TfL's. The figures are averages over the whole train, and the ends of a
# train are usually emptier than the middle, so "seat" needs some slack below the seat count.
SEAT = 0.8  # of seats
MAYBE = 1.1  # of seats
PACKED = 0.9  # of total capacity

LEVELS = ("seat", "maybe", "stand", "packed")


def level(people: float, train: Train) -> str | None:
    if math.isnan(people):
        return None
    if people >= PACKED * train.capacity:
        return "packed"
    if people < SEAT * train.seats:
        return "seat"
    if people < MAYBE * train.seats:
        return "maybe"
    return "stand"


@dataclass(frozen=True)
class Journey:
    people: float  # on the train as it leaves your station
    level: str | None
    seat_from: str | None  # first station where a seat becomes likely, if you start standing


def journey(path: list[Link], slot: int, train: Train) -> Journey:
    """How full the train is when you board, and where seats free up.

    Uses the same 15-minute band for the whole trip, which is close enough for most journeys.
    """
    people = path[0].per_train[slot]
    board = level(people, train)
    seat_from = None
    if board not in ("seat", None):
        seat_from = next(
            (link.origin for link in path[1:] if level(link.per_train[slot], train) == "seat"), None
        )
    return Journey(people, board, seat_from)


def better_earlier(path: list[Link], slot: int, train: Train, steps: int = 2) -> tuple[int, str] | None:
    """The latest earlier band (up to `steps` x 15 min) where boarding is a better level."""
    now = level(path[0].per_train[slot], train)
    if now in ("seat", None):
        return None
    for back in range(1, steps + 1):
        earlier = (slot - back) % SLOTS_PER_DAY
        option = level(path[0].per_train[earlier], train)
        if option is not None and LEVELS.index(option) < LEVELS.index(now):
            return earlier, option
    return None
