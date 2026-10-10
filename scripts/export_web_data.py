"""Write the network data used by the Next.js version of the app (will-i-get-a-seat).

Run from the repo root:  python -m scripts.export_web_data PATH/TO/network.json
"""

import json
import math
import sys
from pathlib import Path

from tube.bikes import load_places
from tube.seats import load_links


def main(out: Path) -> None:
    links = load_links()
    places = load_places()
    data = {
        "stations": {name: [p.naptan_id, p.lat, p.lon] for name, p in sorted(places.items())},
        # day, line, from, to, then people per train for each 15-minute band from 00:00 (null = no trains)
        "links": [
            [lk.day, lk.line, lk.origin, lk.dest, [None if math.isnan(v) else int(v) for v in lk.per_train]]
            for lk in links
        ],
    }
    out.write_text(json.dumps(data, separators=(",", ":")))
    print(f"Wrote {len(data['links'])} links and {len(data['stations'])} stations to {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
