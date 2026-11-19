"""Project the HRRR terrain subset and DEM subset into one shared local coordinate
frame (meters, origin at the bbox center) so the Three.js viewer can place both
directly without doing any geo math itself.

Uses Web Mercator (EPSG:3857) as an intermediate, scaled by cos(origin_lat) to
correct its latitude-dependent distance inflation back to true ground meters.
This is a flat-earth approximation that's accurate to a few meters over a
~25km region - fine for this prototype, not for anything bigger.
"""

import json
import math
from pathlib import Path

import numpy as np
from pyproj import Transformer

OUT_DIR = Path(__file__).parent / "output"

# must match the BBOX in fetch_dem.py / fetch_hrrr_terrain.py / fetch_imagery.py
BBOX = {"lat_min": 39.64, "lat_max": 39.87, "lon_min": -105.37, "lon_max": -105.07}

ORIGIN_LAT = (BBOX["lat_min"] + BBOX["lat_max"]) / 2
ORIGIN_LON = (BBOX["lon_min"] + BBOX["lon_max"]) / 2
SCALE = math.cos(math.radians(ORIGIN_LAT))  # Web Mercator -> true ground meters

DEM_TARGET_SIZE = 400  # decimate DEM to roughly this many points per side

# 39deg44'45.2"N 105deg14'26.9"W converted to decimal degrees
PINS = [
    {"name": "LO LZ", "lat": 39.74992603665513, "lon": -105.2306209586858},
    {"name": "North Launch", "lat": 39.7458888889, "lon": -105.2408055556},
]

to_webmerc = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)


def lonlat_to_local(lon: np.ndarray, lat: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    x, y = to_webmerc.transform(lon, lat)
    ox, oy = to_webmerc.transform(ORIGIN_LON, ORIGIN_LAT)
    return (np.asarray(x) - ox) * SCALE, (np.asarray(y) - oy) * SCALE


def grid_to_json(local_x: np.ndarray, local_y: np.ndarray, elev: np.ndarray) -> dict:
    """local_x/local_y are 2D but only vary along one axis each (flat-earth
    approx of a geographic grid) - collapse to 1D axes for a smaller payload.
    """
    return {
        "width": elev.shape[1],
        "height": elev.shape[0],
        "x": local_x[0, :].tolist(),
        "y": local_y[:, 0].tolist(),
        "elev": elev.tolist(),
    }


def main() -> None:
    hrrr = np.load(OUT_DIR / "hrrr_terrain_subset.npz")
    hx, hy = lonlat_to_local(hrrr["lon"], hrrr["lat"])
    hrrr_out = grid_to_json(hx, hy, hrrr["elev"].astype(np.float32))
    # actual HRRR cell spacing in our local frame (not assumed to be exactly 3000m)
    hrrr_out["cellSizeX"] = float(np.median(np.diff(hrrr_out["x"])))
    hrrr_out["cellSizeY"] = float(np.median(np.abs(np.diff(hrrr_out["y"]))))
    (OUT_DIR / "hrrr.json").write_text(json.dumps(hrrr_out))
    print(
        f"hrrr.json: {hrrr_out['width']}x{hrrr_out['height']} cells, "
        f"cell size ~{hrrr_out['cellSizeX']:.0f}x{hrrr_out['cellSizeY']:.0f}m"
    )

    dem = np.load(OUT_DIR / "dem_subset.npz")
    step_r = max(1, dem["elev"].shape[0] // DEM_TARGET_SIZE)
    step_c = max(1, dem["elev"].shape[1] // DEM_TARGET_SIZE)
    dem_lat = dem["lat"][::step_r, ::step_c]
    dem_lon = dem["lon"][::step_r, ::step_c]
    dem_elev = dem["elev"][::step_r, ::step_c]
    dx, dy = lonlat_to_local(dem_lon, dem_lat)
    dem_out = grid_to_json(dx, dy, dem_elev.astype(np.float32))
    # UV coords into imagery.jpg, which fetch_imagery.py crops to exactly BBOX
    dem_out["u"] = ((dem_lon[0, :] - BBOX["lon_min"]) / (BBOX["lon_max"] - BBOX["lon_min"])).tolist()
    dem_out["v"] = ((dem_lat[:, 0] - BBOX["lat_min"]) / (BBOX["lat_max"] - BBOX["lat_min"])).tolist()
    (OUT_DIR / "dem.json").write_text(json.dumps(dem_out))
    print(f"dem.json: {dem_out['width']}x{dem_out['height']} points (decimated from {dem['elev'].shape})")

    dem_lon_1d, dem_lat_1d = dem_lon[0, :], dem_lat[:, 0]
    pins_out = []
    for pin in PINS:
        c = int(np.argmin(np.abs(dem_lon_1d - pin["lon"])))
        r = int(np.argmin(np.abs(dem_lat_1d - pin["lat"])))
        px, py = lonlat_to_local(np.array([pin["lon"]]), np.array([pin["lat"]]))
        pins_out.append(
            {
                "name": pin["name"],
                "x": float(px[0]),
                "y": float(py[0]),
                "elev": float(dem_elev[r, c]),
            }
        )
    (OUT_DIR / "pins.json").write_text(json.dumps(pins_out))
    print(f"pins.json: {[p['name'] for p in pins_out]}")


if __name__ == "__main__":
    main()
