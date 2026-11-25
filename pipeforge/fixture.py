"""Checking fixture (jig) for a bent tube: base plate, grooved support blocks, datums.

Design logic (explained in docs/FIXTURE_DESIGN.md):

1. **Fixture frame.** The part is laid as flat as possible: the plate normal
   is the direction of least spread of the centerline (principal axes), so
   blocks stay short and the part is stable.
2. **Blocks.** Two blocks per straight, at 20 % and 80 % of its length (one
   at the middle if the straight is short), and one at each arc midpoint.
   Each block is a vertical prism from the plate up to the tube's
   centerline height at that point, oriented along the tube. Its groove is
   cut by subtracting a rod of radius OD/2 + clearance swept along the true
   centerline, so the groove follows arcs and slopes exactly.
3. **Rejections.** A block is dropped if the tube there is too steep to rest
   on it, or if another part of the tube passes through its footprint.
4. **Datums (3-2-1).** A: the three blocks spanning the largest triangle
   (vertical support). B: the two blocks on the longest straight (lateral
   direction). C: an end stop at the tube start (axial position).
5. **Go/no-go.** A tube whose centerline is off by more than about the
   groove clearance cannot drop into every groove at once.

The automated-station additions (M4b): toggle clamps on the datum-A blocks,
an inductive sensor under every clamped groove, and one at each tube end.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field

import numpy as np

from .geometry import Vec, bends, centerline, straight_lengths, unit
from .parts import Part

BLOCK_LEN_FACTOR = 1.2  #: block length along the tube, times OD (min 20 mm)
BLOCK_WIDTH_ADD = 24.0  #: block width = OD + this, mm
MIN_HEIGHT = 25.0  #: lowest tube underside above the plate top, mm
MAX_SLOPE = 0.70  #: skip a block where |tangent . Z| exceeds this (about 44 deg)
PLATE_MARGIN = 30.0
PLATE_T = 20.0
SENSOR_DIA = 12.0  #: M12 inductive proximity sensor (illustrative)
SENSOR_LEN = 50.0


@dataclass
class Block:
    id: str
    kind: str  #: "straight" or "arc"
    segment: int  #: straight index (0-based) or bend number
    contact: Vec  #: tube centerline point the block supports (fixture frame)
    tangent: Vec  #: tube direction at the contact point
    length: float
    width: float
    height: float  #: plate top to the tube centerline at the contact point
    yaw_deg: float  #: block orientation about Z
    datum: str = ""  #: "A1".."A3", "B1", "B2" or ""
    clamp: bool = False
    sensor: str = ""  #: sensor id if one is fitted


@dataclass
class EndStop:
    id: str
    which: str  #: "start" or "end"
    point: Vec  #: tube end centre
    direction: Vec  #: outward tube direction at that end
    gap: float  #: face distance beyond the nominal end, mm
    sensor: str = ""


@dataclass
class FixtureDesign:
    part_no: str
    od: float
    clearance: float
    rotation: Vec  #: 3x3, part frame to fixture frame
    offset: Vec  #: added after rotation
    points: Vec  #: intersection points in the fixture frame
    clr: float | tuple[float, ...]
    blocks: list[Block]
    end_stops: list[EndStop]
    plate_min: Vec  #: plate corner (x, y)
    plate_max: Vec
    plate_t: float
    holes: list[tuple[float, float]]
    rejected: list[str] = field(default_factory=list)

    @property
    def plate_size(self) -> tuple[float, float, float]:
        d = self.plate_max - self.plate_min
        return float(d[0]), float(d[1]), self.plate_t

    def sensors(self) -> list[dict]:
        out = []
        for b in self.blocks:
            if b.sensor:
                out.append({"id": b.sensor, "where": f"block {b.id}", "purpose": "tube seated in clamped groove"})
        for e in self.end_stops:
            if e.sensor:
                out.append({"id": e.sensor, "where": f"end stop {e.id}", "purpose": f"tube {e.which} end in position"})
        return out

    def block_table(self) -> list[dict]:
        return [
            {
                "block": b.id,
                "on": f"straight {b.segment + 1}" if b.kind == "straight" else f"bend {b.segment}",
                "x": round(float(b.contact[0]), 1),
                "y": round(float(b.contact[1]), 1),
                "height": round(b.height, 1),
                "yaw_deg": round(b.yaw_deg, 1),
                "datum": b.datum,
                "clamp": "yes" if b.clamp else "",
                "sensor": b.sensor,
            }
            for b in self.blocks
        ]


def dense_centerline(points: Vec, clr, spacing: float = 2.0) -> Vec:  # type: ignore[no-untyped-def]
    """Centerline with arcs every 2 deg and straights split every *spacing* mm."""
    c = centerline(points, clr, step_deg=2.0)
    out = [c[0]]
    for a, b in zip(c[:-1], c[1:], strict=True):
        n = max(1, int(math.ceil(float(np.linalg.norm(b - a)) / spacing)))
        out.extend(a + (b - a) * k / n for k in range(1, n + 1))
    return np.array(out)


def fixture_frame(points: Vec, clr) -> tuple[Vec, Vec]:  # type: ignore[no-untyped-def]
    """Rotation and offset that lay the part flat with its lowest point at MIN_HEIGHT + OD/2."""
    c = centerline(points, clr, step_deg=3.0)
    centroid = c.mean(axis=0)
    _, _, vt = np.linalg.svd(c - centroid)
    x_ax, z_ax = vt[0], vt[2]
    if z_ax[2] < 0:  # keep the original up direction where we can
        z_ax = -z_ax
    y_ax = np.cross(z_ax, x_ax)
    rot = np.vstack([x_ax, y_ax, z_ax])
    return rot, -rot @ centroid


def design_fixture(part: Part, clearance: float = 0.3, with_station: bool = True,
                   include_arcs: bool = True) -> FixtureDesign:
    """Generate the checking fixture for *part*."""
    rot, off = fixture_frame(part.points, part.clr)
    pts = (rot @ part.points.T).T + off
    dense = dense_centerline(pts, part.clr)
    lift = MIN_HEIGHT + part.od / 2.0 - float(dense[:, 2].min())
    pts = pts + np.array([0.0, 0.0, lift])
    off = off + np.array([0.0, 0.0, lift])
    dense = dense_centerline(pts, part.clr)
    s_dense = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(dense, axis=0), axis=1))])

    bl = bends(pts, part.clr)
    straights = straight_lengths(pts, bl)
    blen = max(20.0, BLOCK_LEN_FACTOR * part.od)
    bwid = part.od + BLOCK_WIDTH_ADD

    candidates: list[tuple[str, int, Vec, Vec]] = []
    starts = [pts[0]] + [b.t_out for b in bl]
    ends = [b.t_in for b in bl] + [pts[-1]]
    for j, (a, b, length) in enumerate(zip(starts, ends, straights, strict=True)):
        if length < blen:
            continue
        d = unit(b - a)
        fracs = (0.2, 0.8) if length >= 3.0 * blen else (0.5,)
        for f in fracs:
            candidates.append(("straight", j, a + d * length * f, d))
    if include_arcs:
        for b in bl:
            mid = b.centre + _rot(b.t_in - b.centre, b.normal, b.angle_rad / 2.0)
            tan = unit(_rot(b.u, b.normal, b.angle_rad / 2.0))
            candidates.append(("arc", b.index, mid, tan))

    blocks: list[Block] = []
    rejected: list[str] = []
    for kind, seg, p, t in candidates:
        label = f"{kind} {seg + 1 if kind == 'straight' else seg}"
        if abs(t[2]) > MAX_SLOPE:
            rejected.append(f"{label}: tube too steep ({math.degrees(math.asin(min(1, abs(t[2])))):.0f} deg) to rest on a block")
            continue
        yaw = math.degrees(math.atan2(t[1], t[0]))
        if _interferes(dense, s_dense, p, yaw, blen, bwid, part.od, clearance):
            rejected.append(f"{label}: another part of the tube passes through the block")
            continue
        blocks.append(Block(id="", kind=kind, segment=seg, contact=p, tangent=t, length=blen, width=bwid,
                            height=float(p[2]), yaw_deg=yaw))
    blocks.sort(key=lambda b: _arc_position(dense, s_dense, b.contact))
    for i, b in enumerate(blocks, start=1):
        b.id = f"S{i:02d}"
    _assign_datums(blocks, straights)

    d0 = unit(pts[0] - pts[1])
    d1 = unit(pts[-1] - pts[-2])
    gap = 1.0
    end_stops = [
        EndStop("C1", "start", pts[0].copy(), d0, gap=0.0),
        EndStop("E2", "end", pts[-1].copy(), d1, gap=gap),
    ]
    if with_station:
        n = 0
        for b in blocks:
            if b.clamp:
                n += 1
                b.sensor = f"PX{n}"
        for e in end_stops:
            n += 1
            e.sensor = f"PX{n}"

    xy = [b.contact[:2] for b in blocks] + [e.point[:2] + e.direction[:2] * 20 for e in end_stops]
    xy_arr = np.array(xy)
    reach = max(bwid, blen) / 2.0 + PLATE_MARGIN
    pmin = xy_arr.min(axis=0) - reach
    pmax = xy_arr.max(axis=0) + reach
    holes = _hole_pattern(pmin, pmax)
    return FixtureDesign(
        part_no=part.part_no, od=part.od, clearance=clearance, rotation=rot, offset=off, points=pts,
        clr=part.clr, blocks=blocks, end_stops=end_stops, plate_min=pmin, plate_max=pmax, plate_t=PLATE_T,
        holes=holes, rejected=rejected,
    )


def _rot(v: Vec, axis: Vec, ang: float) -> Vec:
    from .geometry import rotate

    return rotate(v, axis, ang)


def _arc_position(dense: Vec, s: Vec, p: Vec) -> float:
    return float(s[int(np.argmin(np.linalg.norm(dense - p, axis=1)))])


def _interferes(dense: Vec, s: Vec, p: Vec, yaw_deg: float, blen: float, bwid: float, od: float, c: float) -> bool:
    """True if tube centerline far from p (along the tube) enters the block's envelope."""
    s_p = _arc_position(dense, s, p)
    far = np.abs(s - s_p) > blen + od
    if not far.any():
        return False
    q = dense[far] - p
    ya = math.radians(yaw_deg)
    lx = q[:, 0] * math.cos(ya) + q[:, 1] * math.sin(ya)
    ly = -q[:, 0] * math.sin(ya) + q[:, 1] * math.cos(ya)
    r = od / 2.0 + c
    inside = (np.abs(lx) < blen / 2 + r) & (np.abs(ly) < bwid / 2 + r) & (q[:, 2] + p[2] < p[2] + r)
    return bool(inside.any())


def _assign_datums(blocks: list[Block], straights: list[float]) -> None:
    if len(blocks) >= 3:
        best, best_area = None, -1.0
        for trio in itertools.combinations(range(len(blocks)), 3):
            a, b, c = (blocks[i].contact[:2] for i in trio)
            area = abs(float((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))) / 2.0
            if area > best_area:
                best, best_area = trio, area
        if best is not None:
            if best_area < 1.0:  # collinear blocks: a flat part on one line has no A plane
                best = tuple(sorted(range(len(blocks)), key=lambda i: blocks[i].contact[0])[k] for k in (0, len(blocks) // 2, -1))
            for k, i in enumerate(best, start=1):
                blocks[i].datum = f"A{k}"
                blocks[i].clamp = True
    on_straight = [b for b in blocks if b.kind == "straight"]
    if on_straight:
        longest = max({b.segment for b in on_straight}, key=lambda j: straights[j])
        pair = [b for b in on_straight if b.segment == longest][:2]
        for k, b in enumerate(pair, start=1):
            b.datum = (b.datum + "," if b.datum else "") + f"B{k}"


def _hole_pattern(pmin: Vec, pmax: Vec, inset: float = 20.0, pitch: float = 300.0) -> list[tuple[float, float]]:
    xs = np.linspace(pmin[0] + inset, pmax[0] - inset, max(2, int(math.ceil((pmax[0] - pmin[0]) / pitch)) + 1))
    ys = (pmin[1] + inset, pmax[1] - inset)
    return [(float(x), float(y)) for x in xs for y in ys]


# ------------------------------------------------------------------- CAD (optional)


def fixture_solids(fx: FixtureDesign) -> dict:
    """CadQuery solids: plate, grooved blocks, end stops, clamps and sensors."""
    import cadquery as cq

    from .cad import rod_solid, tube_solid

    w, h, t = fx.plate_size
    plate = (
        cq.Workplane("XY")
        .box(w, h, t, centered=(False, False, False))
        .translate((float(fx.plate_min[0]), float(fx.plate_min[1]), -t))
    )
    for x, y in fx.holes:
        plate = plate.cut(cq.Workplane("XY").circle(5.5).extrude(t + 2).translate((x, y, -t - 1)))
    label = f"{fx.part_no}  CHECK FIXTURE"
    plate = plate.cut(
        cq.Workplane("XY").text(label, 8.0, 1.0, halign="left", valign="bottom")
        .translate((float(fx.plate_min[0]) + 12, float(fx.plate_min[1]) + 8, -1.0))
    )
    rod = rod_solid(fx.points, fx.clr, fx.od + 2 * fx.clearance)
    blocks = []
    for b in fx.blocks:
        blk = (
            cq.Workplane("XY")
            .box(b.length, b.width, b.height, centered=(True, True, False))
            .rotate((0, 0, 0), (0, 0, 1), b.yaw_deg)
            .translate((float(b.contact[0]), float(b.contact[1]), 0.0))
        )
        blk = blk.cut(rod)
        if b.sensor:
            hole = (
                cq.Workplane("XY").circle(SENSOR_DIA / 2 + 0.2).extrude(b.height)
                .translate((float(b.contact[0]), float(b.contact[1]), -1.0))
            )
            blk = blk.cut(hole)
        blocks.append((b.id, blk))
    stops = []
    for e in fx.end_stops:
        size = fx.od + 20
        face = e.point + e.direction * (e.gap + 6.0)
        yaw = math.degrees(math.atan2(e.direction[1], e.direction[0]))
        stop = (
            cq.Workplane("XY").box(12, size, float(face[2]) + fx.od / 2 + 5, centered=(True, True, False))
            .rotate((0, 0, 0), (0, 0, 1), yaw)
            .translate((float(face[0]), float(face[1]), 0.0))
        )
        stops.append((e.id, stop))
    clamps, sensors = [], []
    for b in fx.blocks:
        if b.clamp:
            side = np.array([-math.sin(math.radians(b.yaw_deg)), math.cos(math.radians(b.yaw_deg)), 0.0])
            base = b.contact + side * (b.width / 2 + 18)
            body = (
                cq.Workplane("XY").box(30, 24, b.height + fx.od / 2 + 10, centered=(True, True, False))
                .rotate((0, 0, 0), (0, 0, 1), b.yaw_deg).translate((float(base[0]), float(base[1]), 0.0))
            )
            arm_c = b.contact + side * (b.width / 4)
            arm = (
                cq.Workplane("XY").box(14, b.width / 2 + 24, 8, centered=(True, True, False))
                .rotate((0, 0, 0), (0, 0, 1), b.yaw_deg)
                .translate((float(arm_c[0]), float(arm_c[1]), float(b.contact[2]) + fx.od / 2 + 2))
            )
            clamps.append((f"TC-{b.id}", body.union(arm)))
        if b.sensor:
            sensors.append((b.sensor, cq.Workplane("XY").circle(SENSOR_DIA / 2).extrude(SENSOR_LEN)
                            .translate((float(b.contact[0]), float(b.contact[1]),
                                        float(b.contact[2]) - fx.od / 2 - 2.0 - SENSOR_LEN))))
    for e in fx.end_stops:
        if e.sensor:
            p = e.point + e.direction * (e.gap + 14.0)
            yaw = math.degrees(math.atan2(e.direction[1], e.direction[0]))
            s = (cq.Workplane("YZ").circle(SENSOR_DIA / 2).extrude(SENSOR_LEN)
                 .rotate((0, 0, 0), (0, 0, 1), yaw).translate(tuple(float(v) for v in p)))
            sensors.append((e.sensor, s))
    return {"plate": plate, "blocks": blocks, "stops": stops, "clamps": clamps, "sensors": sensors,
            "tube": tube_solid(fx.points, fx.clr, fx.od, min(1.0, fx.od / 4))}


def export_fixture(fx: FixtureDesign, out_dir) -> dict[str, str]:  # type: ignore[no-untyped-def]
    """STEP of the whole assembly, and one STL per block for 3D printing."""
    from pathlib import Path

    import cadquery as cq

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    s = fixture_solids(fx)
    assy = cq.Assembly(name=f"{fx.part_no}_fixture")
    assy.add(s["plate"], name="plate", color=cq.Color(0.55, 0.58, 0.62))
    for name, blk in s["blocks"]:
        assy.add(blk, name=f"block_{name}", color=cq.Color(0.93, 0.93, 0.90))
    for name, stp in s["stops"]:
        assy.add(stp, name=f"stop_{name}", color=cq.Color(0.95, 0.45, 0.10))
    for name, cl in s["clamps"]:
        assy.add(cl, name=name, color=cq.Color(0.20, 0.35, 0.80))
    for name, sn in s["sensors"]:
        assy.add(sn, name=name, color=cq.Color(0.95, 0.80, 0.10))
    assy.add(s["tube"], name="part_nominal", color=cq.Color(0.70, 0.72, 0.75, 0.6))
    paths = {}
    step = out / f"{fx.part_no}_fixture.step"
    assy.save(str(step), exportType="STEP")
    paths["step"] = str(step)
    blocks_dir = out / "print_blocks"
    blocks_dir.mkdir(exist_ok=True)
    for name, blk in s["blocks"]:
        cq.exporters.export(blk, str(blocks_dir / f"{fx.part_no}_{name}.stl"), tolerance=0.05, angularTolerance=0.1)
    paths["block_stls"] = str(blocks_dir)
    whole = s["plate"]
    for _, blk in s["blocks"] + s["stops"]:
        whole = whole.union(blk)
    cq.exporters.export(whole, str(out / f"{fx.part_no}_fixture.stl"), tolerance=0.1, angularTolerance=0.2)
    paths["stl"] = str(out / f"{fx.part_no}_fixture.stl")
    return paths
