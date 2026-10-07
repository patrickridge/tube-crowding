"""Page: will I get a seat on my train?"""

from __future__ import annotations

import calendar
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import streamlit as st

from tube import charts
from tube.logic import time_to_slot
from tube.models import slot_label
from tube.seats import (
    DAY_TYPES,
    TRAINS,
    Link,
    better_earlier,
    for_weekday,
    journey,
    load_links,
    route,
    stations,
)

ANSWERS = {  # level -> icon, colour, headline
    "seat": (":material/event_seat:", "green", "You'll probably get a seat"),
    "maybe": (":material/event_seat:", "blue", "You might get a seat"),
    "stand": (":material/directions_walk:", "orange", "You'll probably stand"),
    "packed": (":material/warning:", "red", "Very crowded"),
}
TIP = {
    "seat": "you'll probably get a seat",
    "maybe": "you might get a seat",
    "stand": "it's less crowded, though you'll probably still stand",
}
DEFAULT = {"line": "Northern", "from": "Balham", "to": "Bank and Monument"}
DAYS = list(calendar.day_abbr)  # Mon .. Sun, as used in the URL
DAY_TYPE_NAMES = {
    "MON": "Monday",
    "TWT": "Tuesday to Thursday",
    "FRI": "Friday",
    "SAT": "Saturday",
    "SUN": "Sunday",
}
LONDON = ZoneInfo("Europe/London")


@st.cache_data(show_spinner=False)
def get_links() -> list[Link]:
    return load_links()


def _choose(label: str, options: list[str], key: str, fallback: str, container=st, **kwargs) -> str:
    """Selectbox that starts from the URL (so a journey can be bookmarked), else from `fallback`."""
    wanted = st.query_params.get(key, fallback)
    start = wanted if wanted in options else fallback
    return container.selectbox(label, options, index=options.index(start), **kwargs)


def _default(key: str, options: list[str], otherwise: str) -> str:
    return DEFAULT[key] if DEFAULT[key] in options else otherwise


def _start_time() -> time:
    """The time saved in the URL (a bookmarked journey), else now, rounded down to 15 minutes."""
    try:
        return datetime.strptime(st.query_params["time"], "%H:%M").time()
    except (KeyError, ValueError):
        now = datetime.now(LONDON)
        return time(now.hour, now.minute - now.minute % 15)


def page() -> None:
    st.title("Will I get a seat?")
    st.caption("How full trains usually are, from TfL's 2025 passenger counts.")

    lines = sorted(TRAINS)
    line = _choose("Line", lines, "line", DEFAULT["line"])
    names = stations(get_links(), line)
    left, right = st.columns(2)
    origin = _choose("From", names, "from", _default("from", names, names[0]), left)
    dest = _choose("To", names, "to", _default("to", names, names[-1]), right)
    left, right = st.columns(2)
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
    st.query_params.update({"line": line, "from": origin, "to": dest, "time": f"{when:%H:%M}"})
    if st.button(":material/swap_horiz: Return trip"):
        st.query_params.update({"from": dest, "to": origin})
        st.rerun()

    weekday = DAYS.index(day)
    links = for_weekday(get_links(), weekday)

    if origin == dest:
        st.info("Pick two different stations.")
        return
    path = route(links, line, origin, dest)
    if not path:
        st.info(f"There's no direct {line} line train from {origin} to {dest}.")
        return

    train = TRAINS[line]
    slot = time_to_slot(when.hour, when.minute)
    trip = journey(path, slot, train)
    if trip.level is None:
        st.info(f"No {line} line trains leave {origin} at this time.")
        return

    with st.container(border=True):
        icon, colour, headline = ANSWERS[trip.level]
        st.markdown(f"### :{colour}[{icon} {headline}]")
        st.markdown(
            f"Trains leaving {origin} at {slot_label(slot)} usually carry about "
            f"**{round(trip.people, -1):.0f} people**. A {line} line train has {train.seats} seats "
            f"and room for about {train.capacity}."
            + (" You may have to let a train go." if trip.level == "packed" else "")
        )
        earlier = better_earlier(path, slot, train)
        if earlier:
            st.markdown(f":material/lightbulb: Leave at **{slot_label(earlier[0])}** and {TIP[earlier[1]]}.")
        elif trip.seat_from:
            st.markdown(f":material/lightbulb: Seats usually free up from **{trip.seat_from}**.")

    st.plotly_chart(
        charts.train_day(list(path[0].per_train), train.seats, train.capacity, slot), config=charts.CONFIG
    )
    st.caption(
        f"People on each train leaving {origin} towards {dest} on a typical "
        f"{DAY_TYPE_NAMES[DAY_TYPES[weekday]]}. "
        "Bookmark this page to come back to your journey."
    )
