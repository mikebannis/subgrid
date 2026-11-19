"""Single source of truth for which area the pipeline fetches/aligns.

Switch regions by changing ACTIVE below (or setting SUBGRID_REGION), then
rerun fetch_hrrr_terrain.py / fetch_dem.py / fetch_imagery.py / align.py and
copy data-prep/output/*.json + imagery.jpg into site/public/data/.
"""

import os

REGIONS = {
    "golden": {
        "bbox": {"lat_min": 39.64, "lat_max": 39.87, "lon_min": -105.37, "lon_max": -105.07},
        "pins": [
            {"name": "LO LZ", "lat": 39.74992603665513, "lon": -105.2306209586858},
            {"name": "North Launch", "lat": 39.7458888889, "lon": -105.2408055556},
        ],
    },
    "copper_frisco": {
        # Copper Mountain + Frisco + the Tenmile Range between them, Lake Dillon to the east
        "bbox": {"lat_min": 39.47, "lat_max": 39.62, "lon_min": -106.20, "lon_max": -106.02},
        "pins": [],
    },
}

ACTIVE = "golden"  # default if SUBGRID_REGION isn't set


def get_region(name: str | None = None) -> tuple[str, dict, float, float, list[dict]]:
    """:param name: region key from REGIONS, or None to use SUBGRID_REGION / ACTIVE
    :return: (name, bbox, origin_lat, origin_lon, pins)
    """
    name = name or os.environ.get("SUBGRID_REGION", ACTIVE)
    cfg = REGIONS[name]
    bbox = cfg["bbox"]
    origin_lat = (bbox["lat_min"] + bbox["lat_max"]) / 2
    origin_lon = (bbox["lon_min"] + bbox["lon_max"]) / 2
    return name, bbox, origin_lat, origin_lon, cfg["pins"]
