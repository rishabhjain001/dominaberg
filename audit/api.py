"""FastAPI app: mission control API, live WebSocket and the static dashboard."""

from __future__ import annotations

import asyncio
import contextlib
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .mission import Mission
from .report import to_csv, to_geojson, to_markdown
from .world import build_world

VERSION = "0.1.0"
TICK_S = 0.1
WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="A.U.D.I.T. Mission Control", version=VERSION)

_MISSIONS: dict[str, Mission] = {}
_SUBSCRIBERS: dict[str, set[asyncio.Queue]] = {}
_TASKS: dict[str, asyncio.Task] = {}
_LAST_STEP: dict[str, float] = {}
_LOCKS: dict[str, threading.Lock] = {}


class MissionRequest(BaseModel):
    seed: int = Field(default=20261123, ge=1, le=99_999_999)
    altitude_m: float = Field(default=35.0, ge=15.0, le=60.0)
    speed_mps: float = Field(default=8.0, ge=3.0, le=15.0)
    multiplier: float = Field(default=8.0, ge=1.0, le=16.0)


class SpeedRequest(BaseModel):
    multiplier: float = Field(ge=1.0, le=16.0)


def _mission(mission_id: str) -> Mission:
    m = _MISSIONS.get(mission_id)
    if m is None:
        raise HTTPException(status_code=404, detail="unknown mission")
    return m


def _broadcast(mission_id: str, events: list[dict]) -> None:
    for ev in events:
        for q in list(_SUBSCRIBERS.get(mission_id, ())):
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(ev)


def _lock(mission_id: str) -> threading.Lock:
    lock = _LOCKS.get(mission_id)
    if lock is None:
        lock = threading.Lock()
        _LOCKS[mission_id] = lock
    return lock


def _step(mission: Mission, dt_sim: float) -> list[dict]:
    """Advance the mission once, under its own lock.

    The timer task steps from a worker thread and a reader may step from the
    event loop, so every call goes through the same lock.
    """
    with _lock(mission.id):
        events = mission.step(dt_sim)
    _LAST_STEP[mission.id] = time.monotonic()
    return events


def _pump(mission: Mission) -> None:
    """Advance a running mission by the time that has passed since the last step.

    The API steps missions on a timer, but a reader must never depend on that
    timer still being alive: a worker restart, a suspended tab or a test client
    with no event loop would otherwise freeze the mission. Time is counted from
    the last step by either path, so a reader cannot make the mission run faster
    than the wall clock.
    """
    if mission.status != "running":
        return
    task = _TASKS.get(mission.id)
    if task is not None and not task.done():
        return
    now = time.monotonic()
    last = _LAST_STEP.get(mission.id, now - TICK_S)
    dt_sim = min(4.0, (now - last) * mission.multiplier)
    if dt_sim <= 0.05:
        return
    _broadcast(mission.id, _step(mission, dt_sim))


async def _run_loop(mission_id: str) -> None:
    mission = _MISSIONS[mission_id]
    while mission.status in ("running", "paused"):
        if mission.status != "running":
            await asyncio.sleep(TICK_S)
            continue
        await asyncio.sleep(1.0 / mission.multiplier)
        if mission.status != "running":
            continue
        events = await asyncio.to_thread(_step, mission, 1.0)
        _broadcast(mission_id, events)
        if mission.status == "complete":
            break


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": VERSION}


@app.get("/api/scenario")
async def scenario():
    world = build_world()
    payload = world.as_dict()
    payload["default_seed"] = world.seed
    payload["classes"] = ["pothole", "missing_cover", "waterlogging", "debris", "pavement_damage"]
    return payload


@app.post("/api/missions")
async def create_mission(req: MissionRequest):
    mission = Mission(seed=req.seed, altitude_m=req.altitude_m, speed_mps=req.speed_mps, multiplier=req.multiplier)
    _MISSIONS[mission.id] = mission
    world = mission.world.as_dict()
    return {
        "mission_id": mission.id,
        "plan": mission.plan.as_dict(),
        "world": world["world"],
        "roads": world["roads"],
        "home": world["home"],
    }


@app.get("/api/missions/{mission_id}")
async def get_mission(mission_id: str):
    mission = _mission(mission_id)
    _pump(mission)
    return mission.snapshot()


@app.post("/api/missions/{mission_id}/start")
async def start_mission(mission_id: str):
    mission = _mission(mission_id)
    if mission.status == "complete":
        return {"ok": False, "status": mission.status, "detail": "mission already complete"}
    mission.start()
    task = _TASKS.get(mission_id)
    if task is None or task.done():
        _TASKS[mission_id] = asyncio.create_task(_run_loop(mission_id))
    return {"ok": True, "status": mission.status}


@app.post("/api/missions/{mission_id}/pause")
async def pause_mission(mission_id: str):
    mission = _mission(mission_id)
    mission.pause()
    return {"ok": True, "status": mission.status}


@app.post("/api/missions/{mission_id}/speed")
async def set_speed(mission_id: str, req: SpeedRequest):
    mission = _mission(mission_id)
    mission.multiplier = req.multiplier
    return {"ok": True, "multiplier": mission.multiplier}


@app.get("/api/missions/{mission_id}/evaluation")
async def get_evaluation(mission_id: str):
    mission = _mission(mission_id)
    _pump(mission)
    if mission.status != "complete":
        raise HTTPException(status_code=409, detail="mission not complete")
    return {
        "evaluation": mission.evaluation(),
        "stats": mission.stats(),
        "ground_truth": [a.as_dict() for a in mission.world.anomalies],
    }


@app.get("/api/missions/{mission_id}/report.csv")
async def export_csv(mission_id: str):
    mission = _mission(mission_id)
    return PlainTextResponse(
        to_csv(mission),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{mission_id}-discrepancies.csv"'},
    )


@app.get("/api/missions/{mission_id}/report.geojson")
async def export_geojson(mission_id: str):
    mission = _mission(mission_id)
    return Response(
        to_geojson(mission),
        media_type="application/geo+json",
        headers={"Content-Disposition": f'attachment; filename="{mission_id}-discrepancies.geojson"'},
    )


@app.get("/api/missions/{mission_id}/report.md")
async def export_markdown(mission_id: str):
    mission = _mission(mission_id)
    return PlainTextResponse(
        to_markdown(mission),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{mission_id}-discrepancies.md"'},
    )


@app.websocket("/ws/missions/{mission_id}")
async def mission_socket(ws: WebSocket, mission_id: str):
    await ws.accept()
    mission = _MISSIONS.get(mission_id)
    if mission is None:
        await ws.send_json({"type": "error", "detail": "unknown mission"})
        await ws.close()
        return
    queue: asyncio.Queue = asyncio.Queue(maxsize=600)
    _SUBSCRIBERS.setdefault(mission_id, set()).add(queue)
    try:
        await ws.send_json({"type": "snapshot", "snapshot": mission.snapshot()})
        while True:
            try:
                ev = await asyncio.wait_for(queue.get(), timeout=15.0)
            except asyncio.TimeoutError:
                await ws.send_json({"type": "heartbeat", "t": round(time.time(), 2)})
                continue
            await ws.send_json(ev)
    except WebSocketDisconnect:
        pass
    finally:
        _SUBSCRIBERS.get(mission_id, set()).discard(queue)


app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

# Registered last, so every /api and /ws route still wins. ``html=True`` serves
# index.html for "/" and keeps the dashboard's root-absolute asset paths valid.
app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="dashboard")

if WEB_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(WEB_DIR)), name="assets")
