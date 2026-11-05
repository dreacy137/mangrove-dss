"""FastAPI backend for the mangrove decision support system.

Run:  uvicorn app.main:app --reload   then open http://127.0.0.1:8000
"""
from __future__ import annotations

from collections import Counter
from functools import lru_cache
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pyproj import Geod
from shapely.geometry import Point, Polygon, box, mapping

from . import canopy, config, db, factors, rules

app = FastAPI(title="Mangrove Decision Support System")
STATIC = config.ROOT / "app" / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")

_geod = Geod(ellps="WGS84")
MAX_AREA_POINTS = 40


def in_study_area(lat, lon):
    x0, y0, x1, y1 = config.BBOX
    return x0 <= lon <= x1 and y0 <= lat <= y1


def assess_point(lat: float, lon: float) -> dict:
    if not in_study_area(lat, lon):
        raise HTTPException(400, "Outside the Iloilo study area.")
    return rules.assess(factors.measure(lat, lon))


def assess_polygon(coords: list) -> dict:
    """coords: [[lon, lat], ...]. Samples a grid inside the area and combines the results."""
    poly = Polygon(coords)
    if not poly.is_valid or poly.area == 0:
        raise HTTPException(400, "The drawn area is not a valid polygon.")
    c = poly.centroid
    if not in_study_area(c.y, c.x):
        raise HTTPException(400, "Outside the Iloilo study area.")

    area_ha = abs(_geod.geometry_area_perimeter(poly)[0]) / 10_000
    minx, miny, maxx, maxy = poly.bounds
    pts = []
    n = 2
    while True:  # grow the grid until it has enough points inside the polygon
        pts = [
            (minx + (maxx - minx) * (i + 0.5) / n, miny + (maxy - miny) * (j + 0.5) / n)
            for i in range(n) for j in range(n)
        ]
        pts = [p for p in pts if poly.contains(Point(p))]
        if len(pts) >= MAX_AREA_POINTS * 0.6 or n >= 12:
            break
        n += 1
    pts = pts[:MAX_AREA_POINTS] or [(c.x, c.y)]

    results = [rules.assess(factors.measure(lat, lon)) for lon, lat in pts]
    verdicts = Counter(r["verdict"] for r in results)
    suitable = [r for r in results if r["verdict"] == "suitable"]
    share = len(suitable) / len(results)

    species_scores: dict = {}
    for r in suitable:
        for s in r["species"]:
            species_scores.setdefault(s["name"], {"local": s["local"], "scores": []})["scores"].append(s["score"])
    species = sorted(
        (
            {"name": k, "local": v["local"],
             "score": round(sum(v["scores"]) / len(suitable)),  # averaged over all suitable points
             "share_pct": round(100 * len(v["scores"]) / len(suitable)),
             "reasons": [f"Recommended at {len(v['scores'])} of {len(suitable)} suitable sample points."]}
            for k, v in species_scores.items()
        ),
        key=lambda s: s["score"], reverse=True,
    )[:5]

    zones = Counter(r["zone"] for r in suitable if r["zone"])
    if share >= 0.5:
        verdict = "suitable"
    elif verdicts.get("protect", 0) / len(results) >= 0.5:
        verdict = "protect"
    elif suitable:
        verdict = "partly_suitable"
    elif verdicts.get("uncertain", 0):
        verdict = "uncertain"  # some points could not be judged, so "not suitable" would overstate it
    else:
        verdict = "not_suitable"

    pr_scores = [r["priority"]["score"] for r in suitable if r.get("priority")]
    pr = round(share * (sum(pr_scores) / len(pr_scores))) if pr_scores else 0
    reasons = [f"{round(share * 100)}% of {len(results)} sample points are suitable for planting."]
    if zones:
        reasons.append("Zones: " + ", ".join(f"{z} {round(100 * n / len(suitable))}%" for z, n in zones.most_common()))
    other = Counter(rs for r in results if r["verdict"] != "suitable" for rs in r["reasons"][:1])
    for why, n in other.most_common(3):
        reasons.append(f"{n} point(s): {why}")
    cautions = sorted({c for r in results for c in r.get("cautions", [])})

    return {
        "verdict": verdict,
        "area_ha": round(area_ha, 2),
        "sample_points": len(results),
        "suitable_share_pct": round(share * 100),
        "verdict_counts": dict(verdicts),
        "zone": zones.most_common(1)[0][0] if zones else None,
        "zone_label": None,
        "reasons": reasons,
        "cautions": cautions,
        "species": species,
        "priority": None if not suitable else {
            "score": pr, "level": "High" if pr >= 70 else "Medium" if pr >= 40 else "Low",
            "parts": {"suitable_share": {"points": round(share * 100),
                                         "why": "Share of the area that is suitable, times the mean point score."}}},
        "confidence": min((r["confidence"] for r in results), key=["low", "medium", "high"].index),
        "missing_layers": sorted({m for r in results for m in r["missing_layers"]}),
        "points": [{"lon": lon, "lat": lat, "verdict": r["verdict"]} for (lon, lat), r in zip(pts, results)],
    }


# ------------------------------------------------------------------ pages

@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/status")
def status():
    return {
        "center": config.MAP_CENTER,
        "bbox": config.BBOX,
        "layers": {k: p.exists() for k, p in config.LAYERS.items()},
    }


# ------------------------------------------------------------------ assessment

@app.get("/api/assess")
def assess(lat: float, lon: float):
    return assess_point(lat, lon)


class AreaIn(BaseModel):
    coordinates: list = Field(..., description="Polygon ring as [[lon, lat], ...]")


@app.post("/api/assess-area")
def assess_area(body: AreaIn):
    return assess_polygon(body.coordinates)


# ------------------------------------------------------------------ sites

class SiteIn(BaseModel):
    name: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    coordinates: Optional[list] = None


@app.post("/api/sites")
def add_site(body: SiteIn):
    if body.coordinates:
        result = assess_polygon(body.coordinates)
        c = Polygon(body.coordinates).centroid
        lat, lon = c.y, c.x
    elif body.lat is not None and body.lon is not None:
        result = assess_point(body.lat, body.lon)
        lat, lon = body.lat, body.lon
    else:
        raise HTTPException(400, "Give a point (lat, lon) or an area (coordinates).")
    site_id = db.add_site(body.name, lat, lon, body.coordinates, result)
    return {"id": site_id, "result": result}


@app.get("/api/sites")
def list_sites():
    return db.list_sites()


@app.delete("/api/sites/{site_id}")
def delete_site(site_id: int):
    db.delete_site(site_id)
    return {"ok": True}


# ------------------------------------------------------------------ expert corrections

class CorrectionIn(BaseModel):
    lat: float
    lon: float
    expert: str
    site_id: Optional[int] = None
    original_verdict: Optional[str] = None
    original_species: Optional[str] = None
    corrected_verdict: Optional[str] = None
    corrected_species: Optional[str] = None
    notes: Optional[str] = None


@app.post("/api/corrections")
def add_correction(body: CorrectionIn):
    if not body.expert.strip():
        raise HTTPException(400, "Expert name is required.")
    return {"id": db.add_correction(body.model_dump())}


@app.get("/api/corrections")
def list_corrections():
    return db.list_corrections()


# ------------------------------------------------------------------ Module 1: canopy

@app.post("/api/canopy")
async def canopy_endpoint(file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(413, "Image is larger than 25 MB.")
    try:
        return canopy.canopy_cover(data)
    except Exception as e:  # unreadable image
        raise HTTPException(400, f"Could not read the image: {e}")


# ------------------------------------------------------------------ map layers

@lru_cache(maxsize=None)
def _layer_wgs84(name):
    import geopandas as gpd

    path = config.LAYERS[name]
    if not path.exists():
        return None
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    return gdf.to_crs("EPSG:4326")[["geometry"]]


@app.get("/api/layers/{name}")
def layer(name: str, bbox: str):
    """GeoJSON of a vector layer inside bbox=minLon,minLat,maxLon,maxLat (map view)."""
    if name not in ("gmw", "fishponds", "rivers", "coast"):
        raise HTTPException(404, "Unknown layer.")
    gdf = _layer_wgs84(name)
    if gdf is None:
        return JSONResponse({"type": "FeatureCollection", "features": [], "missing": True})
    try:
        x0, y0, x1, y1 = (float(v) for v in bbox.split(","))
    except ValueError:
        raise HTTPException(400, "bbox must be minLon,minLat,maxLon,maxLat")
    if (x1 - x0) * (y1 - y0) > 0.25:
        return JSONResponse({"type": "FeatureCollection", "features": [], "too_large": True})
    sub = gdf[gdf.intersects(box(x0, y0, x1, y1))].head(5000)
    tol = max(x1 - x0, y1 - y0) / 3000
    feats = [{"type": "Feature", "properties": {}, "geometry": mapping(g.simplify(tol))} for g in sub.geometry]
    return {"type": "FeatureCollection", "features": feats}
