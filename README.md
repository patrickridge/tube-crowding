# Will I get a seat?

[![CI](https://github.com/patrickridge/tube-crowding/actions/workflows/ci.yml/badge.svg)](https://github.com/patrickridge/tube-crowding/actions/workflows/ci.yml)

Live app: https://tube-crowding.streamlit.app

Pick your line, where you're going from and to, and when you leave. The app tells you whether you'll probably get a seat, and if not, whether leaving a little earlier helps or where seats free up on the way.

<p>
  <img src="docs/screenshot-desktop.jpg" alt="Seat finder" width="560">
  <img src="docs/screenshot-mobile.jpg" alt="Seat finder on a phone" width="240">
</p>

A second page shows whether a station is busier than usual right now.

## Why

Everyone knows the tube is busy at 8:30. What I actually wanted to know when I moved to London was whether I'd get a seat, and whether it was worth leaving 15 minutes earlier for one. TfL publishes enough data to answer that, but not in a form anyone would read before their commute.

## How it works

**Data.** TfL's NUMBAT dataset (2025) estimates, for a typical Monday, Tuesday to Thursday, Friday, Saturday and Sunday, how many people travel on every stretch of line in each 15-minute band, and how many trains run. Dividing one by the other gives the average number of people on each train. `scripts/build_links.py` turns TfL's spreadsheets into `data/links.csv`, which the app ships with, so the seat finder needs no API calls.

**Your journey.** Each line is a set of one-way links between stations. A breadth-first search finds the path from your station to your destination, which also works out the direction for you.

**Seat or not.** I compare people on the train as it leaves your station with the train's seats and total capacity (from TfL's rolling stock information sheets):

| Average people per train | Answer |
|---|---|
| under 80% of seats | You'll probably get a seat |
| 80–110% of seats | You might get a seat |
| over 110% of seats | You'll probably stand |
| over 90% of total capacity | Very crowded |

These cut-offs are my own judgement. The figures are averages over the whole train, and the ends of a train are usually emptier than the middle, so "probably a seat" needs some slack.

**Tips.** If leaving 15 or 30 minutes earlier gives a better answer, the app says so. Otherwise, if you'll stand at first, it tells you the first station after which a seat is likely.

**Station page.** This uses TfL's live crowding API, compared with the station's usual pattern. More on that, and on problems I found in TfL's data, in [docs/DATA_QUALITY.md](docs/DATA_QUALITY.md).

## Limitations

- Typical days only. It doesn't know about strikes, delays or events.
- Averages over the whole train. Some carriages will be fuller than others.
- The same 15-minute band is used for the whole trip.
- Underground and Elizabeth line only. Metropolitan line fast trains aren't included.
- Piccadilly line figures assume the old trains; the new ones have a different layout.

## Running it locally

Needs Python 3.11 or newer.

```bash
git clone https://github.com/patrickridge/tube-crowding.git
cd tube-crowding
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env    # optional: a free key from api-portal.tfl.gov.uk, for the station page
streamlit run app.py
```

## Tests

```bash
pytest
ruff check .
```

The tests don't touch the network. GitHub Actions runs them and the linter on every push.

## Code layout

```
app.py                  Entry point
tube/ui.py              Navigation and footer
tube/seat_page.py       "Will I get a seat?" page
tube/seats.py           Routes, seat levels, tips (no Streamlit)
tube/station_page.py    "Is my station busy?" page
tube/client.py          TfL API client
tube/logic.py           Smoothing, live vs usual, data repair (no Streamlit)
tube/charts.py          Plotly charts
scripts/                Building the data files, the data quality charts, the live logger
tests/                  pytest
```

## What I'd do next

1. The Overground and DLR (TfL publishes them in the same data).
2. A rent vs commute tab: what a cheaper flat further out really costs once you add fares and travel time.
3. A morning alert for your saved journey when the line is disrupted.
4. Use the live readings the logger is collecting to check how far typical days are from real ones.

## Data and licence

Powered by TfL Open Data. Contains OS data © Crown copyright and database rights 2016 and Geomni UK Map data © and database rights [2019]. Used under TfL's [transport data terms](https://tfl.gov.uk/corporate/terms-and-conditions/transport-data-service). Train capacities from TfL's rolling stock information sheets. A personal learning project, not affiliated with TfL.
