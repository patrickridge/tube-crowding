"""Pure analysis functions: no Streamlit, no network. Values are TfL baseline fractions."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import datetime

from tube.models import DAYS, SLOT_MINUTES, SLOTS_PER_DAY, WeekProfile

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


# ---------- best time to travel ----------


@dataclass(frozen=True)
class BestTime:
    best_slot: int
    best_value: float
    worst_slot: int
    worst_value: float

    @property
    def quieter_by(self) -> float:
        """How much quieter the best slot is than the worst, as a fraction of the worst."""
        return 0.0 if self.worst_value <= 0 else (self.worst_value - self.best_value) / self.worst_value


def window_slots(start_slot: int, end_slot: int) -> list[int]:
    """Departure slots from start to end inclusive. If end < start the window spans midnight,
    and slots after midnight are numbered 96, 97, ... so they can index into the next day."""
    if end_slot < start_slot:
        end_slot += SLOTS_PER_DAY
    return list(range(start_slot, end_slot + 1))


def best_time(
    today: list[float], start_slot: int, end_slot: int, tomorrow: list[float] | None = None
) -> BestTime | None:
    """Least and most crowded departure slots in a window, using the (smoothed) profile.

    Metric: the minimum of the profile over the window. Ties go to the earliest slot,
    since leaving earlier is the safer recommendation. Returns None if there's no data.
    """
    tomorrow = tomorrow if tomorrow is not None else today
    candidates = []
    for slot in window_slots(start_slot, end_slot):
        value = today[slot] if slot < SLOTS_PER_DAY else tomorrow[slot - SLOTS_PER_DAY]
        if not math.isnan(value):
            candidates.append((slot, value))
    if not candidates:
        return None
    # min/max return the first of equal values, and candidates are in time order.
    best = min(candidates, key=lambda c: c[1])
    worst = max(candidates, key=lambda c: c[1])
    return BestTime(best[0] % SLOTS_PER_DAY, best[1], worst[0] % SLOTS_PER_DAY, worst[1])


# ---------- live vs typical ----------

# Below this, typical crowding is near-empty and a ratio would be meaningless (0.02 vs 0.01 = "2x busier").
MIN_TYPICAL_FOR_RATIO = 0.03
# Ratio thresholds: a judgement call, not calibrated. Within +/-10% of typical we say "usual"
# so ordinary day-to-day noise doesn't read as news.
BANDS = [
    (0.75, "much quieter than usual"),
    (0.9, "quieter than usual"),
    (1.1, "about as busy as usual"),
    (1.25, "busier than usual"),
]


# Fewer sampled stations than this and the network factor is too noisy to use.
MIN_NETWORK_SAMPLE = 5


def network_factor(ratios: list[float | None]) -> float | None:
    """Median live/typical ratio across a sample of stations.

    Live readings run systematically above TfL's typical profiles across the whole network
    (median ~1.27 on the evening this was built), most likely because the profiles predate
    current ridership. Dividing by this common factor stops every station looking "busier
    than usual". The median keeps one station with an event from skewing it.
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
    verdict = next((text for limit, text in BANDS if adjusted < limit), "much busier than usual")
    return LiveComparison(live, typical, ratio, adjusted, verdict)


def typical_at(week: WeekProfile, when: datetime) -> float:
    """Smoothed typical value for the 15-minute band containing `when` (NaN if unknown)."""
    day = week.days.get(DAYS[when.weekday()])
    if day is None:
        return math.nan
    return smooth(day.values)[time_to_slot(when.hour, when.minute)]


# ---------- heatmap ----------


def week_grid(week: WeekProfile) -> dict[str, list[float]]:
    """Smoothed profile for each day, Monday first; days TfL didn't send are all NaN."""
    return {
        day: smooth(week.days[day].values) if day in week.days else [math.nan] * SLOTS_PER_DAY for day in DAYS
    }


# ---------- plain-English busyness ----------

# Levels as a share of the station's own busiest 15 minutes of the week. TfL's baseline is
# undocumented, so "% of this station's peak" is the most honest unit a user can read.
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


# ---------- leeway: how much does leaving earlier help? ----------


def departure_window(arrive_by: int, journey: int, leeway: int) -> tuple[int, int]:
    """(earliest, latest) departure slots, from minutes after midnight.

    The latest departure is rounded *down* to its 15-minute band, so it is never too late.
    """
    latest = (arrive_by - journey) % (24 * 60)
    earliest = (latest - leeway) % (24 * 60)
    return earliest // SLOT_MINUTES, latest // SLOT_MINUTES


def is_peak_fare(day: str, slot: int) -> bool:
    """TfL peak fares: Mon-Fri 06:30-09:30 and 16:00-19:00 (by touch-in time).

    Ignores public holidays and the off-peak rule for evening journeys into Zone 1,
    which needs the destination; the UI says so.
    """
    if day not in WEEKDAYS:
        return False
    return time_to_slot(6, 30) <= slot < time_to_slot(9, 30) or time_to_slot(16, 0) <= slot < time_to_slot(
        19, 0
    )
