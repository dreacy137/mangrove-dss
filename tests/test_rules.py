import pytest

from app import config
from app.factors import SiteFactors
from app.rules import assess, rank_species, zone_of


def use_profile(monkeypatch, name):
    p = config.ELEVATION_PROFILES[name]
    monkeypatch.setattr(config, "ELEVATION_SOURCE", name)
    monkeypatch.setattr(config, "ELEV_TOO_LOW", p["too_low"])
    monkeypatch.setattr(config, "ELEV_WATER", p["water_at_or_below"])
    monkeypatch.setattr(config, "ELEV_SEAWARD_MAX", p["seaward_max"])
    monkeypatch.setattr(config, "ELEV_MIDDLE_MAX", p["middle_max"])
    monkeypatch.setattr(config, "ELEV_TOO_HIGH", p["too_high"])


@pytest.fixture(autouse=True)
def drone_profile(monkeypatch):
    """Most tests use the drone thresholds (real tidal elevations)."""
    use_profile(monkeypatch, "drone")


def site(**kw):
    base = dict(lat=10.7, lon=122.5, elevation_m=0.6, dist_coast_m=150, dist_river_m=900,
                dist_road_m=300, in_mangrove=False, dist_mangrove_m=120, in_fishpond=False,
                in_builtup=False, clay_pct=40, ndvi=0.15, ndvi_change=-0.1)
    base.update(kw)
    return SiteFactors(**base)


def test_middle_zone_mud_suits_rhizophora():
    r = assess(site())
    assert r["verdict"] == "suitable"
    assert r["zone"] == "middle"
    assert r["species"][0]["name"].startswith("Rhizophora")
    assert r["priority"]["level"] == "High"


def test_builtup_is_not_suitable():
    assert assess(site(in_builtup=True))["verdict"] == "not_suitable"


def test_dense_mangrove_is_protected():
    r = assess(site(in_mangrove=True, dist_mangrove_m=0, ndvi=0.8))
    assert r["verdict"] == "protect"
    assert r["species"] == []


def test_sparse_mangrove_allows_enrichment_planting():
    r = assess(site(in_mangrove=True, dist_mangrove_m=0, ndvi=0.35))
    assert r["verdict"] == "suitable"


def test_open_water_far_offshore():
    r = assess(site(elevation_m=-2, ndvi=-0.3, dist_coast_m=1500))
    assert r["verdict"] == "not_suitable"
    assert "Open water" in r["reasons"][0]


def test_too_high_ground():
    r = assess(site(elevation_m=4.0, dist_coast_m=800))
    assert r["verdict"] == "not_suitable"


def test_inland_far_from_rivers():
    r = assess(site(elevation_m=None, dist_coast_m=5000, dist_river_m=3000))
    assert r["verdict"] == "not_suitable"


def test_riverine_zone_recommends_nipa():
    f = site(dist_river_m=50, dist_coast_m=1200, elevation_m=0.8)
    z, _, est = zone_of(f)
    assert z == "riverine" and not est
    r = assess(f)
    assert "Nypa fruticans" in [s["name"] for s in r["species"]]


def test_seaward_sandy_suits_avicennia_sonneratia_and_warns_seagrass():
    r = assess(site(elevation_m=0.1, clay_pct=12, dist_coast_m=40))
    assert r["zone"] == "seaward"
    top = {s["name"] for s in r["species"][:3]}
    assert {"Avicennia marina", "Sonneratia alba"} <= top
    assert any("seagrass" in c for c in r["cautions"])


def test_missing_elevation_estimates_zone_and_lowers_confidence():
    f = site(elevation_m=None, clay_pct=None, ndvi=None)
    f.missing = ["dem", "clay", "ndvi"]
    r = assess(f)
    assert r["verdict"] == "suitable"
    assert r["confidence"] == "low"
    assert any("estimate" in c for c in r["cautions"])


def test_fishpond_caution():
    r = assess(site(in_fishpond=True))
    assert any("Fishpond Lease Agreement" in c for c in r["cautions"])


def test_nearby_species_bonus():
    plain = {s["name"]: s["score"] for s in rank_species("middle", "muddy", {})}
    boosted = {s["name"]: s["score"] for s in rank_species("middle", "muddy", {"Rhizophora mucronata": 3})}
    assert boosted["Rhizophora mucronata"] > plain["Rhizophora mucronata"]


def test_satellite_profile_reads_sea_level_zero_as_water(monkeypatch):
    use_profile(monkeypatch, "satellite")
    offshore = assess(site(elevation_m=0.0, ndvi=None, dist_coast_m=2000))
    assert offshore["verdict"] == "not_suitable"
    flat = assess(site(elevation_m=0.0, ndvi=None, dist_coast_m=50))
    assert flat["zone"] == "seaward"
    coastal = assess(site(elevation_m=3.0))
    assert coastal["zone"] == "middle"
    assert any("satellite elevation" in c for c in coastal["cautions"])


def test_without_coast_or_mangrove_map_is_uncertain():
    r = assess(site(dist_coast_m=None, dist_mangrove_m=None, in_mangrove=None))
    assert r["verdict"] == "uncertain"
