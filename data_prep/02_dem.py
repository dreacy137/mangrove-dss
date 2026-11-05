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
import rasterio.errors  # noqa: E402
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


def is_complete(path) -> bool:
    """True if every tile of the GeoTIFF can be read (catches cut-off downloads)."""
    try:
        with rasterio.open(path) as src:
            src.read(1)
        return True
    except rasterio.errors.RasterioError:
        return False


def download(url, dest, attempts=3):
    if dest.exists():
        if is_complete(dest):
            return dest
        print(f"{dest.name} is incomplete; downloading it again ...")
        dest.unlink()
    for attempt in range(1, attempts + 1):
        print(f"Downloading {dest.name} ...")
        part = dest.with_suffix(".part")
        with requests.get(url, stream=True, timeout=120) as r:
            if r.status_code == 404:  # all-ocean tile
                return None
            r.raise_for_status()
            expected = int(r.headers.get("Content-Length", 0))
            with open(part, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
        if (not expected or part.stat().st_size == expected) and is_complete(part):
            part.replace(dest)  # only a complete file gets the real name
            return dest
        print(f"  download was cut off (attempt {attempt}/{attempts}), retrying ...")
        part.unlink(missing_ok=True)
    sys.exit(f"Could not download {dest.name} completely. Check your internet connection and run again.")


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
