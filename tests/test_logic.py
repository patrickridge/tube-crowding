"""Logic tests with small hand-checkable numbers."""

import math
from datetime import datetime

import pytest

from tube.logic import (
    best_time,
    compare_live,
    smooth,
    time_to_slot,
    typical_at,
    week_grid,
    window_slots,
)
from tube.models import DAYS, SLOTS_PER_DAY, DayProfile, WeekProfile

NAN = math.nan


def flat_day(value: float = 0.1) -> list[float]:
    return [value] * SLOTS_PER_DAY


# ---------- smoothing ----------


def test_smooth_centred_average():
    assert smooth([0, 3, 0, 3, 0]) == pytest.approx([1.5, 1, 2, 1, 1.5])


def test_smooth_keeps_constant_series():
    assert smooth([0.2] * 6) == pytest.approx([0.2] * 6)


def test_smooth_skips_nan_and_keeps_all_nan_as_nan():
    out = smooth([1, NAN, 3, NAN, NAN, NAN])
    assert out[:3] == pytest.approx([1, 2, 3])
    assert math.isnan(out[4])


def test_smooth_empty():
    assert smooth([]) == []


def test_time_to_slot():
    assert time_to_slot(0, 0) == 0
    assert time_to_slot(9, 37) == 38
    assert time_to_slot(23, 59) == 95


# ---------- best time ----------


def test_best_time_picks_minimum_in_window():
    day = flat_day(0.5)
    day[30], day[31], day[32] = 0.4, 0.1, 0.3  # 07:30, 07:45, 08:00
    day[36] = 0.8  # 09:00
    result = best_time(day, 30, 38)  # 07:30 to 09:30
    assert (result.best_slot, result.best_value) == (31, 0.1)
    assert (result.worst_slot, result.worst_value) == (36, 0.8)
    assert result.quieter_by == pytest.approx(0.875)  # (0.8 - 0.1) / 0.8


def test_best_time_ignores_values_outside_window():
    day = flat_day(0.5)
    day[10] = 0.0
    assert best_time(day, 30, 38).best_value == 0.5


def test_best_time_ties_go_to_earliest():
    result = best_time(flat_day(0.2), 30, 38)
    assert result.best_slot == 30 and result.worst_slot == 30
    assert result.quieter_by == 0


def test_best_time_window_spanning_midnight_uses_next_day():
    today, tomorrow = flat_day(0.5), flat_day(0.5)
    today[1] = 0.0  # 00:15 *today* must be ignored...
    tomorrow[1] = 0.05  # ...in favour of 00:15 *tomorrow*
    assert window_slots(94, 2) == [94, 95, 96, 97, 98]
    result = best_time(today, 94, 2, tomorrow=tomorrow)  # 23:30 to 00:30
    assert (result.best_slot, result.best_value) == (1, 0.05)


def test_best_time_single_slot_window():
    result = best_time(flat_day(0.3), 40, 40)
    assert result.best_slot == result.worst_slot == 40


def test_best_time_no_data_returns_none():
    assert best_time([NAN] * SLOTS_PER_DAY, 30, 38) is None


def test_best_time_skips_missing_bands():
    day = flat_day(0.5)
    day[31] = NAN
    day[32] = 0.2
    assert best_time(day, 30, 33).best_slot == 32


def test_quieter_by_is_zero_when_window_is_empty_station():
    assert best_time(flat_day(0.0), 30, 38).quieter_by == 0


# ---------- live vs typical ----------


@pytest.mark.parametrize(
    "live, typical, verdict",
    [
        (0.10, 0.20, "much quieter than usual"),  # ratio 0.5
        (0.17, 0.20, "quieter than usual"),  # 0.85
        (0.20, 0.20, "about as busy as usual"),  # 1.0
        (0.23, 0.20, "busier than usual"),  # 1.15
        (0.30, 0.20, "much busier than usual"),  # 1.5
    ],
)
def test_compare_live_verdicts(live, typical, verdict):
    result = compare_live(live, typical)
    assert result.verdict == verdict
    assert result.ratio == pytest.approx(live / typical)


def test_compare_live_boundary_is_exclusive_below():
    # 0.45 / 0.5 is exactly 0.9 in floating point (0.18 / 0.2 is 0.8999...).
    assert compare_live(0.45, 0.5).verdict == "about as busy as usual"


def test_compare_live_near_empty_typical_has_no_ratio():
    assert compare_live(0.02, 0.01).ratio is None
    assert compare_live(0.02, 0.01).verdict == "about as busy as usual"
    assert compare_live(0.20, 0.01).verdict == "busier than usual"


def test_compare_live_unknown_typical():
    assert compare_live(0.1, NAN).ratio is None


# ---------- week helpers ----------


def make_week(days: dict[str, list[float]]) -> WeekProfile:
    return WeekProfile("X", {d: DayProfile(d, tuple(v)) for d, v in days.items()})


def test_typical_at_uses_weekday_and_band():
    tue = flat_day(0.1)
    tue[36] = 0.4  # 09:00, smoothed with neighbours 0.1 -> 0.2
    week = make_week({"TUE": tue})
    assert typical_at(week, datetime(2026, 10, 6, 9, 7)) == pytest.approx(0.2)  # a Tuesday
    assert math.isnan(typical_at(week, datetime(2026, 10, 5, 9, 7)))  # Monday missing


def test_week_grid_orders_days_and_fills_missing():
    grid = week_grid(make_week({"SUN": flat_day(0.1), "MON": flat_day(0.2)}))
    assert list(grid) == list(DAYS)
    assert grid["MON"][0] == pytest.approx(0.2)
    assert all(math.isnan(v) for v in grid["WED"])
