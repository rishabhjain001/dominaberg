"""Deterministic city-block world used by the mission simulator.

Everything here is a pure function of the seed, so a mission can be replayed
and the video for the pitch is reproducible.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

WORLD_W = 240.0
WORLD_H = 180.0
ORIGIN_LAT = 28.7501
ORIGIN_LON = 77.1177
ROAD_WIDTH = 7.0

# Discrepancy classes the perception stack is asked to find.
CLASSES = ("pothole", "missing_cover", "waterlogging", "debris", "pavement_damage")

# Relative frequency in the generated world.
CLASS_COUNTS = {
    "pothole": 9,
    "missing_cover": 4,
    "waterlogging": 3,
    "debris": 3,
    "pavement_damage": 4,
}

SEVERITY_BY_CLASS = {
    "pothole": (1, 3),
    "missing_cover": (2, 3),
    "waterlogging": (2, 3),
    "debris": (1, 2),
    "pavement_damage": (1, 2),
}


@dataclass(frozen=True)
class Road:
    orientation: str  # "h" or "v"
    center_m: float
    width_m: float = ROAD_WIDTH
    from_m: float = 0.0
    to_m: float = WORLD_W

    def as_dict(self) -> dict:
        return {
            "orientation": self.orientation,
            "center_m": self.center_m,
            "width_m": self.width_m,
            "from_m": self.from_m,
            "to_m": self.to_m,
        }


@dataclass
class Anomaly:
    """One ground-truth discrepancy."""

    id: str
    kind: str
    x: float
    y: float
    radius_m: float
    severity: int
    angle: float = 0.0
    shape_seed: int = 0

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "class": self.kind,
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "radius_m": round(self.radius_m, 2),
            "severity": self.severity,
        }


@dataclass
class Building:
    x: float
    y: float
    w: float
    h: float
    tone: float

    def as_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h, "tone": self.tone}


@dataclass
class World:
    seed: int
    roads: list[Road]
    buildings: list[Building]
    anomalies: list[Anomaly]
    home: tuple[float, float] = (8.0, 24.0)
    origin_lat: float = ORIGIN_LAT
    origin_lon: float = ORIGIN_LON
    width_m: float = WORLD_W
    height_m: float = WORLD_H
    meta: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "world": {
                "width_m": self.width_m,
                "height_m": self.height_m,
                "origin_lat": self.origin_lat,
                "origin_lon": self.origin_lon,
            },
            "roads": [r.as_dict() for r in self.roads],
            "home": {"x": self.home[0], "y": self.home[1]},
        }


def _default_roads() -> list[Road]:
    roads: list[Road] = [
        Road("h", 30.0),
        Road("h", 90.0),
        Road("h", 150.0),
        Road("v", 40.0, from_m=0.0, to_m=WORLD_H),
        Road("v", 100.0, from_m=0.0, to_m=WORLD_H),
        Road("v", 160.0, from_m=0.0, to_m=WORLD_H),
        Road("v", 220.0, from_m=0.0, to_m=WORLD_H),
    ]
    return roads


def _road_segments(roads: list[Road]) -> list[tuple[float, float, float, float]]:
    """Return (x1, y1, x2, y2) centre lines."""
    segs = []
    for r in roads:
        if r.orientation == "h":
            segs.append((r.from_m, r.center_m, r.to_m, r.center_m))
        else:
            segs.append((r.center_m, r.from_m, r.center_m, r.to_m))
    return segs


def _buildings(rng: random.Random, roads: list[Road], count: int = 26) -> list[Building]:
    out: list[Building] = []
    for _ in range(count * 4):
        if len(out) >= count:
            break
        w = rng.uniform(14, 26)
        h = rng.uniform(10, 20)
        x = rng.uniform(4, WORLD_W - w - 4)
        y = rng.uniform(4, WORLD_H - h - 4)
        keep_clear = ROAD_WIDTH / 2 + 5.0
        clashing = False
        for r in roads:
            if r.orientation == "h":
                if y - keep_clear < r.center_m < y + h + keep_clear:
                    clashing = True
            else:
                if x - keep_clear < r.center_m < x + w + keep_clear:
                    clashing = True
        if clashing:
            continue
        out.append(Building(round(x, 1), round(y, 1), round(w, 1), round(h, 1), round(rng.uniform(0.55, 0.85), 3)))
    return out


def _point_on_road(rng: random.Random, segments, placed: list[tuple[float, float]], min_gap: float = 7.0):
    for _ in range(400):
        x1, y1, x2, y2 = rng.choice(segments)
        t = rng.uniform(0.04, 0.96)
        x = x1 + (x2 - x1) * t
        y = y1 + (y2 - y1) * t
        # Keep anomalies inside the carriageway, alternating lanes a little.
        offset = rng.uniform(-2.0, 2.0)
        if abs(x2 - x1) > abs(y2 - y1):
            y += offset
        else:
            x += offset
        if all(math.hypot(x - px, y - py) >= min_gap for px, py in placed):
            return x, y
    return None


def _anomalies(seed: int, roads: list[Road]) -> list[Anomaly]:
    rng = random.Random(seed)
    segments = _road_segments(roads)
    placed: list[tuple[float, float]] = []
    out: list[Anomaly] = []
    counter = 1
    for kind in CLASSES:
        for _ in range(CLASS_COUNTS[kind]):
            spot = _point_on_road(rng, segments, placed)
            if spot is None:
                continue
            x, y = spot
            placed.append((x, y))
            if kind == "pothole":
                radius = rng.uniform(0.45, 1.05)
            elif kind == "missing_cover":
                radius = rng.uniform(0.45, 0.62)
            elif kind == "waterlogging":
                radius = rng.uniform(1.6, 3.2)
            elif kind == "debris":
                radius = rng.uniform(0.9, 1.7)
            else:
                radius = rng.uniform(0.8, 1.6)
            lo, hi = SEVERITY_BY_CLASS[kind]
            severity = rng.randint(lo, hi)
            out.append(
                Anomaly(
                    id=f"GT-{counter:02d}",
                    kind=kind,
                    x=round(x, 2),
                    y=round(y, 2),
                    radius_m=round(radius, 3),
                    severity=severity,
                    angle=round(rng.uniform(0, math.pi), 3),
                    shape_seed=rng.randrange(1, 10_000),
                )
            )
            counter += 1
    return out


def build_world(seed: int = 20261123) -> World:
    roads = _default_roads()
    rng = random.Random(seed ^ 0x5EED)
    buildings = _buildings(rng, roads)
    anomalies = _anomalies(seed, roads)
    return World(seed=seed, roads=roads, buildings=buildings, anomalies=anomalies)
