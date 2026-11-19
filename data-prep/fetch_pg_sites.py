"""Pull paragliding launch/landing sites for the active region's bbox from the
free ParaglidingEarth API (CC BY-SA 3.0 - https://www.paragliding.earth/api/),
which is one of paraglidingmap.com's own underlying data sources (it has no
public API of its own). No API key required.
"""

import json
from pathlib import Path

import requests

from region import get_region

OUT_DIR = Path(__file__).parent / "output"
OUT_DIR.mkdir(exist_ok=True)

API_URL = "https://www.paraglidingearth.com/api/geojson/getBoundingBoxSites.php"


def main() -> None:
    region_name, bbox, _, _, _ = get_region()
    print(f"region: {region_name} {bbox}")

    resp = requests.get(
        API_URL,
        params={
            "north": bbox["lat_max"],
            "south": bbox["lat_min"],
            "east": bbox["lon_max"],
            "west": bbox["lon_min"],
            "style": "detailled",
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    sites = []
    for feature in data.get("features", []):
        props = feature.get("properties", {})
        lon, lat = feature["geometry"]["coordinates"]
        sites.append(
            {
                "name": props.get("name", "?"),
                "type": "launch",
                "lat": lat,
                "lon": lon,
                "altitude": props.get("takeoff_altitude"),
            }
        )
        landing = props.get("landing")
        if landing and landing.get("landing_lat"):
            sites.append(
                {
                    "name": landing.get("landing_name") or f"{props.get('name', '?')} LZ",
                    "type": "landing",
                    "lat": float(landing["landing_lat"]),
                    "lon": float(landing["landing_lng"]),
                    "altitude": landing.get("landing_altitude"),
                }
            )

    (OUT_DIR / "pg_sites_raw.json").write_text(json.dumps(sites, indent=2))
    print(f"wrote {len(sites)} sites to {OUT_DIR / 'pg_sites_raw.json'}")


if __name__ == "__main__":
    main()
