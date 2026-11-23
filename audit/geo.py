"""Small geo helpers.

The simulator works in local ENU metres (x east, y north) and converts to
WGS84 for the report exports, so the outputs can be dropped on a map.
"""

from __future__ import annotations

import math

EARTH_RADIUS_M = 6378137.0


def enu_to_latlon(x_m: float, y_m: float, origin_lat: float, origin_lon: float) -> tuple[float, float]:
    """Convert local east/north metres to WGS84 degrees around an origin."""
    d_lat = (y_m / EARTH_RADIUS_M) * (180.0 / math.pi)
    d_lon = (x_m / (EARTH_RADIUS_M * math.cos(math.radians(origin_lat)))) * (180.0 / math.pi)
    return origin_lat + d_lat, origin_lon + d_lon


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))
