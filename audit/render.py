"""Downward-looking camera simulator.

Renders what the UAV sees from its altitude: asphalt, kerbs, lane markings,
roof tops, and the ground-truth discrepancies placed by :mod:`audit.world`.

The renderer is intentionally imperfect - it adds sensor noise, a lighting
gradient, motion blur and JPEG compression - so the perception stack has to
cope with something closer to a real camera feed than a clean vector drawing.
"""

from __future__ import annotations

import math

import cv2
import numpy as np

from .world import Anomaly, World

HFOV_DEG = 60.0
ASPECT = 4.0 / 3.0


def footprint_m(altitude_m: float) -> tuple[float, float]:
    width = 2.0 * altitude_m * math.tan(math.radians(HFOV_DEG / 2.0))
    return width, width * 0.75


class Camera:
    """Pinhole camera model over a flat ground plane."""

    def __init__(self, altitude_m: float, size: tuple[int, int] = (640, 480)) -> None:
        self.altitude_m = altitude_m
        self.width_px, self.height_px = size
        self.ground_w, self.ground_h = footprint_m(altitude_m)
        self.m_per_px = self.ground_w / self.width_px

    def world_to_px(self, x: float, y: float, cam_x: float, cam_y: float, heading_deg: float):
        h = math.radians(heading_deg)
        dx, dy = x - cam_x, y - cam_y
        forward = dx * math.cos(h) + dy * math.sin(h)
        right = dx * math.sin(h) - dy * math.cos(h)
        u = 0.5 + right / self.ground_w
        v = 0.5 - forward / self.ground_h
        return u * self.width_px, v * self.height_px

    def px_to_world(self, u: float, v: float, cam_x: float, cam_y: float, heading_deg: float):
        h = math.radians(heading_deg)
        right = (u / self.width_px - 0.5) * self.ground_w
        forward = (0.5 - v / self.height_px) * self.ground_h
        x = cam_x + forward * math.cos(h) + right * math.sin(h)
        y = cam_y + forward * math.sin(h) - right * math.cos(h)
        return x, y


def _noise_field(rng: np.random.Generator, shape, scale: float) -> np.ndarray:
    small = rng.normal(0.0, 1.0, (max(2, shape[0] // 16), max(2, shape[1] // 16)))
    field = cv2.resize(small, (shape[1], shape[0]), interpolation=cv2.INTER_CUBIC)
    return cv2.GaussianBlur(field, (0, 0), scale)


def _rotated_rect(cam: Camera, cx, cy, w, h, angle_rad, heading):
    ca, sa = math.cos(angle_rad), math.sin(angle_rad)
    pts = []
    for ox, oy in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)):
        wx = cx + ox * ca - oy * sa
        wy = cy + ox * sa + oy * ca
        pts.append(cam.world_to_px(wx, wy, *heading))
    return np.array(pts, dtype=np.int32)


def _draw_pothole(img, cam, an: Anomaly, heading, rng):
    cx, cy = cam.world_to_px(an.x, an.y, *heading)
    r = an.radius_m / cam.m_per_px
    ang = np.linspace(0, 2 * math.pi, 14, endpoint=False)
    wobble = 1.0 + 0.22 * np.sin(ang * 3 + an.shape_seed % 7) + 0.12 * np.sin(ang * 5)
    pts = np.stack([cx + r * wobble * np.cos(ang), cy + r * wobble * np.sin(ang)], axis=1).astype(np.int32)
    cv2.fillPoly(img, [pts], (28, 30, 34))
    inner = 0.62
    pts2 = np.stack([cx + r * inner * wobble * np.cos(ang), cy + r * inner * wobble * np.sin(ang)], axis=1).astype(np.int32)
    cv2.fillPoly(img, [pts2], (12, 14, 18))
    cv2.polylines(img, [pts], True, (58, 60, 64), 1, cv2.LINE_AA)


def _draw_missing_cover(img, cam, an: Anomaly, heading, rng):
    cx, cy = cam.world_to_px(an.x, an.y, *heading)
    r = an.radius_m / cam.m_per_px
    cv2.circle(img, (int(cx), int(cy)), int(r * 1.35), (96, 98, 100), -1, cv2.LINE_AA)
    cv2.circle(img, (int(cx), int(cy)), int(r * 1.12), (60, 62, 64), -1, cv2.LINE_AA)
    cv2.circle(img, (int(cx), int(cy)), int(r), (10, 11, 13), -1, cv2.LINE_AA)


def _draw_water(img, cam, an: Anomaly, heading, rng):
    cx, cy = cam.world_to_px(an.x, an.y, *heading)
    r = an.radius_m / cam.m_per_px
    axes = (int(r * 1.15), int(r * 0.82))
    cv2.ellipse(img, (int(cx), int(cy)), axes, an.angle * 180 / math.pi, 0, 360, (54, 42, 30), -1, cv2.LINE_AA)
    cv2.ellipse(img, (int(cx), int(cy)), (int(r * 0.7), int(r * 0.5)), an.angle * 180 / math.pi, 0, 360, (66, 52, 36), -1, cv2.LINE_AA)


def _draw_debris(img, cam, an: Anomaly, heading, rng):
    """A compact rubble pile: one bright irregular blob plus a few blocks."""
    r = an.radius_m / cam.m_per_px
    ang = np.linspace(0, 2 * math.pi, 12, endpoint=False)
    wobble = 1.0 + 0.30 * np.sin(ang * 2 + an.shape_seed % 11) + 0.15 * np.sin(ang * 4)
    pts = np.stack([cx := (cam.world_to_px(an.x, an.y, *heading)[0] + r * wobble * np.cos(ang)),
                    (cam.world_to_px(an.x, an.y, *heading)[1] + r * wobble * np.sin(ang))], axis=1).astype(np.int32)
    cv2.fillPoly(img, [pts], (176, 172, 162))
    cv2.polylines(img, [pts], True, (120, 118, 112), 2, cv2.LINE_AA)
    for _ in range(5):
        ox = rng.normal(0, an.radius_m * 0.4)
        oy = rng.normal(0, an.radius_m * 0.4)
        quad = _rotated_rect(cam, an.x + ox, an.y + oy, 0.22, 0.22, rng.uniform(0, math.pi), heading)
        tone = int(rng.uniform(150, 196))
        cv2.fillPoly(img, [quad], (tone, tone - 6, tone - 14))


def _draw_pavement_damage(img, cam, an: Anomaly, heading, rng):
    rng2 = np.random.default_rng(an.shape_seed)
    for _ in range(4):
        x, y = an.x, an.y
        pts = []
        for _ in range(7):
            x += rng2.normal(0, an.radius_m * 0.32)
            y += rng2.normal(0, an.radius_m * 0.32)
            pts.append(cam.world_to_px(x, y, *heading))
        cv2.polylines(img, [np.array(pts, dtype=np.int32)], False, (36, 40, 46), 4, cv2.LINE_AA)


def render_tile(
    world: World,
    cam_x: float,
    cam_y: float,
    heading_deg: float,
    camera: Camera,
    supersample: int = 2,
    apply_sensor_effects: bool = True,
) -> np.ndarray:
    """Return a BGR image of what the camera sees at this pose."""
    S = supersample
    W, H = camera.width_px * S, camera.height_px * S
    rng = np.random.default_rng(world.seed + int(cam_x * 7) + int(cam_y * 13) + int(heading_deg))
    heading = (cam_x, cam_y, heading_deg)

    # Work at supersampled scale by temporarily scaling the camera model.
    big = Camera.__new__(Camera)
    big.altitude_m = camera.altitude_m
    big.width_px, big.height_px = W, H
    big.ground_w, big.ground_h = camera.ground_w, camera.ground_h
    big.m_per_px = camera.ground_w / W

    img = np.zeros((H, W, 3), dtype=np.uint8)
    base = 118.0 + _noise_field(rng, (H, W), 2.0) * 6.0
    img[:, :, 0] = np.clip(base * 0.96, 0, 255).astype(np.uint8)
    img[:, :, 1] = np.clip(base * 1.0, 0, 255).astype(np.uint8)
    img[:, :, 2] = np.clip(base * 0.88, 0, 255).astype(np.uint8)

    # Roof tops with a small sun shadow.
    for b in world.buildings:
        quad = _rotated_rect(big, b.x + b.w / 2, b.y + b.h / 2, b.w, b.h, 0.0, heading)
        shadow = quad + np.array([int(1.5 / big.m_per_px), int(1.5 / big.m_per_px)], dtype=np.int32)
        cv2.fillPoly(img, [shadow], (92, 94, 96))
        tone = int(150 * b.tone + 60)
        cv2.fillPoly(img, [quad], (tone - 10, tone, tone + 2))
        cv2.polylines(img, [quad], True, (70, 72, 76), 2, cv2.LINE_AA)

    # Roads.
    for r in world.roads:
        if r.orientation == "h":
            quad = np.array(
                [
                    big.world_to_px(r.from_m, r.center_m - r.width_m / 2, *heading),
                    big.world_to_px(r.to_m, r.center_m - r.width_m / 2, *heading),
                    big.world_to_px(r.to_m, r.center_m + r.width_m / 2, *heading),
                    big.world_to_px(r.from_m, r.center_m + r.width_m / 2, *heading),
                ],
                dtype=np.int32,
            )
        else:
            quad = np.array(
                [
                    big.world_to_px(r.center_m - r.width_m / 2, r.from_m, *heading),
                    big.world_to_px(r.center_m - r.width_m / 2, r.to_m, *heading),
                    big.world_to_px(r.center_m + r.width_m / 2, r.to_m, *heading),
                    big.world_to_px(r.center_m + r.width_m / 2, r.from_m, *heading),
                ],
                dtype=np.int32,
            )
        cv2.fillPoly(img, [quad], (72, 74, 78))
        cv2.polylines(img, [quad], True, (150, 152, 154), 2, cv2.LINE_AA)

        # Dashed centre line.
        length = (r.to_m - r.from_m) if r.orientation == "v" else (r.to_m - r.from_m)
        step = 6.0
        s = r.from_m
        while s < r.to_m:
            e = min(s + 3.0, r.to_m)
            if r.orientation == "h":
                p1 = big.world_to_px(s, r.center_m, *heading)
                p2 = big.world_to_px(e, r.center_m, *heading)
            else:
                p1 = big.world_to_px(r.center_m, s, *heading)
                p2 = big.world_to_px(r.center_m, e, *heading)
            cv2.line(img, (int(p1[0]), int(p1[1])), (int(p2[0]), int(p2[1])), (215, 216, 214), 2, cv2.LINE_AA)
            s += step

    # Anomalies. Only draw the ones inside the footprint plus a margin.
    margin = 4.0
    for an in world.anomalies:
        if abs(an.x - cam_x) > camera.ground_w * 0.85 + margin:
            continue
        if abs(an.y - cam_y) > camera.ground_h * 0.85 + margin:
            continue
        if an.kind == "pothole":
            _draw_pothole(img, big, an, heading, rng)
        elif an.kind == "missing_cover":
            _draw_missing_cover(img, big, an, heading, rng)
        elif an.kind == "waterlogging":
            _draw_water(img, big, an, heading, rng)
        elif an.kind == "debris":
            _draw_debris(img, big, an, heading, rng)
        else:
            _draw_pavement_damage(img, big, an, heading, rng)

    img = cv2.resize(img, (camera.width_px, camera.height_px), interpolation=cv2.INTER_AREA)

    if apply_sensor_effects:
        # Mild lens blur, lighting gradient, sensor noise and JPEG artefacts.
        img = cv2.GaussianBlur(img, (3, 3), 0.6)
        yy, xx = np.mgrid[0 : img.shape[0], 0 : img.shape[1]]
        vignette = 1.0 - 0.18 * (((xx - img.shape[1] / 2) / img.shape[1]) ** 2 + ((yy - img.shape[0] / 2) / img.shape[0]) ** 2)
        img = np.clip(img.astype(np.float32) * vignette[..., None], 0, 255).astype(np.uint8)
        noise = rng.normal(0, 3.2, img.shape)
        img = np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)
        ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 72])
        if ok:
            img = cv2.imdecode(buf, cv2.IMREAD_COLOR)

    return img
