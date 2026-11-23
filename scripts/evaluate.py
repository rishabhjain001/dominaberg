"""Run survey missions and print precision, recall and localization error.

Usage::

    python scripts/evaluate.py                  # one seed
    python scripts/evaluate.py --all-seeds      # the five documented seeds
    python scripts/evaluate.py --seed 42 --frames
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audit.mission import Mission  # noqa: E402

SEEDS = (20261123, 7, 42, 2026, 99)


def run(seed: int, altitude_m: float, speed_mps: float, verbosity: int = 1) -> dict:
    mission = Mission(seed=seed, altitude_m=altitude_m, speed_mps=speed_mps, multiplier=16)
    mission.start()
    while mission.status == "running":
        mission.step(1.0)
    evaluation = mission.evaluation()
    row = {
        "seed": seed,
        "precision": evaluation["precision"],
        "recall": evaluation["recall"],
        "f1": evaluation["f1"],
        "localization_error_m": evaluation["localization_error_m"],
        "reported": len(mission.detections),
        "ground_truth": len(mission.world.anomalies),
        "frames": mission.frames_captured,
        "coverage_pct": mission.stats()["coverage_pct"],
        "per_class": evaluation["per_class"],
    }
    if verbosity:
        print(
            f"seed {seed:>9}  P {row['precision']:.3f}  R {row['recall']:.3f}  "
            f"F1 {row['f1']:.3f}  loc {row['localization_error_m']:.2f} m  "
            f"reported {row['reported']:>2}/{row['ground_truth']}  "
            f"frames {row['frames']:>3}  coverage {row['coverage_pct']:.0f}%"
        )
        if verbosity > 1:
            for item in row["per_class"]:
                print(
                    f"    {item['class']:<16} matched {item['matched']}/{item['truth']:<3} "
                    f"P {item['precision']:.2f}  R {item['recall']:.2f}"
                )
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20261123)
    parser.add_argument("--all-seeds", action="store_true", help="run the five documented seeds")
    parser.add_argument("--altitude", type=float, default=35.0)
    parser.add_argument("--speed", type=float, default=8.0)
    parser.add_argument("--frames", action="store_true", help="print per-class detail")
    args = parser.parse_args()

    seeds = SEEDS if args.all_seeds else (args.seed,)
    rows = [run(s, args.altitude, args.speed, verbosity=2 if args.frames else 1) for s in seeds]
    if len(rows) > 1:
        print(
            "mean            P {:.3f}  R {:.3f}  F1 {:.3f}  loc {:.2f} m".format(
                statistics.mean(r["precision"] for r in rows),
                statistics.mean(r["recall"] for r in rows),
                statistics.mean(r["f1"] for r in rows),
                statistics.mean(r["localization_error_m"] for r in rows),
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
