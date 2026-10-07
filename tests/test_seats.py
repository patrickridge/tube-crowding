"""Seat finder tests: small hand-made lines, plus a few checks on the real data file."""

import math

import pytest

from tube.models import SLOTS_PER_DAY
from tube.seats import (
    TRAINS,
    Link,
    Train,
    better_earlier,
    journey,
    level,
    load_links,
    route,
    stations,
)

NAN = math.nan
TRAIN = Train(seats=100, capacity=500)


def link(origin: str, dest: str, people: float = 50.0, line: str = "Test") -> Link:
    return Link(line, origin, dest, tuple([people] * SLOTS_PER_DAY))


# A -> B -> C -> D one way, and back the other way, with a branch B -> E.
LINE = [
    link("A", "B"),
    link("B", "C"),
    link("C", "D"),
    link("D", "C"),
    link("C", "B"),
    link("B", "A"),
    link("B", "E"),
]


def test_route_follows_direction():
    path = route(LINE, "Test", "A", "D")
    assert [(lk.origin, lk.dest) for lk in path] == [("A", "B"), ("B", "C"), ("C", "D")]
    back = route(LINE, "Test", "D", "A")
    assert [lk.origin for lk in back] == ["D", "C", "B"]


def test_route_takes_branch_and_handles_missing():
    assert [lk.dest for lk in route(LINE, "Test", "A", "E")] == ["B", "E"]
    assert route(LINE, "Test", "E", "A") is None  # no link out of E
    assert route(LINE, "Other", "A", "B") is None
    assert route(LINE, "Test", "A", "A") == []


def test_stations_are_sorted_and_unique():
    assert stations(LINE, "Test") == ["A", "B", "C", "D", "E"]


@pytest.mark.parametrize(
    "people, expected",
    [
        (0, "seat"),
        (79, "seat"),
        (80, "maybe"),
        (109, "maybe"),
        (111, "stand"),  # 1.1 * 100 is 110.00000000000001, so test just past it
        (449, "stand"),
        (450, "packed"),
    ],
)
def test_level_thresholds(people, expected):
    assert level(people, TRAIN) == expected


def test_level_unknown():
    assert level(NAN, TRAIN) is None


def test_journey_seat_frees_up_later():
    path = [link("A", "B", 300), link("B", "C", 150), link("C", "D", 60)]
    trip = journey(path, 32, TRAIN)
    assert (trip.people, trip.level, trip.seat_from) == (300, "stand", "C")


def test_journey_with_seat_from_the_start():
    trip = journey([link("A", "B", 40), link("B", "C", 400)], 32, TRAIN)
    assert trip.level == "seat" and trip.seat_from is None


def test_better_earlier_finds_latest_improvement():
    people = [300.0] * SLOTS_PER_DAY
    people[31] = 90  # 07:45 -> maybe
    people[30] = 50  # 07:30 -> seat
    path = [Link("Test", "A", "B", tuple(people))]
    assert better_earlier(path, 32, TRAIN) == (31, "maybe")


def test_better_earlier_none_when_already_seated_or_no_better():
    assert better_earlier([link("A", "B", 50)], 32, TRAIN) is None
    assert better_earlier([link("A", "B", 300)], 32, TRAIN) is None


# ---------- real data ----------


@pytest.fixture(scope="module")
def real_links():
    return load_links()


def test_every_line_has_a_train(real_links):
    assert {lk.line for lk in real_links} == set(TRAINS)


def test_balham_to_bank_goes_north_and_is_busier_than_southbound(real_links):
    north = route(real_links, "Northern", "Balham", "Bank and Monument")
    south = route(real_links, "Northern", "Balham", "Morden")
    assert north[0].dest == "Clapham South"
    assert south[0].dest == "Tooting Bec"
    morning = 34  # 08:30
    assert north[0].per_train[morning] > 2 * south[0].per_train[morning]
