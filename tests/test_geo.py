import math

from audit.geo import enu_to_latlon, haversine_m


def test_haversine_known_distance():
    # One degree of latitude at the equator is about 111.2 km.
    assert 110_000 < haversine_m(0.0, 0.0, 0.0, 1.0) < 112_500


def test_enu_origin_maps_to_origin():
    lat, lon = enu_to_latlon(0.0, 0.0, 28.7501, 77.1177)
    assert math.isclose(lat, 28.7501, abs_tol=1e-9)
    assert math.isclose(lon, 77.1177, abs_tol=1e-9)


def test_enu_round_trip_is_metric():
    lat, lon = enu_to_latlon(0.0, 100.0, 28.7501, 77.1177)
    assert math.isclose(haversine_m(28.7501, 77.1177, lat, lon), 100.0, rel_tol=1e-3)
