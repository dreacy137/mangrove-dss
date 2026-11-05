"""Shared settings: study area, file paths, and decision thresholds.

Thresholds marked PLACEHOLDER are first guesses. Calibrate them with tide
tables and the drone elevation model before using results for decisions.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_RAW = ROOT / "data" / "raw"
DATA = ROOT / "data" / "processed"
DB_PATH = ROOT / "data" / "dss.sqlite3"

# Iloilo province and its islands (lon/lat, WGS84).
BBOX = (121.95, 10.40, 123.40, 11.75)  # min_lon, min_lat, max_lon, max_lat
MAP_CENTER = (10.85, 122.55)

# Metric CRS for distances: UTM zone 51N.
METRIC_CRS = "EPSG:32651"

# Processed layers written by data_prep/ scripts.
LAYERS = {
    "dem": DATA / "dem_iloilo.tif",              # Copernicus GLO-30, metres above mean sea level
    "gmw": DATA / "gmw_iloilo.gpkg",             # Global Mangrove Watch 2020 extent
    "coast": DATA / "coastline.gpkg",            # OSM coastline lines
    "rivers": DATA / "rivers.gpkg",              # OSM rivers and streams
    "roads": DATA / "roads.gpkg",                # OSM roads (access)
    "fishponds": DATA / "fishponds.gpkg",        # OSM aquaculture / fishpond polygons
    "builtup": DATA / "builtup.gpkg",            # OSM residential / industrial / commercial
    "clay": DATA / "soil_clay_iloilo.tif",       # SoilGrids clay %, 0-5 cm
    "ndvi": DATA / "s2_ndvi_iloilo.tif",         # Sentinel-2 median NDVI (latest year)
    "ndvi_change": DATA / "s2_ndvi_change.tif",  # Sentinel-2 NDVI, latest minus earliest year
    "observations": DATA / "species_observations.csv",  # field or Module 1 species points
}

# ---- Tidal elevation zones (metres above mean sea level) -- PLACEHOLDER ----
# Mangroves grow roughly between mean sea level and the highest tides.
# Iloilo's spring tide range is around 1.5-2 m; confirm with NAMRIA tide tables.
#
# "satellite": Copernicus GLO-30 is a 30 m SURFACE model. It reads the sea as
#   exactly 0 m, and coastal land 2-5 m too high (trees, dikes, +/-2-4 m error),
#   so its zones are wide and rough.
# "drone": a drone terrain model checked against tide tables. Switch to this
#   once the drone survey exists.
ELEVATION_SOURCE = "satellite"
ELEVATION_PROFILES = {
    "satellite": {"too_low": -0.5, "water_at_or_below": 0.0, "seaward_max": 2.0, "middle_max": 4.0, "too_high": 6.0},
    "drone": {"too_low": -0.3, "water_at_or_below": -0.2, "seaward_max": 0.4, "middle_max": 0.9, "too_high": 1.6},
}
_E = ELEVATION_PROFILES[ELEVATION_SOURCE]
ELEV_TOO_LOW = _E["too_low"]                  # below this: permanently submerged, too deep
ELEV_WATER = _E["water_at_or_below"]          # at or below this: water (or tidal flat near the coast)
ELEV_SEAWARD_MAX = _E["seaward_max"]          # up to here: seaward (low) zone
ELEV_MIDDLE_MAX = _E["middle_max"]            # up to here: middle zone
ELEV_TOO_HIGH = _E["too_high"]                # above this: rarely or never flooded by tides

# ---- Distance rules (metres) ----
OPEN_WATER_OFFSHORE = 300  # water this far from the coastline is treated as open sea
INLAND_LIMIT = 2000        # land farther than this from coast and rivers is out of reach of tides
RIVERINE_DIST = 150        # within this of a river (and away from the coast): riverine zone
RIVER_COAST_SEP = 300      # ... and at least this far from the open coast
NEAR_MANGROVE = 1000       # existing mangroves within this distance = proven habitat nearby
NEARBY_SPECIES = 1000      # species observations counted within this distance
ROAD_GOOD = 500            # road within this distance = good access

# ---- Vegetation ----
DENSE_MANGROVE_NDVI = 0.6  # inside existing mangrove and greener than this = protect, don't plant

# ---- Soil (clay %, SoilGrids) ----
MUDDY_CLAY = 35
SANDY_CLAY = 20
