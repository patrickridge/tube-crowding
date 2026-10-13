"""Write random journeys answered by this (tested) Python code, for london-commute's parity test.

The Next.js app has a TypeScript port of the route planner and seat levels; its test checks it gives
the same routes and answers as this version for every case here. Run from the repo root:

    python -m scripts.export_parity_cases PATH/TO/london-commute/test/fixtures/python-journeys.json
"""

import json
import random
import sys
from pathlib import Path

from tube.seats import TRAINS, journey, leg_slot, load_links, overall, plan, stations

CASES = 300
DAYS = ["MON", "TWT", "FRI", "SAT", "SUN"]


def main(out: Path) -> None:
    links = load_links()
    rng = random.Random(2025)  # fixed, so the cases only change when the data does
    by_day = {day: [lk for lk in links if lk.day == day] for day in DAYS}
    names = stations(links)
    cases = []
    while len(cases) < CASES:
        day = rng.choice(DAYS)
        origin, dest = rng.sample(names, 2)
        slot = rng.randrange(20, 92)  # 05:00 to 23:00
        legs = plan(by_day[day], origin, dest, slot)
        if legs is None:
            case = {"day": day, "from": origin, "to": dest, "slot": slot}
            cases.append({**case, "legs": None, "overall": None})
            continue
        trips = [journey(leg.links, leg_slot(slot, leg), TRAINS[leg.line]) for leg in legs]
        cases.append(
            {
                "day": day,
                "from": origin,
                "to": dest,
                "slot": slot,
                "legs": [
                    [leg.line, leg.links[0].origin, leg.links[-1].dest, trip.level]
                    for leg, trip in zip(legs, trips, strict=True)
                ],
                "overall": overall([t.level for t in trips]),
            }
        )
    out.write_text(json.dumps(cases, indent=1) + "\n")
    print(f"Wrote {len(cases)} cases to {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
