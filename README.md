# How busy is my tube station?

[![CI](https://github.com/patrickridge/tube-crowding/actions/workflows/ci.yml/badge.svg)](https://github.com/patrickridge/tube-crowding/actions/workflows/ci.yml)

Live app: https://tube-crowding.streamlit.app

A small web app for London commuters. Pick a station and it tells you:

- when it's usually busiest on weekdays, and how early or late you'd need to travel to avoid the worst of it
- whether it's busier or quieter than normal right now
- if you have to arrive by a certain time, whether leaving 15, 30 or 45 minutes earlier is actually worth it, and whether it changes your fare

It uses TfL's open crowding data.

<p>
  <img src="docs/screenshot-desktop.jpg" alt="Station view for King's Cross" width="560">
  <img src="docs/screenshot-mobile.jpg" alt="Trip planner on a phone" width="240">
</p>

**[What's wrong with TfL's crowding data](docs/DATA_QUALITY.md)**: two problems I found while building this, and what the app does about them.

## Why

I moved to London recently. Everyone knows the tube is busy at 8:30, but I couldn't find out how much quieter it gets if I leave a bit earlier, or whether it's worth it at my station. TfL publishes the data needed to answer that, so I built this.

## How it works

**Data.** `GET /crowding/{station}` gives typical crowding for each day of the week in 15-minute bands. `GET /crowding/{station}/Live` gives the latest reading. Both are a fraction of a baseline that TfL sets per station but doesn't document. Because of that, I show everything as a percentage of the station's own busiest 15 minutes of the week, and never compare one station with another. More detail on the API, and what I found while exploring it, is in [docs/DATA_NOTES.md](docs/DATA_NOTES.md).

**Smoothing.** TfL rounds values to 0.01, which makes quiet stations look jagged. I use a 45-minute moving average (each band averaged with its neighbours). The raw values are still drawn on the chart.

**Broken data.** At 17 stations, including Oxford Circus, Stratford and Baker Street, TfL's typical figures for Tuesday to Thursday drop to almost zero right at the morning or evening peak. That isn't believable, and it would make the app recommend the worst time to travel. If a band falls under 30% of the busy times either side of it, I treat that day as broken, replace it with the average of the station's other weekdays, and say so on the page. Live readings more than 2.5x or less than 0.4x normal are flagged as a likely glitch instead of being reported.

**Weekday summary.** I average Monday to Friday, find the busiest band in the morning (04:00–12:00) and the evening, then find the nearest times either side where it's at least 30% quieter.

**Trip planner.** Your latest departure is your arrival time minus the journey time. Each 15-minute slot between that and how early you're willing to leave gets compared with leaving at the last minute. The app recommends the quietest slot. If two slots are equally quiet, it picks the later one, so you don't leave early for nothing. Each slot is also marked peak or off-peak: TfL charges peak fares Monday to Friday, 06:30–09:30 and 16:00–19:00.

**Live vs usual.** I compare the live reading with the typical value for the same 15-minute band. While building this I noticed that live readings were above typical at almost every station. On the first evening, the median across 42 stations was 1.27x, so on the raw numbers everywhere looked "busier than usual". To correct for that, the app checks 16 big stations, takes the median live/typical ratio, and divides it out. A station is only called busier than usual if it's busier than the rest of the network right now. Anything within 10% counts as normal. That threshold is my own choice, not something fitted to data.

## Limitations

- Typical patterns are averages from the past. They don't know about strikes, events or the weather.
- TfL measures people entering and leaving the station, not how full the trains are. It can't tell you if you'll get a seat.
- Numbers can't be compared between stations.
- 17 of the 270 tube stations have no data (e.g. Arsenal, Pimlico, Monument). There's no crowding data for the Elizabeth line, Overground or DLR.
- Some stations' data is odd in ways I can't fix. Waterloo is the main one.
- The fare flag ignores public holidays, and the rule that evening trips into Zone 1 from outside it are off-peak.

## Running it locally

Needs Python 3.11 or newer.

```bash
git clone https://github.com/patrickridge/tube-crowding.git
cd tube-crowding
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env    # optional: add a free key from api-portal.tfl.gov.uk
streamlit run app.py
```

It works without a key, but TfL's anonymous rate limit is low.

## Tests

```bash
pytest
ruff check .
```

The tests don't touch the network. The API client is tested against real responses saved in `tests/fixtures/`, including the awkward ones (unknown station, all-zero data, duplicated bands). GitHub Actions runs the tests and the linter on every push.

## Code layout

```
app.py              Streamlit page
tube/client.py      TfL API calls, and parsing the JSON into the types in models.py
tube/models.py      Station, DayProfile, WeekProfile, LiveReading
tube/logic.py       Smoothing, peaks, trip planner, live vs usual (no Streamlit, no network)
tube/charts.py      Plotly charts
tube/stations.py    Loads data/stations.csv (rebuilt by scripts/build_stations.py)
tests/              pytest
```

## What I'd do next

1. A job already saves live readings for 30 stations every 15 minutes (on the `data` branch). With a few weeks of that I can set the "busier than usual" threshold from data.
2. Use that history to forecast the next hour, e.g. "likely to get busier than usual by 08:15".
3. Add both ends of a journey, so the planner also considers how busy your destination is when you arrive.
4. Show line status next to the live reading, to explain unusual numbers.

## Data and licence

Powered by TfL Open Data. Contains OS data © Crown copyright and database rights 2016 and Geomni UK Map data © and database rights [2019]. Used under TfL's [transport data terms](https://tfl.gov.uk/corporate/terms-and-conditions/transport-data-service). Data comes only from the official API. This is a personal learning project and isn't affiliated with TfL.
