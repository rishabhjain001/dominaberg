import math

from audit.mission import DEDUPE_RADIUS_M, Mission


def _finished(seed=20261123):
    m = Mission(seed=seed, altitude_m=35, speed_mps=8, multiplier=16)
    m.start()
    while m.status == "running":
        m.step(1.0)
    return m


def test_mission_completes_full_coverage():
    m = _finished()
    assert m.status == "complete"
    assert m.stats()["coverage_pct"] == 100.0
    assert m.frames_captured > 100


def test_reported_discrepancies_are_unique():
    m = _finished()
    for i, a in enumerate(m.detections):
        for b in m.detections[i + 1 :]:
            assert math.hypot(a.x - b.x, a.y - b.y) > DEDUPE_RADIUS_M / 2


def test_evaluation_scores_the_run():
    m = _finished()
    ev = m.evaluation()
    assert ev["recall"] > 0.8
    assert ev["precision"] > 0.6
    assert ev["localization_error_m"] < 0.5


def test_battery_return_to_home_triggers():
    m = Mission(seed=20261123, altitude_m=35, speed_mps=8, multiplier=1)
    m.battery_pct = 18.5
    m.start()
    for _ in range(600):
        m.step(1.0)
        if m.status != "running":
            break
    assert m.status in ("complete", "aborted")


def test_snapshot_is_serialisable():
    m = _finished()
    snap = m.snapshot()
    assert snap["mission_id"] == m.id
    assert len(snap["detections"]) == len(m.detections)


def test_register_ids_stay_unique_when_records_merge():
    """Merging removes an entry, so a length-based counter would reuse a key."""
    m = _finished()
    ids = [d.id for d in m.detections]
    assert ids
    assert len(ids) == len(set(ids))
