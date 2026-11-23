"""Mission execution: fly the plan, capture frames, run perception, report.

The mission runs as a plain state machine. The API layer steps it on a timer,
which keeps the simulator independent from the transport and makes the tests
deterministic.
"""

from __future__ import annotations

import base64
import math
import time
import uuid
from dataclasses import dataclass, field

import cv2

from .detect import Detection, detect_tile
from .geo import enu_to_latlon
from .plan import Plan, plan_coverage
from .render import Camera, render_tile
from .world import World, build_world

BATTERY_ENDURANCE_S = 22 * 60.0
DEDUPE_RADIUS_M = 3.0
MATCH_RADIUS_M = 2.0
# A discrepancy is only reported after two independent frames agree on it.
# Single-frame blobs are almost always road texture or a lane marking.
CONFIRM_HITS = 2


@dataclass
class Track:
    """A discrepancy fused across frames."""

    id: str
    cls: str
    x: float
    y: float
    confidence: float
    hits: int
    lat: float
    lon: float
    crop: str
    first_seen_s: float
    confirmed: bool = False

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "class": self.cls,
            "confidence": round(self.confidence, 3),
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "lat": round(self.lat, 7),
            "lon": round(self.lon, 7),
            "hits": self.hits,
            "crop": self.crop,
        }


def _crop_data_url(img, det: Detection, size: int = 96) -> str:
    pad = 6
    x0 = max(0, det.u - pad)
    y0 = max(0, det.v - pad)
    x1 = min(img.shape[1], det.u + det.w + pad)
    y1 = min(img.shape[0], det.v + det.h + pad)
    patch = img[y0:y1, x0:x1]
    if patch.size == 0:
        patch = img
    patch = cv2.resize(patch, (size, size), interpolation=cv2.INTER_CUBIC)
    ok, buf = cv2.imencode(".jpg", patch, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    if not ok:
        return ""
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode("ascii")


class Mission:
    def __init__(self, seed: int = 20261123, altitude_m: float = 35.0, speed_mps: float = 8.0, multiplier: float = 8.0):
        self.id = "m-" + uuid.uuid4().hex[:6]
        self.seed = seed
        self.altitude_m = altitude_m
        self.speed_mps = speed_mps
        self.multiplier = multiplier
        self.world: World = build_world(seed)
        self.plan: Plan = plan_coverage(self.world, altitude_m)
        self.camera = Camera(altitude_m)

        self.status = "idle"  # idle | running | paused | complete
        self.elapsed_s = 0.0
        self.distance_m = 0.0
        self.battery_pct = 100.0
        self.frames_captured = 0
        self.detections: list[Track] = []  # confirmed tracks only
        self._tracks: list[Track] = []
        self.log: list[dict] = []

        # Route as a dense polyline so the flown path is easy to draw.
        self._route = self.plan.waypoints
        self._leg = 0
        self._leg_progress = 0.0
        self.pose = (self._route[0][0], self._route[0][1], 90.0)
        self.flown: list[tuple[float, float]] = [(self.pose[0], self.pose[1])]
        self._since_capture = 1e9
        self._returning = False

    # ------------------------------------------------------------------ state
    def snapshot(self) -> dict:
        x, y, heading = self.pose
        return {
            "mission_id": self.id,
            "status": self.status,
            "seed": self.seed,
            "altitude_m": self.altitude_m,
            "multiplier": self.multiplier,
            "plan": self.plan.as_dict(),
            "flown": [{"x": round(px, 2), "y": round(py, 2)} for px, py in self.flown],
            "pose": {"x": round(x, 2), "y": round(y, 2), "heading_deg": round(heading, 1), "alt_m": self.altitude_m},
            "telemetry": self.telemetry(),
            "stats": self.stats(),
            "detections": [d.as_dict() for d in self.detections],
            "log": self.log[-40:],
        }

    def telemetry(self) -> dict:
        return {
            "speed_mps": round(self.speed_mps, 2),
            "battery_pct": round(self.battery_pct, 1),
            "elapsed_s": round(self.elapsed_s, 1),
            "gps_sats": 14,
            "link_pct": 100,
        }

    def stats(self) -> dict:
        return {
            "coverage_pct": round(self.coverage_pct(), 1),
            "distance_m": round(self.distance_m, 1),
            "frames_captured": self.frames_captured,
            "detections": sum(d.hits for d in self.detections),
            "unique_discrepancies": len(self.detections),
        }

    def coverage_pct(self) -> float:
        total = self.plan.path_length_m
        if total <= 0:
            return 0.0
        return max(0.0, min(100.0, 100.0 * self.distance_m / total))

    # ------------------------------------------------------------------- step
    def step(self, dt_sim: float) -> list[dict]:
        """Advance the mission. Returns the events produced by this step."""
        if self.status != "running":
            return []

        events: list[dict] = []
        remaining = dt_sim
        while remaining > 1e-6 and self.status == "running":
            slice_s = min(remaining, 0.5)
            self._advance(slice_s, events)
            remaining -= slice_s
        return events

    def _advance(self, dt: float, events: list[dict]) -> None:
        # Battery drain is linear in time, plus a small cost per capture.
        self.battery_pct -= 100.0 * dt / BATTERY_ENDURANCE_S
        self.elapsed_s += dt

        if self.battery_pct <= 18.0 and not self._returning:
            self._returning = True
            self._route = [self.plan.waypoints[-1], self.world.home]
            self._leg = 0
            self._leg_progress = 0.0
            self._log("Return to home triggered (battery reserve)", events)

        if self._leg >= len(self._route) - 1:
            self._finish(events)
            return

        a = self._route[self._leg]
        b = self._route[self._leg + 1]
        leg_len = math.hypot(b[0] - a[0], b[1] - a[1])
        if leg_len <= 0:
            self._leg += 1
            return

        travel = self.speed_mps * dt
        self._leg_progress += travel
        self.distance_m += travel
        self._since_capture += travel

        while self._leg_progress >= leg_len and self._leg < len(self._route) - 1:
            self._leg_progress -= leg_len
            self._leg += 1
            if self._leg >= len(self._route) - 1:
                break
            a = self._route[self._leg]
            b = self._route[self._leg + 1]
            leg_len = math.hypot(b[0] - a[0], b[1] - a[1])
            if leg_len <= 0:
                continue

        a = self._route[self._leg]
        b = self._route[min(self._leg + 1, len(self._route) - 1)]
        t = min(1.0, self._leg_progress / max(leg_len, 1e-6))
        x = a[0] + (b[0] - a[0]) * t
        y = a[1] + (b[1] - a[1]) * t
        heading = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
        self.pose = (x, y, heading)
        if not self.flown or math.hypot(x - self.flown[-1][0], y - self.flown[-1][1]) > 0.8:
            self.flown.append((x, y))

        if self._since_capture >= self.plan.capture_spacing_m:
            self._since_capture = 0.0
            for ev in self._capture():
                events.append(ev)

        events.append(
            {
                "type": "tick",
                "pose": {"x": round(x, 2), "y": round(y, 2), "heading_deg": round(heading, 1), "alt_m": self.altitude_m},
                "telemetry": self.telemetry(),
                "stats": self.stats(),
                "flown": [{"x": round(self.flown[-1][0], 2), "y": round(self.flown[-1][1], 2)}],
            }
        )

    def _capture(self) -> list[dict]:
        events: list[dict] = []
        x, y, heading = self.pose
        img = render_tile(self.world, x, y, heading, self.camera)
        self.frames_captured += 1

        for det in detect_tile(img, self.camera):
            wx, wy = self.camera.px_to_world(*det.center_px, x, y, heading)
            if not (0 <= wx <= self.world.width_m and 0 <= wy <= self.world.height_m):
                continue
            track = self._fuse(wx, wy, det, img)
            if track is not None:
                events.append({"type": "detection", "detection": track.as_dict(), "stats": self.stats()})
        return events

    def _fuse(self, wx: float, wy: float, det: Detection, img) -> Track | None:
        """Attach an observation to a track, or open a new one.

        Pending tracks accept a nearby observation of any class, because a
        single frame often mislabels a defect. A confirmed record keeps its
        class: a different class within 1.5 m is treated as the same physical
        defect seen differently, so it adds evidence but never a second record.
        """
        for t in self._tracks:
            distance = math.hypot(t.x - wx, t.y - wy)
            same_class = t.cls == det.cls
            if t.confirmed:
                matched = distance <= (DEDUPE_RADIUS_M if same_class else 1.5)
            else:
                matched = distance <= 1.6
            if not matched:
                continue

            t.hits += 1
            if not t.confirmed or same_class:
                t.x = (t.x * (t.hits - 1) + wx) / t.hits
                t.y = (t.y * (t.hits - 1) + wy) / t.hits
                if det.confidence > t.confidence:
                    t.confidence = det.confidence
                    t.crop = _crop_data_url(img, det)
                    if not t.confirmed:
                        t.cls = det.cls
            if t.confirmed:
                return None
            if t.hits >= CONFIRM_HITS:
                t.confirmed = True
                t.id = f"D-{len(self.detections) + 1:03d}"
                t.lat, t.lon = enu_to_latlon(t.x, t.y, self.world.origin_lat, self.world.origin_lon)
                self.detections.append(t)
                self._merge_confirmed(t)
                return t
            return None

        lat, lon = enu_to_latlon(wx, wy, self.world.origin_lat, self.world.origin_lon)
        track = Track(
            id="pending",
            cls=det.cls,
            x=wx,
            y=wy,
            confidence=det.confidence,
            hits=1,
            lat=lat,
            lon=lon,
            crop=_crop_data_url(img, det),
            first_seen_s=round(self.elapsed_s, 1),
        )
        self._tracks.append(track)
        if CONFIRM_HITS <= 1:
            track.confirmed = True
            track.id = f"D-{len(self.detections) + 1:03d}"
            self.detections.append(track)
            return track
        return None

    def _merge_confirmed(self, track: Track) -> None:
        """Collapse a second confirmed record of the same class at the same spot.

        Two lobes of one large pool can each collect their own confirmation
        sequence. The register must still hold one entry per physical defect.
        """
        for other in list(self.detections):
            if other is track or other.cls != track.cls:
                continue
            if math.hypot(other.x - track.x, other.y - track.y) <= DEDUPE_RADIUS_M:
                track.hits += other.hits
                track.confidence = max(track.confidence, other.confidence)
                self.detections.remove(other)
                self._tracks.remove(other)

    def _finish(self, events: list[dict]) -> None:
        self.status = "complete"
        self._log("Mission complete - survey coverage achieved", events)
        events.append({"type": "status", "status": "complete", "stats": self.stats()})
        events.append(
            {
                "type": "complete",
                "stats": self.stats(),
                "evaluation": self.evaluation(),
                "ground_truth": [a.as_dict() for a in self.world.anomalies],
            }
        )

    # ------------------------------------------------------------ evaluation
    def evaluation(self) -> dict:
        truth = self.world.anomalies
        unmatched = list(self.detections)
        matched_pairs: list[tuple[Track, object]] = []
        for gt in truth:
            best = None
            best_d = 1e9
            for t in unmatched:
                if t.cls != gt.kind:
                    continue
                d = math.hypot(t.x - gt.x, t.y - gt.y)
                if d <= MATCH_RADIUS_M and d < best_d:
                    best, best_d = t, d
            if best is not None:
                matched_pairs.append((best, gt))
                unmatched.remove(best)

        per_class = []
        for cls in sorted({g.kind for g in truth} | {d.cls for d in self.detections}):
            n_truth = sum(1 for g in truth if g.kind == cls)
            n_matched = sum(1 for _, g in matched_pairs if g.kind == cls)
            n_fp = sum(1 for d in unmatched if d.cls == cls)
            precision = n_matched / (n_matched + n_fp) if (n_matched + n_fp) else 0.0
            recall = n_matched / n_truth if n_truth else 0.0
            per_class.append(
                {
                    "class": cls,
                    "truth": n_truth,
                    "matched": n_matched,
                    "false_positives": n_fp,
                    "precision": round(precision, 3),
                    "recall": round(recall, 3),
                }
            )

        tp = len(matched_pairs)
        fp = len(unmatched)
        fn = len(truth) - tp
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        err = (
            sum(math.hypot(t.x - g.x, t.y - g.y) for t, g in matched_pairs) / len(matched_pairs)
            if matched_pairs
            else 0.0
        )
        return {
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
            "localization_error_m": round(err, 2),
            "matched": tp,
            "missed": fn,
            "false_positives": fp,
            "per_class": per_class,
        }

    # ------------------------------------------------------------------ misc
    def _log(self, message: str, events: list[dict]) -> None:
        entry = {"t": round(self.elapsed_s, 1), "message": message}
        self.log.append(entry)
        events.append({"type": "log", "entry": entry})

    def start(self) -> None:
        if self.status in ("idle", "paused"):
            self.status = "running"

    def pause(self) -> None:
        if self.status == "running":
            self.status = "paused"
