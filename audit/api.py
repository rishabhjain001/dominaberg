"""FastAPI app: mission control API, live WebSocket and the static dashboard."""

from __future__ import annotations

import asyncio
import contextlib
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
_LAST_PUMP: dict[str, float] = {}


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


def _pump(mission: Mission) -> None:
    """Advance a running mission from wall-clock time.

    The API steps missions on a timer, but a reader must never depend on that
    timer still being alive. Pumping on read keeps the simulation correct after
    a worker restart, a suspended tab, or a test client that owns no event loop.
    """
    if mission.status != "running":
        return
    now = time.monotonic()
    last = _LAST_PUMP.get(mission.id, now)
    _LAST_PUMP[mission.id] = now
    dt_sim = min(4.0, max(mission.multiplier * TICK_S, (now - last) * mission.multiplier))
    events = mission.step(dt_sim)
    _broadcast(mission.id, events)


async def _run_loop(mission_id: str) -> None:
    mission = _MISSIONS[mission_id]
    while mission.status in ("running", "paused"):
        await asyncio.sleep(TICK_S)
        if mission.status != "running":
            continue
        dt = mission.multiplier * TICK_S
        events = await asyncio.to_thread(mission.step, dt)
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
    _pump(_mission(mission_id))
    mission = _mission(mission_id)
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
    return PlainTextResponse(to_markdown(mission), media_type="text/markdown")


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
