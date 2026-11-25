"""Centerline geometry of a bent tube: XYZ intersection points to and from LRA.

Conventions (derived in docs/ENGINEERING_NOTES.md, section 1):

* **XYZ** is the list of intersection points ("virtual sharps") where the
  straight segments of the centerline would meet if there were no bend
  radius, from the start of the tube to its end.
* **LRA** gives, for each bend, the straight length *L* fed before it
  (tangent point to tangent point), the plane rotation *R* applied before
  it, and the bend angle *A*, plus the final straight.
* *R* is the signed angle, in (-180, 180], from the previous bend's plane
  normal to this bend's plane normal, measured about the feed direction by
  the right-hand rule. The first bend's *R* is 0 by definition; the tube's
  absolute position and orientation are kept in :class:`Placement`, so a
  round trip XYZ to LRA to XYZ reproduces the original points.

All lengths are millimetres and all angles in the public API are degrees.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

Vec = NDArray[np.float64]

#: Bends flatter than this (degrees) are treated as collinear and rejected.
MIN_BEND_DEG = 1e-4
#: Bends sharper than this are rejected: a 180 degree bend has no tangent length.
MAX_BEND_DEG = 179.0


class GeometryError(ValueError):
    """The centerline cannot be built as a bent tube with the given radii."""


@dataclass(frozen=True, eq=False)
class Bend:
    """One bend, computed from three consecutive intersection points."""

    index: int  #: 1-based bend number, as on the drawing's bend table
    point: Vec  #: intersection point (virtual sharp)
    angle_deg: float  #: bend angle, 0 < A < 180
    clr: float  #: centerline radius
    tangent_len: float  #: distance from the intersection point to each tangent point
    t_in: Vec  #: tangent point where the arc starts
    t_out: Vec  #: tangent point where the arc ends
    centre: Vec  #: arc centre
    normal: Vec  #: unit normal of the bend plane, u x v normalised
    u: Vec  #: unit direction into the bend
    v: Vec  #: unit direction out of the bend

    @property
    def angle_rad(self) -> float:
        return math.radians(self.angle_deg)

    @property
    def arc_len(self) -> float:
        """Centerline arc length, CLR times the bend angle in radians."""
        return self.clr * self.angle_rad


@dataclass(frozen=True)
class LRARow:
    """One bend of an LRA program."""

    L: float  #: straight fed before this bend, mm
    R: float  #: plane rotation before this bend, degrees
    A: float  #: bend angle, degrees
    clr: float  #: centerline radius of this bend, mm


@dataclass(frozen=True)
class Placement:
    """Where the tube sits in the part coordinate system."""

    origin: tuple[float, float, float]
    direction: tuple[float, float, float]  #: unit direction of the first straight
    normal: tuple[float, float, float]  #: unit normal of the first bend's plane


@dataclass(frozen=True)
class LRA:
    """A nominal bending program: one row per bend, then the last straight."""

    rows: tuple[LRARow, ...]
    final_L: float
    placement: Placement | None = None

    @property
    def n_bends(self) -> int:
        return len(self.rows)

    def straights(self) -> list[float]:
        return [r.L for r in self.rows] + [self.final_L]

    def as_table(self) -> list[dict[str, float]]:
        """Rows for display: bend number, L, R, A and CLR; the last row is the final straight."""
        out: list[dict[str, float]] = [
            {"bend": i + 1, "L": r.L, "R": r.R, "A": r.A, "CLR": r.clr}
            for i, r in enumerate(self.rows)
        ]
        out.append({"bend": 0, "L": self.final_L, "R": 0.0, "A": 0.0, "CLR": 0.0})
        return out


# ---------------------------------------------------------------- vector helpers


def unit(v: ArrayLike) -> Vec:
    a = np.asarray(v, dtype=float)
    n = float(np.linalg.norm(a))
    if n == 0.0 or not math.isfinite(n):
        raise GeometryError("zero-length or non-finite vector")
    return a / n


def rotate(v: ArrayLike, axis: ArrayLike, angle_rad: float) -> Vec:
    """Rotate *v* about *axis* by *angle_rad* (right-hand rule), Rodrigues' formula."""
    k = unit(axis)
    a = np.asarray(v, dtype=float)
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    return a * c + np.cross(k, a) * s + k * float(np.dot(k, a)) * (1.0 - c)


def signed_angle(a: ArrayLike, b: ArrayLike, axis: ArrayLike) -> float:
    """Signed angle in radians from *a* to *b* about *axis*, in (-pi, pi]."""
    k = unit(axis)
    ang = math.atan2(float(np.dot(np.cross(a, b), k)), float(np.dot(a, b)))
    return math.pi if ang <= -math.pi + 1e-12 else ang


def any_perpendicular(d: ArrayLike) -> Vec:
    """A unit vector perpendicular to *d*, chosen deterministically."""
    dd = unit(d)
    ref = np.array([0.0, 0.0, 1.0]) if abs(dd[2]) < 0.9 else np.array([0.0, 1.0, 0.0])
    return unit(np.cross(np.cross(dd, ref), dd))


# ---------------------------------------------------------------- XYZ side


def as_points(points: ArrayLike) -> Vec:
    """Validate intersection points: at least two, finite, no repeated point."""
    p = np.asarray(points, dtype=float)
    if p.ndim != 2 or p.shape[1] != 3 or p.shape[0] < 2:
        raise GeometryError("need at least two XYZ points, shape (n, 3)")
    if not np.all(np.isfinite(p)):
        raise GeometryError("points must be finite numbers")
    seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
    if np.any(seg < 1e-9):
        i = int(np.argmin(seg))
        raise GeometryError(f"points {i} and {i + 1} coincide")
    return p


def _radii(clr: float | Sequence[float], n_bends: int) -> list[float]:
    if isinstance(clr, (int, float)):
        radii = [float(clr)] * n_bends
    else:
        radii = [float(r) for r in clr]
        if len(radii) != n_bends:
            raise GeometryError(f"{len(radii)} radii given for {n_bends} bends")
    for i, r in enumerate(radii, start=1):
        if not (r > 0 and math.isfinite(r)):
            raise GeometryError(f"bend {i}: CLR must be a positive number")
    return radii


def bends(points: ArrayLike, clr: float | Sequence[float]) -> tuple[Bend, ...]:
    """Compute every bend: angle, tangent points, arc centre and plane normal."""
    p = as_points(points)
    n_b = p.shape[0] - 2
    radii = _radii(clr, n_b)
    out: list[Bend] = []
    for i in range(1, p.shape[0] - 1):
        u = unit(p[i] - p[i - 1])
        v = unit(p[i + 1] - p[i])
        theta = math.acos(max(-1.0, min(1.0, float(np.dot(u, v)))))
        deg = math.degrees(theta)
        if deg < MIN_BEND_DEG:
            raise GeometryError(
                f"point {i} is collinear with its neighbours (no bend); remove it"
            )
        if deg > MAX_BEND_DEG:
            raise GeometryError(f"bend {i} is {deg:.2f} deg; a tube cannot fold back on itself")
        r = radii[i - 1]
        t = r * math.tan(theta / 2.0)
        normal = unit(np.cross(u, v))
        bisector = unit(v - u)
        centre = p[i] + bisector * (r / math.cos(theta / 2.0))
        out.append(
            Bend(
                index=i,
                point=p[i].copy(),
                angle_deg=deg,
                clr=r,
                tangent_len=t,
                t_in=p[i] - u * t,
                t_out=p[i] + v * t,
                centre=centre,
                normal=normal,
                u=u,
                v=v,
            )
        )
    return tuple(out)


def straight_lengths(points: ArrayLike, bend_list: Sequence[Bend]) -> list[float]:
    """Straight length of every segment, tangent point to tangent point.

    Raises :class:`GeometryError` if two bends overlap, i.e. their tangent
    lengths add up to more than the distance between their intersection points.
    """
    p = as_points(points)
    seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
    tl = [0.0] + [b.tangent_len for b in bend_list] + [0.0]
    out = []
    for j, s in enumerate(seg):
        straight = float(s) - tl[j] - tl[j + 1]
        if straight < -1e-9:
            where = "the tube start" if j == 0 else f"bend {j}"
            to = "the tube end" if j == len(seg) - 1 else f"bend {j + 1}"
            raise GeometryError(
                f"segment {j + 1} (from {where} to {to}) is {-straight:.2f} mm too short "
                "for the bend radii: reduce CLR or move the points apart"
            )
        out.append(max(0.0, straight))
    return out


def xyz_to_lra(points: ArrayLike, clr: float | Sequence[float]) -> LRA:
    """Convert intersection points to an LRA program with its placement."""
    p = as_points(points)
    bl = bends(p, clr)
    straights = straight_lengths(p, bl)
    rows: list[LRARow] = []
    prev_normal: Vec | None = None
    for k, b in enumerate(bl):
        r_deg = 0.0 if prev_normal is None else math.degrees(signed_angle(prev_normal, b.normal, b.u))
        rows.append(LRARow(L=straights[k], R=_tidy_angle(r_deg), A=b.angle_deg, clr=b.clr))
        prev_normal = b.normal
    d0 = unit(p[1] - p[0])
    n0 = bl[0].normal if bl else any_perpendicular(d0)
    placement = Placement(
        origin=tuple(float(x) for x in p[0]),  # type: ignore[arg-type]
        direction=tuple(float(x) for x in d0),  # type: ignore[arg-type]
        normal=tuple(float(x) for x in n0),  # type: ignore[arg-type]
    )
    return LRA(rows=tuple(rows), final_L=straights[-1], placement=placement)


def _tidy_angle(deg: float) -> float:
    """Wrap to (-180, 180] and snap -0.0 to 0.0."""
    a = (deg + 180.0) % 360.0 - 180.0
    if a <= -180.0 + 1e-12:
        a = 180.0
    return 0.0 if abs(a) < 1e-12 else a


def lra_to_xyz(program: LRA) -> Vec:
    """Rebuild the intersection points from an LRA program.

    Without a placement the tube starts at the origin along +X, and the first
    bend lies in the XY plane, turning towards +Y.
    """
    pl = program.placement
    if pl is None:
        origin = np.zeros(3)
        d = np.array([1.0, 0.0, 0.0])
        n = np.array([0.0, 0.0, 1.0])
    else:
        origin = np.asarray(pl.origin, dtype=float)
        d = unit(pl.direction)
        n = unit(pl.normal)
        if abs(float(np.dot(d, n))) > 1e-6:
            raise GeometryError("placement normal must be perpendicular to its direction")
    pts = [origin.copy()]
    cur = origin.copy()
    prev_t = 0.0
    for k, row in enumerate(program.rows, start=1):
        if row.L < 0:
            raise GeometryError(f"bend {k}: L must not be negative")
        if not (MIN_BEND_DEG <= row.A <= MAX_BEND_DEG):
            raise GeometryError(f"bend {k}: A must be between {MIN_BEND_DEG} and {MAX_BEND_DEG} deg")
        if row.clr <= 0:
            raise GeometryError(f"bend {k}: CLR must be positive")
        n = rotate(n, d, math.radians(row.R))
        t = row.clr * math.tan(math.radians(row.A) / 2.0)
        cur = cur + d * (prev_t + row.L + t)
        pts.append(cur.copy())
        d = rotate(d, n, math.radians(row.A))
        prev_t = t
    if program.final_L < 0:
        raise GeometryError("final straight must not be negative")
    cur = cur + d * (prev_t + program.final_L)
    pts.append(cur.copy())
    return np.array(pts)


# ---------------------------------------------------------------- lengths and sampling


def developed_length(program: LRA, elongation_pct: float = 0.0) -> float:
    """Cut length of the blank: straights plus arc lengths (CLR times angle).

    *elongation_pct* removes that percentage of the arc lengths from the blank,
    because the arcs stretch during bending (see ENGINEERING_NOTES, section 1.4).
    The default, 0, is the purely geometric length.
    """
    arcs = sum(r.clr * math.radians(r.A) for r in program.rows)
    return sum(program.straights()) + arcs * (1.0 - elongation_pct / 100.0)


def centerline(points: ArrayLike, clr: float | Sequence[float], step_deg: float = 3.0) -> Vec:
    """Dense centerline: the straights plus arcs sampled every *step_deg* degrees."""
    p = as_points(points)
    bl = bends(p, clr)
    straight_lengths(p, bl)  # raises on overlap
    out: list[Vec] = [p[0]]
    for b in bl:
        out.append(b.t_in)
        n_seg = max(2, math.ceil(b.angle_deg / step_deg))
        radius_vec = b.t_in - b.centre
        for s in range(1, n_seg + 1):
            out.append(b.centre + rotate(radius_vec, b.normal, b.angle_rad * s / n_seg))
    out.append(p[-1])
    arr = np.array(out)
    keep = np.ones(len(arr), dtype=bool)
    keep[1:] = np.linalg.norm(np.diff(arr, axis=0), axis=1) > 1e-9
    return arr[keep]


def bounding_box(points: ArrayLike, clr: float | Sequence[float], od: float) -> tuple[Vec, Vec]:
    """Approximate envelope of the tube: the centerline box grown by OD/2."""
    c = centerline(points, clr, step_deg=1.0)
    return c.min(axis=0) - od / 2.0, c.max(axis=0) + od / 2.0


def rigid_distance(a: ArrayLike, b: ArrayLike) -> float:
    """Largest point distance after the best rigid alignment (Kabsch).

    Used to compare two shapes that may sit differently in space, for example
    an LRA rebuilt without its placement.
    """
    pa, pb = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if pa.shape != pb.shape:
        raise GeometryError("shapes differ in point count")
    ca, cb = pa.mean(axis=0), pb.mean(axis=0)
    h = (pa - ca).T @ (pb - cb)
    u, _, vt = np.linalg.svd(h)
    dsign = np.sign(np.linalg.det(vt.T @ u.T)) or 1.0
    rot = vt.T @ np.diag([1.0, 1.0, dsign]) @ u.T
    aligned = (rot @ (pa - ca).T).T + cb
    return float(np.max(np.linalg.norm(aligned - pb, axis=1)))
