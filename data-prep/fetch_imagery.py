"""Pull ESRI World Imagery aerial tiles (free, no API key) covering the same
Golden, CO bbox as the DEM/HRRR fetches, mosaic them, and crop precisely to
BBOX so align.py can map lon/lat -> UV with a plain linear formula.
"""

import io
import math
from pathlib import Path

import requests
from PIL import Image

OUT_DIR = Path(__file__).parent / "output"
OUT_DIR.mkdir(exist_ok=True)

TILE_URL = "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
ZOOM = 13
TILE_PX = 256

# must match the BBOX in fetch_dem.py / fetch_hrrr_terrain.py
BBOX = {"lat_min": 39.64, "lat_max": 39.87, "lon_min": -105.37, "lon_max": -105.07}


def deg2num(lat: float, lon: float, zoom: int) -> tuple[int, int]:
    lat_rad = math.radians(lat)
    n = 2**zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2.0 * n)
    return x, y


def num2deg(x: int, y: int, zoom: int) -> tuple[float, float]:
    n = 2**zoom
    lon = x / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    return lat, lon


def main() -> None:
    x0, y0 = deg2num(BBOX["lat_max"], BBOX["lon_min"], ZOOM)  # top-left
    x1, y1 = deg2num(BBOX["lat_min"], BBOX["lon_max"], ZOOM)  # bottom-right

    n_cols, n_rows = x1 - x0 + 1, y1 - y0 + 1
    mosaic = Image.new("RGB", (n_cols * TILE_PX, n_rows * TILE_PX))
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            url = TILE_URL.format(z=ZOOM, x=x, y=y)
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            tile = Image.open(io.BytesIO(resp.content)).convert("RGB")
            mosaic.paste(tile, ((x - x0) * TILE_PX, (y - y0) * TILE_PX))
            print(f"fetched tile z{ZOOM}/{x}/{y}")

    # mosaic's exact geographic bounds, from the slippy-tile grid itself
    lat_top, lon_left = num2deg(x0, y0, ZOOM)
    lat_bottom, lon_right = num2deg(x1 + 1, y1 + 1, ZOOM)

    def lonlat_to_px(lon: float, lat: float) -> tuple[int, int]:
        col = (lon - lon_left) / (lon_right - lon_left) * mosaic.width
        row = (lat_top - lat) / (lat_top - lat_bottom) * mosaic.height
        return round(col), round(row)

    left, top = lonlat_to_px(BBOX["lon_min"], BBOX["lat_max"])
    right, bottom = lonlat_to_px(BBOX["lon_max"], BBOX["lat_min"])
    cropped = mosaic.crop((left, top, right, bottom))
    print(f"mosaic {mosaic.size} -> cropped {cropped.size} (should match BBOX exactly)")

    cropped.save(OUT_DIR / "imagery.jpg", quality=90)
    print(f"wrote {OUT_DIR / 'imagery.jpg'}")


if __name__ == "__main__":
    main()
