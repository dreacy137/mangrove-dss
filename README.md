# Mangrove Decision Support System

A web map that helps environmental agencies decide where to plant mangroves and which species to plant. Click a spot or draw an area on the Iloilo map. The system says whether it is a good planting site, which species fit, and how high a priority it is, with the reasons for each answer.

It runs only on open data and data you collect yourself. It does not need government historical records.

## What it does

| Part | Status | What it does |
| --- | --- | --- |
| Module 2: Site suitability | Working | Screens out unsuitable spots (built-up, open sea, too high, inland), places the spot in a tidal zone, and ranks species by zone, soil and species growing nearby |
| Site prioritization | Working | Scores each site 0 to 100 from habitat evidence, zone fit, need and access, and ranks saved sites |
| Expert correction | Working | Staff correct a result. Each correction is saved with their name for calibration and later retraining |
| Change monitoring | Working once the Sentinel-2 layers are added | Uses NDVI change since 2016 as a sign of vegetation loss |
| Module 1: Canopy coverage | Working | Upload a drone photo to get canopy cover % and density |
| Module 1: Species identification | Planned | Needs a deep learning model trained on labelled drone photos from the study sites |

## Setup (Windows, macOS or Linux)

Requires Python 3.10 or newer.

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
```

On Windows, if `pip install` fails on `rasterio` or `geopandas`, install them with conda instead: `conda install -c conda-forge geopandas rasterio`.

## Prepare the data

Run these once, in order. Each writes a file to `data/processed/`. The app works with any subset, but results get more reliable as you add layers. The badge at the top right of the app shows how many layers are loaded.

| Step | Command | Source | Size |
| --- | --- | --- | --- |
| 1. Mangrove map | `python data_prep/01_clip_gmw.py path/to/gmw_v4112_2020_mng_ext_cntry_info_vec.gpkg` | Global Mangrove Watch 2020 (the file you already have) | small after clipping |
| 2. Elevation | `python data_prep/02_dem.py` | Copernicus GLO-30 (AWS Open Data) | about 95 MB download |
| 3. Coast, rivers, roads, fishponds, built-up | `python data_prep/03_osm.py` | OpenStreetMap (Overpass API) | takes 5 to 15 minutes |
| 4. Soil | `python data_prep/04_soil.py` | ISRIC SoilGrids 2.0 | small |
| 5. Sentinel-2 greenness and change | Run `data_prep/05_sentinel2_ndvi.js` in the Google Earth Engine Code Editor, then put both exported files in `data/processed/` | Sentinel-2 via Earth Engine | about 100 MB |
| 6. Species records (optional) | Copy `data_prep/species_observations_template.csv` to `data/processed/species_observations.csv` and add your field records | Your field checks | n/a |

## Run

```bash
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000

## Test

```bash
python -m pytest
```

The tests use small made-up layers, so they run without downloading anything.

## Important limits

- **Elevation is rough until the drone survey.** Copernicus GLO-30 is a 30 m surface model. It reads the sea as 0 m and coastal land 2 to 5 m too high because of trees, dikes and its 2 to 4 m error. The app uses wide "satellite" zones for now. Once you have a drone terrain model checked against NAMRIA tide tables, put it at `data/processed/dem_iloilo.tif` and set `ELEVATION_SOURCE = "drone"` in `app/config.py`.
- **Thresholds are placeholders.** All distances, elevations and scores are in `app/config.py` and `app/rules.py`. Calibrate them with field checks and expert corrections.
- **The species rules are a draft.** `app/species.py` lists 11 common Philippine species with their typical zones and soils. Check every row against Primavera (2009), *Field Guide to Philippine Mangroves*, and other zonation studies before the defense.
- **Seagrass is not mapped.** Seaward results always include a reminder to check for seagrass in the field before planting.

## Project layout

```
app/
  main.py      FastAPI backend and API
  rules.py     decision engine: screen, zone, species, priority
  factors.py   reads map layers and measures site factors at a point
  species.py   species knowledge base (draft)
  canopy.py    Module 1 canopy coverage from drone photos
  db.py        SQLite: candidate sites and expert corrections
  config.py    study area, file paths and thresholds
  static/      map dashboard (Leaflet)
data_prep/     scripts that download and clip the open data
tests/         automated tests
```
