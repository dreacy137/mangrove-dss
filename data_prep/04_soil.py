"""Download SoilGrids topsoil clay content (0-5 cm) for Iloilo.

Usage:
    python data_prep/04_soil.py

Source: ISRIC SoilGrids 2.0 (250 m), free WCS service. Values are converted
from g/kg to percent. At 250 m this is only a general guide; confirm soil type
in the field at each candidate site.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np  # noqa: E402
import rasterio  # noqa: E402
import requests  # noqa: E402

from app import config  # noqa: E402

WCS = "https://maps.isric.org/mapserv?map=/map/clay.map"


def main():
    x0, y0, x1, y1 = config.BBOX
    params = [
        ("SERVICE", "WCS"), ("VERSION", "2.0.1"), ("REQUEST", "GetCoverage"),
        ("COVERAGEID", "clay_0-5cm_mean"), ("FORMAT", "image/tiff"),
        ("SUBSET", f"long({x0},{x1})"), ("SUBSET", f"lat({y0},{y1})"),
        ("SUBSETTINGCRS", "http://www.opengis.net/def/crs/EPSG/0/4326"),
        ("OUTPUTCRS", "http://www.opengis.net/def/crs/EPSG/0/4326"),
    ]
    print("Downloading SoilGrids clay ...")
    r = requests.get(WCS, params=params, timeout=300)
    r.raise_for_status()
    if not r.content.startswith((b"II*", b"MM\x00*")):
        sys.exit(f"SoilGrids did not return a GeoTIFF:\n{r.text[:500]}")
    raw = config.DATA_RAW / "soil_clay_raw.tif"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_bytes(r.content)

    with rasterio.open(raw) as src:
        data = src.read(1).astype("float32")
        nodata = src.nodata
        meta = src.meta.copy()
    mask = (data == nodata) if nodata is not None else np.zeros_like(data, bool)
    data = data / 10.0  # g/kg -> %
    data[mask | (data <= 0)] = -9999
    meta.update(dtype="float32", nodata=-9999, compress="deflate")
    config.DATA.mkdir(parents=True, exist_ok=True)
    with rasterio.open(config.LAYERS["clay"], "w", **meta) as dst:
        dst.write(data, 1)
    print(f"Saved {config.LAYERS['clay']}")


if __name__ == "__main__":
    main()
