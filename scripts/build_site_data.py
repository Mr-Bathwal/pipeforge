"""Write site/data.json: every number and shape the showcase site displays.

The site computes nothing on its own and hard-codes no result: it renders
what this script reads from the repository's artifacts, so the page cannot
drift from the code. Rerun after `make artifacts train sim`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeforge.fixture import design_fixture  # noqa: E402
from pipeforge.geometry import bends, centerline  # noqa: E402
from pipeforge.line_sim import baseline_line  # noqa: E402
from pipeforge.parts import sample_parts  # noqa: E402

OUT = ROOT / "site" / "data.json"


def _r(a, n: int = 2):  # type: ignore[no-untyped-def]
    return np.round(np.asarray(a, dtype=float), n).tolist()


def part_block(part) -> dict:  # type: ignore[no-untyped-def]
    lra = part.lra()
    c = centerline(part.points, part.clr, step_deg=3.0)
    centre = (c.min(axis=0) + c.max(axis=0)) / 2
    return {
        "part_no": part.part_no, "name": part.name, "name_ja": part.name_ja, "category": part.category,
        "material": part.material, "od": part.od, "wall": part.wall, "clr": part.radii,
        "points": _r(part.points - centre), "centerline": _r(c - centre),
        "lra": [{"L": round(r.L, 2), "R": round(r.R, 2), "A": round(r.A, 2), "CLR": r.clr} for r in lra.rows],
        "final_L": round(lra.final_L, 2), "cut_length": round(part.cut_length(), 2),
        "bends": [{"angle": round(b.angle_deg, 2), "point": _r(b.point - centre)} for b in bends(part.points, part.clr)],
    }


def main() -> None:
    parts = sample_parts()
    hero = parts["PF-HB-2201"]
    data: dict = {"generated_by": "scripts/build_site_data.py", "parts": [part_block(p) for p in parts.values()]}
    fx = design_fixture(hero)
    c = centerline(fx.points, fx.clr, step_deg=3.0)
    mid = np.array([(fx.plate_min[0] + fx.plate_max[0]) / 2, (fx.plate_min[1] + fx.plate_max[1]) / 2, 0.0])
    data["fixture"] = {
        "part_no": fx.part_no, "od": fx.od, "clearance": fx.clearance,
        "plate": {"size": _r(fx.plate_size), "min": _r(fx.plate_min - mid[:2]), "max": _r(fx.plate_max - mid[:2])},
        "centerline": _r(c - mid),
        "blocks": [{"id": b.id, "x": round(float(b.contact[0] - mid[0]), 2), "y": round(float(b.contact[1] - mid[1]), 2),
                    "height": round(b.height, 2), "length": b.length, "width": b.width, "yaw": round(b.yaw_deg, 2),
                    "datum": b.datum, "clamp": b.clamp, "sensor": b.sensor} for b in fx.blocks],
        "end_stops": [{"id": e.id, "x": round(float(e.point[0] - mid[0]), 2), "y": round(float(e.point[1] - mid[1]), 2),
                       "z": round(float(e.point[2]), 2)} for e in fx.end_stops],
        "rejected": fx.rejected,
    }
    line = baseline_line()
    data["line"] = {
        "takt_s": round(line.takt_s, 2), "demand_per_day": line.demand_per_day,
        "stations": [{"key": s.key, "name": s.name, "name_ja": s.name_ja, "cycle_s": s.cycle_s,
                      "elements": [{"name": e.name, "s": e.seconds, "kind": e.kind} for e in s.elements]}
                     for s in line.stations],
        "synthetic": True,
    }
    for name, path in (("kaizen", ROOT / "artifacts/line/kaizen_results.json"),
                       ("springback", ROOT / "artifacts/springback/metrics.json"),
                       ("closed_loop", ROOT / "artifacts/springback/closed_loop.json"),
                       ("shap_setup", ROOT / "artifacts/springback/shap_importance_setup.json"),
                       ("dfm", ROOT / "artifacts/parts/dfm_summary.json")):
        if path.exists():
            d = json.loads(path.read_text(encoding="utf-8"))
            if name == "kaizen":
                d = {k: d[k] for k in ("rows", "throughput_gain_pct", "scrap_change_pts", "reps", "days", "smed",
                                         "buffer_curve", "yamazumi_before", "yamazumi_after")}
            data[name] = d
    oof = ROOT / "artifacts/springback/oof_predictions.csv"
    if oof.exists():
        import pandas as pd

        df = pd.read_csv(oof)
        best = data.get("closed_loop", {}).get("models", {}).get("ml")
        if best and best in df:
            data["parity"] = {"measured": _r(df["springback_deg"], 3), "predicted": _r(df[best], 3), "model": best}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB); sections: {', '.join(data)}")


if __name__ == "__main__":
    main()
