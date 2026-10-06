"""Smoke tests: each figure builds, including with missing data, and carries labelled axes."""

import math

from tube import charts
from tube.models import DAYS, SLOTS_PER_DAY


def test_day_profile_with_live_marker():
    values = [0.1] * SLOTS_PER_DAY
    fig = charts.day_profile(values, values, live=(40, 0.2))
    assert len(fig.data) == 3
    assert fig.layout.yaxis.title.text == charts.Y_TITLE
    assert fig.layout.xaxis.title.text == "Time of day"


def test_week_heatmap_handles_missing_day():
    grid = {d: [0.1] * SLOTS_PER_DAY for d in DAYS}
    grid["SUN"] = [math.nan] * SLOTS_PER_DAY
    fig = charts.week_heatmap(grid)
    assert list(fig.data[0].y) == ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def test_window_bars_labels_only_best_and_worst():
    fig = charts.window_bars([30, 31, 32], [0.3, 0.1, 0.5], best_slot=31, worst_slot=32)
    assert list(fig.data[0].text) == ["", "10%", "50%"]
