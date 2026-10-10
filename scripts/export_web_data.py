"""Write the network data used by the Next.js version of the app (london-commute).

Writes stations.json and one links-<DAY>.json per day type, so a page only downloads the day it
needs. Run from the repo root:  python -m scripts.export_web_data PATH/TO/public/data
"""

import json
import math
import sys
from pathlib import Path

from tube.bikes import load_places
from tube.seats import load_links


def main(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    places = load_places()
    stations = {name: [p.naptan_id, p.lat, p.lon] for name, p in sorted(places.items())}
    (out_dir / "stations.json").write_text(json.dumps(stations, separators=(",", ":")))

    links = load_links()
    for day in sorted({lk.day for lk in links}):
        # line, from, to, then people per train for each 15-minute band from 00:00 (null = no trains)
        rows = [
            [lk.line, lk.origin, lk.dest, [None if math.isnan(v) else int(v) for v in lk.per_train]]
            for lk in links
            if lk.day == day
        ]
        (out_dir / f"links-{day}.json").write_text(json.dumps(rows, separators=(",", ":")))
    print(f"Wrote {len(stations)} stations and {len(links)} links to {out_dir}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
