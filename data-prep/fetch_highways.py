"""Pull major highway geometries (motorway/trunk/primary) for the active
region's bbox from OpenStreetMap's Overpass API (free, no key). Saves raw
lat/lon way geometries + tags; align.py does the elevation sampling and
local-meters projection, same as everything else.
"""

import json
import time
from pathlib import Path

import requests

from region import get_region

OUT_DIR = Path(__file__).parent / "output"
OUT_DIR.mkdir(exist_ok=True)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def main() -> None:
    region_name, bbox, _, _, _ = get_region()
    print(f"region: {region_name} {bbox}")

    # ["ref"] requires a route number (I-70, US 6, CO 93, ...) - this is what
    # excludes plain arterial streets that OSM also tags highway=primary
    query = f"""
    [out:json][timeout:30];
    (
      way["highway"~"^(motorway|trunk|primary)$"]["ref"]
        ({bbox["lat_min"]},{bbox["lon_min"]},{bbox["lat_max"]},{bbox["lon_max"]});
    );
    out geom;
    """
    headers = {"User-Agent": "subgrid-dataprep/0.1 (terrain visualization prototype)"}
    # the public Overpass instance is frequently overloaded (502s transiently)
    for attempt in range(5):
        resp = requests.post(OVERPASS_URL, data={"data": query}, headers=headers, timeout=60)
        if resp.ok:
            break
        print(f"  attempt {attempt + 1} got {resp.status_code}, retrying...")
        time.sleep(5)
    resp.raise_for_status()
    elements = resp.json().get("elements", [])

    ways = []
    for el in elements:
        if el.get("type") != "way" or "geometry" not in el:
            continue
        tags = el.get("tags", {})
        label = tags.get("ref") or tags.get("name") or "unnamed"
        ways.append(
            {
                "label": label,
                "highway": tags.get("highway"),
                "points": [[pt["lat"], pt["lon"]] for pt in el["geometry"]],
            }
        )

    (OUT_DIR / "highways_raw.json").write_text(json.dumps(ways))
    labels = sorted({w["label"] for w in ways})
    print(f"wrote {len(ways)} way segments ({len(labels)} distinct labels: {labels})")


if __name__ == "__main__":
    main()
