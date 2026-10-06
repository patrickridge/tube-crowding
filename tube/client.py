"""TfL Unified API client.

Two halves: `parse_*` functions turn raw JSON into models (pure, tested against saved
responses), and `TflClient` does the HTTP. Callers only ever see models or a TflError.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

import requests

from tube.models import DAYS, SLOT_MINUTES, SLOTS_PER_DAY, DayProfile, LiveReading, WeekProfile

BASE_URL = "https://api.tfl.gov.uk"
TIMEOUT_SECONDS = 10


class TflError(Exception):
    """Base error. `str(err)` is a message safe to show to users."""


class StationNotCovered(TflError):
    """TfL has no crowding data for this station."""


class RateLimited(TflError):
    pass


class ApiUnavailable(TflError):
    """Timeout, connection failure or a 5xx from TfL."""


class MalformedResponse(TflError):
    pass


# ---------- parsing ----------


def _band_to_slot(band: str) -> int:
    """'08:15-08:30' -> 33."""
    hours, minutes = band.split("-")[0].split(":")
    slot = (int(hours) * 60 + int(minutes)) // SLOT_MINUTES
    if not 0 <= slot < SLOTS_PER_DAY:
        raise ValueError(band)
    return slot


def parse_day(raw: dict[str, Any]) -> DayProfile:
    """Parse one entry of `daysOfWeek` (or the single-day endpoint) into a DayProfile."""
    sums = [0.0] * SLOTS_PER_DAY
    counts = [0] * SLOTS_PER_DAY
    for band in raw.get("timeBands") or []:
        try:
            slot = _band_to_slot(band["timeBand"])
            value = float(band["percentageOfBaseLine"])
        except (KeyError, TypeError, ValueError):
            continue  # skip a bad band rather than lose the whole day
        # Some stations (e.g. Hammersmith H&C) send every band twice with different
        # values; we average them rather than guess which one is right.
        sums[slot] += value
        counts[slot] += 1
    values = tuple(s / c if c else math.nan for s, c in zip(sums, counts, strict=True))
    return DayProfile(
        day=str(raw.get("dayOfWeek", "")).upper(),
        values=values,
        am_peak=raw.get("amPeakTimeBand"),
        pm_peak=raw.get("pmPeakTimeBand"),
    )


def parse_week(raw: Any, naptan_id: str) -> WeekProfile:
    """Parse /crowding/{naptan}. Raises StationNotCovered if there is nothing usable."""
    if not isinstance(raw, dict):
        raise MalformedResponse("TfL sent crowding data in an unexpected format.")
    days: dict[str, DayProfile] = {}
    for entry in raw.get("daysOfWeek") or []:
        if isinstance(entry, dict):
            day = parse_day(entry)
            if day.day in DAYS:
                days[day.day] = day
    week = WeekProfile(naptan_id=naptan_id, days=days)
    if not week.has_data:
        raise StationNotCovered("TfL doesn't publish crowding data for this station.")
    return week


def parse_live(raw: Any) -> LiveReading | None:
    """Parse /crowding/{naptan}/Live. Returns None when live data isn't available."""
    if not isinstance(raw, dict) or not raw.get("dataAvailable"):
        return None
    try:
        return LiveReading(
            value=float(raw["percentageOfBaseline"]),
            time_local=datetime.strptime(raw["timeLocal"], "%Y-%m-%d %H:%M:%S"),
        )
    except (KeyError, TypeError, ValueError):
        return None  # live data is a nice-to-have; never fail the page over it


# ---------- HTTP ----------


class TflClient:
    def __init__(self, app_key: str | None = None, session: requests.Session | None = None):
        self.app_key = app_key
        self.session = session or requests.Session()

    def _get(self, path: str) -> Any:
        params = {"app_key": self.app_key} if self.app_key else {}
        try:
            resp = self.session.get(BASE_URL + path, params=params, timeout=TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            raise ApiUnavailable("TfL's servers didn't respond. Please try again shortly.") from exc
        if resp.status_code == 429:
            raise RateLimited("Too many requests to TfL right now. Please wait a minute and retry.")
        if resp.status_code >= 500:
            raise ApiUnavailable("TfL's data service is having problems. Please try again shortly.")
        if resp.status_code == 404:
            raise StationNotCovered("TfL doesn't publish crowding data for this station.")
        if not resp.ok:
            raise ApiUnavailable(f"TfL returned an unexpected error ({resp.status_code}).")
        try:
            return resp.json()
        except ValueError as exc:
            raise MalformedResponse("TfL sent a response we couldn't read.") from exc

    def week_profile(self, naptan_id: str) -> WeekProfile:
        return parse_week(self._get(f"/crowding/{naptan_id}"), naptan_id)

    def live(self, naptan_id: str) -> LiveReading | None:
        return parse_live(self._get(f"/crowding/{naptan_id}/Live"))
