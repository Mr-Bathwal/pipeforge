"""Regenerate artifacts/parts/<part_no>/ for every sample part.

Writes the CAD (STEP, STL), the drawing (PDF, SVG), the YBC program (CSV),
the process sheet (XLSX, PDF), the DFM report and analysis summary (JSON),
and the checking fixture (assembly STEP, plate+blocks STL, one STL per block
for 3D printing). The hosted app serves these files, so it does not need
CadQuery. Run locally or in CI: `python scripts/build_artifacts.py`.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeforge import cad  # noqa: E402
from pipeforge.drawing import DrawingInfo, make_drawing  # noqa: E402
from pipeforge.fixture import export_fixture  # noqa: E402
from pipeforge.parts import sample_parts  # noqa: E402
from pipeforge.pipeline import analyze, in_tubebend_domain  # noqa: E402
from pipeforge.process_sheet import write_excel, write_pdf  # noqa: E402

OUT = ROOT / "artifacts" / "parts"


def build(part_no: str | None = None) -> dict:
    index: dict = {}
    for pn, part in sample_parts().items():
        if part_no and pn != part_no:
            continue
        t0 = time.time()
        d = OUT / pn
        d.mkdir(parents=True, exist_ok=True)
        mode = "ml" if in_tubebend_domain(part) else "physics"
        a = analyze(part, mode)
        info = DrawingInfo(part.part_no, part.name, f"{part.material}", part.od, part.wall, drawn_by="PipeForge")
        drw = make_drawing(part.points, part.clr, info, d / f"{pn}_drawing.pdf", d / f"{pn}_drawing.svg")
        a.ybc.write_csv(d / f"{pn}_ybc.csv", pn)
        write_excel(a, d / f"{pn}_process_sheet.xlsx")
        write_pdf(a, d / f"{pn}_process_sheet.pdf")
        (d / f"{pn}_dfm.json").write_text(json.dumps({"status": a.dfm.status, "counts": a.dfm.counts(),
                                                      "sequence": a.dfm.sequence, "tooling": a.dfm.tooling,
                                                      "checks": a.dfm.as_rows()}, indent=1, default=str),
                                          encoding="utf-8")
        (d / f"{pn}_summary.json").write_text(json.dumps(a.summary(), indent=1, ensure_ascii=False), encoding="utf-8")
        files = {"drawing_scale": drw["scale"]}
        if cad.available():
            solid = cad.tube_solid(part.points, part.clr, part.od, part.wall)
            cad.export(solid, d / f"{pn}.step", None)
            import cadquery as cq

            cq.exporters.export(solid, str(d / f"{pn}.stl"), tolerance=0.1, angularTolerance=0.25)
            files["step_volume_mm3"] = round(cad.solid_volume(solid), 1)
            fx_paths = export_fixture(a.fixture, d / "fixture")
            files["fixture"] = {k: str(Path(v).relative_to(ROOT)).replace("\\", "/") for k, v in fx_paths.items()}
        index[pn] = {"name": part.name, "springback_model": a.springback_model, "dfm": a.dfm.status,
                     "cut_length_mm": round(a.ybc.cut_length, 1), **files, "seconds": round(time.time() - t0, 1)}
        print(pn, index[pn])
    summary = OUT / "index.json"
    old = json.loads(summary.read_text(encoding="utf-8")) if summary.exists() else {}
    old.update(index)
    summary.write_text(json.dumps(old, indent=1), encoding="utf-8")
    dfm_summary = {pn: {"status": v["dfm"], "name": v["name"]} for pn, v in old.items()}
    (OUT / "dfm_summary.json").write_text(json.dumps(dfm_summary, indent=1), encoding="utf-8")
    return index


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else None)
