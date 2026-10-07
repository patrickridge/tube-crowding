"""Smoke tests: each figure builds, including with missing data, and carries labelled axes."""

import math

from tube import charts
from tube.models import SLOTS_PER_DAY


def test_day_profile_with_live_marker():
    values = [0.1] * SLOTS_PER_DAY
    fig = charts.day_profile(values, live=(40, 0.2))
    assert len(fig.data) == 2
    assert fig.layout.yaxis.title.text == charts.Y_TITLE
    assert fig.layout.xaxis.title.text == "Time of day"


def test_train_day_marks_seats_and_full():
    people = [math.nan] * 20 + [300.0] * (SLOTS_PER_DAY - 20)
    fig = charts.train_day(people, seats=248, capacity=752, slot=34)
    assert [a.text for a in fig.layout.annotations] == ["Seats", "Full"]
    assert fig.layout.yaxis.range[1] > 752
