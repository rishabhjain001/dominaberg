"""Perception stack: find road discrepancies in a single camera frame.

This is deliberately a classical-CV baseline. It is small, deterministic and
inspectable, which is what a 75-day sprint needs first: a documented baseline
with measurable precision and recall that a learned detector can be compared
against later. The classifier uses only the image, never the simulator's
ground truth.

Pipeline
--------
1. Estimate the carriageway region so grass, roofs and field noise cannot
   produce candidates.
2. Build a dark mask (holes, pools, cracks) and a bright mask (rubble piles)
   normalised by a multi-scale local background.
3. Describe each blob with hull geometry so a ring-shaped response - the rim of
   a large dark pool - is still measured at its true footprint.
4. Assign a class from geometry and size, and report a confidence.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .render import Camera

MIN_BLOB_PX = 30


@dataclass
class Detection:
    cls: str
    u: int
    v: int
    w: int
    h: int
    confidence: float
    area_m2: float

    @property
    def center_px(self) -> tuple[float, float]:
        return self.u + self.w / 2.0, self.v + self.h / 2.0


def _detection(cls: str, comp: dict, confidence: float, area_m2: float) -> Detection:
    return Detection(
        cls=cls,
        u=comp["x"],
        v=comp["y"],
        w=comp["w"],
        h=comp["h"],
        confidence=round(confidence, 3),
        area_m2=round(area_m2, 2),
    )


def road_mask(gray: np.ndarray) -> np.ndarray:
    """Boolean carriageway estimate.

    Asphalt is markedly darker than verges and roofs. Closing bridges the light
    lane markings and the discrepancies themselves; the size filter then drops
    isolated dark specks such as kerb shadows.
    """
    core = (gray < 92).astype(np.uint8)
    core = cv2.morphologyEx(core, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (41, 41)))
    core = cv2.morphologyEx(core, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(core, connectivity=8)
    road = np.zeros_like(core)
    for i in range(1, count):
        if stats[i, cv2.CC_STAT_AREA] >= 3000:
            road[labels == i] = 1
    return road.astype(bool)


def _components(mask: np.ndarray) -> list[dict]:
    """Describe blobs with hull geometry.

    ``area_px`` is the raw pixel count; ``hull_area`` is the filled footprint.
    ``hull_area`` is what a pool or a hole physically occupies even when the
    response is only its rim.
    """
    height, width = mask.shape[:2]
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    out: list[dict] = []
    for i in range(1, count):
        x, y, w, h, area = stats[i]
        if area < MIN_BLOB_PX or w < 4 or h < 4:
            continue
        if x <= 2 or y <= 2 or x + w >= width - 2 or y + h >= height - 2:
            # A blob cut by the frame border has no trustworthy footprint.
            continue
        roi = (labels == i)[y : y + h, x : x + w].astype(np.uint8)
        contours, _ = cv2.findContours(roi, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue
        contour = max(contours, key=cv2.contourArea)
        hull = cv2.convexHull(contour)
        hull_area = float(cv2.contourArea(hull))
        if hull_area < MIN_BLOB_PX * 0.6:
            continue
        hull_perim = float(cv2.arcLength(hull, True))
        rect = cv2.minAreaRect(hull)
        rw, rh = max(rect[1]), min(rect[1])
        out.append(
            {
                "x": int(x),
                "y": int(y),
                "w": int(w),
                "h": int(h),
                "area_px": int(area),
                "hull_px": hull_area,
                "circularity": float(4.0 * np.pi * hull_area / (hull_perim * hull_perim)) if hull_perim > 0 else 0.0,
                "elongation": float(rw / max(rh, 1e-3)),
                "fill": float(area / float(w * h)),
            }
        )
    return out


def _background(gray: np.ndarray) -> np.ndarray:
    """Brighter of two neighbourhood scales.

    A single window fails on one of two cases: a small defect is averaged away
    by a wide window, while a wide defect fills a narrow window and becomes its
    own background. Taking the brighter estimate keeps both visible.
    """
    near = cv2.blur(gray, (61, 61), borderType=cv2.BORDER_REPLICATE).astype(np.float32)
    far = cv2.blur(gray, (201, 201), borderType=cv2.BORDER_REPLICATE).astype(np.float32)
    return np.maximum(near, far)


def _patch(gray: np.ndarray, comp: dict, centroid: tuple[float, float], half: int):
    """Clip the neighbourhood around a blob to the frame bounds.

    Returns the patch and the centroid's coordinates inside it.
    """
    x0 = max(0, int(centroid[0]) - half)
    y0 = max(0, int(centroid[1]) - half)
    x1 = min(gray.shape[1], int(centroid[0]) + half)
    y1 = min(gray.shape[0], int(centroid[1]) + half)
    return gray[y0:y1, x0:x1], centroid[0] - x0, centroid[1] - y0


def _blob_radius(comp: dict) -> float:
    return max(3.0, float(np.sqrt(comp["hull_px"] / np.pi)))


def _ring_ratio(gray: np.ndarray, comp: dict, centroid: tuple[float, float]) -> float:
    """Brightness of the surroundings relative to the blob interior.

    A missing cover is a dark hole inside a bright collar, so the ratio is well
    above one. A plain pothole reads close to one.
    """
    r = _blob_radius(comp)
    half = int(max(comp["w"], comp["h"]) * 0.85) + 3
    patch, ox, oy = _patch(gray, comp, centroid, half)
    if patch.shape[0] < 6 or patch.shape[1] < 6:
        return 1.0
    yy, xx = np.mgrid[0 : patch.shape[0], 0 : patch.shape[1]]
    d = np.hypot(xx - ox, yy - oy)
    inner = patch[d <= r * 0.7]
    ring = patch[(d > r * 1.15) & (d <= r * 1.6)]
    if inner.size == 0 or ring.size < 8:
        return 1.0
    return float(ring.mean() / max(inner.mean(), 1.0))


def _solid_fraction(gray: np.ndarray, comp: dict, centroid: tuple[float, float]) -> float:
    """Share of the blob footprint that is genuinely dark.

    A filled pool or hole covers most of its footprint. A crack network is thin
    lines, so asphalt dominates the area between its branches.
    """
    r = _blob_radius(comp)
    patch, ox, oy = _patch(gray, comp, centroid, int(r) + 2)
    if patch.shape[0] < 4 or patch.shape[1] < 4:
        return 1.0
    yy, xx = np.mgrid[0 : patch.shape[0], 0 : patch.shape[1]]
    inside = np.hypot(xx - ox, yy - oy) <= r * 0.9
    if not inside.any():
        return 1.0
    return float((patch[inside] < 58).mean())


def _on_road(road: np.ndarray, comp: dict) -> bool:
    x, y, w, h = comp["x"], comp["y"], comp["w"], comp["h"]
    patch = road[y : y + h, x : x + w]
    if patch.size == 0:
        return False
    return float(patch.mean()) >= 0.62


def detect_tile(img: np.ndarray, camera: Camera) -> list[Detection]:
    """Return the discrepancies found in one BGR frame."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1].astype(np.float32)
    val = hsv[:, :, 2].astype(np.float32)
    m2 = camera.m_per_px * camera.m_per_px

    road = road_mask(gray)
    bg = _background(gray)
    ratio = gray.astype(np.float32) / np.maximum(bg, 1.0)

    # ``gray < 62`` keeps asphalt out even where a long road edge sits beside a
    # bright verge, which the ratio test alone would flag as one large defect.
    dark = ((ratio < 0.80) & (gray < 62) & (val < 165) & (sat < 110)).astype(np.uint8) * 255
    dark = cv2.morphologyEx(dark, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    dark = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))

    bright = ((ratio > 1.16) & (val > 130) & (val < 215) & (sat < 80)).astype(np.uint8) * 255
    bright = cv2.morphologyEx(bright, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    bright = cv2.morphologyEx(bright, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))

    detections: list[Detection] = []

    for s in _components(dark):
        if not _on_road(road, s):
            continue
        hull_m2 = s["hull_px"] * m2
        span_m = max(s["w"], s["h"]) * camera.m_per_px
        if hull_m2 < 0.2 or span_m > 10.0:
            continue
        centroid = (s["x"] + s["w"] / 2.0, s["y"] + s["h"] / 2.0)
        ring = _ring_ratio(gray, s, centroid)
        patch = gray[s["y"] : s["y"] + s["h"], s["x"] : s["x"] + s["w"]]
        darkness = float(np.clip(1.0 - patch.mean() / max(bg[int(centroid[1]), int(centroid[0])], 1.0), 0.0, 0.95))

        solid = _solid_fraction(gray, s, centroid)

        if solid < 0.45 and hull_m2 >= 0.6:
            cls, base = "pavement_damage", 0.68
        elif hull_m2 >= 4.0 and solid >= 0.5:
            cls, base = "waterlogging", 0.79
        elif ring >= 2.6 and hull_m2 <= 1.7 and s["circularity"] >= 0.55:
            cls, base = "missing_cover", 0.81
        elif s["circularity"] >= 0.45 and 0.2 <= hull_m2 <= 3.8 and span_m <= 4.4 and solid >= 0.5:
            cls, base = "pothole", 0.75
        else:
            continue

        conf = float(np.clip(base * (0.80 + 0.30 * darkness), 0.3, 0.97))
        detections.append(_detection(cls, s, conf, hull_m2))

    for s in _components(bright):
        if not _on_road(road, s):
            continue
        hull_m2 = s["hull_px"] * m2
        if not 0.6 <= hull_m2 <= 9.0:
            continue
        if s["fill"] < 0.35 or s["elongation"] > 2.4 or s["circularity"] < 0.22:
            continue
        patch = gray[s["y"] : s["y"] + s["h"], s["x"] : s["x"] + s["w"]]
        brightness = float(np.clip((patch.mean() - 115.0) / 90.0, 0.0, 1.0))
        conf = float(np.clip(0.60 + 0.35 * brightness, 0.3, 0.95))
        detections.append(_detection("debris", s, conf, hull_m2))

    # A rubble pile casts a dark shadow; keep the pile and drop the shadow.
    piles = [d for d in detections if d.cls == "debris"]
    detections = [
        d
        for d in detections
        if d.cls == "debris"
        or not any(
            abs(d.center_px[0] - p.center_px[0]) < 1.4 * max(p.w, p.h)
            and abs(d.center_px[1] - p.center_px[1]) < 1.4 * max(p.w, p.h)
            for p in piles
        )
    ]

    return _dedupe(detections)


def _dedupe(detections: list[Detection]) -> list[Detection]:
    kept: list[Detection] = []
    for d in sorted(detections, key=lambda d: d.confidence, reverse=True):
        duplicate = False
        for k in kept:
            if k.cls != d.cls:
                continue
            cx1, cy1 = d.center_px
            cx2, cy2 = k.center_px
            if abs(cx1 - cx2) < max(d.w, k.w) and abs(cy1 - cy2) < max(d.h, k.h):
                duplicate = True
                break
        if not duplicate:
            kept.append(d)
    return kept
