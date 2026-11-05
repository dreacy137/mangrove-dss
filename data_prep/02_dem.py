"""Download Copernicus GLO-30 elevation for Iloilo and clip it to the study area.

Usage:
    python data_prep/02_dem.py

Source: Copernicus DEM GLO-30 (30 m), free on AWS Open Data.
Note: it is a surface model (it includes tree height), so values inside dense
mangroves are too high. It is a stand-in until the drone elevation model exists.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import rasterio  # noqa: E402
import requests  # noqa: E402
from rasterio.merge import merge  # noqa: E402

from app import config  # noqa: E402

URL = ("https://copernicus-dem-30m.s3.amazonaws.com/"
       "Copernicus_DSM_COG_10_{ns}{lat:02d}_00_{ew}{lon:03d}_00_DEM/"
       "Copernicus_DSM_COG_10_{ns}{lat:02d}_00_{ew}{lon:03d}_00_DEM.tif")


def tiles():
    x0, y0, x1, y1 = config.BBOX
    for lat in range(math.floor(y0), math.floor(y1) + 1):
        for lon in range(math.floor(x0), math.floor(x1) + 1):
            yield URL.format(ns="N", lat=lat, ew="E", lon=lon)


def download(url, dest):
    if dest.exists():
        return dest
    print(f"Downloading {dest.name} ...")
    with requests.get(url, stream=True, timeout=120) as r:
        if r.status_code == 404:  # all-ocean tile
            return None
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    return dest


def main():
    raw = config.DATA_RAW / "dem"
    raw.mkdir(parents=True, exist_ok=True)
    paths = [p for p in (download(u, raw / u.rsplit("/", 1)[1]) for u in tiles()) if p]
    srcs = [rasterio.open(p) for p in paths]
    mosaic, transform = merge(srcs, bounds=config.BBOX, nodata=-9999)
    meta = srcs[0].meta.copy()
    meta.update(height=mosaic.shape[1], width=mosaic.shape[2], transform=transform,
                nodata=-9999, compress="deflate", driver="GTiff")
    config.DATA.mkdir(parents=True, exist_ok=True)
    with rasterio.open(config.LAYERS["dem"], "w", **meta) as dst:
        dst.write(mosaic)
    print(f"Saved {config.LAYERS['dem']} ({mosaic.shape[2]} x {mosaic.shape[1]} px)")


if __name__ == "__main__":
    main()
