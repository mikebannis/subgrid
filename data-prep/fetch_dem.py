"""Pull high-res DEM tiles (AWS Open Data 'Terrain Tiles', USGS-derived in the US,
~10-15m resolution) covering the same Golden, CO bbox as fetch_hrrr_terrain.py,
mosaic them, and crop to the bbox.
"""

import math
from pathlib import Path

import numpy as np
import rasterio
import requests
from rasterio.io import MemoryFile
from rasterio.warp import transform_bounds

OUT_DIR = Path(__file__).parent / "output"
OUT_DIR.mkdir(exist_ok=True)

TILE_URL = "https://s3.amazonaws.com/elevation-tiles-prod/geotiff/{z}/{x}/{y}.tif"
ZOOM = 13

BBOX = {"lat_min": 39.64, "lat_max": 39.87, "lon_min": -105.37, "lon_max": -105.07}


def deg2num(lat: float, lon: float, zoom: int) -> tuple[int, int]:
    lat_rad = math.radians(lat)
    n = 2**zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2.0 * n)
    return x, y


def main() -> None:
    x0, y0 = deg2num(BBOX["lat_max"], BBOX["lon_min"], ZOOM)  # top-left
    x1, y1 = deg2num(BBOX["lat_min"], BBOX["lon_max"], ZOOM)  # bottom-right

    # Fetch each tile and place it directly into a pre-sized mosaic array by its
    # known (x, y) grid position - rasterio.merge() mishandles this dataset's
    # extreme float32 nodata value (overflow warning, silently zeros everything).
    tile_px = None
    crs = None
    tiles = {}
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            url = TILE_URL.format(z=ZOOM, x=x, y=y)
            for attempt in range(3):
                resp = requests.get(url, timeout=30)
                resp.raise_for_status()
                try:
                    ds = MemoryFile(resp.content).open()
                    arr = ds.read(1)
                    break
                except Exception as exc:
                    print(f"  retry {attempt + 1} for z{ZOOM}/{x}/{y}: {exc}")
            else:
                raise RuntimeError(f"tile z{ZOOM}/{x}/{y} kept failing to decode")
            if tile_px is None:
                tile_px = arr.shape
                crs = ds.crs
                top_left_transform = ds.transform
            tiles[(x, y)] = arr
            print(f"fetched tile z{ZOOM}/{x}/{y} ({len(resp.content)} bytes)")

    n_cols, n_rows = x1 - x0 + 1, y1 - y0 + 1
    mosaic = np.zeros((n_rows * tile_px[0], n_cols * tile_px[1]), dtype=np.float32)
    for (x, y), arr in tiles.items():
        r0 = (y - y0) * tile_px[0]
        c0 = (x - x0) * tile_px[1]
        mosaic[r0 : r0 + tile_px[0], c0 : c0 + tile_px[1]] = arr
    # top_left_transform is tile (x0, y0)'s own affine, which already has the
    # correct origin/pixel-size for the whole mosaic's top-left corner.
    transform = top_left_transform
    print(f"mosaic shape: {mosaic.shape}, crs: {crs}")

    # crop to bbox (reprojected into the mosaic's CRS, which is Web Mercator)
    left, bottom, right, top = transform_bounds(
        "EPSG:4326",
        crs,
        BBOX["lon_min"],
        BBOX["lat_min"],
        BBOX["lon_max"],
        BBOX["lat_max"],
    )
    inv = ~transform
    col0, row1 = inv * (left, bottom)
    col1, row0 = inv * (right, top)
    row0, row1, col0, col1 = int(row0), int(row1), int(col0), int(col1)

    cropped = mosaic[row0:row1, col0:col1]
    print(
        f"cropped shape: {cropped.shape}, "
        f"elevation range: {cropped.min():.1f}-{cropped.max():.1f} m"
    )

    # build lon/lat for every pixel center so downstream alignment can share one method with HRRR
    crop_transform = rasterio.Affine(
        transform.a, transform.b, transform.c + col0 * transform.a,
        transform.d, transform.e, transform.f + row0 * transform.e,
    )
    rows, cols = np.indices(cropped.shape)
    xs, ys = crop_transform * (cols + 0.5, rows + 0.5)
    lon, lat = rasterio.warp.transform(crs, "EPSG:4326", xs.ravel(), ys.ravel())
    lon = np.array(lon).reshape(cropped.shape)
    lat = np.array(lat).reshape(cropped.shape)

    np.savez(OUT_DIR / "dem_subset.npz", lat=lat, lon=lon, elev=cropped.astype(np.float32))
    print(f"wrote {OUT_DIR / 'dem_subset.npz'}")


if __name__ == "__main__":
    main()
