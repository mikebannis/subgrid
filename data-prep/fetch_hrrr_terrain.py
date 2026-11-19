"""Pull the HRRR model's own surface terrain height (HGT:surface) for the
active region's bbox (see region.py), using byte-range requests against the
.idx sidecar so we avoid downloading the full multi-GB grib2 file.
"""

import sys
from pathlib import Path

import requests
import xarray as xr

from region import get_region

OUT_DIR = Path(__file__).parent / "output"
OUT_DIR.mkdir(exist_ok=True)

GRIB_URL = "https://noaa-hrrr-bdp-pds.s3.amazonaws.com/hrrr.{date}/conus/hrrr.t{hour}z.wrfsfcf00.grib2"

REGION_NAME, BBOX, _, _, _ = get_region()


def find_byte_range(idx_url: str, field: str) -> tuple[int, int | None]:
    idx = requests.get(idx_url, timeout=30).text.strip().splitlines()
    for i, line in enumerate(idx):
        if field in line:
            start = int(line.split(":")[1])
            end = int(idx[i + 1].split(":")[1]) - 1 if i + 1 < len(idx) else None
            return start, end
    raise ValueError(f"field {field!r} not found in idx")


def fetch_message(date: str, hour: str, field: str, out_path: Path) -> None:
    base_url = GRIB_URL.format(date=date, hour=hour)
    start, end = find_byte_range(base_url + ".idx", field)
    range_header = f"bytes={start}-{end}" if end is not None else f"bytes={start}-"
    resp = requests.get(base_url, headers={"Range": range_header}, timeout=60)
    resp.raise_for_status()
    out_path.write_bytes(resp.content)
    print(f"wrote {out_path} ({len(resp.content)} bytes)")


def main() -> None:
    print(f"region: {REGION_NAME} {BBOX}")
    date, hour = (sys.argv[1], sys.argv[2]) if len(sys.argv) > 2 else ("20261118", "00")
    grib_path = OUT_DIR / "hrrr_terrain.grib2"
    fetch_message(date, hour, "HGT:surface:anl", grib_path)

    ds = xr.open_dataset(grib_path, engine="cfgrib")
    print(ds)

    lat = ds.latitude.values
    lon = ds.longitude.values - 360  # cfgrib gives 0-360 longitudes
    elev = ds.orog.values if "orog" in ds else ds[list(ds.data_vars)[0]].values

    mask = (
        (lat >= BBOX["lat_min"])
        & (lat <= BBOX["lat_max"])
        & (lon >= BBOX["lon_min"])
        & (lon <= BBOX["lon_max"])
    )
    rows, cols = mask.nonzero()
    r0, r1 = rows.min(), rows.max() + 1
    c0, c1 = cols.min(), cols.max() + 1

    sub_lat = lat[r0:r1, c0:c1]
    sub_lon = lon[r0:r1, c0:c1]
    sub_elev = elev[r0:r1, c0:c1]

    print(f"subset shape: {sub_elev.shape}, elevation range: {sub_elev.min():.1f}-{sub_elev.max():.1f} m")

    import numpy as np

    np.savez(
        OUT_DIR / "hrrr_terrain_subset.npz",
        lat=sub_lat,
        lon=sub_lon,
        elev=sub_elev,
    )
    print(f"wrote {OUT_DIR / 'hrrr_terrain_subset.npz'}")


if __name__ == "__main__":
    main()
