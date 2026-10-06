"""Parsing tests against real TfL responses saved in tests/fixtures (no network)."""

import json
import math
from datetime import datetime
from pathlib import Path

import pytest
import requests

from tube.client import (
    ApiUnavailable,
    MalformedResponse,
    RateLimited,
    StationNotCovered,
    TflClient,
    parse_day,
    parse_live,
    parse_week,
)
from tube.models import DAYS, SLOTS_PER_DAY

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str):
    return json.loads((FIXTURES / name).read_text())


def test_week_has_seven_full_days():
    week = parse_week(load("week_kings_cross.json"), "940GZZLUKSX")
    assert set(week.days) == set(DAYS)
    for day in week.days.values():
        assert len(day.values) == SLOTS_PER_DAY
        assert not any(math.isnan(v) for v in day.values)
    assert week.days["MON"].am_peak == "08:00-10:00"


def test_band_lands_in_the_right_slot():
    raw = load("week_kings_cross.json")
    raw_mon = next(d for d in raw["daysOfWeek"] if d["dayOfWeek"] == "MON")
    expected = next(b["percentageOfBaseLine"] for b in raw_mon["timeBands"] if b["timeBand"] == "08:30-08:45")
    assert parse_day(raw_mon).values[34] == expected  # 08:30 is slot 34


def test_last_band_crossing_midnight_is_slot_95():
    day = parse_day(
        {"dayOfWeek": "MON", "timeBands": [{"timeBand": "23:45-00:00", "percentageOfBaseLine": 0.3}]}
    )
    assert day.values[95] == 0.3
    assert math.isnan(day.values[0])


def test_duplicate_bands_are_averaged():
    day = parse_day(
        {
            "dayOfWeek": "MON",
            "timeBands": [
                {"timeBand": "16:00-16:15", "percentageOfBaseLine": 0.2},
                {"timeBand": "16:00-16:15", "percentageOfBaseLine": 0.3},
            ],
        }
    )
    assert day.values[64] == pytest.approx(0.25)


def test_real_duplicate_band_station_still_gives_96_slots():
    week = parse_week(load("week_duplicate_bands_hammersmith.json"), "940GZZLUHSC")
    assert all(len(d.values) == SLOTS_PER_DAY for d in week.days.values())


def test_bad_bands_are_skipped_not_fatal():
    day = parse_day(
        {
            "dayOfWeek": "mon",
            "timeBands": [
                {"timeBand": "garbage", "percentageOfBaseLine": 0.5},
                {"timeBand": "09:00-09:15", "percentageOfBaseLine": None},
                {"timeBand": "09:15-09:30", "percentageOfBaseLine": 0.4},
            ],
        }
    )
    assert day.day == "MON"
    assert day.values[37] == 0.4
    assert math.isnan(day.values[36])


def test_unknown_station_raises_not_covered():
    with pytest.raises(StationNotCovered):
        parse_week(load("week_not_found_monument.json"), "940GZZLUMMT")


def test_all_zero_station_raises_not_covered():
    with pytest.raises(StationNotCovered):
        parse_week(load("week_all_zero_arsenal.json"), "940GZZLUASL")


@pytest.mark.parametrize("raw", [None, [], "oops", 42])
def test_non_dict_week_is_malformed(raw):
    with pytest.raises(MalformedResponse):
        parse_week(raw, "X")


def test_live_available():
    reading = parse_live(load("live_available.json"))
    assert reading is not None
    assert 0 < reading.value < 2
    assert reading.time_local == datetime(2026, 10, 6, 22, 1)


@pytest.mark.parametrize(
    "raw",
    [
        load("live_unavailable.json"),
        {"dataAvailable": True, "percentageOfBaseline": 0.2, "timeLocal": None},
        None,
    ],
)
def test_live_missing_or_broken_returns_none(raw):
    assert parse_live(raw) is None


# ---------- HTTP error mapping, with a fake session instead of the network ----------


class FakeResponse:
    def __init__(self, status: int, body=None):
        self.status_code, self._body = status, body
        self.ok = status < 400

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


class FakeSession:
    def __init__(self, result):
        self.result, self.calls = result, []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.mark.parametrize(
    "result, error",
    [
        (FakeResponse(429), RateLimited),
        (FakeResponse(503), ApiUnavailable),
        (FakeResponse(404), StationNotCovered),
        (FakeResponse(200, None), MalformedResponse),
        (requests.Timeout(), ApiUnavailable),
        (requests.ConnectionError(), ApiUnavailable),
    ],
)
def test_http_errors_become_friendly_tfl_errors(result, error):
    with pytest.raises(error):
        TflClient(session=FakeSession(result)).week_profile("940GZZLUKSX")


def test_app_key_is_sent_as_query_param():
    session = FakeSession(FakeResponse(200, load("live_available.json")))
    TflClient(app_key="k", session=session).live("940GZZLUKSX")
    assert session.calls == [("https://api.tfl.gov.uk/crowding/940GZZLUKSX/Live", {"app_key": "k"})]
