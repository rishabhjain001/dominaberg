import math

import cv2
import pytest

from audit.detect import detect_tile
from audit.render import Camera, render_tile
from audit.world import CLASSES, build_world

CAM = Camera(35.0)


@pytest.mark.parametrize("kind", CLASSES)
def test_overhead_frame_of_known_anomaly_is_classified(kind):
    world = build_world(20261123)
    anomaly = next(a for a in world.anomalies if a.kind == kind)
    img = render_tile(world, anomaly.x, anomaly.y, 0.0, CAM)
    cx, cy = CAM.world_to_px(anomaly.x, anomaly.y, anomaly.x, anomaly.y, 0.0)
    hits = [d for d in detect_tile(img, CAM) if math.hypot(d.center_px[0] - cx, d.center_px[1] - cy) < 45]
    assert hits, f"no detection near the {kind} at the frame centre"
    assert hits[0].cls == kind


def test_empty_verge_frame_has_no_detections():
    world = build_world(20261123)
    img = render_tile(world, 20.0, 60.0, 0.0, CAM)  # grass between two roads
    assert cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).mean() > 90
    assert detect_tile(img, CAM) == []
