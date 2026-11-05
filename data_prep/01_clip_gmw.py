"""Clip the Global Mangrove Watch 2020 extent to the Iloilo study area.

Usage:
    python data_prep/01_clip_gmw.py path/to/gmw_v4112_2020_mng_ext_cntry_info_vec.gpkg

Uses the GMW file you already downloaded. Download page:
https://zenodo.org/communities/globalmangrovewatch
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import geopandas as gpd  # noqa: E402

from app import config  # noqa: E402


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else config.DATA_RAW / "gmw_v4112_2020_mng_ext_cntry_info_vec.gpkg"
    if not src.exists():
        sys.exit(f"GMW file not found: {src}")
    print(f"Reading {src.name} inside {config.BBOX} ...")
    gdf = gpd.read_file(src, bbox=config.BBOX)
    gdf = gdf.to_crs("EPSG:4326")[["geometry"]]
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]
    config.DATA.mkdir(parents=True, exist_ok=True)
    gdf.to_file(config.LAYERS["gmw"], driver="GPKG")
    area_ha = gdf.to_crs(config.METRIC_CRS).area.sum() / 10_000
    print(f"Saved {len(gdf):,} mangrove polygons ({area_ha:,.0f} ha) to {config.LAYERS['gmw']}")


if __name__ == "__main__":
    main()
