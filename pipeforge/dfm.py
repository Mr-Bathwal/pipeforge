"""Manufacturability checks for rotary-draw bending: pass, warn or fail, each with its rule and source.

Rules (sources and reasoning in docs/ENGINEERING_NOTES.md, section 5):

* D1 **D of bend** (CLR / OD): 1D is extreme, 2D severe, 3D optimal
  (Pines); below 1D is specialist territory (Yamato publicly reports 0.6D).
* D2 **Wall factor** (OD / t) with D of bend: mandrel and wiper-die
  selection from the Bend Tooling Inc. chart, with its material and
  bend-angle column shifts.
* D3 **Straight between bends** at least the clamp length (Bend Tooling:
  5 OD - CLR, not less than 2 OD) and the Pines minimum distance between bends.
* D4 **Leading and trailing ends**: first straight at least 2 OD without
  boost (McGrew), else add clamping stock and trim; collet depth at least 0.5 OD.
* D5 **Bend angle** within the machine's range.
* D6 **Collision while bending**: the bend sequence is simulated in the
  machine frame and the swinging part checked against the floor and the
  machine body, for bending from either end.
* D7 **Self-interference**: no two parts of the finished tube closer than OD.
* D8 **Elongation required** at the extrados, (OD/2)/CLR, against the
  material's specified minimum; JIS does not guarantee elongation for tubes
  of 40 mm OD or less, so then it must go into the purchase specification.
* D9 **Wall thinning and ovality** (engineering estimates, for information).

Machine values are an illustrative envelope for a generic electric CNC
rotary-draw bender, not a particular model: replace them with the real
machine's data sheet.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

import numpy as np

from .geometry import LRA, LRARow, centerline, lra_to_xyz
from .mechanics import wall_change
from .parts import Part

PASS, WARN, FAIL = "pass", "warn", "fail"


@dataclass(frozen=True)
class Machine:
    """Illustrative bender envelope (replace with the real machine's data)."""

    name: str = "Generic CNC rotary-draw bender (illustrative)"
    max_od: float = 42.0
    max_angle_deg: float = 180.0
    boost: bool = False  #: pressure-die / collet boost fitted (shortens the first straight needed)
    serrated_clamp: bool = False  #: serrated clamp insert (Bend Tooling Ks = 1 instead of 2)
    axis_height_mm: float = 1050.0  #: tube axis above the floor
    body_behind_mm: float = 3500.0  #: machine bed length behind the bend die
    body_half_width_mm: float = 300.0
    body_below_axis_mm: float = 150.0  #: bed top below the tube axis (parts may swing above it)
    body_above_axis_mm: float = 400.0  #: bend head and carriage above the axis near the die
    head_length_mm: float = 450.0  #: length behind the die where the head rises above the axis


@dataclass
class Check:
    rule: str
    title: str
    status: str
    detail: str
    where: str = ""
    source: str = ""


@dataclass
class DFMReport:
    part_no: str
    checks: list[Check] = field(default_factory=list)
    sequence: str = ""  #: recommended bending direction
    tooling: dict = field(default_factory=dict)

    @property
    def status(self) -> str:
        s = {c.status for c in self.checks}
        return FAIL if FAIL in s else WARN if WARN in s else PASS

    def counts(self) -> dict[str, int]:
        return {k: sum(c.status == k for c in self.checks) for k in (PASS, WARN, FAIL)}

    def as_rows(self) -> list[dict]:
        return [asdict(c) for c in self.checks]


# ------------------------------------------------------------------ bend die chart

#: Bend Tooling Inc., "Mandrel and Wiper Selection Chart" (2011), transcribed in
#: docs/ENGINEERING_NOTES.md section 5.2. Rows: wall factor OD/t. Columns: D of bend CLR/OD.
#: Code: 1st N/R/C/D = no mandrel / regular / close / double-close pitch; 2nd 0 = plug,
#: 1-9 = balls; 3rd N/W/H = no wiper / inserted mandrel + wiper / high-pressure tooling.
CHART_SOURCE = "Bend Tooling Inc. mandrel and wiper selection chart (ENGINEERING_NOTES 5.2)"
CHART_COLS = (0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 7.0, 9.0, 12.0)
CHART: dict[int, tuple[str, ...]] = {
    0: ("NNN",) * 12,
    5: ("R0N",) + ("NNN",) * 11,
    7: ("R1N", "R0N", "R0N", "R0N") + ("NNN",) * 8,
    10: ("R1W", "R1N", "R1N", "R1N", "R0N", "R0N", "R0N") + ("NNN",) * 5,
    15: ("R2W", "R1W", "R1W", "R1N", "R1N", "R1N", "R1N", "R0N") + ("NNN",) * 4,
    20: ("R2W", "R2W", "R2W", "R1W", "R1W", "R1N", "R1N", "R0N", "R0N", "NNN", "NNN", "NNN"),
    25: ("R3W", "R2W", "R2W", "R2W", "R1W", "R1W", "R1W", "R1N", "R0N", "R0N", "NNN", "NNN"),
    30: ("R3W", "R3W", "R3W", "R2W", "R2W", "R2W", "R1W", "R1W", "R1N", "R0N", "R0N", "R0N"),
    35: ("R3W", "R3W", "R3W", "R3W", "R2W", "R2W", "R2W", "R2W", "R1W", "R0N", "R0N", "R0N"),
    40: ("C4W", "R3W", "R3W", "R3W", "R3W", "R2W", "R2W", "R2W", "R2W", "R1N", "R0N", "R0N"),
    45: ("C4H", "C4W", "R3W", "R3W", "R3W", "R3W", "R2W", "R2W", "R2W", "R1W", "R0N", "R0N"),
    50: ("C4H", "C4W", "C4W", "R3W", "R3W", "R3W", "R3W", "R3W", "R3W", "R2W", "R1N", "R0N"),
    60: ("C4H", "C4H", "C4W", "C4W", "R3W", "R3W", "R3W", "R3W", "R3W", "R2W", "R1W", "R0N"),
    70: ("C5H", "C4H", "C4H", "C4W", "C4W", "R3W", "R3W", "R3W", "R3W", "R3W", "R2W", "R1N"),
    80: ("C5H", "C5H", "C5H", "C4H", "C4H", "C4H", "C4H", "C4H", "C4H", "R3W", "R2W", "R1W"),
    90: ("C5H", "C5H", "C5H", "C5H", "C5H", "C4H", "C4H", "C4H", "C4H", "C4H", "R3W", "R2W"),
    100: ("C6H", "C5H", "C5H", "C5H", "C5H", "C5H", "C5H", "C4H", "C4H", "C4H", "C4H", "R3W"),
    125: ("C6H", "C6H", "C6H", "C5H", "C5H", "C5H", "C5H", "C5H", "C5H", "C4H", "C4H", "C4H"),
    150: ("D7H", "C6H", "C6H", "C6H", "C6H", "C6H", "C6H", "C5H", "C5H", "C5H", "C4H", "C4H"),
    175: ("D8H", "D7H", "D7H", "D7H", "D7H", "D7H", "D7H", "C6H", "C6H", "C5H", "C5H", "C5H"),
    200: ("D9H", "D9H", "D9H", "D9H", "D8H", "D8H", "D8H", "D7H", "D7H", "C6H", "C6H", "C6H"),
}
#: chart note 4: one column to the left for stainless, titanium, copper-nickel and T6 aluminium
LEFT_SHIFT_PREFIXES = ("SUS", "TI", "CUNI")
PITCH = {"N": "none", "R": "regular pitch", "C": "close pitch", "D": "double-close pitch"}
WIPER = {"N": "no wiper", "W": "inserted mandrel + wiper die", "H": "high-pressure mandrel + wiper die"}


def decode(code: str) -> dict:
    """Chart code to words; zone 1 = mandrel optional, 2 = inserted tooling, 3 = high-pressure tooling."""
    pitch, balls, wiper = code[0], code[1], code[2]
    if pitch == "N":
        mandrel = "none"
    elif balls == "0":
        mandrel = f"plug ({PITCH[pitch]})"
    else:
        mandrel = f"{balls}-ball ({PITCH[pitch]})"
    zone = 1 if wiper == "N" else 2 if wiper == "W" else 3
    return {"code": code, "mandrel": mandrel, "wiper": WIPER[wiper], "zone": zone}


def tooling_for(od: float, wall: float, clr: float, material: str = "", angle_deg: float = 90.0) -> dict:
    """Mandrel and wiper from the chart: largest row <= WF, largest column <= D, then the chart's shifts."""
    wf = od / wall
    d = clr / od
    row = max(k for k in CHART if k <= wf + 1e-9)
    cols = [i for i, c in enumerate(CHART_COLS) if c <= d + 1e-9]
    out = {"wall_factor": wf, "d_of_bend": d, "row": row, "difficulty_factor": wf / d, "notes": []}
    if not cols:
        return {**out, "code": None, "class": "beyond chart (D < 0.75)", "mandrel": "specialist",
                "wiper": "specialist", "zone": 4, "col": None}
    col = cols[-1]
    notes: list[str] = []
    mat = material.upper()
    if mat.startswith(LEFT_SHIFT_PREFIXES) or mat.endswith("T6"):
        col -= 1
        notes.append("one column left for this material (chart note 4)")
    if angle_deg < 45.0:
        col += 1
        notes.append("one column right for a bend under 45 deg")
    if col < 0:
        return {**out, "code": None, "class": "beyond chart after the material shift", "mandrel": "specialist",
                "wiper": "specialist", "zone": 4, "col": None, "notes": notes}
    col = min(col, len(CHART_COLS) - 1)
    info = decode(CHART[row][col])
    cls = "empty bend (no mandrel)" if info["mandrel"] == "none" else info["mandrel"] + " mandrel" + (
        ", " + info["wiper"] if info["zone"] > 1 else ", no wiper")
    return {**out, **info, "class": cls, "col": CHART_COLS[col], "notes": notes}


def clamp_length(od: float, clr: float, serrated: bool = False) -> float:
    """Bend Tooling: Lc = OD x (Kr x 2.5) - CLR with Kr = 2, not less than OD x Ks (Ks 2 smooth, 1 serrated)."""
    ks = 1.0 if serrated else 2.0
    return max(od * 5.0 - clr, od * ks)


def min_between_bends(od: float, clr: float) -> float:
    """Pines: minimum distance between bends 3 OD if D of bend > 2, else 4 OD."""
    return (3.0 if clr / od > 2.0 else 4.0) * od


# ------------------------------------------------------------------ collision while bending


def _reverse(lra: LRA) -> LRA:
    """The same tube described from its other end."""
    rows = list(lra.rows)
    n = len(rows)
    straights = lra.straights()[::-1]
    new_rows = []
    for k in range(n):
        src = rows[n - 1 - k]
        r = 0.0 if k == 0 else rows[n - k].R
        new_rows.append(LRARow(L=straights[k], R=r, A=src.A, clr=src.clr))
    return LRA(rows=tuple(new_rows), final_L=straights[-1])


def machine_states(lra: LRA, step_deg: float = 15.0):  # type: ignore[no-untyped-def]
    """Yield (bend number, partial angle, leading-part points) in the machine frame.

    Machine frame: bend die tangent point at the origin, the unbent tube
    behind it along -X, the bend turning towards +Y about +Z. Bends are made
    in program order, so the already-formed bends ride on the leading part.
    """
    rows = lra.rows
    for i, row in enumerate(rows):
        n_steps = max(1, math.ceil(row.A / step_deg))
        for s in range(1, n_steps + 1):
            phi = row.A * s / n_steps
            # leading part, described from the die outwards: bend i (partial), then bends i-1 .. 1 in reverse
            seq = [LRARow(L=0.0, R=0.0, A=phi, clr=row.clr)]
            straights = [rows[k].L for k in range(i, 0, -1)]  # straights between formed bends, walking back
            for k in range(i - 1, -1, -1):
                seq.append(LRARow(L=straights[i - 1 - k], R=rows[k + 1].R, A=rows[k].A, clr=rows[k].clr))
            prog = LRA(rows=tuple(seq), final_L=rows[0].L)
            pts = lra_to_xyz(prog)
            pts = pts - pts[0]
            # the leading part starts at the die tangent point; the formed arcs need their radii
            radii = [r.clr for r in seq]
            dense = centerline(pts, radii, step_deg=5.0) if len(pts) > 2 else pts
            yield i + 1, phi, dense


def collision_scan(lra: LRA, od: float, m: Machine) -> list[dict]:
    """Every contact between the swinging leading part and the floor, bed or bend head."""
    hits: list[dict] = []
    r = od / 2.0
    for bend, phi, pts in machine_states(lra):
        clr = lra.rows[bend - 1].clr
        x, y, z = pts[:, 0], pts[:, 1], pts[:, 2]
        # the arc being formed wraps the bend die (centre (0, CLR, 0)); that contact is intended
        on_die = (np.hypot(x, y - clr) < clr + od) & (np.abs(z) < od)
        behind = (x < -r) & ~on_die
        foot = (np.abs(y) < m.body_half_width_mm + r)
        floor = z - r < -m.axis_height_mm
        bed = behind & foot & (x > -m.body_behind_mm) & (z - r < -m.body_below_axis_mm)
        head = behind & foot & (x > -m.head_length_mm) & (z + r > -m.body_below_axis_mm) & (z - r < m.body_above_axis_mm)
        for name, mask in (("floor", floor), ("machine bed", bed), ("bend head", head)):
            if mask.any():
                k = int(np.argmax(mask))
                hits.append({"bend": bend, "at_deg": round(phi, 1), "with": name,
                             "point": [round(float(v), 1) for v in pts[k]]})
    return hits


def _first_per_bend(hits: list[dict]) -> list[dict]:
    seen, out = set(), []
    for h in hits:
        key = (h["bend"], h["with"])
        if key not in seen:
            seen.add(key)
            out.append(h)
    return out


# ------------------------------------------------------------------ the checks


def check_part(part: Part, machine: Machine | None = None) -> DFMReport:
    """Run every rule on *part*; see the module docstring for the list."""
    from .materials import MATERIALS
    from .mechanics import ovality_estimate

    m = machine or Machine()
    rep = DFMReport(part_no=part.part_no)
    lra = part.lra()
    od, t = part.od, part.wall

    if od > m.max_od:
        rep.checks.append(Check("D0", "Tube size", FAIL, f"OD {od} mm exceeds machine capacity {m.max_od} mm",
                                source="machine data"))

    pines = "Pines (The Fabricator 2016): 1D extreme, 2D severe, 3D optimal"
    tools = []
    for i, row in enumerate(lra.rows, start=1):
        d = row.clr / od
        if d < 0.6:
            rep.checks.append(Check("D1", "D of bend", FAIL, f"CLR/OD = {d:.2f}, tighter than any process in the "
                                    "sources (Yamato publicly reports 0.6D)", f"bend {i}", pines))
        elif d < 1.0:
            rep.checks.append(Check("D1", "D of bend", WARN, f"CLR/OD = {d:.2f}: ultra-tight, beyond the generic "
                                    "chart; specialist process (Yamato publicly reports 0.6D)", f"bend {i}", pines))
        elif d < 1.5:
            rep.checks.append(Check("D1", "D of bend", WARN, f"CLR/OD = {d:.2f}: extreme bend, needs a close-fitting "
                                    "mandrel, wiper die and boost", f"bend {i}", pines))
        else:
            sev = "severe" if d < 2.5 else "manageable" if d < 3.0 else "optimal"
            rep.checks.append(Check("D1", "D of bend", PASS, f"CLR/OD = {d:.2f} ({sev})", f"bend {i}", pines))
        tools.append(tooling_for(od, t, row.clr, part.material, row.A))
    if tools:
        worst = max(tools, key=lambda x: (x["zone"], x["difficulty_factor"]))
        st = FAIL if worst["zone"] == 4 else WARN if worst["zone"] == 3 else PASS
        extra = ("; " + "; ".join(worst["notes"])) if worst.get("notes") else ""
        rep.checks.append(Check("D2", "Wall factor and tooling", st,
                                f"WF {worst['wall_factor']:.1f} at {worst['d_of_bend']:.2f}D: {worst['class']}"
                                f" (chart code {worst.get('code')}){extra}", "tightest bend", CHART_SOURCE))
        rep.tooling = worst

    straights = lra.straights()
    src3 = "Bend Tooling clamp length; Pines distance between bends (ENGINEERING_NOTES 5.3)"
    for i in range(1, len(straights) - 1):
        s_ = straights[i]
        clr_max = max(lra.rows[i - 1].clr, lra.rows[i].clr)
        need = max(clamp_length(od, clr_max, m.serrated_clamp), min_between_bends(od, clr_max))
        where = f"between bends {i} and {i + 1}"
        if s_ >= need:
            rep.checks.append(Check("D3", "Straight between bends", PASS, f"{s_:.1f} mm >= {need:.1f} mm", where, src3))
        elif s_ >= 0.5 * need:
            rep.checks.append(Check("D3", "Straight between bends", WARN,
                                    f"{s_:.1f} mm < {need:.1f} mm: short or serrated clamp, or clamp-in-bend tooling",
                                    where, src3))
        else:
            rep.checks.append(Check("D3", "Straight between bends", FAIL,
                                    f"{s_:.1f} mm, under half of {need:.1f} mm: compound tooling or redesign",
                                    where, src3))
    if lra.n_bends:
        lead, tail = straights[0], straights[-1]
        first = (1.5 if m.boost else 2.0) * od
        extra = max(0.0, first - lead)
        rep.checks.append(Check("D4", "Leading end", PASS if extra == 0 else WARN,
                                f"first straight {lead:.1f} mm vs {first:.1f} mm"
                                + (f": add {extra:.0f} mm clamping stock, trim after bending" if extra else ""),
                                "tube start", "McGrew (The Fabricator 2008): first straight >= 2D, 1.5D with boost"))
        collet = 0.5 * od
        extra = max(0.0, collet - tail)
        rep.checks.append(Check("D4", "Trailing end", PASS if extra == 0 else WARN,
                                f"last straight {tail:.1f} mm vs collet depth {collet:.1f} mm"
                                + (f": add {extra:.0f} mm stock" if extra else ""),
                                "tube end", "McGrew (The Fabricator 2008): collet depth >= 0.5D"))
    over = [i for i, r in enumerate(lra.rows, start=1) if m.max_angle_deg < r.A]
    for i in over:
        rep.checks.append(Check("D5", "Bend angle", FAIL, f"{lra.rows[i - 1].A:.1f} deg > machine max "
                                f"{m.max_angle_deg:.0f}", f"bend {i}", "machine data"))
    if not over:
        rep.checks.append(Check("D5", "Bend angles", PASS, f"all within {m.max_angle_deg:.0f} deg", "", "machine data"))

    fwd = _first_per_bend(collision_scan(lra, od, m)) if lra.n_bends else []
    rev = _first_per_bend(collision_scan(_reverse(lra), od, m)) if lra.n_bends else []
    if not fwd:
        rep.sequence = "start end first (as drawn)"
        rep.checks.append(Check("D6", "Collision while bending", PASS, "no contact with floor, bed or head",
                                "all bends", "machine-frame simulation"))
    elif not rev:
        rep.sequence = "reverse: bend from the tube end"
        rep.checks.append(Check("D6", "Collision while bending", WARN,
                                f"as drawn: {fwd[0]['with']} at bend {fwd[0]['bend']}; bending from the other end "
                                "is clear", "sequence", "machine-frame simulation"))
    else:
        rep.sequence = "neither direction is clear"
        rep.checks.append(Check("D6", "Collision while bending", FAIL,
                                f"{fwd[0]['with']} at bend {fwd[0]['bend']} (as drawn) and {rev[0]['with']} at bend "
                                f"{rev[0]['bend']} (reversed): left/right-hand bender or split the part",
                                "sequence", "machine-frame simulation"))

    gap = self_clearance(part)
    rep.checks.append(Check("D7", "Self-interference", PASS if gap >= 0 else FAIL,
                            f"closest approach between distant tube sections: {gap + od:.1f} mm centre to centre "
                            f"({'clear' if gap >= 0 else 'overlap'})", "", "geometry"))

    if lra.rows:
        tight = min(r.clr for r in lra.rows)
        need = 100.0 * (od / 2.0) / tight
        mat = MATERIALS.get(part.material)
        src8 = "Pines/Unison: elongation = (OD/2)/CLR; JIS G 3445 Table 3 note a), JIS G 3459 clause 6.1"
        if mat is None:
            rep.checks.append(Check("D8", "Elongation required", WARN, f"{need:.1f}% needed; material "
                                    f"{part.material!r} is not in the table", "tightest bend", src8))
        elif mat.elongation_unspecified_below_od is not None and od <= mat.elongation_unspecified_below_od:
            rep.checks.append(Check("D8", "Elongation required", WARN,
                                    f"{need:.1f}% needed at the extrados; {mat.standard} does not guarantee "
                                    f"elongation for OD <= {mat.elongation_unspecified_below_od:g} mm: state a "
                                    "minimum in the purchase specification", "tightest bend", src8))
        elif need > mat.elongation_pct:
            rep.checks.append(Check("D8", "Elongation required", FAIL,
                                    f"{need:.1f}% needed > {mat.elongation_pct:g}% minimum for {mat.grade}: bend in a "
                                    f"softer temper (e.g. O or T4, then age) or raise CLR to "
                                    f">= {od / 2 / (mat.elongation_pct / 100):.0f} mm", "tightest bend", src8))
        else:
            rep.checks.append(Check("D8", "Elongation required", PASS,
                                    f"{need:.1f}% needed <= {mat.elongation_pct:g}% minimum for {mat.grade}",
                                    "tightest bend", src8))
        if tight <= od / 2.0:
            rep.checks.append(Check("D9", "Wall thinning and ovality (estimates)", FAIL,
                                    f"CLR {tight:g} mm <= OD/2: the inside of the bend would have zero or negative "
                                    "radius, so no estimate exists", "tightest bend", "geometry"))
        else:
            w = wall_change(od, t, tight)
            ov = ovality_estimate(od, t, tight)
            rep.checks.append(Check("D9", "Wall thinning and ovality (estimates)", PASS,
                                    f"extrados wall {w.t_outer:.2f} mm ({w.thinning_pct:.1f}% thinner); ovality without "
                                    f"a mandrel about {ov:.1f}% (typical acceptance 5-8%), lower with one",
                                    "tightest bend",
                                    "Bend Tooling thinning rule; Tube Form Solutions: ovality = 0.7 x difficulty factor"))
    return rep


def self_clearance(part: Part) -> float:
    """Smallest centre-to-centre distance minus OD between tube sections far apart along the tube."""
    from .fixture import dense_centerline

    c = dense_centerline(part.points, part.clr, spacing=2.0)
    s = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(c, axis=0), axis=1))])
    best = math.inf
    step = 4
    for i in range(0, len(c), step):
        far = np.abs(s - s[i]) > 3.0 * part.od + math.pi * max(part.radii)
        if far.any():
            best = min(best, float(np.min(np.linalg.norm(c[far] - c[i], axis=1))))
    return best - part.od if math.isfinite(best) else math.inf

