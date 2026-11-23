# Screen-2 — Pitch and working model

Dossier `#SEVA-2026-NAT-003-PS-AUDIT`, team `dominaberg`, Track II.
Video length 2:51, under the 5-minute limit.
Save as draft only. Do not submit.

## Video pitch URL

Paste the unlisted YouTube link here after upload.
Fallback download: GitHub release asset `AUDIT-pitch.mp4`.

## 1. Explanation of the proposed solution

A.U.D.I.T. turns one coverage flight into a road-discrepancy register. The input is a ward polygon, a cruise altitude and a cruise speed. The output is one record per defect: class, confidence, latitude, longitude, observation count, time and a cropped frame. The register exports as CSV, GeoJSON and markdown.

Four blocks do the work. A boustrophedon planner lays lanes at 35 percent side overlap, captures a frame every 11.5 m, and holds an 18 percent battery reserve for return to home. The survey holds the camera nadir at 35 m and 8 m/s. Each 640 by 480 frame is masked to the carriageway. Dark and bright responses are measured by convex-hull area and by solidity, the share of that hull that is genuinely dark. Gates label pavement damage, waterlogging, missing cover, pothole and debris, in that order. A record is confirmed only when two frames agree within 3 m. The stored position is the mean of the sightings. Ground truth never enters the detector.

The working model is software. The ward, the camera and the flight are simulated, so a jury can rerun the trial from the repository. Thresholds are fitted to rendered asphalt, not to a field camera. That limit is stated under technical gaps.

## 2. Prototype

Status: Working Software / App MVP
Demo URL: https://github.com/rishabhjain001/dominaberg
Highlights: Mean P 0.774, R 0.826, F1 0.799, localization 0.23 m, five seeds, 186 frames, 100 percent coverage.

## 3. Drawings

No mechanical CAD and no circuit board exist yet. The design artefacts are the architecture diagram, the mission-flow diagram, and the mission-control screen: live map, detection feed, telemetry and an evaluation card.

Camera geometry used by the model: 60 degree horizontal field of view, 640 by 480, footprint 40.4 by 30.3 m at 35 m altitude, 6.3 cm per pixel. Reference ward roads are 7 m wide. These figures are the drawing set for this round.

Diagram: https://github.com/rishabhjain001/dominaberg/blob/vorflux/audit-mission-control/docs/architecture.svg

## 4. Calculations

At 35 m and a 60 degree horizontal field of view, ground width is 2 times 35 times tan(30 degrees), which is 40.4 m. The 4:3 frame gives 30.3 m of height, so one pixel is 40.4 divided by 640, which is 6.3 cm. A 1.5 m pothole is about 24 pixels across.

Lane spacing uses 35 percent side overlap: 30.3 times 0.65 is 19.7 m. Capture spacing is 0.38 of the frame height, 11.5 m, so along-track overlap is about 62 percent. The reference path is 2,224 m. At 8 m/s that is 278 s of flight, 4 min 38 s. Model endurance is 22 min, so the survey uses 21 percent of the battery and lands near 79 percent, above the 18 percent return-to-home gate.

Five seeds give mean precision 0.774, recall 0.826, F1 0.799 and 0.23 m mean localization error. Every seed records 186 frames and 100 percent path coverage. A match needs the same class and a position within 2.0 m. These figures come from the harness, not from a field camera.

## 5. Bill of materials

Planning estimate for one aircraft. Not a quotation. Software licence cost is zero.

1. 450 mm quad frame, Qty 1, Rs 8,000
2. Flight controller with GPS, Qty 1, Rs 18,000
3. Motors and ESCs, Qty 4, Rs 16,000
4. Companion computer, Qty 1, Rs 25,000
5. Nadir camera, Qty 1, Rs 12,000
6. Flight batteries, Qty 3, Rs 15,000
7. Field charger, Qty 1, Rs 4,000
8. Radio link and transmitter, Qty 1, Rs 8,000
9. Operator tablet, Qty 1, Rs 10,000
10. Props, power distribution and wiring, Qty 1 set, Rs 4,000

Total estimated prototype cost: Rs 1,20,000.
Software: Python, OpenCV, NumPy, FastAPI, ArduPilot or PX4, QGIS. No licence fee and no cloud subscription.

## 6. Team roles

The registered team is one member. Rishabh Jain, Guru Tegh Bahadur 4th Centenary Engineering College, holds systems engineering, perception code, the simulation, the tests, the pitch and this dossier. That software work is done and is in the repository.

The field phase needs two roles that are planned and not yet named: a DGCA-certified remote pilot for airworthiness, geofence, permits and flight logs; and a municipal liaison for ward access and engineer review. A student intern covers annotation from the first field week. Until those names are fixed, this dossier does not claim a multi-person hardware team.

## 7. 75-day milestone chart

Software sprint, complete: coverage planner, camera model, five-class detector, two-frame fusion, mission-control dashboard, CSV, GeoJSON and markdown export, 24 tests, and the five-seed scorecard.

Days 1-15, field calibration at three altitudes against 50 known defects: not started. It needs the aircraft and a permitted site.
Days 16-30, move the pipeline onto the companion computer and measure frame timing: not started.
Days 31-45, geofence, return-to-home transit, lost-link behaviour and the safety case: not started.
Days 46-60, two-ward pilot with one urban local body, weekly flights, engineer review: not started.
Days 61-75, GIS import, operator manual, training and handover: not started.

The software trial is the evidence for this round. The 75-day field plan starts when an aircraft and a permitted site are available.

## 8. Technical gaps

1. Thresholds are fitted to rendered asphalt. A real camera, real aggregate and real shadows will move precision. The first field week exists to refit them.
2. Seed 42 scores F1 0.694. The mean hides that spread. Read the five-seed table, not only the mean.
3. Frame-to-waypoint timing is assumed. No airborne test has measured it.
4. Return to home in the model jumps to the last waypoint. A real aircraft must fly a transit leg. The safety case stays open until that leg exists.
5. No aircraft is on the bench, and no Digital Sky permission is filed.

## 9. Risks and mitigation

1. A shadow or a wet patch can pass the gates and create a false repair order. Mitigation: two frames must agree within 3 m, and a person reviews every crop before a work order. The pilot does not auto-dispatch a crew.
2. A ward flight without Digital Sky permission is not legal. Mitigation: no flight until the remote pilot files the permission. This software trial needs no aircraft.
3. Lost link or low battery over a road. Mitigation: 18 percent reserve, a geofence, and a pre-flight checklist in the field phase. The model does not yet fly the return transit, so that risk is not closed.
4. Nadir imagery can contain personal data. Mitigation: imagery stays on the operator device. The export is the register, not the raw film.
5. One person holds the software. Mitigation: the repository, the tests and the five-seed harness are the record. Field work waits for the pilot role.
