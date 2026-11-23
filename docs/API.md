# A.U.D.I.T. Mission Control - HTTP + WebSocket contract

All endpoints are served by the same FastAPI process that serves the static UI.
Base path: `/api`. JSON in, JSON out. Times in milliseconds of simulation.

## Coordinate system

Local ENU metres. `x` grows east, `y` grows north. World size is
`world.width_m` by `world.height_m`. The UI draws `x` to the right and `y` to
the top (so `screen_y = height_px - (y / world.height_m) * height_px`).

Geo coordinates are WGS84 degrees derived from `world.origin_lat` /
`world.origin_lon`.

## GET /api/health

```json
{"status": "ok", "version": "0.1.0"}
```

## GET /api/scenario

Returns the static world that the map draws before a mission starts.

```json
{
  "world": {"width_m": 240, "height_m": 180, "origin_lat": 28.7501, "origin_lon": 77.1177},
  "roads": [
    {"orientation": "h", "center_m": 30, "width_m": 7, "from_m": 0, "to_m": 240},
    {"orientation": "v", "center_m": 100, "width_m": 7, "from_m": 0, "to_m": 180}
  ],
  "home": {"x": 6, "y": 6},
  "default_seed": 20261123
}
```

`orientation` is `h` (a road parallel to the x axis at `y = center_m`) or `v`
(a road parallel to the y axis at `x = center_m`).

## POST /api/missions

```json
{"seed": 20261123, "altitude_m": 35, "speed_mps": 8, "multiplier": 8}
```

Response:

```json
{
  "mission_id": "m-8f21c0",
  "plan": {"waypoints": [{"x": 6, "y": 6}, {"x": 24, "y": 6}], "lane_count": 9, "path_length_m": 1180},
  "world": {"width_m": 240, "height_m": 180, "origin_lat": 28.7501, "origin_lon": 77.1177},
  "roads": [...]
}
```

Ground-truth anomalies are NOT included here. They are revealed only in the
`complete` event and in `/api/missions/{id}/evaluation`.

## POST /api/missions/{id}/start

Starts or resumes the simulation. Returns `{"ok": true, "status": "running"}`.

## POST /api/missions/{id}/pause

Returns `{"ok": true, "status": "paused"}`.

## POST /api/missions/{id}/speed

```json
{"multiplier": 4}
```

Accepted range 1 to 16. Returns `{"ok": true, "multiplier": 4}`.

## GET /api/missions/{id}

Snapshot for reconnect and for the first paint.

```json
{
  "mission_id": "m-8f21c0",
  "status": "running",
  "plan": {"waypoints": [...], "lane_count": 9, "path_length_m": 1180},
  "flown": [{"x": 6, "y": 6}],
  "pose": {"x": 12.4, "y": 6.0, "heading_deg": 90.0, "alt_m": 35.0},
  "telemetry": {"speed_mps": 8.0, "battery_pct": 98.2, "elapsed_s": 4.2, "gps_sats": 14, "link_pct": 100},
  "stats": {"coverage_pct": 3.1, "distance_m": 21.0, "frames_captured": 2, "detections": 0, "unique_discrepancies": 0},
  "detections": [{"id": "D-001", "class": "pothole", "confidence": 0.86, "lat": 28.75, "lon": 77.11, "x": 101.2, "y": 30.4, "crop": "data:image/jpeg;base64,..."}]
}
```

## WebSocket /ws/missions/{id}

The server sends one JSON object per message. Event shapes:

```json
{"type": "tick", "pose": {...}, "telemetry": {...}, "stats": {...}, "flown": [{"x": 1, "y": 2}]}
{"type": "detection", "detection": {...}}
{"type": "status", "status": "running"}
{"type": "complete", "stats": {...}, "evaluation": {...}, "ground_truth": [...]}
```

`flown` contains only the points added since the previous tick (usually one).
`detection.crop` is a base64 JPEG data URL, 96x96.

## Evaluation object

```json
{
  "precision": 0.91, "recall": 0.88, "f1": 0.89, "localization_error_m": 0.42,
  "matched": 22, "missed": 3, "false_positives": 2,
  "per_class": [
    {"class": "pothole", "truth": 7, "matched": 6, "false_positives": 1, "precision": 0.86, "recall": 0.86}
  ]
}
```

## Exports

- `GET /api/missions/{id}/report.csv`
- `GET /api/missions/{id}/report.geojson`
- `GET /api/missions/{id}/report.md`

## UI behaviour contract

Single page at `/`. No build step, no framework. Files:
`web/index.html`, `web/styles.css`, `web/app.js`.

Panels:

1. Header: product name `A.U.D.I.T.` and subtitle `Autonomous UAV Discrepancy
   Identification Trials - Mission Control`. Status pill that shows
   `Idle`, `Running`, `Paused`, or `Complete`.
2. Mission panel: seed input, altitude slider (20-50 m), speed slider (4-12
   m/s), `Launch mission` button, `Pause`, `Reset`. Show planned lane count and
   path length once a plan exists.
3. Live map canvas: world grid, roads, planned route (dashed), flown path
   (solid), drone marker with heading, detection pins coloured by class. Click a
   pin to show its crop and confidence.
4. Telemetry strip: coverage %, distance, battery %, frames captured, unique
   discrepancies, elapsed time.
5. Detection feed: newest first, each row shows crop thumbnail, class, confidence
   bar, lat/lon. Empty state: `No discrepancies yet. Launch a mission to begin.`
6. Mission log: one line per meaningful event with simulation time.
7. Scorecard: hidden until `complete`, then shows precision, recall, F1,
   localization error, and per-class rows, plus links to the three exports.

Keyboard: space toggles start/pause. Do not add confirm dialogs for pause or
reset; reset is idempotent.

The UI must keep working when the WebSocket drops: show a `Reconnecting` pill and
retry every 2 seconds, using the snapshot endpoint to catch up.
