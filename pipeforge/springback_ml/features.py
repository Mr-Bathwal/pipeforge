"""Reduce TubeBEND to one row per run: setup, labels and signal features.

Run ``python -m pipeforge.springback_ml.features`` once after downloading.
It writes ``data/tubebend/derived/runs.csv`` (315 rows) and a few example
signal traces; training and the app use only these derived files, which are
redistributed under CC BY 4.0 with attribution (data/tubebend/ATTRIBUTION.md).

Label: the bend angle is the angle between the two straight legs' centre
axes. Each leg is scanned as 2 mm cross-section slices; we fit a circle to
every slice and a line through the circle centres (a "virtual CMM").
Springback = 47 deg target - measured angle. This label agrees with the
dataset's own arc end angle (Pearson r = 0.99) and has a replicate scatter
of about 0.07 deg, against 0.36 deg for a single principal axis fitted to the
whole leg point cloud, which is why the slice method is used.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .load import DERIVED, DESIGN_COLS, FAILED, SETUP_COLS, TARGET_DEG, _num, load_raw

CLR_MM = 33.0  #: bend radius of the TubeBEND tooling (paper, section III-E)
SENSORS = {
    "mandrel_kN": "SENSOR_MANDREL_AXIAL_Load_[kN]",
    "pd1_kN": "SENSOR_PRESSURE-DIE_LATERAL_1_Load_[kN]",
    "pd2_kN": "SENSOR_PRESSURE-DIE_LATERAL_2_Load_[kN]",
}
TORQUES = {
    "bend_rot": "MACHINE_BEND-DIE_ROTATING_Max_Torque_[%]",
    "collet_ax": "MACHINE_COLLET_AXIAL_Max_Torque_[%]",
    "pd_ax": "MACHINE_PRESSURE-DIE_AXIAL_Max_Torque_[%]",
    "pd_lat": "MACHINE_PRESSURE-DIE_LATERAL_Max_Torque_[%]",
    "mandrel_ax": "MACHINE_MANDREL_AXIAL_Max_Torque_[%]",
    "clamp_lat": "MACHINE_CLAMP-DIE_LATERAL_Max_Torque_[%]",
}


# ---------------------------------------------------------------- label: virtual CMM


def circle_fit_3d(points: np.ndarray) -> tuple[np.ndarray, float]:
    """Centre and radius of a ring of points (plane by SVD, then Kasa circle fit)."""
    c = points.mean(axis=0)
    _, _, vt = np.linalg.svd(points - c, full_matrices=False)
    u, v = vt[0], vt[1]
    x, y = (points - c) @ u, (points - c) @ v
    a = np.column_stack([2 * x, 2 * y, np.ones_like(x)])
    sol, *_ = np.linalg.lstsq(a, x * x + y * y, rcond=None)
    r = float(np.sqrt(sol[2] + sol[0] ** 2 + sol[1] ** 2))
    return c + sol[0] * u + sol[1] * v, r


def leg_axis_from_slices(df: pd.DataFrame, min_points: int = 30) -> dict:
    """Axis direction of a straight leg from its slice-circle centres, with outlier rejection."""
    centres, radii = [], []
    for _, g in df.groupby("Tube_Section"):
        p = _num(g[["X [mm]", "Y [mm]", "Z [mm]"]]).dropna().to_numpy()
        if len(p) < min_points:
            continue
        c, r = circle_fit_3d(p)
        centres.append(c)
        radii.append(r)
    cen = np.array(centres)
    keep = np.ones(len(cen), dtype=bool)
    for _ in range(2):  # refit after dropping slices far from the line (scan artefacts)
        m = cen[keep].mean(axis=0)
        _, _, vt = np.linalg.svd(cen[keep] - m, full_matrices=False)
        d = vt[0]
        res = np.linalg.norm((cen - m) - np.outer((cen - m) @ d, d), axis=1)
        mad = np.median(np.abs(res[keep] - np.median(res[keep]))) + 1e-9
        keep = res <= np.median(res[keep]) + 5 * 1.4826 * mad
    return {"direction": d, "n_slices": int(keep.sum()), "n_dropped": int((~keep).sum()),
            "radius_mean": float(np.mean(np.array(radii)[keep])), "line_residual_max": float(res[keep].max())}


def measured_angle(e: dict) -> dict:
    a1 = leg_axis_from_slices(e["geometry_data_stl_suitable_linear_1"])
    a2 = leg_axis_from_slices(e["geometry_data_stl_suitable_linear_2"])
    ang = float(np.degrees(np.arccos(np.clip(abs(float(a1["direction"] @ a2["direction"])), 0.0, 1.0))))
    return {"angle_measured": ang, "leg1_radius": a1["radius_mean"], "leg2_radius": a2["radius_mean"],
            "leg1_slices_dropped": a1["n_dropped"], "leg2_slices_dropped": a2["n_dropped"]}


# ---------------------------------------------------------------- signal features


def bend_window(mov: pd.DataFrame) -> tuple[float, float, np.ndarray, np.ndarray]:
    """Start and end time of the bend stroke from the bend-die angle."""
    angle_col = next(c for c in mov.columns if c.startswith("BEND-DIE_ROTATING_Angle"))
    t = mov["Time_[s]"].to_numpy()
    a = mov[angle_col].to_numpy()
    ok = np.isfinite(t) & np.isfinite(a)
    t, a = t[ok], a[ok]
    a0, a1 = a[0], np.nanmin(a)
    moving = np.abs(a - a0) > 0.2
    start = float(t[np.argmax(moving)])
    end = float(t[np.argmax(np.abs(a - a1) < 0.2)])
    return start, end, t, a


def _series_features(prefix: str, t: np.ndarray, y: np.ndarray, t0: float, t1: float) -> dict:
    m = (t >= t0) & (t <= t1) & np.isfinite(y)
    if m.sum() < 3:
        return {}
    tt, yy = t[m], y[m]
    peak = float(np.max(yy))
    i90 = int(np.argmax(yy >= 0.9 * peak)) if peak > 0 else 0
    return {
        f"{prefix}_peak": peak,
        f"{prefix}_mean": float(np.mean(yy)),
        f"{prefix}_std": float(np.std(yy)),
        f"{prefix}_impulse": float(np.trapezoid(yy, tt)),
        f"{prefix}_end": float(yy[-1]),
        f"{prefix}_rise_s": float(tt[i90] - tt[0]),
    }


def run_features(e: dict) -> dict:
    mov = _num(e["process_parameters_movements"])
    sen = _num(e["process_parameters_loads_sensor"])
    mac = _num(e["process_parameters_loads_machine"])
    t0, t1, t_ang, ang = bend_window(mov)
    f: dict = {"bend_duration_s": t1 - t0, "bend_stroke_deg": float(ang[0] - np.nanmin(ang))}
    f["bend_speed_dps"] = f["bend_stroke_deg"] / max(f["bend_duration_s"], 1e-6)
    ts = sen["Time_[s]"].to_numpy()
    for key, col in SENSORS.items():
        f.update(_series_features(key, ts, sen[col].to_numpy(), t0, t1))
    tm = mac["Time_[s]"].to_numpy()
    for key, col in TORQUES.items():
        if col in mac:
            f.update(_series_features(key, tm, mac[col].to_numpy(), t0, t1))
    # physics-inspired features
    bend_tq = mac[TORQUES["bend_rot"]].to_numpy()
    m = (tm >= t0) & (tm <= t1)
    ang_at = np.interp(tm[m], t_ang, ang)
    f["bend_work_proxy"] = float(abs(np.trapezoid(bend_tq[m], ang_at)))  # torque % x deg
    col_mv = mov["COLLET_AXIAL_Movement_[mm]"].to_numpy()
    tmov = mov["Time_[s]"].to_numpy()
    travel = float(abs(np.interp(t1, tmov, col_mv) - np.interp(t0, tmov, col_mv)))
    f["collet_travel_mm"] = travel
    f["boost_measured"] = travel / (CLR_MM * np.radians(max(f["bend_stroke_deg"], 1e-6)))
    if "pd1_kN_impulse" in f and "pd2_kN_impulse" in f:
        f["pd_impulse_total"] = f["pd1_kN_impulse"] + f["pd2_kN_impulse"]
    return f


def build(write: bool = True) -> pd.DataFrame:
    data = load_raw()
    rows = []
    examples: dict = {}
    for key in sorted(data, key=lambda k: int(k.split("_")[1])):
        exp = int(key.split("_")[1])
        if exp in FAILED:
            continue
        e = data[key]
        s = e["bending_setups"].iloc[0]
        row = {"exp": exp, **{c: float(s[c]) for c in SETUP_COLS}}
        row.update(measured_angle(e))
        row["springback_deg"] = TARGET_DEG - row["angle_measured"]
        arc = _num(e["geometry_data_key_characteristics_arc"].drop(columns=["Tube_Section"]))
        row["angle_arc_end"] = float(arc["Angle[degree]ORDistance[mm]"].dropna().iloc[-1])
        row["ovality_arc_max_pct"] = 100.0 * float(arc["Out-of-roundness [-]"].abs().max())
        row["collapse_arc_max_mm"] = float(arc["Collapse [mm]"].abs().max())
        row.update(run_features(e))
        rows.append(row)
        if exp in (2, 100, 250):
            mov = _num(e["process_parameters_movements"])
            sen = _num(e["process_parameters_loads_sensor"])
            examples[str(exp)] = {
                "t_sensor": sen["Time_[s]"].to_numpy()[::5].round(3).tolist(),
                **{k: sen[c].to_numpy()[::5].round(3).tolist() for k, c in SENSORS.items()},
                "t_move": mov["Time_[s]"].to_numpy().round(3).tolist(),
                "bend_angle": mov[next(c for c in mov.columns if c.startswith("BEND-DIE_ROTATING_Angle"))]
                .to_numpy().round(3).tolist(),
            }
    df = pd.DataFrame(rows).set_index("exp")
    df["group"] = df[DESIGN_COLS].astype(str).agg("|".join, axis=1)
    if write:
        DERIVED.mkdir(parents=True, exist_ok=True)
        df.round(6).to_csv(DERIVED / "runs.csv")
        (DERIVED / "signal_examples.json").write_text(json.dumps(examples), encoding="utf-8")
    return df


if __name__ == "__main__":
    out = build()
    print(out.shape, "rows x cols written to", DERIVED / "runs.csv")
    print(out[["springback_deg", "angle_arc_end", "ovality_arc_max_pct"]].describe().round(3))
