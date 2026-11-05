"""SQLite storage for candidate sites and expert corrections."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS sites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    polygon TEXT,             -- GeoJSON coordinates when the site is a drawn area
    verdict TEXT,
    priority REAL,
    result TEXT,              -- full assessment JSON
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id INTEGER,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    original_verdict TEXT,
    original_species TEXT,
    corrected_verdict TEXT,
    corrected_species TEXT,
    notes TEXT,
    expert TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect(path=None):
    con = sqlite3.connect(path or config.DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        con.executescript(SCHEMA)
        yield con
        con.commit()
    finally:
        con.close()


def add_site(name, lat, lon, polygon, result, path=None):
    pr = result.get("priority") or {}
    with connect(path) as con:
        cur = con.execute(
            "INSERT INTO sites (name, lat, lon, polygon, verdict, priority, result, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (name, lat, lon, json.dumps(polygon) if polygon else None,
             result.get("verdict"), pr.get("score"), json.dumps(result), now()),
        )
        return cur.lastrowid


def list_sites(path=None):
    with connect(path) as con:
        rows = con.execute(
            "SELECT * FROM sites ORDER BY (verdict = 'suitable') DESC, priority DESC, id"
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["polygon"] = json.loads(d["polygon"]) if d["polygon"] else None
        d["result"] = json.loads(d["result"]) if d["result"] else None
        out.append(d)
    return out


def delete_site(site_id, path=None):
    with connect(path) as con:
        con.execute("DELETE FROM sites WHERE id = ?", (site_id,))


def add_correction(c: dict, path=None):
    with connect(path) as con:
        cur = con.execute(
            "INSERT INTO corrections (site_id, lat, lon, original_verdict, original_species, "
            "corrected_verdict, corrected_species, notes, expert, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (c.get("site_id"), c["lat"], c["lon"], c.get("original_verdict"), c.get("original_species"),
             c.get("corrected_verdict"), c.get("corrected_species"), c.get("notes"), c["expert"], now()),
        )
        return cur.lastrowid


def list_corrections(path=None):
    with connect(path) as con:
        return [dict(r) for r in con.execute("SELECT * FROM corrections ORDER BY id DESC").fetchall()]
