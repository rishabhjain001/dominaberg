# A.U.D.I.T. - Autonomous UAV Discrepancy Identification Trials

Working software for problem statement **NAT-003-PS-AUDIT** (SEVA FIRST - Rashtriya
Youth Innovation Challenge 2026, Track II: Diploma and Higher Education).

A.U.D.I.T. flies a coverage survey over a city ward, detects five classes of road
discrepancy on board, confirms each one across frames, and exports a
georeferenced register a municipal engineer can act on.

```
plan coverage  ->  fly the path  ->  detect per frame  ->  fuse across frames  ->  export
```

## What is in the box

| Path | What it does |
| --- | --- |
| `audit/world.py` | The reference ward: 240 x 180 m, 7 roads, 23 planted discrepancies in 5 classes |
| `audit/render.py` | Downward camera simulator: 35 m AGL, 60 deg HFOV, 6.3 cm per pixel, sensor noise and JPEG artefacts |
| `audit/detect.py` | Classical perception: carriageway mask, hull geometry, solidity, 5 classes |
| `audit/mission.py` | Mission state machine, capture scheduling, temporal fusion, evaluation |
| `audit/plan.py` | Boustrophedon coverage planner with overlap and battery reserve |
| `audit/report.py` | CSV, GeoJSON and markdown exports |
| `audit/api.py` | REST + WebSocket API and the static dashboard |
| `web/` | Mission-control dashboard: live map, detection feed, telemetry, trial evaluation |
| `docs/` | API contract, Screen-1 dossier, deck builder, diagrams |
| `tests/` | 22 tests across geometry, planning, perception, mission and API |

## Run it

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python app.py                      # http://localhost:8000
```

Or: `uvicorn app:app --host 0.0.0.0 --port 8000`

Open the dashboard, press **Launch mission**, and watch the survey run at 8x real
time. A full pass over the reference ward takes about 45 seconds of wall time and
produces 180+ frames.

## Measure it

```bash
python scripts/evaluate.py --all-seeds     # five survey runs
python scripts/evaluate.py --seed 42 --frames
```

Reference results, five seeds (20261123, 7, 42, 2026, 99):

| Metric | Value |
| --- | --- |
| Precision (mean) | 0.774 |
| Recall (mean) | 0.826 |
| F1 (mean) | 0.799 |
| Localization error (mean) | 0.23 m |
| Path coverage | 100 % every run |

Ground truth belongs to the simulator and is never passed to the detector;
scoring happens after the mission finishes.

## Test it

```bash
pytest -q
```

## API

`docs/API.md` is the full contract. The short version:

```
GET  /api/health
GET  /api/scenario
POST /api/missions                     {seed, altitude_m, speed_mps, multiplier}
POST /api/missions/{id}/start|pause|speed
GET  /api/missions/{id}                snapshot for reconnect and first paint
GET  /api/missions/{id}/evaluation     precision, recall, F1, per class
GET  /api/missions/{id}/report.csv|.geojson|.md
WS   /ws/missions/{id}                 snapshot, tick, detection, log, complete
```

## Submission artefacts

| Artefact | Path |
| --- | --- |
| Screen-1 answers (12 fields) | `docs/SUBMISSION-screen1.md` |
| Pitch deck (10 slides) | `docs/AUDIT-screen1.pptx`, built by `scripts/build_deck.py` |
| Architecture and state diagrams | `docs/architecture.svg`, `docs/mission-flow.svg` |
| Trial results | `docs/trial-results.json` |
| Video scene source | `docs/video-scenes.html` |

## Design notes

**Why classical vision, not a trained detector.** A 75-day sprint needs a
baseline that is inspectable and calibratable on site. Every class threshold is
one readable number in `audit/detect.py`, so a new city can be tuned from fifty
measured defects instead of a retraining campaign. A learned detector can be
compared against this baseline later; the temporal fusion and export layers do
not change.

**Why the hull and the solidity.** A large dark pool responds mostly at its rim.
Measuring blob pixel area would under-report it, so each response is described
by the filled hull of its contour (the true footprint) and by the share of that
footprint that is genuinely dark (solidity). A pool is large and solid, a
pothole is small and solid, a missing cover is small and solid with a bright
collar, debris is bright and compact, and a crack network is thin and sparse.

**Why two agreeing frames.** A single frame cannot separate a defect from a
shadow, a lane marking or a wet patch. A candidate is reported only after a
second frame lands within 3 m, and its position is the running mean of the
sightings. This is what turns a detector into a register.

## Limits

- The scenario is simulated. Thresholds are calibrated on rendered asphalt, not
  on a real camera; the first field sprint exists to refit them.
- The camera model is nadir only. Oblique views, tree canopy and parked vehicles
  are not modelled yet.
- Battery endurance is a constant, not a measured curve.

These limits are stated in the deck and in the Screen-1 dossier.
