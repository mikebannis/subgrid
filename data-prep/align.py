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

from region import get_region

OUT_DIR = Path(__file__).parent / "output"

REGION_NAME, BBOX, ORIGIN_LAT, ORIGIN_LON, PINS = get_region()
SCALE = math.cos(math.radians(ORIGIN_LAT))  # Web Mercator -> true ground meters

DEM_TARGET_SIZE = 400  # decimate DEM to roughly this many points per side

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
    print(f"region: {REGION_NAME} {BBOX}")
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

    def sample_elev(lat: float, lon: float) -> float:
        c = int(np.argmin(np.abs(dem_lon_1d - lon)))
        r = int(np.argmin(np.abs(dem_lat_1d - lat)))
        return float(dem_elev[r, c])

    pins_out = []
    for pin in PINS:
        px, py = lonlat_to_local(np.array([pin["lon"]]), np.array([pin["lat"]]))
        pins_out.append(
            {
                "name": pin["name"],
                "x": float(px[0]),
                "y": float(py[0]),
                "elev": sample_elev(pin["lat"], pin["lon"]),
            }
        )
    (OUT_DIR / "pins.json").write_text(json.dumps(pins_out))
    print(f"pins.json: {[p['name'] for p in pins_out]}")

    highways_raw_path = OUT_DIR / "highways_raw.json"
    if highways_raw_path.exists():
        raw_ways = json.loads(highways_raw_path.read_text())
        ways_out = []
        by_label: dict[str, list[dict]] = {}
        for way in raw_ways:
            lats = np.array([p[0] for p in way["points"]])
            lons = np.array([p[1] for p in way["points"]])
            wx, wy = lonlat_to_local(lons, lats)
            way_entry = {
                "label": way["label"],
                "x": wx.tolist(),
                "y": wy.tolist(),
                "elev": [sample_elev(lat, lon) for lat, lon in zip(lats, lons)],
            }
            ways_out.append(way_entry)
            by_label.setdefault(way["label"], []).append(way_entry)

        # one label per distinct ref, placed at the midpoint of its longest segment
        labels_out = []
        for label, segs in by_label.items():
            longest = max(segs, key=lambda s: len(s["x"]))
            mid = len(longest["x"]) // 2
            labels_out.append(
                {
                    "label": label,
                    "x": longest["x"][mid],
                    "y": longest["y"][mid],
                    "elev": longest["elev"][mid],
                }
            )

        (OUT_DIR / "highways.json").write_text(json.dumps({"ways": ways_out, "labels": labels_out}))
        print(f"highways.json: {len(ways_out)} segments, {len(labels_out)} labels")
    else:
        print("no highways_raw.json found, skipping (run fetch_highways.py first)")


if __name__ == "__main__":
    main()
