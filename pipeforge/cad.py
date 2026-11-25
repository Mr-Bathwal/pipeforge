"""Exact B-rep of a bent tube with CadQuery: STEP and STL export.

The path is built from true lines and circular arcs (not a polyline), and an
annulus of OD and ID is swept along it, so the solid's volume equals the
annulus area times the developed length to within the kernel's tolerance.
tests/test_cad.py checks exactly that.

CadQuery is optional at runtime: the hosted app imports this module only
when CadQuery is installed, and otherwise serves the pre-generated STEP files
in artifacts/ (see README, "Deployment").
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from .geometry import as_points, bends, rotate, straight_lengths, unit


def available() -> bool:
    try:
        import cadquery  # noqa: F401
    except ImportError:
        return False
    return True


def _v(cq, p):  # type: ignore[no-untyped-def]
    return cq.Vector(float(p[0]), float(p[1]), float(p[2]))


def path_wire(points: Sequence[Sequence[float]] | np.ndarray, clr: float | Sequence[float]):  # type: ignore[no-untyped-def]
    """CadQuery wire of the centerline: lines and three-point arcs."""
    import cadquery as cq

    p = as_points(points)
    bl = bends(p, clr)
    straight_lengths(p, bl)  # raises if bends overlap
    edges = []
    cur = p[0]
    for b in bl:
        if np.linalg.norm(b.t_in - cur) > 1e-6:
            edges.append(cq.Edge.makeLine(_v(cq, cur), _v(cq, b.t_in)))
        mid = b.centre + rotate(b.t_in - b.centre, b.normal, b.angle_rad / 2.0)
        edges.append(cq.Edge.makeThreePointArc(_v(cq, b.t_in), _v(cq, mid), _v(cq, b.t_out)))
        cur = b.t_out
    if np.linalg.norm(p[-1] - cur) > 1e-6:
        edges.append(cq.Edge.makeLine(_v(cq, cur), _v(cq, p[-1])))
    return cq.Wire.assembleEdges(edges)


def tube_solid(
    points: Sequence[Sequence[float]] | np.ndarray,
    clr: float | Sequence[float],
    od: float,
    wall: float,
):  # type: ignore[no-untyped-def]
    """Sweep an annulus (OD, OD - 2t) along the centerline; returns a cq.Workplane."""
    import cadquery as cq

    if not (0 < wall < od / 2):
        raise ValueError("wall must be positive and less than OD/2")
    p = as_points(points)
    wire = path_wire(p, clr)
    d0 = unit(p[1] - p[0])
    x_dir = np.cross(d0, [0.0, 0.0, 1.0])
    if np.linalg.norm(x_dir) < 1e-9:
        x_dir = np.cross(d0, [0.0, 1.0, 0.0])
    plane = cq.Plane(origin=_v(cq, p[0]), xDir=_v(cq, unit(x_dir)), normal=_v(cq, d0))
    return (
        cq.Workplane(plane)
        .circle(od / 2.0)
        .circle(od / 2.0 - wall)
        .sweep(cq.Workplane().add(wire), transition="round")
    )


def rod_solid(points: Sequence[Sequence[float]] | np.ndarray, clr: float | Sequence[float], diameter: float):  # type: ignore[no-untyped-def]
    """A solid round bar swept along the centerline (used to cut fixture grooves)."""
    import cadquery as cq

    p = as_points(points)
    wire = path_wire(p, clr)
    d0 = unit(p[1] - p[0])
    x_dir = np.cross(d0, [0.0, 0.0, 1.0])
    if np.linalg.norm(x_dir) < 1e-9:
        x_dir = np.cross(d0, [0.0, 1.0, 0.0])
    plane = cq.Plane(origin=_v(cq, p[0]), xDir=_v(cq, unit(x_dir)), normal=_v(cq, d0))
    return cq.Workplane(plane).circle(diameter / 2.0).sweep(cq.Workplane().add(wire), transition="round")


def export(solid, step_path: str | Path | None = None, stl_path: str | Path | None = None) -> dict[str, str]:  # type: ignore[no-untyped-def]
    """Write STEP and/or STL; returns the paths written."""
    import cadquery as cq

    out: dict[str, str] = {}
    if step_path is not None:
        cq.exporters.export(solid, str(step_path), exportType="STEP")
        out["step"] = str(step_path)
    if stl_path is not None:
        cq.exporters.export(solid, str(stl_path), exportType="STL", tolerance=0.05, angularTolerance=0.1)
        out["stl"] = str(stl_path)
    return out


def solid_volume(solid) -> float:  # type: ignore[no-untyped-def]
    return float(solid.val().Volume())


def expected_volume(od: float, wall: float, developed: float) -> float:
    """Annulus area times centerline length (Pappus)."""
    return math.pi / 4.0 * (od**2 - (od - 2 * wall) ** 2) * developed
