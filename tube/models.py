"""Typed data structures shared by every layer. Nothing here touches the network."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

DAYS: tuple[str, ...] = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
SLOT_MINUTES = 15
SLOTS_PER_DAY = 24 * 60 // SLOT_MINUTES  # 96


def slot_label(slot: int) -> str:
    """Slot index (0-95) -> 'HH:MM' start time."""
    minutes = (slot % SLOTS_PER_DAY) * SLOT_MINUTES
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


@dataclass(frozen=True)
class Station:
    naptan_id: str
    name: str
    lines: tuple[str, ...]

    @property
    def label(self) -> str:
        """Display name. Lines are included so stations sharing a name stay distinguishable."""
        return f"{self.name} ({', '.join(self.lines)})" if self.lines else self.name


@dataclass(frozen=True)
class DayProfile:
    """Typical crowding for one day of the week.

    `values[i]` is the 15-minute band starting at slot i, as a fraction of TfL's
    station baseline (0.25 means 25% of baseline). NaN marks a band TfL did not send.
    """

    day: str
    values: tuple[float, ...]
    am_peak: str | None = None
    pm_peak: str | None = None

    @property
    def has_data(self) -> bool:
        # TfL returns all-zero profiles for stations it does not actually measure.
        return any(v > 0 for v in self.values if not math.isnan(v))


@dataclass(frozen=True)
class WeekProfile:
    naptan_id: str
    days: dict[str, DayProfile]

    @property
    def has_data(self) -> bool:
        return any(d.has_data for d in self.days.values())


@dataclass(frozen=True)
class LiveReading:
    """Latest live crowding figure; same units as DayProfile.values."""

    value: float
    time_local: datetime
