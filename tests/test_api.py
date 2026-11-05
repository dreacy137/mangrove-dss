"""End-to-end API test on small synthetic layers (no downloads needed)."""
import io

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from fastapi.testclient import TestClient
from PIL import Image
from rasterio.transform import from_bounds
from shapely.geometry import LineString, box

from app import config, factors


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # A tiny coast near Iloilo City: sea to the south of lat 10.70, land to the north.
    layers = {k: tmp_path / p.name for k, p in config.LAYERS.items()}
    monkeypatch.setattr(config, "LAYERS", layers)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.sqlite3")

    crs = "EPSG:4326"
    gpd.GeoDataFrame(geometry=[LineString([(122.50, 10.70), (122.60, 10.70)])], crs=crs).to_file(layers["coast"])
    gpd.GeoDataFrame(geometry=[LineString([(122.55, 10.70), (122.55, 10.75)])], crs=crs).to_file(layers["rivers"])
    gpd.GeoDataFrame(geometry=[LineString([(122.50, 10.72), (122.60, 10.72)])], crs=crs).to_file(layers["roads"])
    gpd.GeoDataFrame(geometry=[box(122.58, 10.700, 122.59, 10.705)], crs=crs).to_file(layers["gmw"])

    # Elevation rises 0.05 m per 0.001 deg north of the coast; sea is -3 m.
    w, h = 100, 100
    bounds = (122.50, 10.65, 122.60, 10.75)
    lat = np.linspace(10.75, 10.65, h)[:, None].repeat(w, axis=1)
    dem = np.where(lat < 10.70, -3.0, (lat - 10.70) * 50).astype("float32")
    with rasterio.open(layers["dem"], "w", driver="GTiff", width=w, height=h, count=1, dtype="float32",
                       crs=crs, transform=from_bounds(*bounds, w, h), nodata=-9999) as d:
        d.write(dem, 1)

    factors.reload_layers()
    from app.main import app
    from app import main as main_mod
    main_mod._layer_wgs84.cache_clear()
    yield TestClient(app)
    factors.reload_layers()


def test_status(client):
    s = client.get("/api/status").json()
    assert s["layers"]["dem"] and s["layers"]["gmw"]


def test_point_suitable_near_coast(client):
    r = client.get("/api/assess", params={"lat": 10.7055, "lon": 122.52}).json()
    assert r["verdict"] == "suitable", r
    assert r["zone"] in ("seaward", "middle")
    assert r["species"]


def test_point_open_sea(client):
    r = client.get("/api/assess", params={"lat": 10.66, "lon": 122.52}).json()
    assert r["verdict"] == "not_suitable"


def test_inside_mangrove_protected(client):
    r = client.get("/api/assess", params={"lat": 10.7025, "lon": 122.585}).json()
    assert r["verdict"] == "protect"


def test_outside_study_area(client):
    assert client.get("/api/assess", params={"lat": 14.6, "lon": 121.0}).status_code == 400


def test_area_and_sites_ranking(client):
    ring = [[122.51, 10.701], [122.53, 10.701], [122.53, 10.712], [122.51, 10.712], [122.51, 10.701]]
    a = client.post("/api/assess-area", json={"coordinates": ring}).json()
    assert a["sample_points"] > 10
    assert a["verdict"] in ("suitable", "partly_suitable")

    client.post("/api/sites", json={"name": "Area A", "coordinates": ring})
    client.post("/api/sites", json={"name": "Sea", "lat": 10.66, "lon": 122.52})
    sites = client.get("/api/sites").json()
    assert sites[0]["name"] == "Area A"  # suitable sites rank first


def test_corrections(client):
    r = client.post("/api/corrections", json={"lat": 10.71, "lon": 122.52, "expert": "CENRO staff",
                                              "corrected_verdict": "not_suitable", "notes": "Seagrass bed"})
    assert r.status_code == 200
    assert client.get("/api/corrections").json()[0]["notes"] == "Seagrass bed"


def test_layer_geojson(client):
    fc = client.get("/api/layers/gmw", params={"bbox": "122.5,10.65,122.6,10.75"}).json()
    assert len(fc["features"]) == 1


def test_canopy(client):
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    img[:, :] = (120, 100, 80)       # brown mud
    img[:, :60] = (40, 140, 50)      # green canopy on 60%
    buf = io.BytesIO()
    Image.fromarray(img).save(buf, format="PNG")
    r = client.post("/api/canopy", files={"file": ("x.png", buf.getvalue(), "image/png")}).json()
    assert 55 <= r["canopy_cover_pct"] <= 65
