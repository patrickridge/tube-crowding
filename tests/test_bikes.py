"""Bike tests: hand-made docks with easy distances, plus parsing of saved TfL responses."""

import json
from pathlib import Path

import pytest

from tube.bikes import (
    HIRE_KMH,
    OWN_BIKE_KMH,
    ROUTE_FACTOR,
    WALK_KMH,
    Dock,
    Place,
    distance_m,
    hire_trip,
    load_places,
    minutes,
    nearby,
    own_bike_minutes,
    parse_docks,
)
from tube.client import parse_journey_minutes

FIXTURES = Path(__file__).parent / "fixtures"

# Along the equator, 0.001 degrees of longitude is about 111 metres, which keeps distances easy.
DEG = 0.001
METRES_PER_DEG = distance_m(0, 0, 0, DEG)

A = Place("A", "id-a", 0, 0)
B = Place("B", "id-b", 0, 0.1)  # about 11.1 km east of A


def dock(name: str, lon: float, bikes: int = 5, spaces: int = 5, ebikes: int = 0) -> Dock:
    return Dock(name, 0, lon, bikes, ebikes, spaces)


def test_distance_is_about_111_metres_per_thousandth_of_a_degree():
    assert pytest.approx(111.2, abs=0.5) == METRES_PER_DEG


def test_minutes():
    assert minutes(1_000, 15) == pytest.approx(4)


def test_nearby_keeps_docks_within_radius_nearest_first():
    docks = [dock("far", 0.006), dock("near", 0.001), dock("mid", 0.003)]  # about 667, 111, 333 m
    assert [d.name for d, _ in nearby(docks, A)] == ["near", "mid"]


def test_hire_trip_uses_nearest_dock_with_a_bike_and_with_a_space():
    docks = [
        dock("A-empty", 0.001, bikes=0),
        dock("A-full", 0.002, bikes=3, ebikes=1),
        dock("B-full", 0.099, spaces=0),
        dock("B-free", 0.098, spaces=4),
    ]
    trip = hire_trip(docks, A, B)
    assert (trip.start.name, trip.end.name) == ("A-full", "B-free")
    assert (trip.bikes_nearby, trip.ebikes_nearby, trip.spaces_nearby) == (3, 1, 4)
    expected = (
        minutes(2 * METRES_PER_DEG, WALK_KMH)
        + minutes(ROUTE_FACTOR * 96 * METRES_PER_DEG, HIRE_KMH)
        + minutes(2 * METRES_PER_DEG, WALK_KMH)
    )
    assert trip.minutes == pytest.approx(expected, rel=1e-3)


def test_hire_trip_without_docks_or_bikes_has_no_time():
    assert hire_trip([], A, B).minutes is None
    no_bikes = hire_trip([dock("A-empty", 0.001, bikes=0), dock("B", 0.099)], A, B)
    assert no_bikes.minutes is None and no_bikes.docks_at_start == 1


def test_own_bike_minutes():
    expected = minutes(ROUTE_FACTOR * distance_m(0, 0, 0, 0.1), OWN_BIKE_KMH)
    assert own_bike_minutes(A, B) == pytest.approx(expected)


# ---------- parsing real TfL responses ----------


def test_parse_docks_from_saved_response_skips_broken_entries():
    docks = parse_docks(json.loads((FIXTURES / "bikepoints.json").read_text()))
    assert [d.name for d in docks] == ["Waterloo Station 1, Waterloo", "Birkenhead Street, King's Cross"]
    assert all(d.bikes >= d.ebikes >= 0 and d.spaces >= 0 for d in docks)


@pytest.mark.parametrize("raw", [None, "oops", {"bad": 1}])
def test_parse_docks_handles_junk(raw):
    assert parse_docks(raw) == []


def test_parse_journey_minutes_takes_the_shortest():
    raw = json.loads((FIXTURES / "journey_balham_oxford_circus.json").read_text())
    assert parse_journey_minutes(raw) == 19
    assert parse_journey_minutes({"journeys": []}) is None
    assert parse_journey_minutes(None) is None


def test_every_app_station_has_coordinates():
    from tube.seats import load_links, stations

    places = load_places()
    assert set(stations(load_links())) <= set(places)
