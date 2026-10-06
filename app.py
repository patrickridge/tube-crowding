"""Tube Crowding: how busy is a London Underground station, now and usually?

UI layer only. Data comes from tube.client, analysis from tube.logic, figures from tube.charts.
Run locally with:  streamlit run app.py
"""

from __future__ import annotations

import calendar
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from tube import charts
from tube.client import StationNotCovered, TflClient, TflError
from tube.config import KEY_NAME, app_key_from_env
from tube.logic import (
    best_time,
    compare_live,
    network_factor,
    smooth,
    time_to_slot,
    typical_at,
    week_grid,
    window_slots,
)
from tube.models import DAYS, SLOTS_PER_DAY, LiveReading, Station, WeekProfile, slot_label
from tube.stations import load_stations

# Streamlit Cloud runs on UTC; every "now" in this app must be London time.
LONDON = ZoneInfo("Europe/London")
DEFAULT_STATION = "940GZZLUKSX"  # King's Cross St. Pancras
TYPICAL_TTL = timedelta(hours=24)  # typical profiles are rebuilt by TfL rarely
LIVE_TTL = timedelta(minutes=2)  # TfL refreshes live figures about every 5 minutes
NETWORK_TTL = timedelta(minutes=5)
# Busy stations spread across lines and zones, used to measure the network-wide live/typical drift.
NETWORK_SAMPLE = (
    "940GZZLUKSX",  # King's Cross St. Pancras
    "940GZZLUOXC",  # Oxford Circus
    "940GZZLUWLO",  # Waterloo
    "940GZZLULVT",  # Liverpool Street
    "940GZZLUBNK",  # Bank
    "940GZZLUVIC",  # Victoria
    "940GZZLULSQ",  # Leicester Square
    "940GZZLUCYF",  # Canary Wharf
    "940GZZLUSTD",  # Stratford
    "940GZZLUBXN",  # Brixton
    "940GZZLUCPC",  # Clapham Common
    "940GZZLUEBY",  # Ealing Broadway
    "940GZZLUMDN",  # Morden
    "940GZZLUWWL",  # Walthamstow Central
    "940GZZLUHOH",  # Harrow-on-the-Hill
    "940GZZLUWIM",  # Wimbledon
)

log = logging.getLogger(__name__)

VERDICT_STYLE = {  # icon + colour + words, so meaning never relies on colour alone
    "much quieter than usual": (":material/keyboard_double_arrow_down:", "green"),
    "quieter than usual": (":material/arrow_downward:", "green"),
    "about as busy as usual": (":material/drag_handle:", "gray"),
    "busier than usual": (":material/arrow_upward:", "orange"),
    "much busier than usual": (":material/keyboard_double_arrow_up:", "red"),
}


# ---------- cached data access ----------


def _app_key() -> str | None:
    try:
        if KEY_NAME in st.secrets:  # Streamlit Cloud
            return st.secrets[KEY_NAME]
    except FileNotFoundError:  # no secrets.toml locally; fall through to .env
        pass
    return app_key_from_env()


@st.cache_resource
def get_client() -> TflClient:
    return TflClient(app_key=_app_key())


@st.cache_data(show_spinner=False)
def get_stations() -> list[Station]:
    return load_stations()


@st.cache_data(ttl=TYPICAL_TTL, show_spinner="Loading typical crowding…")
def get_week(naptan_id: str) -> WeekProfile:
    return get_client().week_profile(naptan_id)


@st.cache_data(ttl=LIVE_TTL, show_spinner=False)
def get_live(naptan_id: str) -> LiveReading | None:
    try:
        return get_client().live(naptan_id)
    except TflError:
        return None  # live is optional; the typical view still works without it


def _station_ratio(client: TflClient, naptan_id: str) -> float | None:
    try:
        week, reading = client.week_profile(naptan_id), client.live(naptan_id)
    except TflError:
        return None
    if reading is None:
        return None
    return compare_live(reading.value, typical_at(week, reading.time_local)).ratio


@st.cache_data(ttl=NETWORK_TTL, show_spinner=False)
def get_network_factor() -> float | None:
    """Median live/typical ratio over NETWORK_SAMPLE, fetched in parallel (about 1 second)."""
    key = _app_key()
    # One client per task: requests.Session isn't guaranteed to be thread-safe.
    with ThreadPoolExecutor(max_workers=8) as pool:
        ratios = list(pool.map(lambda n: _station_ratio(TflClient(key), n), NETWORK_SAMPLE))
    return network_factor(ratios)


# ---------- page sections ----------


def pick_station(stations: list[Station]) -> Station:
    """Searchable station picker, remembered in the URL so a view can be shared."""
    by_id = {s.naptan_id: s for s in stations}
    ids = list(by_id)
    wanted = st.query_params.get("station", DEFAULT_STATION)
    chosen = st.selectbox(
        "Station",
        ids,
        index=ids.index(wanted) if wanted in by_id else ids.index(DEFAULT_STATION),
        format_func=lambda i: by_id[i].label,
        placeholder="Type a station name",
    )
    st.query_params["station"] = chosen
    return by_id[chosen]


def _more_or_less(ratio: float) -> str:
    change = (ratio - 1) * 100
    return f"{abs(change):.0f}% {'busier' if change >= 0 else 'quieter'}"


def show_live(week: WeekProfile, reading: LiveReading | None, network: float | None) -> None:
    with st.container(border=True):
        if reading is None:
            st.markdown("**Live data is unavailable right now.**")
            st.caption("The typical patterns below still apply.")
            return
        result = compare_live(reading.value, typical_at(week, reading.time_local), network)
        icon, colour = VERDICT_STYLE[result.verdict]
        st.markdown(f"#### :{colour}[{icon} {result.verdict.capitalize()}]")

        at = f"{reading.time_local:%H:%M}"
        head = f"Live {reading.value:.0%} vs typical {result.typical:.0%} of station baseline at {at}"
        if result.ratio is None:
            st.caption(f"{head}: too quiet at this time to compare fairly.")
        elif network:
            st.caption(
                f"{head} ({result.ratio - 1:+.0%}). Across the network, stations are running "
                f"{network - 1:+.0%} against TfL's typical figures right now; allowing for that, "
                f"this station is {_more_or_less(result.adjusted)} than usual."
            )
        else:
            st.caption(f"{head}: {_more_or_less(result.ratio)} than usual.")


def pick_day(today: str) -> str:
    names = dict(zip(DAYS, calendar.day_name, strict=True))  # MON -> Monday
    return st.selectbox(
        "Day",
        DAYS,
        index=DAYS.index(today),
        format_func=lambda d: f"{names[d]} (today)" if d == today else names[d],
    )


def show_day(week: WeekProfile, day: str, live_marker: tuple[int, float] | None) -> None:
    profile = week.days[day]
    fig = charts.day_profile(list(profile.values), smooth(profile.values), live_marker)
    st.plotly_chart(fig, config=charts.CONFIG)
    if profile.am_peak and profile.pm_peak:
        st.caption(f"TfL's peak periods for this station: {profile.am_peak} and {profile.pm_peak}.")


def show_best_time(week: WeekProfile, day: str) -> None:
    step = timedelta(minutes=15)
    left, right = st.columns(2)
    start = left.time_input("Leaving from", time(7, 30), step=step)
    end = right.time_input("Leaving by", time(9, 30), step=step)
    start_slot, end_slot = time_to_slot(start.hour, start.minute), time_to_slot(end.hour, end.minute)

    next_day = DAYS[(DAYS.index(day) + 1) % 7]
    today_vals = smooth(week.days[day].values)
    tomorrow_vals = smooth(week.days[next_day].values) if next_day in week.days else None
    result = best_time(today_vals, start_slot, end_slot, tomorrow_vals)
    if result is None:
        st.info("No crowding data for that window.")
        return

    best, worst = slot_label(result.best_slot), slot_label(result.worst_slot)
    with st.container(border=True):
        st.markdown(f"#### :blue[:material/schedule:] Leave at {best}")
        if result.quieter_by > 0:
            st.markdown(
                f"Typically **{result.quieter_by:.0%} quieter** than {worst}, the busiest time in "
                f"your window ({result.best_value:.0%} vs {result.worst_value:.0%} of baseline)."
            )
        else:
            st.markdown("Every departure in this window is typically about equally busy.")

    slots = window_slots(start_slot, end_slot)
    values = [
        today_vals[s] if s < SLOTS_PER_DAY else (tomorrow_vals or today_vals)[s - SLOTS_PER_DAY]
        for s in slots
    ]
    shown = [s % SLOTS_PER_DAY for s in slots]
    st.plotly_chart(
        charts.window_bars(shown, values, result.best_slot, result.worst_slot), config=charts.CONFIG
    )
    if end_slot < start_slot:
        next_name = charts.DAY_NAMES[next_day]
        st.caption(f"Your window crosses midnight: times after 00:00 use {next_name}'s pattern.")

    with st.expander("How this is worked out"):
        st.markdown(
            "Each departure time is scored with TfL's typical crowding for that 15-minute band, "
            "smoothed with a 45-minute moving average to remove rounding jitter. The recommendation "
            "is the band with the **lowest** smoothed value in your window (ties go to the earlier "
            "time). *Quieter by* compares it with the busiest band: (busiest − quietest) / busiest."
        )
        table = pd.DataFrame(
            {
                "Departure": [slot_label(s) for s in shown],
                "% of baseline": [round(v * 100, 1) for v in values],
            }
        )
        st.dataframe(table, hide_index=True)


def show_footer() -> None:
    st.divider()
    st.caption(
        "Powered by TfL Open Data. Contains OS data © Crown copyright and database rights 2016 and "
        "Geomni UK Map data © and database rights [2019]. "
        "Crowding is shown as a percentage of an undocumented baseline TfL sets for each station, so "
        "figures compare a station with its own usual pattern, not with other stations. Typical "
        "patterns describe the past, not a prediction of today. "
        "A learning project, not affiliated with or endorsed by TfL."
    )


# ---------- page ----------


def main() -> None:
    st.set_page_config(page_title="Tube Crowding", page_icon="🚇", layout="centered")
    st.title("How busy is my tube station?")
    st.caption("Typical and live crowding for London Underground stations, from TfL open data.")

    station = pick_station(get_stations())
    try:
        week = get_week(station.naptan_id)
    except StationNotCovered:
        st.info(f"TfL doesn't publish crowding data for {station.name}. Try a nearby station.")
        show_footer()
        return
    except TflError as err:
        st.error(str(err))
        show_footer()
        return

    now = datetime.now(LONDON)
    today = DAYS[now.weekday()]
    reading = get_live(station.naptan_id)
    show_live(week, reading, get_network_factor() if reading else None)

    day = pick_day(today)
    live_marker = None
    if reading is not None and day == DAYS[reading.time_local.weekday()]:
        live_marker = (time_to_slot(reading.time_local.hour, reading.time_local.minute), reading.value)

    tab_day, tab_best, tab_week = st.tabs(["Through the day", "Best time to travel", "Whole week"])
    with tab_day:
        show_day(week, day, live_marker)
    with tab_best:
        show_best_time(week, day)
    with tab_week:
        st.plotly_chart(charts.week_heatmap(week_grid(week)), config=charts.CONFIG)
        st.caption("Darker means busier. Each cell is a 15-minute band, smoothed.")

    show_footer()


try:
    main()
except Exception:  # last line of defence: log the trace, show the user a sentence
    log.exception("Unhandled error")
    st.error("Something went wrong loading this page. Please refresh, or try again in a minute.")
