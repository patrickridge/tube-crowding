"""Page: is my station busy right now, and when is it usually busy?"""

from __future__ import annotations

import calendar
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import streamlit as st

from tube import charts
from tube.client import StationNotCovered, TflClient, TflError
from tube.logic import (
    EVENING,
    MORNING,
    busyness_level,
    compare_live,
    find_peak,
    network_factor,
    repair_dropouts,
    smooth,
    station_peak,
    time_to_slot,
    typical_at,
    weekday_average,
)
from tube.models import DAYS, LiveReading, Station, WeekProfile, slot_label
from tube.stations import load_stations
from tube.tfl import app_key, get_client

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

VERDICT_STYLE = {  # icon and colour, so it doesn't rely on colour alone
    "much quieter than usual": (":material/keyboard_double_arrow_down:", "green"),
    "quieter than usual": (":material/arrow_downward:", "green"),
    "about as busy as usual": (":material/drag_handle:", "gray"),
    "busier than usual": (":material/arrow_upward:", "orange"),
    "much busier than usual": (":material/keyboard_double_arrow_up:", "red"),
    "an unusual reading": (":material/help:", "gray"),
}


# ---------- cached data access ----------


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
        return None  # the page still works without live data


def _station_ratio(client: TflClient, naptan_id: str) -> float | None:
    try:
        week, reading = repair_dropouts(client.week_profile(naptan_id))[0], client.live(naptan_id)
    except TflError:
        return None
    if reading is None:
        return None
    return compare_live(reading.value, typical_at(week, reading.time_local)).ratio


@st.cache_data(ttl=NETWORK_TTL, show_spinner=False)
def get_network_factor() -> float | None:
    """Median live/typical ratio over NETWORK_SAMPLE, fetched in parallel (about 1 second)."""
    key = app_key()
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


def show_summary(week: WeekProfile, peak: float) -> None:
    """One line per weekday peak: when it is, and when it's at least 30% quieter."""
    profile = weekday_average(week)
    lines = []
    for name, window in (("Mornings", MORNING), ("Evenings", EVENING)):
        found = find_peak(profile, window)
        if found is None:
            continue
        line = f"**{name}** peak around **{slot_label(found.slot)}**"
        escapes = []
        if found.before is not None:
            escapes.append(f"by {slot_label(found.before)}")
        if found.after is not None:
            escapes.append(f"from {slot_label(found.after)}")
        if escapes:
            line += f". Travel {' or '.join(escapes)} and it's 30%+ quieter."
        lines.append(line)
    if lines:
        st.markdown("  \n".join(["On weekdays at this station:", *lines]))


def show_live(week: WeekProfile, peak: float, reading: LiveReading | None, network: float | None) -> None:
    with st.container(border=True):
        if reading is None:
            st.markdown("**Live data is unavailable right now.**")
            st.caption("The typical patterns below still apply.")
            return
        result = compare_live(reading.value, typical_at(week, reading.time_local), network)
        icon, colour = VERDICT_STYLE[result.verdict]
        st.markdown(f"#### :{colour}[{icon} Right now: {result.verdict}]")

        usual = busyness_level(result.typical / peak) if peak else "Unknown"
        detail = f"Usually {usual.lower()} at {reading.time_local:%H:%M} on a {reading.time_local:%A}."
        if reading.value == 0:
            detail += " TfL's live feed shows zero here, which usually means it isn't working right now."
        elif result.verdict == "an unusual reading":
            detail += (
                f" The live figure is {_more_or_less(result.adjusted)} than normal, which is more "
                "likely a data glitch than real crowds, so treat it with caution."
            )
        elif result.adjusted is not None:
            detail += f" Live crowding is {_more_or_less(result.adjusted)} than normal for this time"
            if network:
                detail += (
                    f", after allowing for the whole network running {network - 1:+.0%} "
                    "against TfL's typical figures"
                )
            detail += "."
        st.caption(detail)


def pick_day(today: str) -> str:
    names = dict(zip(DAYS, calendar.day_name, strict=True))  # MON -> Monday
    return st.selectbox(
        "Day",
        DAYS,
        index=DAYS.index(today),
        format_func=lambda d: f"{names[d]} (today)" if d == today else names[d],
    )


def show_day(week: WeekProfile, day: str, peak: float, live_marker: tuple[int, float] | None) -> None:
    fig = charts.day_profile([v / peak for v in smooth(week.days[day].values)], live_marker)
    st.plotly_chart(fig, config=charts.CONFIG)
    st.caption("100% is this station's busiest 15 minutes of the week.")


# ---------- page ----------


def page() -> None:
    st.title("Is my station busy?")
    st.caption("Live and typical crowding at Underground stations.")

    station = pick_station(get_stations())
    try:
        week = get_week(station.naptan_id)
    except StationNotCovered:
        st.info(f"TfL doesn't publish crowding data for {station.name}. Try a nearby station.")
        return
    except TflError as err:
        st.error(str(err))
        return

    week, repaired = repair_dropouts(week)
    peak = station_peak(week)
    reading = get_live(station.naptan_id)
    show_live(week, peak, reading, get_network_factor() if reading else None)
    show_summary(week, peak)

    today = DAYS[datetime.now(LONDON).weekday()]
    day = pick_day(today)
    live_marker = None
    if reading is not None and day == DAYS[reading.time_local.weekday()]:
        slot = time_to_slot(reading.time_local.hour, reading.time_local.minute)
        live_marker = (slot, reading.value / peak)
    show_day(week, day, peak, live_marker)
    if repaired:
        full = [calendar.day_name[DAYS.index(d)] for d in repaired]
        names = full[0] if len(full) == 1 else ", ".join(full[:-1]) + " and " + full[-1]
        st.caption(
            f"TfL's figures for {names} at this station drop to almost zero at peak times, "
            "which isn't believable, so those days use the average of the other weekdays."
        )
