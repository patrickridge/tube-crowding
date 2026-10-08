"""Page: will I get a seat on my journey?"""

from __future__ import annotations

import calendar
import html
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import streamlit as st

from tube import charts
from tube.logic import time_to_slot
from tube.models import slot_label
from tube.seats import (
    DAY_TYPES,
    TRAINS,
    Leg,
    Link,
    better_earlier,
    for_weekday,
    journey,
    leg_slot,
    load_links,
    overall,
    plan,
    stations,
)

LONDON = ZoneInfo("Europe/London")
DEFAULT = {"from": "Balham", "to": "Oxford Circus"}
DAYS = list(calendar.day_abbr)  # Mon .. Sun
DAY_TYPE_NAMES = {
    "MON": "Monday",
    "TWT": "Tuesday to Thursday",
    "FRI": "Friday",
    "SAT": "Saturday",
    "SUN": "Sunday",
}

HEADLINES = {  # overall level -> icon, colour, headline
    "seat": (":material/event_seat:", "green", "You'll probably get a seat"),
    "maybe": (":material/event_seat:", "blue", "You might get a seat"),
    "part": (":material/event_seat:", "blue", "You'll get a seat for part of it"),
    "stand": (":material/directions_walk:", "orange", "You'll probably stand"),
    "packed": (":material/warning:", "red", "Very crowded"),
}
LEG_TEXT = {
    "seat": "probably a seat",
    "maybe": "might get a seat",
    "stand": "you'll stand",
    "packed": "very crowded",
    None: "no trains at this time",
}
TIP = {
    "seat": "you'll probably get a seat",
    "maybe": "you might get a seat",
    "stand": "it's less crowded, though you'll probably still stand",
}
# TfL line colours, for the small line labels.
LINE_COLOURS = {
    "Bakerloo": ("#B36305", "white"),
    "Central": ("#E32017", "white"),
    "Circle / Hammersmith & City": ("#FFD300", "#1c1c1c"),
    "District": ("#00782A", "white"),
    "Elizabeth line": ("#6950A1", "white"),
    "Jubilee": ("#A0A5A9", "#1c1c1c"),
    "Metropolitan": ("#9B0056", "white"),
    "Northern": ("#1c1c1c", "white"),
    "Piccadilly": ("#003688", "white"),
    "Victoria": ("#0098D4", "white"),
    "Waterloo & City": ("#95CDBA", "#1c1c1c"),
}


@st.cache_data(show_spinner=False)
def get_links() -> list[Link]:
    return load_links()


def _choose(label: str, options: list[str], key: str, fallback: str, container=st, **kwargs) -> str:
    """Selectbox that starts from the URL (so a journey can be bookmarked), else from `fallback`."""
    wanted = st.query_params.get(key, fallback)
    start = wanted if wanted in options else fallback
    return container.selectbox(label, options, index=options.index(start), **kwargs)


def _start_time() -> time:
    """The time saved in the URL (a bookmarked journey), else now, rounded down to 15 minutes."""
    try:
        return datetime.strptime(st.query_params["time"], "%H:%M").time()
    except (KeyError, ValueError):
        now = datetime.now(LONDON)
        return time(now.hour, now.minute - now.minute % 15)


def _line_label(line: str) -> str:
    background, text = LINE_COLOURS[line]
    return (
        f'<span style="background:{background};color:{text};border-radius:4px;'
        f'padding:1px 7px;font-size:0.8rem;font-weight:600;white-space:nowrap">{html.escape(line)}</span>'
    )


def _leg_row(leg: Leg, level: str | None) -> str:
    stops = len(leg.links)
    return (
        f"{_line_label(leg.line)}&nbsp; to {html.escape(leg.dest)} · {stops} stop{'s' * (stops != 1)}"
        f" · <b>{LEG_TEXT[level]}</b>"
    )


def page() -> None:
    st.title("Will I get a seat?")
    st.caption("How full trains usually are on the Underground and Elizabeth line, from TfL's 2025 counts.")

    names = stations(get_links())
    left, right = st.columns(2)
    origin = _choose("From", names, "from", DEFAULT["from"], left)
    dest = _choose("To", names, "to", DEFAULT["to"], right)
    left, right = st.container(key="when").columns(2)  # kept side by side on phones, see ui.py
    today = DAYS[datetime.now(LONDON).weekday()]
    day = _choose(
        "Day",
        DAYS,
        "day",
        today,
        left,
        format_func=lambda d: calendar.day_name[DAYS.index(d)] + (" (today)" if d == today else ""),
    )
    when = right.time_input("Leaving at", _start_time(), step=timedelta(minutes=15))
    # The day isn't saved: a bookmarked journey should open on today.
    st.query_params.update({"from": origin, "to": dest, "time": f"{when:%H:%M}"})
    if st.button(":material/swap_horiz: Return trip"):
        st.query_params.update({"from": dest, "to": origin})
        st.rerun()

    if origin == dest:
        st.info("Pick two different stations.")
        return
    weekday = DAYS.index(day)
    legs = plan(for_weekday(get_links(), weekday), origin, dest)
    if not legs:
        st.info(f"Couldn't find a route from {origin} to {dest} on the Underground or Elizabeth line.")
        return

    slot = time_to_slot(when.hour, when.minute)
    trips = [journey(list(leg.links), leg_slot(slot, leg), TRAINS[leg.line]) for leg in legs]
    summary = overall([trip.level for trip in trips])
    if summary is None:
        st.info(f"No trains leave {origin} at this time.")
        return

    first, first_trip = legs[0], trips[0]
    with st.container(border=True):
        icon, colour, headline = HEADLINES[summary]
        st.markdown(f"### :{colour}[{icon} {headline}]")
        rows = [_leg_row(leg, trip.level) for leg, trip in zip(legs, trips, strict=True)]
        st.markdown("<br>".join(rows), unsafe_allow_html=True)
        earlier = better_earlier(list(first.links), slot, TRAINS[first.line])
        if earlier:
            st.markdown(f":material/lightbulb: Leave at **{slot_label(earlier[0])}** and {TIP[earlier[1]]}.")
        elif first_trip.seat_from:
            st.markdown(
                f":material/lightbulb: On the {first.line} line, seats usually free up from "
                f"**{first_trip.seat_from}**."
            )

    with st.expander(f"How busy is the {first.line} line from {origin} through the day?"):
        train = TRAINS[first.line]
        st.plotly_chart(
            charts.train_day(list(first.links[0].per_train), train.seats, train.capacity, slot),
            config=charts.CONFIG,
        )
        st.caption(
            f"People on each train leaving {origin}, typical {DAY_TYPE_NAMES[DAY_TYPES[weekday]]}. "
            f"A {first.line} line train has {train.seats} seats and room for about {train.capacity}."
        )
    st.caption("Bookmark this page to come back to your journey.")
