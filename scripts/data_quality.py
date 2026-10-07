"""Charts and numbers for docs/DATA_QUALITY.md.

Run from the repo root:  python -m scripts.data_quality
Needs a TFL_APP_KEY in .env (it makes about 500 requests) and matplotlib (in requirements-dev.txt).
"""

import csv
import statistics
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt

from tube.client import TflClient, TflError
from tube.config import app_key_from_env
from tube.logic import compare_live, has_dropout, typical_at
from tube.models import SLOTS_PER_DAY

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
BLUE, ORANGE, GREY = "#2a78d6", "#eb6834", "#898781"


def stations() -> list[tuple[str, str]]:
    with (ROOT / "data" / "stations.csv").open() as f:
        return [(r["naptan_id"], r["name"]) for r in csv.DictReader(f)]


def dropout_chart(client: TflClient) -> None:
    week = client.week_profile("940GZZLUOXC")  # Oxford Circus
    hours = [s / 4 for s in range(SLOTS_PER_DAY)]
    fig, ax = plt.subplots(figsize=(7, 3.2))
    ax.plot(hours, [v * 100 for v in week.days["MON"].values], color=GREY, lw=1.5, label="Monday")
    ax.plot(hours, [v * 100 for v in week.days["WED"].values], color=ORANGE, lw=2, label="Wednesday")
    ax.set_xlim(5, 24)
    ax.set_xticks(range(6, 25, 3), [f"{h:02d}:00" for h in range(6, 25, 3)])
    ax.set_xlabel("Time of day")
    ax.set_ylabel("% of TfL baseline")
    ax.set_title("Oxford Circus: typical crowding, as published by TfL", loc="left", fontsize=11)
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(DOCS / "dropout-oxford-circus.png", dpi=150)


def drift_chart(client_key: str | None) -> None:
    def ratio(naptan: str) -> float | None:
        client = TflClient(client_key)
        try:
            week, live = client.week_profile(naptan), client.live(naptan)
        except TflError:
            return None
        if live is None or has_dropout(week.days[live.time_local.strftime("%a").upper()].values):
            return None
        return compare_live(live.value, typical_at(week, live.time_local)).ratio

    with ThreadPoolExecutor(4) as pool:
        ratios = [r for r in pool.map(ratio, [n for n, _ in stations()]) if r and r > 0]
    median = statistics.median(ratios)
    q1, _, q3 = statistics.quantiles(ratios, n=4)
    print(
        f"{len(ratios)} stations at {datetime.now():%a %d %b %H:%M}: "
        f"median live/typical {median:.2f}, middle half {q1:.2f}-{q3:.2f}"
    )

    fig, ax = plt.subplots(figsize=(7, 3.2))
    ax.hist([min(r, 3) for r in ratios], bins=30, color=BLUE)
    ax.axvline(1, color=GREY, ls="--", lw=1)
    ax.axvline(median, color=ORANGE, lw=2)
    ax.text(median, ax.get_ylim()[1] * 0.9, f"  median {median:.2f}", color=ORANGE)
    ax.set_xlabel("Live reading / typical for the same 15 minutes (capped at 3)")
    ax.set_ylabel("Stations")
    ax.set_title(f"Live vs typical across the network, {datetime.now():%a %H:%M}", loc="left", fontsize=11)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(DOCS / "network-drift.png", dpi=150)


if __name__ == "__main__":
    key = app_key_from_env()
    dropout_chart(TflClient(key))
    drift_chart(key)
