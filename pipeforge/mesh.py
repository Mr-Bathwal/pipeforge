"""Triangle mesh of a bent tube, with no CAD kernel needed.

CadQuery (cad.py) gives the exact B-rep and the STEP file, but it is a heavy
install. This module sweeps rings along the sampled centerline with
parallel-transport frames, so the deployed app can still draw any part in 3D
and export an STL for a part the user typed in.

The mesh is closed (outer wall, inner wall and two end rings), so its volume
can be checked against the exact value: annulus area times developed length
(Pappus's theorem).
"""

from __future__ import annotations

import struct
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .geometry import Vec, any_perpendicular, centerline, unit


@dataclass(frozen=True, eq=False)
class TubeMesh:
    vertices: Vec  #: (n, 3)
    faces: np.ndarray  #: (m, 3) int, counter-clockwise seen from outside

    def volume(self) -> float:
        """Signed volume of the closed mesh (divergence theorem)."""
        v = self.vertices[self.faces]
        return float(np.einsum("ij,ij->i", v[:, 0], np.cross(v[:, 1], v[:, 2])).sum() / 6.0)

    def write_stl(self, path: str | Path, name: str = "pipeforge") -> Path:
        """Write a binary STL."""
        path = Path(path)
        tri = self.vertices[self.faces].astype(np.float32)
        normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        lens = np.linalg.norm(normals, axis=1, keepdims=True)
        normals = np.divide(normals, lens, out=np.zeros_like(normals), where=lens > 0)
        header = name.encode("ascii", "replace")[:80].ljust(80, b" ")
        with path.open("wb") as fh:
            fh.write(header)
            fh.write(struct.pack("<I", len(tri)))
            rec = np.zeros(len(tri), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
            rec["n"] = normals
            rec["v"] = tri
            fh.write(rec.tobytes())
        return path


def frames(path: Vec) -> tuple[Vec, Vec, Vec]:
    """Tangent, normal and binormal at each path point, by parallel transport.

    Parallel transport keeps the ring orientation from twisting along the
    path, unlike Frenet frames, which flip on straights and inflections.
    """
    n = len(path)
    tangents = np.zeros((n, 3))
    for i in range(n):
        a = path[max(i - 1, 0)]
        b = path[min(i + 1, n - 1)]
        tangents[i] = unit(b - a)
    normals = np.zeros((n, 3))
    normals[0] = any_perpendicular(tangents[0])
    for i in range(1, n):
        t0, t1 = tangents[i - 1], tangents[i]
        axis = np.cross(t0, t1)
        s = float(np.linalg.norm(axis))
        nv = normals[i - 1]
        if s > 1e-12:
            c = float(np.clip(np.dot(t0, t1), -1.0, 1.0))
            k = axis / s
            ang = np.arctan2(s, c)
            nv = nv * np.cos(ang) + np.cross(k, nv) * np.sin(ang) + k * np.dot(k, nv) * (1 - np.cos(ang))
        nv = nv - tangents[i] * np.dot(nv, tangents[i])
        normals[i] = unit(nv)
    binormals = np.cross(tangents, normals)
    return tangents, normals, binormals


def tube_mesh(
    points: Sequence[Sequence[float]] | Vec,
    clr: float | Sequence[float],
    od: float,
    wall: float,
    segments: int = 32,
    step_deg: float = 4.0,
) -> TubeMesh:
    """Closed annular tube mesh along the centerline of the part."""
    if not (0 < wall < od / 2):
        raise ValueError("wall must be positive and less than OD/2")
    path = _with_straight_subdivision(centerline(points, clr, step_deg=step_deg))
    _, nrm, bin_ = frames(path)
    ang = np.linspace(0.0, 2 * np.pi, segments, endpoint=False)
    ring = np.cos(ang)[:, None, None] * nrm[None] + np.sin(ang)[:, None, None] * bin_[None]
    ring = ring.transpose(1, 0, 2)  # (n_path, segments, 3)
    ro, ri = od / 2.0, od / 2.0 - wall
    outer = path[:, None, :] + ro * ring
    inner = path[:, None, :] + ri * ring
    n_path = len(path)
    verts = np.concatenate([outer.reshape(-1, 3), inner.reshape(-1, 3)])
    off_in = n_path * segments

    def idx(i: int, j: int, base: int = 0) -> int:
        return base + i * segments + (j % segments)

    faces: list[tuple[int, int, int]] = []
    for i in range(n_path - 1):
        for j in range(segments):
            a, b = idx(i, j), idx(i, j + 1)
            c, d = idx(i + 1, j + 1), idx(i + 1, j)
            faces += [(a, b, c), (a, c, d)]  # outer wall faces outwards
            a, b = idx(i, j, off_in), idx(i, j + 1, off_in)
            c, d = idx(i + 1, j + 1, off_in), idx(i + 1, j, off_in)
            faces += [(a, c, b), (a, d, c)]  # inner wall faces the bore
    last = n_path - 1
    for j in range(segments):
        o0, o1 = idx(0, j), idx(0, j + 1)
        i0, i1 = idx(0, j, off_in), idx(0, j + 1, off_in)
        faces += [(o0, i1, o1), (o0, i0, i1)]  # start ring faces backwards
        o0, o1 = idx(last, j), idx(last, j + 1)
        i0, i1 = idx(last, j, off_in), idx(last, j + 1, off_in)
        faces += [(o0, o1, i1), (o0, i1, i0)]  # end ring faces forwards
    mesh = TubeMesh(vertices=verts, faces=np.array(faces, dtype=np.int64))
    if mesh.volume() < 0:  # ring handedness depends on the first frame
        mesh = TubeMesh(vertices=verts, faces=mesh.faces[:, ::-1].copy())
    return mesh


def _with_straight_subdivision(path: Vec, max_len: float = 25.0) -> Vec:
    """Split long straights so the transported frames stay smooth in the viewer."""
    out = [path[0]]
    for a, b in zip(path[:-1], path[1:], strict=True):
        n = max(1, int(np.ceil(np.linalg.norm(b - a) / max_len)))
        for s in range(1, n + 1):
            out.append(a + (b - a) * s / n)
    return np.array(out)
