"""Will I get a seat? Pure functions over data/links.csv (built by scripts/build_links.py).

Each link is one stretch of line in one direction, with the typical number of people on each
train leaving that stretch's first station, per 15-minute band (TfL NUMBAT 2025), for one of
five day types: MON, TWT (Tuesday to Thursday), FRI, SAT and SUN.
"""

from __future__ import annotations

import csv
import heapq
import math
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


def stations(links: list[Link]) -> list[str]:
    return sorted({name for link in links for name in (link.origin, link.dest)})


# ---------- planning a journey ----------

CHANGE_COST = 4  # a change "costs" as much as 4 stops, so routes don't swap lines to save one
MINUTES_PER_STOP = 2  # rough, only used to pick the 15-minute band for later legs
MINUTES_PER_CHANGE = 5


@dataclass(frozen=True)
class Leg:
    line: str
    links: tuple[Link, ...]
    minutes_in: int  # rough minutes from setting off to boarding this leg

    @property
    def origin(self) -> str:
        return self.links[0].origin

    @property
    def dest(self) -> str:
        return self.links[-1].dest


def plan(links: list[Link], origin: str, dest: str) -> list[Leg] | None:
    """Cheapest route from origin to dest, split into one leg per line.

    Dijkstra's algorithm over (station, line) pairs: each stop costs 1 and each change of
    line costs CHANGE_COST. Stations with the same name on different lines are treated as
    the same place, so changing there is allowed.
    """
    outgoing: dict[str, list[Link]] = {}
    for link in links:
        outgoing.setdefault(link.origin, []).append(link)

    start = (origin, "")
    best = {start: 0}
    came_by: dict[tuple[str, str], tuple[tuple[str, str], Link]] = {}
    queue = [(0, origin, "")]
    while queue:
        cost, here, line = heapq.heappop(queue)
        if here == dest:
            path = []
            state = (here, line)
            while state != start:
                state, link = came_by[state]
                path.append(link)
            return _legs(path[::-1])
        if cost > best[(here, line)]:
            continue  # already reached this state more cheaply
        for link in outgoing.get(here, []):
            step = 1 + (CHANGE_COST if line and link.line != line else 0)
            state = (link.dest, link.line)
            if cost + step < best.get(state, math.inf):
                best[state] = cost + step
                came_by[state] = ((here, line), link)
                heapq.heappush(queue, (cost + step, link.dest, link.line))
    return None


def _legs(path: list[Link]) -> list[Leg]:
    legs: list[Leg] = []
    minutes = 0
    for link in path:
        if legs and legs[-1].line == link.line:
            legs[-1] = Leg(link.line, (*legs[-1].links, link), legs[-1].minutes_in)
        else:
            if legs:
                minutes += MINUTES_PER_STOP * len(legs[-1].links) + MINUTES_PER_CHANGE
            legs.append(Leg(link.line, (link,), minutes))
    return legs


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


def leg_slot(slot: int, leg: Leg) -> int:
    """The 15-minute band you're likely to board this leg in, if you set off in `slot`."""
    return (slot + leg.minutes_in // 15) % SLOTS_PER_DAY


def overall(levels: list[str | None]) -> str | None:
    """One answer for the whole trip: the shared level, 'part' if you'd sit for only some
    of it, otherwise the worst leg."""
    known = [lv for lv in levels if lv is not None]
    if not known:
        return None
    if len(set(known)) == 1:
        return known[0]
    if "seat" in known or "maybe" in known:
        return "part"
    return max(known, key=LEVELS.index)
