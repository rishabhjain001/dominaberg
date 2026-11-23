"""Coverage planning: a lawnmower survey that respects the camera footprint."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .render import footprint_m
from .world import World


@dataclass
class Plan:
    waypoints: list[tuple[float, float]]
    lane_count: int
    path_length_m: float
    capture_spacing_m: float

    def as_dict(self) -> dict:
        return {
            "waypoints": [{"x": round(x, 2), "y": round(y, 2)} for x, y in self.waypoints],
            "lane_count": self.lane_count,
            "path_length_m": round(self.path_length_m, 1),
            "capture_spacing_m": self.capture_spacing_m,
        }


def plan_coverage(world: World, altitude_m: float, overlap: float = 0.35) -> Plan:
    """Plan lanes across the world with `overlap` fraction of side overlap."""
    _, swath_h = footprint_m(altitude_m)
    spacing = max(8.0, swath_h * (1.0 - overlap))

    margin_x, margin_y = 6.0, 10.0
    x0, x1 = margin_x, world.width_m - margin_x
    y0, y1 = margin_y, world.height_m - margin_y

    lanes = []
    y = y0
    while y <= y1:
        lanes.append(y)
        y += spacing
    if lanes and lanes[-1] < y1 - spacing * 0.4:
        lanes.append(y1)

    waypoints: list[tuple[float, float]] = [world.home]
    for i, lane_y in enumerate(lanes):
        left_to_right = i % 2 == 0
        start_x, end_x = (x0, x1) if left_to_right else (x1, x0)
        waypoints.append((start_x, lane_y))
        waypoints.append((end_x, lane_y))

    length = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(waypoints, waypoints[1:]))

    # One frame roughly every 1.6 camera heights keeps ground overlap between
    # consecutive frames comfortably above 60 percent.
    capture_spacing = max(5.0, swath_h * 0.38)
    return Plan(
        waypoints=[(round(x, 2), round(y, 2)) for x, y in waypoints],
        lane_count=len(lanes),
        path_length_m=round(length, 1),
        capture_spacing_m=round(capture_spacing, 2),
    )
