"""One call from a part to everything needed to make and check it.

``analyze(part)`` runs geometry, manufacturability, mechanics, compensation
and the fixture design, and returns plain data that the app, the process
sheet, the artifacts script and the LLM assistant all read. Nothing here
invents a number: every value is computed by the modules it calls.

Springback models for compensation:

* ``physics``: the elastic-plastic estimate (mechanics.py), mid flow
  stress. Needs a material with a specified yield strength.
* ``ml``: the TubeBEND model (springback_ml). It is valid only for the
  TubeBEND tube and tooling (22 x 1 mm stainless, CLR 33 mm, mandrel). Within
  that domain the prediction at the 47 deg training angle is scaled in
  proportion to the bend angle, as measured springback grows linearly with
  target angle (Lee and Van Tyne, The Fabricator 2007; ENGINEERING_NOTES 4.3).
  Outside the domain ``analyze`` falls back to physics and says so.
* ``measured``: springback measured on trial bends, given as degrees per
  90 deg of bend and scaled linearly with angle (the shop-floor method).
* ``none``: no compensation (YBC = LRA).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from .compensation import YBCProgram, compensate, no_springback
from .dfm import DFMReport, Machine, check_part
from .fixture import FixtureDesign, design_fixture
from .materials import MATERIALS
from .mechanics import physics_model, springback_band, wall_change
from .parts import Part
from .station import io_list

ROOT = Path(__file__).resolve().parent.parent
ML_DIR = ROOT / "artifacts" / "springback"
TUBEBEND_DOMAIN = {"od": 22.0, "wall": 1.0, "clr": 33.0, "materials": ("SUS304",)}
DEFAULT_SETUP = {"Collet boost": 0.9, "Pressure-die distance": 0.6, "Pressure-die boost": 0.9,
                 "Mandrel retraction timing": 2.0}


@dataclass
class Analysis:
    part: Part
    lra: list[dict]
    ybc: YBCProgram
    springback_model: str
    springback_note: str
    dfm: DFMReport
    bends: list[dict]
    fixture: FixtureDesign
    io: list[dict]
    cut_length_nominal: float
    extra: dict = field(default_factory=dict)

    def summary(self) -> dict:
        """The computed facts, as plain JSON, for the process sheet and the LLM assistant."""
        p = self.part
        return {
            "part_no": p.part_no, "name": p.name, "material": p.material, "od_mm": p.od, "wall_mm": p.wall,
            "n_bends": p.n_bends, "cut_length_nominal_mm": round(self.cut_length_nominal, 1),
            "cut_length_program_mm": round(self.ybc.cut_length, 1),
            "springback_model": self.springback_model,
            "dfm_status": self.dfm.status, "dfm_counts": self.dfm.counts(),
            "dfm_findings": [f"{c.rule} {c.title}: {c.detail}" for c in self.dfm.checks if c.status != "pass"],
            "tooling": self.dfm.tooling.get("class", ""),
            "bend_sequence": self.dfm.sequence,
            "bends": self.bends,
            "fixture_blocks": len(self.fixture.blocks),
            "fixture_clamps": sum(b.clamp for b in self.fixture.blocks),
            "fixture_sensors": len(self.fixture.sensors()),
        }


def in_tubebend_domain(part: Part) -> bool:
    d = TUBEBEND_DOMAIN
    return (abs(part.od - d["od"]) < 0.05 and abs(part.wall - d["wall"]) < 0.05
            and all(abs(r - d["clr"]) < 0.5 for r in part.radii) and part.material in d["materials"])


def ml_springback_at_47(setup: dict | None = None) -> float:
    """TubeBEND setup-only XGBoost prediction (deg) for a machine setup."""
    import numpy as np
    import xgboost as xgb

    meta = json.loads((ML_DIR / "model_meta.json").read_text(encoding="utf-8"))
    info = meta["models"]["springback_setup"]
    setup = {**DEFAULT_SETUP, **(setup or {})}
    row = []
    for f in info["features"]:
        if f in setup:
            row.append(float(setup[f]))
        else:  # nuisance positions: training median of the range
            lo, hi = info["ranges"][f]
            row.append((lo + hi) / 2.0)
    booster = xgb.Booster()
    booster.load_model(str(ML_DIR / "springback_setup.json"))
    return float(booster.predict(xgb.DMatrix(np.array([row]), feature_names=info["features"]))[0])


def analyze(part: Part, springback: str = "physics", machine: Machine | None = None,
            ml_setup: dict | None = None, elongation_pct: float = 0.0,
            measured_per_90: float | None = None) -> Analysis:
    lra = part.lra()
    note = ""
    used = springback
    if springback == "ml":
        if in_tubebend_domain(part) and (ML_DIR / "springback_setup.json").exists():
            base = ml_springback_at_47(ml_setup)

            def model(angle: float, clr: float) -> float:  # noqa: ARG001
                return base * angle / 47.0

            note = (f"ML (TubeBEND, setup-only XGBoost): {base:.2f} deg at 47 deg, scaled linearly with angle; "
                    "valid for this tube and tooling only")
        else:
            used = "physics"
            note = "ML model is valid only for the TubeBEND tube (22 x 1 mm stainless, CLR 33); using physics"
    if springback == "measured":
        if measured_per_90 is None or measured_per_90 < 0:
            raise ValueError("measured mode needs measured_per_90 >= 0 (deg of springback per 90 deg bend)")

        def model(angle: float, clr: float) -> float:  # noqa: ARG001
            return measured_per_90 * angle / 90.0

        note = f"measured on trial bends: {measured_per_90:.2f} deg per 90 deg, scaled linearly with angle"
    if used == "physics":
        mat = MATERIALS.get(part.material)
        if mat is None or mat.yield_mpa is None:
            used = "none"
            model = no_springback
            note = (note + "; " if note else "") + (
                f"{part.material} has no specified yield strength, so no physics estimate: enter a measured "
                "springback from trial bends")
        else:
            model = physics_model(part.od, part.wall, mat, "mid")
            note = note or "physics estimate (elastic-plastic, mean of yield and tensile strength); engineering estimate"
    elif used == "none":
        model = no_springback
        note = "no compensation"
    ybc = compensate(lra, model, used, elongation_pct=elongation_pct)
    mat = MATERIALS.get(part.material)
    bends = []
    for i, (row, y) in enumerate(zip(lra.rows, ybc.rows, strict=True), start=1):
        w = wall_change(part.od, part.wall, row.clr) if row.clr > part.od / 2 else None
        b = {"bend": i, "A_deg": round(row.A, 2), "C_deg": round(y.C, 2), "springback_deg": round(y.springback, 3),
             "CLR_mm": row.clr, "D_of_bend": round(row.clr / part.od, 2),
             "elongation_needed_pct": round(100 * (part.od / 2) / row.clr, 1),
             "wall_outer_mm": round(w.t_outer, 3) if w else None, "thinning_pct": round(w.thinning_pct, 1) if w else None}
        if mat is not None and mat.yield_mpa is not None and row.clr > part.od / 2:
            band = springback_band(row.A, row.clr, part.od, part.wall, mat)
            b["physics_band_deg"] = [round(band.low.springback_deg, 3), round(band.high.springback_deg, 3)]
        bends.append(b)
    fx = design_fixture(part)
    n_clamps = sum(bl.clamp for bl in fx.blocks)
    return Analysis(part=part, lra=lra.as_table(), ybc=ybc, springback_model=used, springback_note=note,
                    dfm=check_part(part, machine), bends=bends, fixture=fx, io=io_list(n_clamps),
                    cut_length_nominal=part.cut_length())


def _fmt(x: float) -> str:
    return f"{x:.2f}" if math.isfinite(x) else "n/a"
