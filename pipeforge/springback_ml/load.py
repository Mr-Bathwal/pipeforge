"""Load TubeBEND safely and reduce it to one row per bending run.

TubeBEND (Oz, Knoche, Yazdani, Engel, Van Laerhoven; Zenodo
10.5281/zenodo.18458823, CC BY 4.0) is a pickled nested dict of pandas
DataFrames: ``data["Exp_<n>"][<table>]`` for 318 rotary-draw bends of a
22 x 1 mm stainless tube to a 47 deg target on a WAFIOS RBV 35.

Unpickling runs code, so :class:`SafeUnpickler` only resolves the ten
pandas/numpy reconstruction classes this file actually uses, found by a
logging pass over the whole file. Anything else raises.

Labels (paper section III-E): the actual bend angle is the angle between the
centre axes of the two straight legs; springback = target - actual. The
dataset has no springback column, so we fit each leg's axis to its scanned
surface points (principal axis of the point cloud) and cross-check against
the end angle of the arc section's key characteristics.
"""

from __future__ import annotations

import hashlib
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "tubebend" / "raw" / "experiments_process_and_results.pkl"
DERIVED = ROOT / "data" / "tubebend" / "derived"
MD5 = "f407dbce2d13c351ff81baab2da3343b"
SIZE = 797_223_431
FAILED = (1, 48, 166)  #: runs the authors mark as failed
TARGET_DEG = 47.0

_ALLOWED = {
    ("builtins", "slice"),
    ("numpy", "dtype"),
    ("numpy", "ndarray"),
    ("numpy.core.multiarray", "_reconstruct"),
    ("pandas._libs.internals", "_unpickle_block"),
    ("pandas.core.frame", "DataFrame"),
    ("pandas.core.indexes.base", "Index"),
    ("pandas.core.indexes.base", "_new_Index"),
    ("pandas.core.indexes.range", "RangeIndex"),
    ("pandas.core.internals.managers", "BlockManager"),
}

SETUP_COLS = [
    "Collet boost",
    "Pressure-die distance",
    "Pressure-die boost",
    "Mandrel retraction timing",
    "Mandrel position",
    "Pressure-die lateral position",
    "Clamp-die lateral position",
    "Wiper-die shortening",
]
#: the factors the authors varied on purpose; a group = one combination of these
DESIGN_COLS = ["Collet boost", "Pressure-die distance", "Pressure-die boost", "Mandrel retraction timing"]


class SafeUnpickler(pickle.Unpickler):
    def find_class(self, module: str, name: str):  # type: ignore[no-untyped-def]
        if (module, name) not in _ALLOWED:
            raise pickle.UnpicklingError(f"blocked global {module}.{name}")
        return super().find_class(module, name)


def md5_of(path: Path, chunk: int = 1 << 22) -> str:
    h = hashlib.md5()
    with path.open("rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


def load_raw(path: Path = RAW, verify: bool = True) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"{path} not found: run `python -m pipeforge.springback_ml.download`")
    if verify and md5_of(path) != MD5:
        raise ValueError(f"{path} does not match the published md5 {MD5}")
    with path.open("rb") as fh:
        return SafeUnpickler(fh).load()


def _num(df: pd.DataFrame) -> pd.DataFrame:
    return df.apply(pd.to_numeric, errors="coerce")


def leg_axis(points: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    """Principal axis of a straight leg's surface points: (centroid, unit direction, rms radius).

    For a scanned cylinder section longer than its diameter the direction of
    greatest spread is the cylinder axis. The rms distance of the points from
    that axis should be close to the tube's outer radius, which is checked.
    """
    c = points.mean(axis=0)
    _, _, vt = np.linalg.svd(points - c, full_matrices=False)
    d = vt[0]
    rel = points - c
    radial = rel - np.outer(rel @ d, d)
    return c, d, float(np.sqrt((radial**2).sum(axis=1).mean()))


def bend_angle_from_legs(l1: np.ndarray, l2: np.ndarray) -> tuple[float, float, float]:
    """Bend angle (deg) between the two leg axes, plus each leg's rms radius."""
    _, d1, r1 = leg_axis(l1)
    _, d2, r2 = leg_axis(l2)
    ang = float(np.degrees(np.arccos(np.clip(abs(float(d1 @ d2)), 0.0, 1.0))))
    return ang, r1, r2


def run_record(exp_id: int, e: dict) -> dict:
    """One row: setup, labels, and the arrays needed for features (kept separately)."""
    setup = e["bending_setups"].iloc[0]
    rec: dict = {"exp": exp_id}
    for col in SETUP_COLS + ["Outer-diameter", "Wall-thickness", "Target-angle", "Tube"]:
        rec[col] = float(setup[col]) if col in setup and pd.notna(setup[col]) else np.nan
    rec["comment"] = "" if pd.isna(setup.get("Comments", np.nan)) else str(setup["Comments"])

    l1 = _num(e["geometry_data_stl_suitable_linear_1"][["X [mm]", "Y [mm]", "Z [mm]"]]).dropna().to_numpy()
    l2 = _num(e["geometry_data_stl_suitable_linear_2"][["X [mm]", "Y [mm]", "Z [mm]"]]).dropna().to_numpy()
    if len(l1) > 100 and len(l2) > 100:
        ang, r1, r2 = bend_angle_from_legs(l1, l2)
        rec.update({"angle_legs": ang, "leg1_rms_radius": r1, "leg2_rms_radius": r2})
    arc = _num(e["geometry_data_key_characteristics_arc"].drop(columns=["Tube_Section"], errors="ignore"))
    if len(arc) and arc.notna().any().any():
        a = arc.dropna(subset=["Angle[degree]ORDistance[mm]"])
        rec["angle_arc_end"] = float(a["Angle[degree]ORDistance[mm]"].iloc[-1])
        rec["arc_oor_max"] = float(a["Out-of-roundness [-]"].abs().max())
        rec["arc_collapse_max"] = float(a["Collapse [mm]"].abs().max())
        mid = a.iloc[(a["Angle[degree]ORDistance[mm]"] - 22.0).abs().argsort()[:1]]
        rec["arc_oor_mid"] = float(mid["Out-of-roundness [-]"].abs().iloc[0])
    return rec
