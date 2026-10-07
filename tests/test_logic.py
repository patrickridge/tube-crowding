"""Logic tests with small hand-checkable numbers."""

import math
from datetime import datetime

import pytest

from tube.logic import (
    busyness_level,
    compare_live,
    find_peak,
    has_dropout,
    network_factor,
    repair_dropouts,
    smooth,
    station_peak,
    time_to_slot,
    typical_at,
    week_grid,
    weekday_average,
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


# ---------- live vs typical ----------


@pytest.mark.parametrize(
    "live, typical, verdict",
    [
        (0.10, 0.20, "much quieter than usual"),  # ratio 0.5
        (0.17, 0.20, "quieter than usual"),  # 0.85
        (0.20, 0.20, "about as busy as usual"),  # 1.0
        (0.23, 0.20, "busier than usual"),  # 1.15
        (0.30, 0.20, "much busier than usual"),  # 1.5
        (0.06, 0.20, "an unusual reading"),  # 0.3, more likely a glitch
        (0.60, 0.20, "an unusual reading"),  # 3.0
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


# ---------- network adjustment ----------


def test_network_factor_is_median_and_ignores_missing():
    assert network_factor([1.0, 1.2, 1.3, None, 1.4, 5.0]) == pytest.approx(1.3)


def test_network_factor_needs_enough_stations():
    assert network_factor([1.2, 1.3, None, None]) is None
    assert network_factor([]) is None


def test_compare_live_divides_out_network_factor():
    # Raw ratio 1.5 looks "much busier", but the whole network is running 1.5x typical.
    result = compare_live(0.3, 0.2, network=1.5)
    assert result.ratio == pytest.approx(1.5)
    assert result.adjusted == pytest.approx(1.0)
    assert result.verdict == "about as busy as usual"


def test_compare_live_without_network_uses_raw_ratio():
    assert compare_live(0.3, 0.2).adjusted == pytest.approx(1.5)


# ---------- busyness levels ----------


@pytest.mark.parametrize(
    "share, level",
    [
        (0.0, "Quiet"),
        (0.249, "Quiet"),
        (0.25, "Moderate"),
        (0.5, "Busy"),
        (0.75, "Very busy"),
        (1.2, "Very busy"),
    ],
)
def test_busyness_level_bands(share, level):
    assert busyness_level(share) == level


def test_busyness_level_unknown():
    assert busyness_level(NAN) == "Unknown"


def test_station_peak_is_max_of_smoothed_week():
    mon = flat_day(0.1)
    mon[40] = 0.4  # smoothed -> (0.1 + 0.4 + 0.1) / 3 = 0.2
    assert station_peak(make_week({"MON": mon})) == pytest.approx(0.2)


def test_station_peak_empty_week():
    assert station_peak(make_week({})) == 0.0


# ---------- commute summary ----------


def test_weekday_average_ignores_weekend():
    week = make_week({"MON": flat_day(0.2), "TUE": flat_day(0.4), "SAT": flat_day(0.9)})
    assert weekday_average(week)[0] == pytest.approx(0.3)


def test_find_peak_and_shoulders():
    profile = [0.0] * SLOTS_PER_DAY
    # 07:00 .. 10:00 ramp: 0.2, 0.5, 0.8, 1.0 (08:00), 0.8, 0.6, 0.3
    for slot, v in zip(range(28, 35), [0.2, 0.5, 0.8, 1.0, 0.8, 0.6, 0.3], strict=True):
        profile[slot] = v
    peak = find_peak(profile, range(16, 48))
    assert peak.slot == 31  # 07:45
    assert peak.before == 29  # 0.5 <= 0.7
    assert peak.after == 33  # 0.6 <= 0.7


def test_find_peak_no_shoulder_inside_window():
    profile = [1.6] * SLOTS_PER_DAY  # 1.6 > 0.7 * 2.0, so nothing is 30% quieter
    profile[20] = 2.0
    peak = find_peak(profile, range(16, 48))
    assert (peak.slot, peak.before, peak.after) == (20, None, None)


def test_find_peak_empty_or_zero():
    assert find_peak([NAN] * SLOTS_PER_DAY, range(16, 48)) is None
    assert find_peak([0.0] * SLOTS_PER_DAY, range(16, 48)) is None


# ---------- dropout repair ----------


def commuter_day(dip: bool = False) -> list[float]:
    """Quiet night, 0.3 from 07:00 to 19:00; optionally a collapse to 0.01 around 09:00."""
    day = [0.02] * SLOTS_PER_DAY
    for s in range(time_to_slot(7, 0), time_to_slot(19, 0)):
        day[s] = 0.3
    if dip:
        for s in range(time_to_slot(8, 45), time_to_slot(9, 30)):
            day[s] = 0.01
    return day


def test_has_dropout():
    assert has_dropout(commuter_day(dip=True))
    assert not has_dropout(commuter_day())
    assert not has_dropout([0.0] * SLOTS_PER_DAY)


def test_repair_replaces_bad_weekdays_with_clean_average():
    days = {d: commuter_day() for d in ["MON", "FRI"]}
    days["MON"] = [v * 2 for v in days["MON"]]  # MON 0.6, FRI 0.3 -> average 0.45
    days["WED"] = commuter_day(dip=True)
    repaired, bad = repair_dropouts(make_week(days))
    assert bad == ["WED"]
    assert repaired.days["WED"].values[time_to_slot(9, 0)] == pytest.approx(0.45)
    assert repaired.days["MON"].values == make_week(days).days["MON"].values


def test_repair_needs_a_clean_weekday():
    week = make_week({"TUE": commuter_day(dip=True)})
    repaired, bad = repair_dropouts(week)
    assert bad == [] and repaired is week
