"""Nominal LRA to a compensated YBC machine program.

YBC is the Eaton Leonard axis naming that most CNC benders use:

* **Y** is the feed of the carriage between bends;
* **B** is the rotation of the collet (the tube) before each bend;
* **C** is the angle the bend die turns through.

LRA describes the part; YBC is what the machine runs. The two differ in
two ways that this module corrects (derivation in ENGINEERING_NOTES, section 4):

1. **Overbend.** After the die releases, the bend opens by the springback
   angle, so the die must turn through C = A + springback.
2. **Radius growth.** The arc keeps its length while it opens, so its radius
   grows from the die's CLR to CLR * C / A. A larger radius has longer
   tangents, which would push every later intersection point outwards. The
   feed before and after each bend is shortened by that tangent growth, so
   the intersection points land where the drawing puts them.

Stretch of the arcs during bending is compensated on the blank (cut length),
not on the feed: see :func:`pipeforge.geometry.developed_length`.

Twist (B correction) is not modelled; B equals the nominal R.
"""

from __future__ import annotations

import csv
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .geometry import LRA, GeometryError

#: springback model: (nominal angle deg, CLR mm) -> springback deg
SpringbackModel = Callable[[float, float], float]


@dataclass(frozen=True)
class YBCRow:
    bend: int
    Y: float  #: feed before this bend, mm
    B: float  #: rotation before this bend, deg, (-180, 180]
    C: float  #: die angle, deg (overbend included)
    springback: float  #: springback assumed for this bend, deg
    radius_after: float  #: arc radius after springback, mm
    nominal_L: float
    nominal_A: float


@dataclass(frozen=True)
class YBCProgram:
    rows: tuple[YBCRow, ...]
    final_Y: float  #: last feed (to the tube end), mm
    model: str  #: which springback model produced it
    cut_length: float  #: blank length, mm

    def as_table(self) -> list[dict[str, float | int]]:
        out: list[dict[str, float | int]] = [
            {
                "bend": r.bend,
                "Y": round(r.Y, 3),
                "B": round(r.B, 3),
                "C": round(r.C, 3),
                "springback": round(r.springback, 3),
                "L nominal": round(r.nominal_L, 3),
                "A nominal": round(r.nominal_A, 3),
            }
            for r in self.rows
        ]
        return out

    def write_csv(self, path: str | Path, part_no: str = "") -> Path:
        """A plain YBC program, one line per bend, as a machine import would take."""
        path = Path(path)
        with path.open("w", newline="", encoding="utf-8") as fh:
            fh.write(f"# PipeForge YBC program{(' for ' + part_no) if part_no else ''}\n")
            fh.write(f"# springback model: {self.model}; cut length {self.cut_length:.2f} mm\n")
            fh.write("# Y = feed mm, B = rotation deg, C = die angle deg (overbend included)\n")
            w = csv.writer(fh)
            w.writerow(["BEND", "Y", "B", "C"])
            for r in self.rows:
                w.writerow([r.bend, f"{r.Y:.2f}", f"{r.B:.2f}", f"{r.C:.2f}"])
            w.writerow(["END", f"{self.final_Y:.2f}", "", ""])
        return path


def no_springback(angle_deg: float, clr: float) -> float:  # noqa: ARG001
    return 0.0


def compensate(
    lra: LRA,
    springback: SpringbackModel = no_springback,
    model_name: str = "none",
    elongation_pct: float = 0.0,
    correct_radius_growth: bool = True,
) -> YBCProgram:
    """Turn a nominal LRA into a YBC program with springback compensation.

    The springback model is evaluated at the nominal angle. For the
    springback ratios seen in tube bending (a few percent), evaluating it at
    the overbent angle instead changes C by far less than the 0.1 deg a
    bender resolves; ENGINEERING_NOTES 4.2 shows the size of that term.
    """
    from .geometry import developed_length

    rows = lra.rows
    sb = [float(springback(r.A, r.clr)) for r in rows]
    for i, s in enumerate(sb, start=1):
        if not math.isfinite(s) or s < 0:
            raise GeometryError(f"bend {i}: springback model returned {s}")
    growth: list[float] = []
    radii: list[float] = []
    for r, s in zip(rows, sb, strict=True):
        c = r.A + s
        if c >= 180.0:
            raise GeometryError(f"bend of {r.A:.1f} deg needs C = {c:.1f} deg, beyond a die's range")
        r_after = r.clr * c / r.A
        radii.append(r_after)
        t_nom = r.clr * math.tan(math.radians(r.A) / 2.0)
        t_after = r_after * math.tan(math.radians(r.A) / 2.0)
        growth.append(t_after - t_nom if correct_radius_growth else 0.0)
    ybc: list[YBCRow] = []
    for i, (r, s) in enumerate(zip(rows, sb, strict=True)):
        before = growth[i - 1] if i > 0 else 0.0
        y = r.L - before - growth[i]
        if y < 0:
            raise GeometryError(
                f"bend {i + 1}: after radius growth the straight before it is {y:.2f} mm; "
                "the bends would overlap"
            )
        ybc.append(YBCRow(bend=i + 1, Y=y, B=r.R, C=r.A + s, springback=s, radius_after=radii[i],
                          nominal_L=r.L, nominal_A=r.A))
    final_y = lra.final_L - (growth[-1] if growth else 0.0)
    if final_y < 0:
        raise GeometryError("the last straight is consumed by radius growth")
    # The die forms CLR * C of arc from the blank; that material length is what is cut.
    cut = sum(r.Y for r in ybc) + final_y + sum(
        r.clr * math.radians(row.C) for r, row in zip(rows, ybc, strict=True)
    ) * (1.0 - elongation_pct / 100.0)
    if not rows:
        cut = developed_length(lra, elongation_pct)
    return YBCProgram(rows=tuple(ybc), final_Y=final_y, model=model_name, cut_length=cut)


def as_lra_after_springback(program: YBCProgram, clrs: Sequence[float]) -> LRA:
    """The part the machine actually makes, if springback is exactly as predicted.

    Each arc opens from C to C - springback at constant arc length, so its
    radius becomes CLR * C / (C - springback). Used by tests to show that a
    compensated program reproduces the nominal intersection points.
    """
    from .geometry import LRARow

    rows = []
    for r, clr in zip(program.rows, clrs, strict=True):
        a_after = r.C - r.springback
        rows.append(LRARow(L=r.Y, R=r.B, A=a_after, clr=clr * r.C / a_after))
    # LRA's L is tangent to tangent at the formed radius; the feed Y is exactly that.
    return LRA(rows=tuple(rows), final_L=program.final_Y)
