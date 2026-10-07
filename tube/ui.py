"""The Streamlit page. Data comes from tube.client, analysis from tube.logic, charts from tube.charts."""

from __future__ import annotations

import calendar
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from tube import charts
from tube.client import StationNotCovered, TflClient, TflError
from tube.config import KEY_NAME, app_key_from_env
from tube.logic import (
    EVENING,
    MORNING,
    busyness_level,
    compare_live,
    departure_window,
    find_peak,
    is_peak_fare,
    leeway_options,
    network_factor,
    quietest,
    repair_dropouts,
    smooth,
    station_peak,
    time_to_slot,
    typical_at,
    week_grid,
    weekday_average,
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

VERDICT_STYLE = {  # icon and colour, so it doesn't rely on colour alone
    "much quieter than usual": (":material/keyboard_double_arrow_down:", "green"),
    "quieter than usual": (":material/arrow_downward:", "green"),
    "about as busy as usual": (":material/drag_handle:", "gray"),
    "busier than usual": (":material/arrow_upward:", "orange"),
    "much busier than usual": (":material/keyboard_double_arrow_up:", "red"),
    "an unusual reading": (":material/help:", "gray"),
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
        if result.verdict == "an unusual reading":
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
    raw = [v / peak for v in week.days[day].values]
    fig = charts.day_profile(raw, smooth(raw), live_marker)
    st.plotly_chart(fig, config=charts.CONFIG)
    st.caption("100% is this station's busiest 15 minutes of the week.")


def show_planner(week: WeekProfile, day: str, peak: float) -> None:
    left, right = st.columns(2)
    arrive = left.time_input("Arrive by", time(9, 0), step=timedelta(minutes=5))
    journey = right.number_input("Journey time (min)", min_value=5, max_value=180, value=30, step=5)
    leeway = st.select_slider(
        "How much earlier could you leave?",
        options=[15, 30, 45, 60, 75, 90],
        value=45,
        format_func=lambda m: f"{m} min",
    )
    earliest, latest = departure_window(arrive.hour * 60 + arrive.minute, int(journey), leeway)

    # Departures after midnight belong to the next day's profile.
    next_day = DAYS[(DAYS.index(day) + 1) % 7]
    today_vals = [v / peak for v in smooth(week.days[day].values)]
    next_vals = today_vals
    if next_day in week.days:
        next_vals = [v / peak for v in smooth(week.days[next_day].values)]
    slots = window_slots(earliest, latest)
    values = [today_vals[s] if s < SLOTS_PER_DAY else next_vals[s - SLOTS_PER_DAY] for s in slots]

    options = leeway_options(slots, values)
    best = quietest(options)
    if best is None:
        st.info("No crowding data for that time.")
        return
    last = options[-1]

    with st.container(border=True):
        if best.minutes_earlier == 0:
            st.markdown(f"#### :blue[:material/schedule:] Leave at {slot_label(best.slot)}")
            st.markdown("Leaving at the last minute is already the quietest option in your window.")
        else:
            st.markdown(
                f"#### :blue[:material/schedule:] Leave at {slot_label(best.slot)}, "
                f"{best.minutes_earlier} min earlier"
            )
            st.markdown(
                f"Typically **{-best.vs_latest:.0%} quieter** than leaving at {slot_label(last.slot)} "
                f"({busyness_level(best.value).lower()} instead of {busyness_level(last.value).lower()})."
            )
        st.caption(_fare_note(day, best.slot, last.slot))

    st.plotly_chart(
        charts.window_bars([o.slot for o in options], [o.value for o in options], best.slot, last.slot),
        config=charts.CONFIG,
    )
    rows = [
        {
            "Leave": slot_label(o.slot),
            "Earlier by": f"{o.minutes_earlier} min" if o.minutes_earlier else "latest",
            "Busyness": f"{busyness_level(o.value)} ({o.value:.0%})",
            "vs latest": f"{o.vs_latest:+.0%}" if o.minutes_earlier else "",
            "Fare": "Peak" if is_peak_fare(day, o.slot) else "Off-peak",
        }
        for o in reversed(options)
    ]
    table = pd.DataFrame(rows)
    st.dataframe(table, hide_index=True)
    if latest < earliest:
        st.caption(f"Times after midnight use {calendar.day_name[DAYS.index(next_day)]}'s pattern.")
    st.caption(
        "Times are when you enter the station, in 15-minute steps. Peak fares apply Mon–Fri "
        "06:30–09:30 and 16:00–19:00, except public holidays and evening trips from outside "
        "Zone 1 into Zone 1."
    )


def _fare_note(day: str, best_slot: int, latest_slot: int) -> str:
    best_peak, latest_peak = is_peak_fare(day, best_slot), is_peak_fare(day, latest_slot)
    if latest_peak and not best_peak:
        return "Off-peak fare, so it's cheaper too."
    if best_peak and not latest_peak:
        return "Note: this is a peak-fare time; your latest option is off-peak."
    return "Peak fare." if best_peak else "Off-peak fare."


def show_footer() -> None:
    st.divider()
    st.caption(
        "Powered by TfL Open Data. Contains OS data © Crown copyright and database rights 2016 and "
        "Geomni UK Map data © and database rights [2019]. "
        "Busyness is relative to each station's own busiest time, so it can't be compared between "
        "stations. Typical patterns describe the past, not a prediction of today. "
        "A learning project, not affiliated with or endorsed by TfL. "
        "[Source code](https://github.com/patrickridge/tube-crowding)"
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

    week, repaired = repair_dropouts(week)
    peak = station_peak(week)
    show_summary(week, peak)
    if repaired:
        full = [calendar.day_name[DAYS.index(d)] for d in repaired]
        names = full[0] if len(full) == 1 else ", ".join(full[:-1]) + " and " + full[-1]
        st.caption(
            f":material/info: TfL's figures for {names} at this station drop to almost zero at peak "
            "times, which isn't believable, so those days use the average of the other weekdays."
        )
    reading = get_live(station.naptan_id)
    show_live(week, peak, reading, get_network_factor() if reading else None)

    today = DAYS[datetime.now(LONDON).weekday()]
    day = pick_day(today)
    live_marker = None
    if reading is not None and day == DAYS[reading.time_local.weekday()]:
        slot = time_to_slot(reading.time_local.hour, reading.time_local.minute)
        live_marker = (slot, reading.value / peak)

    tab_plan, tab_day, tab_week = st.tabs(["Plan my trip", "Through the day", "Whole week"])
    with tab_plan:
        show_planner(week, day, peak)
    with tab_day:
        show_day(week, day, peak, live_marker)
    with tab_week:
        grid = {d: [v / peak for v in values] for d, values in week_grid(week).items()}
        st.plotly_chart(charts.week_heatmap(grid), config=charts.CONFIG)
        st.caption("Darker is busier. 100% is this station's busiest 15 minutes of the week.")

    show_footer()
