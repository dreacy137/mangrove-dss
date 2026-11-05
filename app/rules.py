"""Decision engine: turns site factors into a planting decision.

Steps
1. Screen: is the spot unsuitable (built-up, open water, too high, inland),
   or already a dense mangrove that should be protected instead of planted?
2. Zone: seaward, middle, landward or riverine, from tidal elevation and
   distance to rivers and the coast.
3. Species: rank species whose zone and substrate fit, with a bonus for
   species already growing nearby.
4. Priority: score 0-100 from habitat evidence, zone fit, need and access.

Every result carries plain-language reasons so agency staff can see why.
"""
from __future__ import annotations

from . import config as C
from .factors import SiteFactors
from .species import SPECIES, ZONE_LABELS

KEY_LAYERS = ["dem", "coast", "gmw", "clay", "ndvi"]


def _fmt_m(v):
    return f"{v:,.0f} m"


# ------------------------------------------------------------------ 1. screen

def screen(f: SiteFactors):
    """Returns (verdict, reasons). verdict is None when the spot passes."""
    if f.in_builtup:
        return "not_suitable", ["Inside a built-up area (OpenStreetMap)."]

    if f.in_mangrove:
        if f.ndvi is not None and f.ndvi < C.DENSE_MANGROVE_NDVI:
            return None, [
                f"Inside mapped mangrove (GMW 2020) but canopy is sparse (NDVI {f.ndvi:.2f}); "
                "suitable for enrichment planting in gaps."
            ]
        if f.ndvi is None:
            return "protect", [
                "Inside mapped mangrove (GMW 2020). Protect the existing stand; "
                "check canopy density before planting in gaps."
            ]
        return "protect", [
            f"Inside dense existing mangrove (GMW 2020, NDVI {f.ndvi:.2f}). "
            "Protect it; planting is not needed here."
        ]

    is_water = (f.ndvi is not None and f.ndvi < 0) or (
        f.elevation_m is not None and f.elevation_m <= C.ELEV_WATER
    )
    if is_water and f.dist_coast_m is not None and f.dist_coast_m > C.OPEN_WATER_OFFSHORE:
        return "not_suitable", [
            f"Open water about {_fmt_m(f.dist_coast_m)} from the coastline; too deep and exposed for seedlings."
        ]
    if f.elevation_m is not None and f.elevation_m < C.ELEV_TOO_LOW:
        return "not_suitable", [
            f"Elevation {f.elevation_m:.1f} m is below the planting window; permanently submerged."
        ]

    near_river = f.dist_river_m is not None and f.dist_river_m <= C.RIVERINE_DIST
    if f.elevation_m is not None and f.elevation_m > C.ELEV_TOO_HIGH and not near_river:
        return "not_suitable", [
            f"Elevation {f.elevation_m:.1f} m is above the highest tides; the ground is rarely or never flooded."
        ]

    far_coast = f.dist_coast_m is not None and f.dist_coast_m > C.INLAND_LIMIT
    far_river = f.dist_river_m is None or f.dist_river_m > C.RIVERINE_DIST
    if far_coast and far_river:
        return "not_suitable", [
            f"{_fmt_m(f.dist_coast_m)} inland and away from rivers; out of reach of tidal water."
        ]
    return None, []


# ------------------------------------------------------------------ 2. zone

def zone_of(f: SiteFactors):
    """Returns (zone, reason, is_estimate)."""
    if (
        f.dist_river_m is not None
        and f.dist_river_m <= C.RIVERINE_DIST
        and (f.dist_coast_m is None or f.dist_coast_m >= C.RIVER_COAST_SEP)
    ):
        return "riverine", f"{_fmt_m(f.dist_river_m)} from a river and away from the open coast.", False

    if f.elevation_m is not None:
        e = f.elevation_m
        if e <= C.ELEV_WATER:
            return "seaward", "Water or tidal flat near the coast: seaward edge.", False
        if e <= C.ELEV_SEAWARD_MAX:
            return "seaward", f"Elevation {e:.1f} m: flooded at most high tides.", False
        if e <= C.ELEV_MIDDLE_MAX:
            return "middle", f"Elevation {e:.1f} m: flooded at normal high tides.", False
        return "landward", f"Elevation {e:.1f} m: flooded only at spring tides.", False

    if f.dist_coast_m is not None:  # rough fallback when elevation is missing
        d = f.dist_coast_m
        z = "seaward" if d < 100 else "middle" if d < 400 else "landward"
        return z, f"No elevation data; zone estimated from distance to coast ({_fmt_m(d)}).", True
    return None, "No elevation or coastline data to place the area in a zone.", True


def substrate_of(f: SiteFactors):
    if f.clay_pct is None:
        return None
    if f.clay_pct >= C.MUDDY_CLAY:
        return "muddy"
    if f.clay_pct <= C.SANDY_CLAY:
        return "sandy"
    return "mixed"


# ------------------------------------------------------------------ 3. species

def rank_species(zone, substrate, nearby: dict):
    ranked = []
    for sp in SPECIES:
        reasons = []
        if zone in sp["primary"]:
            score = 60
            reasons.append(f"Typical of the {zone} zone.")
        elif zone in sp["secondary"]:
            score = 30
            reasons.append(f"Also occurs in the {zone} zone.")
        else:
            continue

        subs = sp["substrate"]
        if substrate is None:
            pass
        elif substrate == "mixed":
            score += 10
            reasons.append("Soil is mixed sand and mud.")
        elif substrate in subs or (substrate == "muddy" and "firm" in subs) or "any" in subs:
            score += 20
            reasons.append(f"Suits {substrate} soil.")
        else:
            score -= 15
            reasons.append(f"Prefers {'/'.join(subs)} soil, not {substrate}.")

        count = nearby.get(sp["name"], 0)
        if count:
            score += min(20, 10 + 2 * count)
            reasons.append(f"Already growing nearby ({count} record{'s' if count > 1 else ''}).")

        ranked.append({
            "name": sp["name"],
            "local": sp["local"],
            "score": max(0, min(100, score)),
            "reasons": reasons,
            "note": sp["note"],
        })
    ranked.sort(key=lambda r: r["score"], reverse=True)
    return ranked[:5]


# ------------------------------------------------------------------ 4. priority

def priority(f: SiteFactors, zone, zone_estimated):
    parts = {}

    d = f.dist_mangrove_m
    if d is None:
        parts["habitat_evidence"] = (0, "No mangrove map loaded.")
    elif d <= 250:
        parts["habitat_evidence"] = (35, f"Existing mangroves within {_fmt_m(d)}: proven habitat.")
    elif d <= C.NEAR_MANGROVE:
        parts["habitat_evidence"] = (25, f"Existing mangroves {_fmt_m(d)} away.")
    elif d <= 3000:
        parts["habitat_evidence"] = (10, f"Nearest mangroves {_fmt_m(d)} away.")
    else:
        parts["habitat_evidence"] = (0, f"No mangroves within 3 km ({_fmt_m(d)}).")

    if zone is None:
        parts["zone_fit"] = (0, "Zone unknown.")
    elif zone_estimated:
        parts["zone_fit"] = (10, "Zone estimated without elevation data.")
    elif zone == "middle":
        parts["zone_fit"] = (25, "Middle zone: the widest range of species fit.")
    else:
        parts["zone_fit"] = (20, f"Inside the {zone} planting window.")

    need = 0
    need_why = []
    if f.ndvi is not None and f.ndvi < 0.3:
        need += 15
        need_why.append(f"little vegetation now (NDVI {f.ndvi:.2f})")
    elif f.ndvi is None and not f.in_mangrove:
        need += 10
        need_why.append("not mapped as mangrove")
    if f.ndvi_change is not None and f.ndvi_change < -0.05:
        need += round(10 * min(1.0, -f.ndvi_change / 0.2))
        need_why.append(f"vegetation loss since 2016 (NDVI change {f.ndvi_change:+.2f})")
    parts["need"] = (need, "; ".join(need_why).capitalize() + "." if need_why else "No clear sign of need.")

    r = f.dist_road_m
    if r is None:
        parts["access"] = (0, "No road data.")
    elif r <= C.ROAD_GOOD:
        parts["access"] = (15, f"Road {_fmt_m(r)} away.")
    elif r <= 2000:
        parts["access"] = (8, f"Road {_fmt_m(r)} away.")
    else:
        parts["access"] = (3, f"Far from roads ({_fmt_m(r)}).")

    total = min(100, sum(v for v, _ in parts.values()))
    level = "High" if total >= 70 else "Medium" if total >= 40 else "Low"
    return {
        "score": total,
        "level": level,
        "parts": {k: {"points": v, "why": why} for k, (v, why) in parts.items()},
    }


# ------------------------------------------------------------------ assemble

def confidence(f: SiteFactors):
    missing = [m for m in KEY_LAYERS if m in f.missing]
    if len(missing) <= 1:
        return "high" if not missing else "medium"
    return "medium" if len(missing) <= 2 else "low"


def assess(f: SiteFactors) -> dict:
    verdict, reasons = screen(f)
    cautions = []

    if f.in_fishpond:
        cautions.append(
            "Inside a fishpond. Check tenure (Fishpond Lease Agreement) first; "
            "abandoned ponds are good candidates for reversion to mangrove."
        )

    result = {
        "factors": f.to_dict(),
        "confidence": confidence(f),
        "missing_layers": sorted(set(f.missing)),
    }

    if verdict in ("not_suitable", "protect"):
        result.update(verdict=verdict, reasons=reasons, cautions=cautions,
                      zone=None, zone_label=None, species=[], priority=None)
        return result

    if f.dist_coast_m is None and f.dist_mangrove_m is None:
        reasons.append("No coastline or mangrove map loaded, so distance to the sea cannot be checked. "
                       "Run data_prep/01_clip_gmw.py and 03_osm.py.")
        result.update(verdict="uncertain", reasons=reasons, cautions=cautions,
                      zone=None, zone_label=None, species=[], priority=None)
        return result

    zone, zone_reason, estimated = zone_of(f)
    reasons.append(zone_reason)
    if zone is None:
        result.update(verdict="uncertain", reasons=reasons, cautions=cautions,
                      zone=None, zone_label=None, species=[], priority=None)
        return result

    substrate = substrate_of(f)
    if substrate:
        reasons.append(f"Soil is {substrate} (clay {f.clay_pct:.0f}%).")
    if zone == "seaward":
        cautions.append("Field check for seagrass beds first; planting on seagrass or open mudflats destroys those habitats.")
    if estimated:
        cautions.append("Zone is an estimate. Confirm elevation with the drone survey.")
    elif C.ELEVATION_SOURCE == "satellite" and zone != "riverine":
        cautions.append("Zone is from 30 m satellite elevation (about 2-4 m error). Confirm with the drone survey and tide tables.")

    result.update(
        verdict="suitable",
        reasons=reasons,
        cautions=cautions,
        zone=zone,
        zone_label=ZONE_LABELS[zone],
        substrate=substrate,
        species=rank_species(zone, substrate, f.nearby_species),
        priority=priority(f, zone, estimated),
    )
    return result
