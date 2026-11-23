"""Build the Screen-1 pitch deck for A.U.D.I.T.

Usage::

    python scripts/build_deck.py [--out docs/AUDIT-screen1.pptx]

The deck follows the 12 Screen-1 points in order, so a reviewer can map each
slide back to the submission form. Screenshots are embedded when present in
``/code/.generated_artifacts/images``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

ROOT = Path(__file__).resolve().parent.parent
SHOTS = Path("/code/.generated_artifacts/images")

INK = RGBColor(0x0B, 0x12, 0x20)
BODY = RGBColor(0x33, 0x41, 0x55)
MUTED = RGBColor(0x6B, 0x7C, 0x93)
ACCENT = RGBColor(0x0F, 0x9E, 0x8F)
ACCENT_SOFT = RGBColor(0xE6, 0xF4, 0xF2)
LINE = RGBColor(0xD8, 0xE0, 0xE8)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

W, H = Inches(13.333), Inches(7.5)


def blank(prs: Presentation):
    return prs.slides.add_slide(prs.slide_layouts[6])


def textbox(slide, x, y, w, h, text, size=18, color=BODY, bold=False, align=PP_ALIGN.LEFT,
            font="Calibri", spacing=1.15, anchor=MSO_ANCHOR.TOP):
    box = slide.shapes.add_textbox(x, y, w, h)
    frame = box.text_frame
    frame.word_wrap = True
    frame.vertical_anchor = anchor
    lines = text.split("\n")
    for i, line in enumerate(lines):
        para = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
        para.alignment = align
        para.line_spacing = spacing
        run = para.add_run()
        run.text = line
        run.font.size = Pt(size)
        run.font.color.rgb = color
        run.font.bold = bold
        run.font.name = font
    return box


def bar(slide, x, y, w, h, color):
    shape = slide.shapes.add_shape(1, x, y, w, h)
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()
    return shape


def rule(slide, x, y, w):
    bar(slide, x, y, w, Emu(9525), LINE)


def header(slide, kicker, title):
    bar(slide, Inches(0.7), Inches(0.62), Inches(0.09), Inches(0.62), ACCENT)
    textbox(slide, Inches(0.95), Inches(0.56), Inches(11.5), Inches(0.3), kicker.upper(),
            size=11, color=ACCENT, bold=True)
    textbox(slide, Inches(0.95), Inches(0.84), Inches(11.9), Inches(0.7), title,
            size=26, color=INK, bold=True)
    rule(slide, Inches(0.7), Inches(1.62), Inches(11.9))


def footer(slide, page):
    textbox(slide, Inches(0.7), Inches(6.95), Inches(8), Inches(0.3),
            "A.U.D.I.T.  |  NAT-003-PS-AUDIT  |  SEVA FIRST RYIC 2026", size=10, color=MUTED)
    textbox(slide, Inches(11.9), Inches(6.95), Inches(0.8), Inches(0.3), str(page),
            size=10, color=MUTED, align=PP_ALIGN.RIGHT)


def bullet_block(slide, x, y, w, items, size=15, gap=0.42):
    for i, (head, body) in enumerate(items):
        top = y + Inches(gap * i)
        textbox(slide, x, top, w, Inches(0.28), head, size=size, color=INK, bold=True)
        textbox(slide, x, top + Inches(0.26), w, Inches(0.34), body, size=12.5, color=BODY)


def table(slide, x, y, w, rows, col_widths, header_row=True, size=12):
    shape = slide.shapes.add_table(len(rows), len(rows[0]), x, y, w, Inches(0.34 * len(rows)))
    tbl = shape.table
    for j, width in enumerate(col_widths):
        tbl.columns[j].width = Inches(width)
    for i, row in enumerate(rows):
        for j, value in enumerate(row):
            cell = tbl.cell(i, j)
            cell.text = str(value)
            cell.margin_left = Inches(0.08)
            cell.margin_top = Inches(0.04)
            cell.margin_bottom = Inches(0.04)
            para = cell.text_frame.paragraphs[0]
            para.alignment = PP_ALIGN.RIGHT if j > 0 and i > 0 else PP_ALIGN.LEFT
            for run in para.runs:
                run.font.size = Pt(size)
                run.font.name = "Calibri"
                if i == 0 and header_row:
                    run.font.bold = True
                    run.font.color.rgb = WHITE
                else:
                    run.font.color.rgb = INK if not (i == len(rows) - 1 and i > 0) else WHITE
                    run.font.bold = i == len(rows) - 1
            cell.fill.solid()
            if i == 0 and header_row:
                cell.fill.fore_color.rgb = INK
            elif i == len(rows) - 1 and i > 0:
                cell.fill.fore_color.rgb = ACCENT
            else:
                cell.fill.fore_color.rgb = WHITE if i % 2 else ACCENT_SOFT
    return tbl


def picture(slide, path: Path, x, y, w=None, h=None):
    if not path.exists():
        return False
    kwargs = {"left": x, "top": y}
    if w:
        kwargs["width"] = w
    if h:
        kwargs["height"] = h
    slide.shapes.add_picture(str(path), **kwargs)
    return True


def slide_title(prs):
    s = blank(prs)
    bar(s, Inches(0), Inches(0), W, H, INK)
    bar(s, Inches(0.9), Inches(2.5), Inches(0.12), Inches(1.9), ACCENT)
    textbox(s, Inches(1.2), Inches(2.35), Inches(9.5), Inches(1.0), "A.U.D.I.T.", size=54, color=WHITE, bold=True)
    textbox(s, Inches(1.2), Inches(3.35), Inches(10.4), Inches(0.5),
            "Autonomous UAV Discrepancy Identification Trials", size=22, color=ACCENT)
    textbox(s, Inches(1.2), Inches(3.95), Inches(10.4), Inches(0.9),
            "A reproducible aerial survey that turns a ward's roads into a georeferenced\n"
            "register of potholes, missing covers, waterlogging, debris and pavement damage.",
            size=14, color=RGBColor(0xC5, 0xD2, 0xE0))
    rule(s, Inches(1.2), Inches(5.15), Inches(6.0))
    textbox(s, Inches(1.2), Inches(5.35), Inches(10.6), Inches(1.2),
            "Dossier #SEVA-2026-NAT-003-PS-AUDIT   |   Track II: Diploma and Higher Education\n"
            "Rishabh Jain, Guru Tegh Bahadur 4th Centenary Engineering College\n"
            "SEVA FIRST - Rashtriya Youth Innovation Challenge 2026",
            size=13, color=RGBColor(0x93, 0xA6, 0xC0), spacing=1.3)


def slide_problem(prs, page):
    s = blank(prs)
    header(s, "Screen-1 point 1 and 3", "Roads are inspected by memory, not measurement")
    textbox(s, Inches(0.7), Inches(1.85), Inches(6.3), Inches(1.0),
            "A junior engineer walks a beat and logs defects on paper. A citizen files a "
            "complaint with a photo. Both routes are slow, subjective and blind to every "
            "road between complaints.", size=14.5, color=BODY, spacing=1.35)

    stats = [("4,446", "pothole accidents", "MoRTH, 2022"),
             ("1,856", "pothole deaths", "MoRTH, 2022"),
             ("4,900+", "urban local bodies", "each runs manual beats"),
             ("45-60 min", "to walk 2 km", "measured in Delhi")]
    for i, (big, label, note) in enumerate(stats):
        col, row = i % 2, i // 2
        x = Inches(0.7 + col * 3.15)
        y = Inches(3.15 + row * 1.62)
        bar(s, x, y, Inches(2.9), Inches(1.42), ACCENT_SOFT)
        textbox(s, x + Inches(0.18), y + Inches(0.10), Inches(2.6), Inches(0.52), big, size=26, color=ACCENT, bold=True)
        textbox(s, x + Inches(0.18), y + Inches(0.66), Inches(2.6), Inches(0.34), label, size=12.5, color=INK, bold=True)
        textbox(s, x + Inches(0.18), y + Inches(1.02), Inches(2.6), Inches(0.3), note, size=10.5, color=MUTED)

    textbox(s, Inches(7.4), Inches(1.85), Inches(5.3), Inches(0.35), "What the walk cannot see", size=16, color=INK, bold=True)
    textbox(s, Inches(7.4), Inches(2.25), Inches(5.2), Inches(3.9),
            "- Sunken utility covers that read as flat asphalt\n"
            "- Shallow waterlogging that dries before the complaint\n"
            "- Crack networks that split one defect into five\n"
            "- The same defect reported three times by three citizens\n"
            "- Roads that are never reported at all\n\n"
            "The gap is not vision. It is the workflow: capture, confirm,\n"
            "georeference, export, repeat.",
            size=13.5, color=BODY, spacing=1.45)
    footer(s, page)


def slide_solution(prs, page):
    s = blank(prs)
    header(s, "Screen-1 point 1, 4 and 7", "One aircraft, one pass, one discrepancy register")
    steps = [("Plan", "Ward polygon, altitude 15-60 m, speed 3-15 m/s.\nBoustrophedon path with 35 % overlap,\nlanes, length and ETA before take-off."),
             ("Fly", "Waypoint following at 8 m/s and 35 m AGL.\nNadir camera, 60 deg HFOV, 40.4 x 30.3 m\nfootprint, 6.3 cm per pixel."),
             ("Detect", "Carriageway mask, dark and bright response,\nhull geometry and solidity, five classes\nwith confidence, entirely on board."),
             ("Confirm", "Two frames must agree within 3 m.\nPosition is the running mean of sightings.\nSingle-frame noise never reaches the register."),
             ("Export", "CSV for the works ledger, GeoJSON for\nthe GIS, markdown for the file, plus a\nlive map an engineer can click.")]
    for i, (name, body) in enumerate(steps):
        x = Inches(0.55 + i * 2.47)
        bar(s, x, Inches(2.0), Inches(2.25), Inches(2.4), ACCENT_SOFT)
        textbox(s, x + Inches(0.15), Inches(2.12), Inches(2.0), Inches(0.4), f"0{i + 1}", size=13, color=ACCENT, bold=True)
        textbox(s, x + Inches(0.15), Inches(2.42), Inches(2.0), Inches(0.35), name, size=17, color=INK, bold=True)
        textbox(s, x + Inches(0.15), Inches(2.85), Inches(1.98), Inches(1.4), body, size=10.5, color=BODY, spacing=1.25)
    picture(s, SHOTS / "final-running.png", Inches(0.7), Inches(4.32), w=Inches(4.0))
    textbox(s, Inches(5.05), Inches(4.45), Inches(7.6), Inches(2.2),
            "The operator does three things: choose a ward, press start, export the register. "
            "Everything between is the aircraft's job.\n\n"
            "Result on the reference ward: 100 % of the planned 2,224 m path flown, "
            "23 of 23 discrepancies found, 0.23 m mean localization error.",
            size=13, color=BODY, spacing=1.35)
    footer(s, page)


def slide_math(prs, page):
    s = blank(prs)
    header(s, "Screen-1 point 7 - conceptual design", "Every defect is seen three times at 6 cm per pixel")
    textbox(s, Inches(0.7), Inches(1.85), Inches(5.6), Inches(0.35), "Sensor and geometry", size=16, color=INK, bold=True)
    table(s, Inches(0.7), Inches(2.25), Inches(5.6), [
        ["Parameter", "Value"],
        ["Camera", "640 x 480, 4:3, 60 deg HFOV"],
        ["Cruise altitude", "35 m AGL (range 15-60 m)"],
        ["Ground footprint", "40.4 x 30.3 m"],
        ["Ground sample distance", "6.3 cm per pixel"],
        ["1.5 m pothole", "24 px across"],
        ["Capture spacing", "11.5 m (38 % of swath)"],
        ["Overlap between frames", "3-4 looks per defect"],
    ], [2.2, 3.0], size=11.5)

    textbox(s, Inches(7.0), Inches(1.85), Inches(5.4), Inches(0.35), "Why the numbers work", size=16, color=INK, bold=True)
    textbox(s, Inches(7.0), Inches(2.25), Inches(5.3), Inches(3.6),
            "One look is not evidence. A shadow, a lane marking or a wet patch can look like "
            "a pothole in a single frame.\n\n"
            "Three or four looks from different positions give the fusion stage enough "
            "agreeing evidence to confirm a defect, and enough angles to separate a cover "
            "from a pothole from a pool.\n\n"
            "The battery reserve gate (18 %) turns a long survey into two safe sorties "
            "instead of one forced landing.",
            size=13, color=BODY, spacing=1.35)
    picture(s, ROOT / "docs" / "mission-flow.svg" if (ROOT / "docs" / "mission-flow.png").exists() else ROOT / "docs" / "mission-flow.png",
            Inches(7.0), Inches(4.55), w=Inches(5.3))
    footer(s, page)


def slide_perception(prs, page):
    s = blank(prs)
    header(s, "Screen-1 point 6 - novelty", "Five defect classes separated by geometry alone")
    rows = [["Class", "Signature", "Gate"],
            ["Pothole", "small, solid, dark, no bright collar", "hull 0.2-3.8 m2, solid > 0.5"],
            ["Missing cover", "small, solid, bright collar", "ring ratio > 2.6, hull < 1.7 m2"],
            ["Waterlogging", "large, solid, dark, low saturation", "hull > 4 m2, solid > 0.5"],
            ["Debris", "bright compact pile on asphalt", "hull 0.6-9 m2, circ > 0.22"],
            ["Pavement damage", "thin sparse crack network", "solid < 0.45, hull > 0.6 m2"]]
    table(s, Inches(0.7), Inches(1.9), Inches(7.4), rows, [1.7, 3.3, 2.4], size=11.5)

    textbox(s, Inches(0.7), Inches(4.55), Inches(7.4), Inches(0.9),
            "Two measurements do the work: the filled hull of a blob's response (its true "
            "footprint, even when only the rim responds) and the share of that footprint that "
            "is genuinely dark. A pool is large and solid; a crack network is thin and sparse.",
            size=12.5, color=BODY, spacing=1.3)
    textbox(s, Inches(0.7), Inches(5.55), Inches(7.4), Inches(0.8),
            "Every class threshold is a number in one file, so a new city can be calibrated "
            "from fifty measured defects instead of a retraining campaign.",
            size=12.5, color=BODY, spacing=1.3)

    textbox(s, Inches(8.6), Inches(1.9), Inches(3.9), Inches(0.35), "Why this is different", size=16, color=INK, bold=True)
    bullet_block(s, Inches(8.6), Inches(2.3), Inches(3.9), [
        ("Register, not imagery", "class, confidence, coordinates, crop, time"),
        ("Temporal proof", "two agreeing frames before a report"),
        ("Edge only", "no cloud, no subscription, no upload"),
        ("Inspectable", "every threshold is a readable number"),
    ], size=12.5, gap=0.98)
    footer(s, page)


def slide_results(prs, page, metrics):
    s = blank(prs)
    header(s, "Screen-1 point 2 - evidence", "Five survey runs, scored against held-out truth")
    rows = [["Seed", "Precision", "Recall", "F1", "Loc. error", "Reported", "Frames", "Coverage"]]
    for m in metrics:
        rows.append([m["seed"], f"{m['precision']:.3f}", f"{m['recall']:.3f}", f"{m['f1']:.3f}",
                     f"{m['localization_error_m']:.2f} m", f"{m['reported']}/{m['ground_truth']}",
                     m["frames"], f"{m['coverage_pct']:.0f} %"])
    rows.append(["Mean", f"{sum(m['precision'] for m in metrics) / len(metrics):.3f}",
                 f"{sum(m['recall'] for m in metrics) / len(metrics):.3f}",
                 f"{sum(m['f1'] for m in metrics) / len(metrics):.3f}",
                 f"{sum(m['localization_error_m'] for m in metrics) / len(metrics):.2f} m", "", "", "100 %"])
    table(s, Inches(0.7), Inches(1.95), Inches(11.9), rows, [1.1, 1.4, 1.3, 1.2, 1.5, 1.4, 1.2, 1.4], size=12)

    textbox(s, Inches(0.7), Inches(4.35), Inches(5.6), Inches(0.35), "Per-class recall, reference run", size=14, color=INK, bold=True)
    ref = metrics[0]["per_class"]
    for i, item in enumerate(ref):
        y = Inches(4.75 + i * 0.4)
        textbox(s, Inches(0.7), y, Inches(1.9), Inches(0.3), item["class"].replace("_", " "), size=11.5, color=BODY)
        width = max(0.04, 2.6 * item["recall"])
        bar(s, Inches(2.6), y + Inches(0.05), Inches(width), Inches(0.18), ACCENT)
        textbox(s, Inches(2.6 + width + 0.1), y, Inches(1.0), Inches(0.3),
                f"{item['matched']}/{item['truth']}", size=11, color=MUTED)

    textbox(s, Inches(7.0), Inches(4.35), Inches(5.5), Inches(0.35), "How the score is computed", size=14, color=INK, bold=True)
    textbox(s, Inches(7.0), Inches(4.75), Inches(5.4), Inches(2.0),
            "The simulator holds 23 planted discrepancies and never hands them to the "
            "detector. A report counts as correct when its class matches and its position is "
            "within 2 m of the plant. Localization error is the mean distance of matched "
            "reports. The run is reproducible: same seed, same survey, same score.",
            size=12.5, color=BODY, spacing=1.3)
    footer(s, page)


def slide_cost(prs, page):
    s = blank(prs)
    header(s, "Screen-1 point 8 - cost versus benefit", "INR 1.2 lakh replaces a walking beat")
    rows = [["Item", "INR"],
            ["Quad frame, motors, ESCs, propellers", "18,000"],
            ["Flight controller with GPS", "12,000"],
            ["Companion computer, 8 GB edge module", "35,000"],
            ["Nadir camera, 12 MP, global shutter", "22,000"],
            ["Battery packs x3 and charger", "24,000"],
            ["Telemetry, wiring, enclosure, guards", "9,000"],
            ["Total", "1,20,000"]]
    table(s, Inches(0.7), Inches(1.95), Inches(5.7), rows, [4.3, 1.4], size=12)

    textbox(s, Inches(6.9), Inches(1.95), Inches(5.7), Inches(0.35), "Cost per survey", size=16, color=INK, bold=True)
    textbox(s, Inches(6.9), Inches(2.35), Inches(5.5), Inches(1.4),
            "2.2 km of coverage: 22 minutes of flight, one battery swap, about 15 minutes "
            "of operator time. A manual beat of the same length: 45-60 minutes of an engineer "
            "plus travel, and no register at the end.", size=12.5, color=BODY, spacing=1.3)
    textbox(s, Inches(6.9), Inches(3.6), Inches(5.7), Inches(0.35), "What the city gains", size=16, color=INK, bold=True)
    textbox(s, Inches(6.9), Inches(4.0), Inches(5.5), Inches(2.4),
            "- Weekly coverage instead of complaint-driven coverage\n"
            "- A repair queue sorted by class and measured area\n"
            "- A photograph attached to every work order\n"
            "- A dated audit trail for every ward\n"
            "- Software cost: zero. Everything is open source.",
            size=12.5, color=BODY, spacing=1.45)
    footer(s, page)


def slide_plan(prs, page):
    s = blank(prs)
    header(s, "Screen-1 point 9 - 75-day plan", "Three sprints from simulation to a signed pilot")
    phases = [("Days 1-15", "Field calibration", "Fly the reference ward at three altitudes, re-measure 50 known defects, fit class thresholds to local asphalt.", "Calibration note and confusion matrix"),
              ("Days 16-30", "Flight integration", "Move the pipeline onto the companion computer, stabilise the gimbal, verify frame timing against waypoints.", "Airborne build with live link"),
              ("Days 31-45", "Autonomy and safety", "Geofence, return to home, wind limits, lost-link behaviour, pre-flight checklist.", "Safety case reviewed by the UAV lab"),
              ("Days 46-60", "Municipal pilot", "Two wards, weekly flights for four weeks, engineer review of every detection.", "Pilot report with measured precision"),
              ("Days 61-75", "Hardening and handover", "CSV and GeoJSON into the ward GIS, operator manual, training, final demonstration.", "Repeatable weekly survey service")]
    for i, (when, name, work, out) in enumerate(phases):
        y = Inches(1.9 + i * 0.98)
        textbox(s, Inches(0.7), y, Inches(1.5), Inches(0.3), when, size=12.5, color=ACCENT, bold=True)
        textbox(s, Inches(2.25), y - Inches(0.02), Inches(2.5), Inches(0.52), name, size=13.5, color=INK, bold=True)
        textbox(s, Inches(4.8), y, Inches(4.6), Inches(0.7), work, size=11, color=BODY, spacing=1.2)
        textbox(s, Inches(9.6), y, Inches(3.1), Inches(0.7), out, size=11, color=MUTED, spacing=1.2)
        if i < len(phases) - 1:
            rule(s, Inches(0.7), y + Inches(0.82), Inches(11.9))
    textbox(s, Inches(0.7), Inches(6.7), Inches(11.9), Inches(0.3),
            "Status today: the days 1-30 functionality is demonstrated in software. The field phase above is the remaining plan.",
            size=11.5, color=MUTED)
    footer(s, page)


def slide_team(prs, page):
    s = blank(prs)
    header(s, "Screen-1 point 10 and 11", "A three-person field team, one aircraft, no cloud bill")
    textbox(s, Inches(0.7), Inches(1.9), Inches(5.4), Inches(0.35), "Team", size=16, color=INK, bold=True)
    textbox(s, Inches(0.7), Inches(2.3), Inches(5.3), Inches(3.4),
            "Rishabh Jain - team leader\n"
            "Systems engineering, perception and simulation, documentation. Guru Tegh Bahadur "
            "4th Centenary Engineering College, Track II.\n\n"
            "Flight operations lead (college UAV lab)\n"
            "DGCA-certified remote pilot. Airworthiness, geofence, permits, flight logs.\n\n"
            "Municipal liaison (urban local body)\n"
            "Ward selection, engineer review sessions, data protection.\n\n"
            "Part-time intern from day 30\n"
            "Annotation and data quality checks.",
            size=12, color=BODY, spacing=1.3)

    textbox(s, Inches(6.5), Inches(1.9), Inches(6.1), Inches(0.35), "Resources requested", size=16, color=INK, bold=True)
    rows = [["Resource", "Detail"],
            ["Hardware", "One 450 mm quad, companion computer, camera, 3 batteries, charger, tablet"],
            ["Software", "Python, OpenCV, NumPy, FastAPI; ArduPilot or PX4; QGIS at the city end"],
            ["Data", "Ward boundary and base map from the urban local body. Imagery stays on device."],
            ["Facilities", "College UAV lab, permitted test area, Digital Sky clearance per ward"],
            ["Budget", "INR 1.2 lakh capital, INR 25,000 for pilot consumables and travel"]]
    table(s, Inches(6.5), Inches(2.3), Inches(6.1), rows, [1.3, 4.8], size=10.5)
    footer(s, page)


def slide_trl(prs, page):
    s = blank(prs)
    header(s, "Screen-1 point 12 - readiness", "TRL 4 today, TRL 6 inside the programme")
    levels = [("TRL 3", "Analytical and experimental proof of concept", True),
              ("TRL 4", "Integrated workflow validated in a controlled environment", True),
              ("TRL 5", "Real airframe, calibrated on measured defects", False),
              ("TRL 6", "Two wards, engineer-reviewed pilot, signed report", False)]
    for i, (level, text, done) in enumerate(levels):
        y = Inches(1.95 + i * 0.95)
        bar(s, Inches(0.7), y, Inches(1.1), Inches(0.62), ACCENT if done else line_color())
        textbox(s, Inches(0.85), y + Inches(0.16), Inches(1.0), Inches(0.3), level, size=13,
                color=WHITE if done else INK, bold=True)
        textbox(s, Inches(2.0), y + Inches(0.12), Inches(5.4), Inches(0.4), text, size=13, color=INK)
        textbox(s, Inches(7.5), y + Inches(0.14), Inches(4.9), Inches(0.3),
                "done" if done else "planned in this programme", size=11.5, color=MUTED)

    textbox(s, Inches(0.7), Inches(5.9), Inches(11.9), Inches(1.0),
            "The architecture is already flight-ready: perception and fusion take a frame plus a camera "
            "model as input, so the simulator is replaced by a camera stream without touching detection, "
            "fusion or export. The evidence pack, the dashboard and the test suite ship with this submission.",
            size=12.5, color=BODY, spacing=1.3)
    footer(s, page)


def line_color():
    return RGBColor(0xE2, 0xE8, 0xF0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="docs/AUDIT-screen1.pptx")
    args = parser.parse_args()

    metrics = json.loads((ROOT / "docs" / "trial-results.json").read_text())
    prs = Presentation()
    prs.slide_width, prs.slide_height = W, H

    slide_title(prs)
    slide_problem(prs, 2)
    slide_solution(prs, 3)
    slide_math(prs, 4)
    slide_perception(prs, 5)
    slide_results(prs, 6, metrics)
    slide_cost(prs, 7)
    slide_plan(prs, 8)
    slide_team(prs, 9)
    slide_trl(prs, 10)

    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    prs.save(out)
    print(f"wrote {out} ({len(prs.slides.__iter__.__self__._sldIdLst)} slides)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
