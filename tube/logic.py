"""Pure analysis functions: no Streamlit, no network. Values are TfL baseline fractions."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import datetime

from tube.models import DAYS, SLOT_MINUTES, SLOTS_PER_DAY, DayProfile, WeekProfile

SMOOTHING_WINDOW = 3  # bands, i.e. a 45-minute centred moving average


def smooth(values: tuple[float, ...] | list[float], window: int = SMOOTHING_WINDOW) -> list[float]:
    """Centred moving average that ignores missing (NaN) bands.

    TfL rounds to 0.01, which is coarse for quiet stations (a peak of 0.10 moves in 10%
    steps), so a short average removes jitter without shifting the peaks. At the ends of
    the day the window just shrinks rather than wrapping into an unrelated day.
    """
    half = window // 2
    out = []
    for i in range(len(values)):
        neighbours = [v for v in values[max(0, i - half) : i + half + 1] if not math.isnan(v)]
        out.append(sum(neighbours) / len(neighbours) if neighbours else math.nan)
    return out


def time_to_slot(hour: int, minute: int) -> int:
    """09:37 -> slot 38 (the band 09:30-09:45 it falls in)."""
    return (hour * 60 + minute) // SLOT_MINUTES


# ---------- live vs typical ----------

# Below this, typical crowding is near-empty and a ratio would be meaningless (0.02 vs 0.01 = "2x busier").
MIN_TYPICAL_FOR_RATIO = 0.03
# My own thresholds, not fitted to data. Within 10% of typical counts as normal.
BANDS = [
    (0.75, "much quieter than usual"),
    (0.9, "quieter than usual"),
    (1.1, "about as busy as usual"),
    (1.25, "busier than usual"),
]


# Live readings further than this from normal are more likely a data glitch than real crowds.
PLAUSIBLE_LIVE = (0.4, 2.5)
# Fewer sampled stations than this and the network factor is too noisy to use.
MIN_NETWORK_SAMPLE = 5


def network_factor(ratios: list[float | None]) -> float | None:
    """Median live/typical ratio across a sample of stations.

    Live readings are above TfL's typical figures almost everywhere (about 1.27x when I
    checked), so without this every station looks "busier than usual". Median rather than
    mean so one station with an event doesn't move it much.
    """
    valid = [r for r in ratios if r is not None and r > 0]
    return statistics.median(valid) if len(valid) >= MIN_NETWORK_SAMPLE else None


@dataclass(frozen=True)
class LiveComparison:
    live: float
    typical: float
    ratio: float | None  # live / typical; None when typical is too small to divide by
    adjusted: float | None  # ratio / network factor; equals ratio when no factor is available
    verdict: str


def compare_live(live: float, typical: float, network: float | None = None) -> LiveComparison:
    if math.isnan(typical) or typical < MIN_TYPICAL_FOR_RATIO:
        verdict = "about as busy as usual" if live < 2 * MIN_TYPICAL_FOR_RATIO else "busier than usual"
        return LiveComparison(live, typical, None, None, verdict)
    ratio = live / typical
    adjusted = ratio / network if network else ratio
    if not PLAUSIBLE_LIVE[0] <= adjusted <= PLAUSIBLE_LIVE[1]:
        return LiveComparison(live, typical, ratio, adjusted, "an unusual reading")
    verdict = next((text for limit, text in BANDS if adjusted < limit), "much busier than usual")
    return LiveComparison(live, typical, ratio, adjusted, verdict)


def typical_at(week: WeekProfile, when: datetime) -> float:
    """Smoothed typical value for the 15-minute band containing `when` (NaN if unknown)."""
    day = week.days.get(DAYS[when.weekday()])
    if day is None:
        return math.nan
    return smooth(day.values)[time_to_slot(when.hour, when.minute)]


# ---------- week grid ----------


def week_grid(week: WeekProfile) -> dict[str, list[float]]:
    """Smoothed profile for each day, Monday first; days TfL didn't send are all NaN."""
    return {
        day: smooth(week.days[day].values) if day in week.days else [math.nan] * SLOTS_PER_DAY for day in DAYS
    }


# ---------- busyness levels ----------

# Busyness as a share of the station's busiest 15 minutes of the week. TfL's own baseline
# isn't documented, so this is easier to understand.
LEVELS = [(0.25, "Quiet"), (0.5, "Moderate"), (0.75, "Busy")]


def station_peak(week: WeekProfile) -> float:
    """Highest smoothed value in the week; the 100% mark for this station."""
    peaks = [v for values in week_grid(week).values() for v in values if not math.isnan(v)]
    return max(peaks, default=0.0)


def busyness_level(share_of_peak: float) -> str:
    if math.isnan(share_of_peak):
        return "Unknown"
    return next((name for limit, name in LEVELS if share_of_peak < limit), "Very busy")


# ---------- commute summary ----------

SHOULDER = 0.7  # "at least 30% quieter than the peak"
MORNING = range(time_to_slot(4, 0), time_to_slot(12, 0))
EVENING = range(time_to_slot(12, 0), SLOTS_PER_DAY)
WEEKDAYS = DAYS[:5]


@dataclass(frozen=True)
class Peak:
    slot: int
    before: int | None  # last slot before the peak at or below SHOULDER x peak
    after: int | None  # first slot after the peak at or below SHOULDER x peak


def weekday_average(week: WeekProfile) -> list[float]:
    """Mean smoothed weekday profile, ignoring missing bands."""
    grid = week_grid(week)
    out = []
    for slot in range(SLOTS_PER_DAY):
        vals = [grid[d][slot] for d in WEEKDAYS if not math.isnan(grid[d][slot])]
        out.append(sum(vals) / len(vals) if vals else math.nan)
    return out


def find_peak(profile: list[float], window: range) -> Peak | None:
    """Busiest slot in `window`, plus the nearest times either side that are 30%+ quieter."""
    valid = [s for s in window if not math.isnan(profile[s])]
    if not valid:
        return None
    top = max(valid, key=lambda s: profile[s])  # ties go to the earliest slot
    if profile[top] <= 0:
        return None
    limit = SHOULDER * profile[top]
    before = next((s for s in range(top - 1, window.start - 1, -1) if profile[s] <= limit), None)
    after = next((s for s in range(top + 1, window.stop) if profile[s] <= limit), None)
    return Peak(top, before, after)


# ---------- data repair ----------

# Some stations' typical profiles collapse to near zero at peak times on Tue-Thu (e.g. Waterloo
# at 09:00), which isn't believable. A band counts as a dropout if both sides, within two hours,
# are busy (at least half the day's peak) and the band is under 30% of the quieter side.
DROPOUT_RATIO = 0.3
DROPOUT_REACH = 8  # bands either side (two hours)


def has_dropout(values: tuple[float, ...] | list[float]) -> bool:
    v = [0.0 if math.isnan(x) else x for x in smooth(values)]
    day_max = max(v, default=0.0)
    if day_max <= 0:
        return False
    for s in range(time_to_slot(6, 0), time_to_slot(20, 0)):
        side = min(max(v[s - DROPOUT_REACH : s]), max(v[s + 1 : s + 1 + DROPOUT_REACH]))
        if side >= 0.5 * day_max and v[s] < DROPOUT_RATIO * side:
            return True
    return False


def repair_dropouts(week: WeekProfile) -> tuple[WeekProfile, list[str]]:
    """Replace weekdays that have a dropout with the average of the station's clean weekdays.

    Returns the repaired week and the days that were replaced (empty if none, or if no
    clean weekday is available to copy from).
    """
    bad = [d for d in WEEKDAYS if d in week.days and has_dropout(week.days[d].values)]
    clean = [week.days[d] for d in WEEKDAYS if d in week.days and d not in bad]
    if not bad or not clean:
        return week, []
    average = []
    for slot in range(SLOTS_PER_DAY):
        vals = [d.values[slot] for d in clean if not math.isnan(d.values[slot])]
        average.append(sum(vals) / len(vals) if vals else math.nan)
    days = dict(week.days)
    for d in bad:
        days[d] = DayProfile(d, tuple(average), week.days[d].am_peak, week.days[d].pm_peak)
    return WeekProfile(week.naptan_id, days), bad
