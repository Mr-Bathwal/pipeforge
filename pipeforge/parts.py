"""A bent-tube part: the data a process engineer starts from."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .geometry import LRA, Vec, as_points, bends, developed_length, straight_lengths, xyz_to_lra

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "data" / "samples"


@dataclass(frozen=True, eq=False)
class Part:
    part_no: str
    name: str
    material: str  #: key into materials.MATERIALS
    od: float  #: outside diameter, mm
    wall: float  #: wall thickness, mm
    clr: float | tuple[float, ...]  #: centerline radius, one value or one per bend
    points: Vec  #: XYZ intersection points, mm
    name_ja: str = ""
    category: str = ""  #: "2W" or "4W"
    notes: str = ""
    extra: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not (self.od > 0 and 0 < self.wall < self.od / 2):
            raise ValueError(f"{self.part_no}: need OD > 0 and 0 < wall < OD/2")
        p = as_points(self.points)
        straight_lengths(p, bends(p, self.clr))  # validates the radii fit

    @property
    def n_bends(self) -> int:
        return len(self.points) - 2

    @property
    def radii(self) -> list[float]:
        if isinstance(self.clr, (int, float)):
            return [float(self.clr)] * self.n_bends
        return [float(r) for r in self.clr]

    @property
    def id(self) -> float:
        return self.od - 2 * self.wall

    def lra(self) -> LRA:
        return xyz_to_lra(self.points, self.clr)

    def cut_length(self, elongation_pct: float = 0.0) -> float:
        return developed_length(self.lra(), elongation_pct)

    def to_dict(self) -> dict:
        return {
            "part_no": self.part_no,
            "name": self.name,
            "name_ja": self.name_ja,
            "category": self.category,
            "material": self.material,
            "od": self.od,
            "wall": self.wall,
            "clr": list(self.clr) if isinstance(self.clr, tuple) else self.clr,
            "points": np.asarray(self.points).round(4).tolist(),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Part:
        clr = d["clr"]
        return cls(
            part_no=str(d["part_no"]),
            name=str(d["name"]),
            name_ja=str(d.get("name_ja", "")),
            category=str(d.get("category", "")),
            material=str(d["material"]),
            od=float(d["od"]),
            wall=float(d["wall"]),
            clr=tuple(float(r) for r in clr) if isinstance(clr, list) else float(clr),
            points=np.asarray(d["points"], dtype=float),
            notes=str(d.get("notes", "")),
        )

    @classmethod
    def load(cls, path: str | Path) -> Part:
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def sample_parts() -> dict[str, Part]:
    """All sample parts in data/samples, keyed by part number."""
    out = {}
    for f in sorted(SAMPLES_DIR.glob("*.json")):
        part = Part.load(f)
        out[part.part_no] = part
    return out
