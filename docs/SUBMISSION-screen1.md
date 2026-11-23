# A.U.D.I.T. - Screen 1 dossier (NAT-003-PS-AUDIT)

Paste-ready answers for the 12 Screen-1 fields. Character counts are noted per
field. Working software, test numbers and exports are in this repository.

Trial numbers quoted below come from five simulated survey runs
(seeds 20261123, 7, 42, 2026, 99) and are reproducible with
`python scripts/evaluate.py --all-seeds`.

---

## 1. Problem statement

Indian city roads are inspected by hand. A junior engineer walks or drives a
beat and logs defects on paper, or a citizen files a complaint with a photo.
Both routes are slow, subjective and blind to the road network between
complaints. The result is late repair, repeated complaints and avoidable harm:
MoRTH recorded 4,446 pothole-related accidents, 1,856 deaths and 3,734 injuries
in 2022 alone.

A.U.D.I.T. replaces the walk with a repeatable aerial trial. A small
multi-rotor UAV flies a coverage path over a ward, captures nadir imagery, and
runs an on-board detector that identifies five road discrepancies in one pass:
potholes, missing utility covers, waterlogging, debris and pavement damage.
Every detection becomes a georeferenced record with a cropped photograph, a
class, a confidence score and a timestamp. A municipal engineer receives a
discrepancy register, not a photograph album: a CSV for the works ledger, a
GeoJSON layer for the GIS, and a markdown report for the file.

*Character count: 1,035*

## 2. Observation evidence

Evidence comes from three sources.

1. Field observation. A beat inspection of one 2 km municipal road in Delhi
   takes 45-60 minutes on foot and produces a paper list. The same road carries
   defects that a rider cannot see from a two-wheeler: sunken covers, shallow
   waterlogging and crack networks.
2. Published data. MoRTH "Road Accidents in India 2022" reports 4,446 accidents
   and 1,856 deaths on potholed roads. CAG audits and Lok Sabha answers record
   the same failure of routine inspection.
3. Engineering measurement. We built a 240 x 180 m reference ward (7 roads,
   23 known discrepancies, 5 classes) and ran five survey missions. Each
   mission covered 100 % of the planned path (2,224 m, 186 frames). Mean
   detection precision is 0.77, recall 0.83, F1 0.80, with 0.23 m mean
   localization error against the surveyed ground truth.

The third source matters most: it shows that a camera alone is not enough and
that the gap is in the *workflow* - capture, confirm, georeference, export.

*Character count: 1,010*

## 3. Affected demographic count

The direct users are municipal road-maintenance departments: more than 4,900
urban local bodies in India, plus state public works departments and national
highway concessionaires. A single ward-level road engineer typically owns
20-60 km of carriageway, so the primary user group is in the tens of thousands
of engineers and contractors.

The affected population is far larger. Urban India holds about 500 million
residents who use municipal roads daily: commuters, school transport, delivery
riders, ambulances and pedestrians. MoRTH counts 4,446 pothole accidents and
1,856 deaths in 2022, and every one of those events happened on a road that
somebody was already paid to inspect.

A secondary group is the informal repair economy - contractors and small firms
who quote repairs from photographs. A calibrated discrepancy register with area
and location lets them price work without a site visit.

*Character count: 950*

## 4. User interaction

The operator interacts at three points, and only the first one needs a person.

1. Plan. The engineer selects the ward boundary, cruise altitude (15-60 m) and
   cruise speed (3-15 m/s). A.U.D.I.T. computes a boustrophedon coverage path
   with overlap, then shows lane count, path length and expected flight time
   before take-off.
2. Fly. The mission runs itself. The dashboard streams position, battery,
   coverage, frames captured and detections. The operator can pause, resume or
   change simulation speed. A battery reserve of 18 % triggers an automatic
   return to home.
3. Review. Detections arrive as a live feed of thumbnail crops with class,
   confidence and coordinates. The engineer clicks a pin to inspect the crop,
   then exports the register as CSV, GeoJSON or markdown. The keyboard shortcut
   Space starts and pauses a mission.

A field crew that has never seen the tool can run a full survey after a
ten-minute briefing: plan, launch, wait, export.

*Character count: 1,020*

## 5. Existing solutions and gaps

Three families of tools exist today.

Manual inspection and citizen complaint apps (Swachhata, municipal 311
portals, WhatsApp helplines). Strength: cheap to start. Gap: coverage depends
on complaints, so quiet roads are never inspected; reports are uncalibrated
photographs, not measurements.

Vehicle-mounted road scanners (laser profilers, multi-camera vans). Strength:
high accuracy. Gap: they must drive the road, so they cannot inspect a footpath,
a flooded underpass or a lane blocked by traffic; capital cost is in crores, and
processing is usually a post-hoc survey, not a live map.

Drone survey firms with cloud photogrammetry. Strength: good imagery. Gap: the
deliverable is an orthomosaic, not a defect register. Classification is manual
or a generic vision model, single-frame false positives are common, and the
data leaves the city network.

No product in the Indian municipal market combines an autonomous coverage
flight, on-board multi-class detection, multi-frame confirmation and a
georeferenced export in one run. That combination is the gap A.U.D.I.T. closes.

*Character count: 1,065*

## 6. Novelty

Four design choices separate A.U.D.I.T. from an image classifier bolted to a
drone.

1. Discrepancy register, not imagery. The output is a record per defect: class,
   confidence, latitude, longitude, first-seen time, observation count, crop.
   It drops straight into a works ledger or a GIS layer.
2. Temporal confirmation instead of a single-frame threshold. A candidate is
   reported only after two independent frames agree within 3 m, and its position
   is the running mean of the sightings. Single-frame noise, lane markings and
   shadows never reach the register.
3. Footprint geometry, not blob area. Each blob is measured by the filled hull
   of its response and by the share of that footprint that is genuinely dark.
   This separates a water pool (large, solid), a missing cover (small, solid,
   bright collar), a pothole (small, solid, no collar) and a crack network
   (thin, sparse) without a trained model.
4. Closed loop, on the edge. Planning, flight, detection, fusion and export run
   in one process with no cloud dependency, so a ward with poor connectivity
   still produces a complete register.

*Character count: 1,040*

## 7. Conceptual sketches

The system has four blocks and one data contract.

```
ward polygon + flight limits
        |
        v
[1] Coverage planner  --boustrophedon path, 35 % overlap, RTH reserve
        |
        v
[2] Survey autopilot -- waypoint following, gimbal nadir, 8 m/s, 35 m AGL
        |  frame stream (640 x 480, 4:3, 60 deg HFOV, 40 x 30 m footprint)
        v
[3] Perception        -- carriageway mask -> dark/bright response ->
        |                 hull geometry + solidity -> class + confidence
        v
[4] Temporal fusion   -- 3 m association, 2-frame confirmation, mean position
        |
        v
  register: CSV / GeoJSON / markdown + live map
```

Frame math: at 35 m altitude the footprint is 40.4 x 30.3 m, so one pixel spans
6.3 cm. A 1.5 m pothole is 24 pixels across. Capture spacing is 11.5 m, so each
defect appears in three to four frames - enough for confirmation and for a
second look at low-contrast defects.

Reference sketches in the repository: `docs/architecture.svg` (system blocks)
and `docs/mission-flow.svg` (state machine: idle -> flying -> returning ->
complete, with the battery trigger).

*Character count: 1,030*

## 8. Cost vs benefit

Prototype bill of materials, one aircraft.

| Item | Cost (INR) |
| --- | --- |
| 450 mm quad frame, motors, ESCs, props | 18,000 |
| Flight controller with GPS (ArduPilot/PX4 class) | 12,000 |
| Companion computer (8 GB edge module) | 35,000 |
| Nadir camera, 12 MP, global shutter | 22,000 |
| Battery pack x3, charger | 24,000 |
| Telemetry radio, wiring, enclosure, prop guards | 9,000 |
| **Total** | **1,20,000** |

Cost per survey: a 2.2 km coverage flight takes 22 minutes of flight time and
one battery swap, roughly 15 minutes of operator time. A manual beat inspection
of the same length costs 45-60 minutes of an engineer plus travel, and it
produces no register.

Benefit: one ward surveyed weekly instead of after complaints; a repair queue
sorted by class and area; photographic evidence attached to every work order;
and a measurable fall in repeat complaints. A single avoided injury claim or
one avoided re-paving contract outweighs the aircraft cost many times over.
The trial also produces the audit trail that CAG audits ask for.

*Character count: 1,020*

## 9. 75-day work plan

Days 1-15, field calibration. Fly the reference ward at three altitudes,
re-measure 50 known defects, fit class thresholds to local asphalt. Deliverable:
calibration note and a per-class confusion matrix.

Days 16-30, flight integration. Move the pipeline to the companion computer,
add gimbal stabilisation, verify frame timing against waypoints, and measure
on-board throughput. Deliverable: airborne build with a live link.

Days 31-45, autonomy and safety. Geofence, return-to-home on battery reserve,
wind limits, lost-link behaviour, and a pre-flight checklist. Deliverable:
safety case reviewed by the institute's UAV lab.

Days 46-60, municipal pilot. Two wards with one urban local body, weekly
flights for four weeks, engineer review of every detection, and
precision/recall measured against their repair records. Deliverable: pilot
report.

Days 61-75, hardening and handover. CSV/GeoJSON import into the ward GIS,
operator manual, training session, and the final demo. Deliverable: repeatable
weekly survey service.

Current status: days 1-30 functionality is demonstrated in software; the plan
above is the field phase.

*Character count: 1,040*

## 10. Team composition

The registered dossier is a single-member team: Rishabh Jain (leader), Guru Tegh
Bahadur 4th Centenary Engineering College, Track II - Diploma and Higher
Education.

Roles held by the lead: systems engineering, perception and simulation code,
field testing and documentation. The 75-day plan adds two named roles that the
college has agreed to support through its UAV lab:

- Flight operations lead, remote pilot certified under DGCA rules, responsible
  for airworthiness, geofence, permits and flight logs.
- Municipal liaison, responsible for ward selection, engineer review sessions
  and data-protection compliance with the urban local body.

A student intern covers annotation and data QA from day 30. The team is
deliberately small: the system is one aircraft, one operator and one export, so
additional people add coordination cost before they add coverage.

*Character count: 890*

## 11. Resource requirements

Hardware: one 450 mm class quad with a companion computer and a nadir camera
(see the cost table), three battery packs, a field charger, a rugged tablet for
the operator, and a laptop for post-flight review. Estimated INR 1.2 lakh.

Software: all open source. Python, OpenCV, NumPy, FastAPI; ArduPilot or PX4 for
flight control; QGIS on the municipal side for the GeoJSON layer. No licence
cost and no cloud subscription.

Data: a ward boundary polygon and a base map from the urban local body. Imagery
stays on the operator's device, which keeps personal data out of the cloud.

People: the lead, one certified remote pilot, one municipal liaison and a
part-time intern, as described in the team section.

Facilities: the college UAV lab for assembly, calibration and test flights, and
a permitted flying area for the weekly ward sorties. Airspace permission for
each survey area is requested through the Digital Sky platform.

*Character count: 950*

## 12. Technology readiness level

Current TRL: 4. The complete workflow - coverage planning, simulated flight,
multi-class detection, temporal fusion, georeferenced export and a live
operations dashboard - is integrated and validated in a controlled environment.
Five survey runs over the reference ward give mean precision 0.77, recall 0.83,
F1 0.80 and 0.23 m localization error, with 100 % path coverage each time.

What is missing for TRL 5: flight on the real airframe, calibration against
measured defects on real asphalt, and validation under wind, sun angle and
shadow conditions. Those are exactly the first 45 days of the work plan.

TRL 6 is reachable inside the programme: two wards, four weekly sorties each,
engineer-reviewed detections, and a signed pilot report. The architecture is
already flight-ready - the perception and fusion modules take a frame and a
camera model as input, so the simulator is swapped for a camera stream without
touching the detection or export paths.

*Character count: 980*
