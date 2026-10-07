"""Page: will I get a seat on my train?"""

from __future__ import annotations

from datetime import datetime, timedelta

import streamlit as st

from tube import charts
from tube.logic import time_to_slot
from tube.models import slot_label
from tube.seats import TRAINS, Link, better_earlier, journey, load_links, route, stations

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
DEFAULT = {"line": "Northern", "from": "Balham", "to": "Bank and Monument", "time": "08:30"}


@st.cache_data(show_spinner=False)
def get_links() -> list[Link]:
    return load_links()


def _choose(label: str, options: list[str], key: str, fallback: str, container=st) -> str:
    """Selectbox that starts from the URL (so a journey can be bookmarked)."""
    wanted = st.query_params.get(key, DEFAULT[key])
    start = wanted if wanted in options else fallback
    return container.selectbox(label, options, index=options.index(start))


def _time_from_url() -> datetime:
    try:
        return datetime.strptime(st.query_params.get("time", DEFAULT["time"]), "%H:%M")
    except ValueError:
        return datetime.strptime(DEFAULT["time"], "%H:%M")


def page() -> None:
    st.title("Will I get a seat?")
    st.caption("How full trains usually are on a weekday, from TfL's 2025 passenger counts.")

    links = get_links()
    lines = sorted(TRAINS)
    line = _choose("Line", lines, "line", DEFAULT["line"])
    names = stations(links, line)
    left, right = st.columns(2)
    origin = _choose("From", names, "from", names[0], left)
    dest = _choose("To", names, "to", names[-1], right)
    when = st.time_input("Leaving at", _time_from_url().time(), step=timedelta(minutes=15))
    st.query_params.update({"line": line, "from": origin, "to": dest, "time": f"{when:%H:%M}"})

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
        f"People on each train leaving {origin} towards {dest} on a typical Tuesday to Thursday. "
        "Bookmark this page to come back to your journey."
    )
