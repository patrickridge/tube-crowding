"""App shell: page config, navigation between the two pages, and the footer."""

import streamlit as st

from tube import seat_page, station_page

# Small layout fixes for phones: a smaller title, and Day / Time staying on one row so the
# answer shows without scrolling.
PHONE_CSS = """
<style>
@media (max-width: 640px) {
  h1 { font-size: 2rem !important; }
  .st-key-when [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; }
  .st-key-when [data-testid="stColumn"] { min-width: 0 !important; }
}
</style>
"""


def footer() -> None:
    st.divider()
    st.caption(
        "Powered by TfL Open Data. Contains OS data © Crown copyright and database rights 2016 and "
        "Geomni UK Map data © and database rights [2019]. Typical figures describe the past, not a "
        "forecast. A learning project, not affiliated with TfL. "
        "[How it works](https://github.com/patrickridge/tube-crowding#readme)"
    )


def main() -> None:
    st.set_page_config(page_title="Will I get a seat?", page_icon="🚇", layout="centered")
    st.html(PHONE_CSS)
    pages = [
        st.Page(seat_page.page, title="Will I get a seat?", url_path="seat", default=True),
        st.Page(station_page.page, title="Is my station busy?", url_path="station"),
    ]
    st.navigation(pages, position="top").run()
    footer()
