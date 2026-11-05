"""Module 1 (first piece): canopy coverage from a drone RGB photo.

Uses the Excess Green index (ExG = 2G - R - B on normalised colours) with an
Otsu threshold to separate vegetation from mud and water. This gives canopy
cover %, not species. Species identification needs a deep learning model
trained on labelled drone photos from the study sites (planned).
"""
import base64
import io

import numpy as np
from PIL import Image

MAX_SIDE = 1600


def _otsu(values: np.ndarray) -> float:
    hist, edges = np.histogram(values, bins=256)
    centers = (edges[:-1] + edges[1:]) / 2
    w = np.cumsum(hist)
    w_b = w[-1] - w
    m = np.cumsum(hist * centers)
    mean_f = m / np.maximum(w, 1)
    mean_b = (m[-1] - m) / np.maximum(w_b, 1)
    between = w * w_b * (mean_f - mean_b) ** 2
    return float(centers[np.argmax(between)])


def canopy_cover(image_bytes: bytes) -> dict:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    rgb = np.asarray(img, dtype=np.float32)
    total = rgb.sum(axis=2) + 1e-6
    r, g, b = (rgb[..., i] / total for i in range(3))
    exg = 2 * g - r - b

    thr = max(_otsu(exg.ravel()), 0.05)  # never call grey or brown pixels vegetation
    mask = exg > thr
    cover = float(mask.mean() * 100)

    overlay = np.asarray(img).copy()
    overlay[mask] = (0.45 * overlay[mask] + 0.55 * np.array([20, 200, 90])).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(overlay).save(buf, format="JPEG", quality=80)

    if cover >= 70:
        density = "Dense"
    elif cover >= 40:
        density = "Moderate"
    elif cover >= 10:
        density = "Sparse"
    else:
        density = "Very sparse or bare"

    return {
        "canopy_cover_pct": round(cover, 1),
        "density_class": density,
        "threshold": round(thr, 3),
        "width": img.width,
        "height": img.height,
        "overlay_jpeg_base64": base64.b64encode(buf.getvalue()).decode(),
        "note": "Canopy from the Excess Green index. Species identification is planned (needs labelled drone photos).",
    }
