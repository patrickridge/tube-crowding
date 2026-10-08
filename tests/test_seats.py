"""Seat finder tests: small hand-made lines, plus a few checks on the real data file."""

import math

import pytest

from tube.models import SLOTS_PER_DAY
from tube.seats import (
    TRAINS,
    Link,
    Train,
    better_earlier,
    for_weekday,
    journey,
    leg_slot,
    level,
    load_links,
    overall,
    plan,
    stations,
)

NAN = math.nan
TRAIN = Train(seats=100, capacity=500)


def link(origin: str, dest: str, people: float = 50.0, line: str = "Test") -> Link:
    return Link("TWT", line, origin, dest, tuple([people] * SLOTS_PER_DAY))


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


def stops(legs):
    return [[(lk.origin, lk.dest) for lk in leg.links] for leg in legs]


def test_plan_follows_direction():
    assert stops(plan(LINE, "A", "D")) == [[("A", "B"), ("B", "C"), ("C", "D")]]
    assert [lk.origin for lk in plan(LINE, "D", "A")[0].links] == ["D", "C", "B"]


def test_plan_takes_branch_and_handles_missing():
    assert stops(plan(LINE, "A", "E")) == [[("A", "B"), ("B", "E")]]
    assert plan(LINE, "E", "A") is None  # no link out of E
    assert plan(LINE, "A", "Z") is None
    assert plan(LINE, "A", "A") == []


# Line X: P -> Q -> R -> S. Line Y: Q -> T.
NETWORK = [
    link("P", "Q", line="X"),
    link("Q", "R", line="X"),
    link("R", "S", line="X"),
    link("Q", "T", line="Y"),
]


def test_plan_changes_line_and_splits_into_legs():
    legs = plan(NETWORK, "P", "T")
    assert [(leg.line, leg.origin, leg.dest) for leg in legs] == [("X", "P", "Q"), ("Y", "Q", "T")]
    assert legs[1].minutes_in == 2 + 5  # one stop, then a change


def test_plan_prefers_staying_on_a_line_over_saving_a_stop():
    # Via a change: P -X- Q -Y- R costs 1 + 1 + 4 = 6. Staying on X: P -> Q -> R costs 2.
    network = [*NETWORK, link("Q", "R", line="Y")]
    assert [leg.line for leg in plan(network, "P", "R")] == ["X"]


def test_leg_slot_moves_to_later_band():
    legs = plan(NETWORK, "P", "T")
    assert leg_slot(32, legs[0]) == 32
    assert leg_slot(32, legs[1]) == 32  # 7 minutes in: still the same band
    assert leg_slot(95, legs[0]) == 95


@pytest.mark.parametrize(
    "levels, expected",
    [
        (["seat", "seat"], "seat"),
        (["stand"], "stand"),
        (["stand", "seat"], "part"),
        (["maybe", "packed"], "part"),
        (["stand", "packed"], "packed"),
        ([None, "stand"], "stand"),
        ([None], None),
    ],
)
def test_overall(levels, expected):
    assert overall(levels) == expected


def test_stations_are_sorted_and_unique():
    assert stations(LINE) == ["A", "B", "C", "D", "E"]


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
    path = [Link("TWT", "Test", "A", "B", tuple(people))]
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


def test_every_day_type_is_present(real_links):
    assert {lk.day for lk in real_links} == {"MON", "TWT", "FRI", "SAT", "SUN"}
    assert {lk.day for lk in for_weekday(real_links, 2)} == {"TWT"}  # Wednesday
    assert {lk.day for lk in for_weekday(real_links, 6)} == {"SUN"}


def test_balham_to_bank_goes_north_and_is_busier_than_southbound(real_links):
    weekday = for_weekday(real_links, 1)
    north = plan(weekday, "Balham", "Bank and Monument")[0].links
    south = plan(weekday, "Balham", "Morden")[0].links
    assert north[0].dest == "Clapham South"
    assert south[0].dest == "Tooting Bec"
    morning = 34  # 08:30
    assert north[0].per_train[morning] > 2 * south[0].per_train[morning]


def test_balham_to_oxford_circus_changes_at_stockwell(real_links):
    legs = plan(for_weekday(real_links, 1), "Balham", "Oxford Circus")
    assert [(leg.line, leg.dest) for leg in legs] == [
        ("Northern", "Stockwell"),
        ("Victoria", "Oxford Circus"),
    ]
