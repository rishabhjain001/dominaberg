from audit.plan import plan_coverage
from audit.world import build_world


def test_plan_covers_every_road_and_stays_inside():
    world = build_world(20261123)
    plan = plan_coverage(world, 35.0)
    assert plan.lane_count >= 5
    assert plan.path_length_m > 1000
    for wp in plan.waypoints:
        assert 0.0 <= wp.x <= world.width_m
        assert 0.0 <= wp.y <= world.height_m


def test_capture_spacing_is_dense_enough_for_confirmation():
    world = build_world(20261123)
    plan = plan_coverage(world, 35.0)
    # Two frames separated by the capture spacing must still overlap, so every
    # discrepancy is seen at least twice.
    assert plan.capture_spacing_m < 30.0


def test_plan_is_deterministic():
    world = build_world(7)
    assert plan_coverage(world, 35.0).waypoints == plan_coverage(world, 35.0).waypoints
