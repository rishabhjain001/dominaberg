"""Export helpers: CSV, GeoJSON and a Markdown mission report."""

from __future__ import annotations

import csv
import io
import json

from .mission import Mission


def to_csv(mission: Mission) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "class", "confidence", "lat", "lon", "x_m", "y_m", "observations", "first_seen_s"])
    for d in mission.detections:
        writer.writerow(
            [
                d.id,
                d.cls,
                f"{d.confidence:.3f}",
                f"{d.lat:.7f}",
                f"{d.lon:.7f}",
                f"{d.x:.2f}",
                f"{d.y:.2f}",
                d.hits,
                f"{d.first_seen_s:.1f}",
            ]
        )
    return buf.getvalue()


def to_geojson(mission: Mission) -> str:
    features = []
    for d in mission.detections:
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [round(d.lon, 7), round(d.lat, 7)]},
                "properties": {
                    "id": d.id,
                    "class": d.cls,
                    "confidence": round(d.confidence, 3),
                    "observations": d.hits,
                    "mission": mission.id,
                },
            }
        )
    return json.dumps(
        {"type": "FeatureCollection", "name": "audit-discrepancies", "features": features},
        indent=2,
    )


def to_markdown(mission: Mission) -> str:
    ev = mission.evaluation() if mission.status == "complete" else None
    lines = [
        f"# A.U.D.I.T. mission report - {mission.id}",
        "",
        f"- Seed: {mission.seed}",
        f"- Altitude: {mission.altitude_m:.0f} m AGL",
        f"- Cruise speed: {mission.speed_mps:.1f} m/s",
        f"- Planned path: {mission.plan.path_length_m:.0f} m over {mission.plan.lane_count} lanes",
        f"- Coverage achieved: {mission.stats()['coverage_pct']:.1f}%",
        f"- Frames captured: {mission.frames_captured}",
        f"- Unique discrepancies: {len(mission.detections)}",
        "",
        "## Discrepancy register",
        "",
        "| ID | Class | Confidence | Latitude | Longitude | Observations |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for d in mission.detections:
        lines.append(
            f"| {d.id} | {d.cls} | {d.confidence:.2f} | {d.lat:.6f} | {d.lon:.6f} | {d.hits} |"
        )
    if ev:
        lines += [
            "",
            "## Perception score against ground truth",
            "",
            f"- Precision: {ev['precision']:.2f}",
            f"- Recall: {ev['recall']:.2f}",
            f"- F1: {ev['f1']:.2f}",
            f"- Mean localization error: {ev['localization_error_m']:.2f} m",
            f"- Matched: {ev['matched']}, missed: {ev['missed']}, false positives: {ev['false_positives']}",
        ]
    return "\n".join(lines) + "\n"
