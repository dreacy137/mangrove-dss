"""Download OpenStreetMap layers for Iloilo: coastline, rivers, roads, fishponds, built-up areas.

Usage:
    python data_prep/03_osm.py            # all layers
    python data_prep/03_osm.py rivers     # one layer

Source: OpenStreetMap via the Overpass API (free). The study area is split into
tiles so each request stays small. If a tile fails, run the script again;
finished layers are skipped unless you pass --force.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import geopandas as gpd  # noqa: E402
import requests  # noqa: E402
from shapely.geometry import LineString, Polygon  # noqa: E402

from app import config  # noqa: E402

OVERPASS = "https://overpass-api.de/api/interpreter"
# Overpass rejects the default python-requests User-Agent with "406 Not Acceptable".
HEADERS = {"User-Agent": "mangrove-dss/0.1 (mangrove research prototype; https://github.com/dreacy137/mangrove-dss)"}
TILES = 3  # split the bbox into 3 x 3 tiles

QUERIES = {
    # name: (Overpass filter lines, geometry kind)
    "coast": (['way["natural"="coastline"]'], "line"),
    "rivers": (['way["waterway"~"^(river|stream|canal|tidal_channel)$"]'], "line"),
    "roads": (['way["highway"~"^(trunk|primary|secondary|tertiary|unclassified|residential|track|service)$"]'], "line"),
    "fishponds": (['way["landuse"="aquaculture"]', 'way["water"="fishpond"]', 'way["aquaculture"]'], "polygon"),
    "builtup": (['way["landuse"~"^(residential|commercial|industrial|retail)$"]'], "polygon"),
}


def tiles():
    x0, y0, x1, y1 = config.BBOX
    dx, dy = (x1 - x0) / TILES, (y1 - y0) / TILES
    for i in range(TILES):
        for j in range(TILES):
            # Overpass bbox order: south, west, north, east
            yield (y0 + j * dy, x0 + i * dx, y0 + (j + 1) * dy, x0 + (i + 1) * dx)


def fetch(filters, bbox):
    s, w, n, e = bbox
    body = "".join(f"{f}({s},{w},{n},{e});" for f in filters)
    q = f"[out:json][timeout:180];({body});out geom;"
    for attempt in range(4):
        try:
            r = requests.post(OVERPASS, data={"data": q}, headers=HEADERS, timeout=240)
            if r.status_code in (400, 403, 406):
                raise RuntimeError(f"Overpass refused the request ({r.status_code}): {r.text[:300]}")
            if r.status_code in (429, 504):
                raise requests.HTTPError(f"Overpass busy ({r.status_code})")
            r.raise_for_status()
            return r.json()["elements"]
        except (requests.RequestException, ValueError) as ex:
            wait = 10 * (attempt + 1)
            print(f"  retry in {wait}s: {ex}")
            time.sleep(wait)
    raise RuntimeError("Overpass request failed 4 times; try again later.")


def to_geom(el, kind):
    pts = [(p["lon"], p["lat"]) for p in el.get("geometry", [])]
    if kind == "line" and len(pts) >= 2:
        return LineString(pts)
    if kind == "polygon" and len(pts) >= 4 and pts[0] == pts[-1]:
        poly = Polygon(pts)
        return poly if poly.is_valid else poly.buffer(0)
    return None


def build(name, force=False):
    out = config.LAYERS[name]
    if out.exists() and not force:
        print(f"{name}: already exists, skipping ({out.name})")
        return
    filters, kind = QUERIES[name]
    seen, geoms = set(), []
    for k, bbox in enumerate(tiles(), 1):
        print(f"{name}: tile {k}/{TILES * TILES}")
        for el in fetch(filters, bbox):
            if el["id"] in seen:
                continue
            seen.add(el["id"])
            g = to_geom(el, kind)
            if g is not None and not g.is_empty:
                geoms.append(g)
        time.sleep(2)  # be polite to the public server
    config.DATA.mkdir(parents=True, exist_ok=True)
    gpd.GeoDataFrame(geometry=geoms, crs="EPSG:4326").to_file(out, driver="GPKG")
    print(f"{name}: saved {len(geoms):,} features to {out}")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    force = "--force" in sys.argv
    for name in args or QUERIES:
        build(name, force)


if __name__ == "__main__":
    main()
