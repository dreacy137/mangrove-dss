"""Reads the processed map layers and measures site factors at a point.

Every layer is optional. A missing layer gives None for its factors, and the
decision engine lowers its confidence and says which data was missing.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, asdict, field
from functools import lru_cache
from typing import Optional

from pyproj import Transformer
from shapely.geometry import Point
from shapely.strtree import STRtree

from . import config

_to_metric = Transformer.from_crs("EPSG:4326", config.METRIC_CRS, always_xy=True)


@dataclass
class SiteFactors:
    lat: float
    lon: float
    elevation_m: Optional[float] = None       # metres above mean sea level
    dist_coast_m: Optional[float] = None
    dist_river_m: Optional[float] = None
    dist_road_m: Optional[float] = None
    in_mangrove: Optional[bool] = None        # inside GMW 2020 extent
    dist_mangrove_m: Optional[float] = None   # to nearest GMW 2020 mangrove
    in_fishpond: Optional[bool] = None
    in_builtup: Optional[bool] = None
    clay_pct: Optional[float] = None
    ndvi: Optional[float] = None
    ndvi_change: Optional[float] = None       # latest minus earliest year
    nearby_species: dict = field(default_factory=dict)  # species -> count within NEARBY_SPECIES
    missing: list = field(default_factory=list)          # layers that were not available

    def to_dict(self):
        return asdict(self)


# ---------------------------------------------------------------- loaders

class VectorLayer:
    """A vector layer in metric coordinates with a spatial index."""

    def __init__(self, path):
        import geopandas as gpd

        gdf = gpd.read_file(path)
        if gdf.crs is None:
            gdf = gdf.set_crs("EPSG:4326")
        gdf = gdf.to_crs(config.METRIC_CRS)
        self.geoms = [g for g in gdf.geometry if g is not None and not g.is_empty]
        self.tree = STRtree(self.geoms)

    def distance(self, pt: Point) -> Optional[float]:
        if not self.geoms:
            return None
        idx = self.tree.nearest(pt)
        return float(self.geoms[idx].distance(pt))

    def contains(self, pt: Point) -> bool:
        for idx in self.tree.query(pt, predicate="intersects"):
            return True
        return False


class RasterLayer:
    def __init__(self, path):
        import rasterio

        self.ds = rasterio.open(path)

    def sample(self, lon: float, lat: float) -> Optional[float]:
        b = self.ds.bounds
        if not (b.left <= lon <= b.right and b.bottom <= lat <= b.top):
            return None
        val = next(self.ds.sample([(lon, lat)]))[0]
        nodata = self.ds.nodata
        if nodata is not None and val == nodata:
            return None
        if val != val:  # NaN
            return None
        return float(val)


@lru_cache(maxsize=None)
def vector(name: str) -> Optional[VectorLayer]:
    path = config.LAYERS[name]
    return VectorLayer(path) if path.exists() else None


@lru_cache(maxsize=None)
def raster(name: str) -> Optional[RasterLayer]:
    path = config.LAYERS[name]
    return RasterLayer(path) if path.exists() else None


@lru_cache(maxsize=None)
def observations() -> list:
    """Species points: CSV with columns species, lat, lon (from field work or Module 1)."""
    path = config.LAYERS["observations"]
    if not path.exists():
        return []
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                x, y = _to_metric.transform(float(r["lon"]), float(r["lat"]))
                rows.append((r["species"].strip(), Point(x, y)))
            except (KeyError, ValueError):
                continue
    return rows


def reload_layers():
    """Forget cached layers, e.g. after running a data_prep script."""
    vector.cache_clear()
    raster.cache_clear()
    observations.cache_clear()


# ---------------------------------------------------------------- measuring

def measure(lat: float, lon: float) -> SiteFactors:
    f = SiteFactors(lat=lat, lon=lon)
    x, y = _to_metric.transform(lon, lat)
    pt = Point(x, y)

    def vdist(name):
        layer = vector(name)
        if layer is None:
            f.missing.append(name)
            return None
        return layer.distance(pt)

    def vin(name):
        layer = vector(name)
        if layer is None:
            f.missing.append(name)
            return None
        return layer.contains(pt)

    def rval(name):
        layer = raster(name)
        if layer is None:
            f.missing.append(name)
            return None
        return layer.sample(lon, lat)

    f.elevation_m = rval("dem")
    f.dist_coast_m = vdist("coast")
    f.dist_river_m = vdist("rivers")
    f.dist_road_m = vdist("roads")
    gmw = vector("gmw")
    if gmw is None:
        f.missing.append("gmw")
    else:
        f.in_mangrove = gmw.contains(pt)
        f.dist_mangrove_m = 0.0 if f.in_mangrove else gmw.distance(pt)
    f.in_fishpond = vin("fishponds")
    f.in_builtup = vin("builtup")
    f.clay_pct = rval("clay")
    f.ndvi = rval("ndvi")
    f.ndvi_change = rval("ndvi_change")

    obs = observations()
    if not obs:
        f.missing.append("observations")
    for sp, opt in obs:
        if opt.distance(pt) <= config.NEARBY_SPECIES:
            f.nearby_species[sp] = f.nearby_species.get(sp, 0) + 1
    return f
