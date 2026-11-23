import time

from fastapi.testclient import TestClient

from audit.api import app

client = TestClient(app)


def test_health():
    assert client.get("/api/health").json()["status"] == "ok"


def test_scenario_exposes_roads_and_bounds():
    body = client.get("/api/scenario").json()
    assert body["world"]["width_m"] == 240.0
    assert len(body["roads"]) >= 7


def test_mission_lifecycle_and_exports():
    created = client.post("/api/missions", json={"seed": 20261123, "multiplier": 16}).json()
    mid = created["mission_id"]
    assert created["plan"]["lane_count"] >= 5
    client.post(f"/api/missions/{mid}/start")
    deadline = time.time() + 240
    while time.time() < deadline:
        state = client.get(f"/api/missions/{mid}").json()
        if state["status"] in ("complete", "aborted"):
            break
        time.sleep(0.5)
    assert state["status"] == "complete"
    assert state["stats"]["coverage_pct"] == 100.0
    for ext in ("csv", "geojson", "md"):
        resp = client.get(f"/api/missions/{mid}/report.{ext}")
        assert resp.status_code == 200 and len(resp.content) > 100


def test_websocket_sends_a_snapshot_first():
    # Event streaming is exercised against the live uvicorn server (see
    # docs/API.md); a test client cannot drive a background task and a socket
    # at the same time without deadlocking.
    created = client.post("/api/missions", json={"seed": 7, "multiplier": 16}).json()
    mid = created["mission_id"]
    with client.websocket_connect(f"/ws/missions/{mid}") as ws:
        first = ws.receive_json()
        assert first["type"] == "snapshot"
        snapshot = first["snapshot"]
        assert snapshot["mission_id"] == mid
        assert "plan" in snapshot and "detections" in snapshot


def test_unknown_mission_returns_404():
    assert client.get("/api/missions/nope").status_code == 404
