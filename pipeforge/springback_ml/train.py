"""Train and evaluate springback (and ovality) models on TubeBEND.

Evaluation design (docs/MODEL_CARD.md explains why):

* **GroupKFold by setup.** Runs that share the four designed factors
  (collet boost, pressure-die distance, pressure-die boost, mandrel
  retraction timing) are replicates; they always fall in the same fold, so
  every score is for a machine setting the model never saw. 5 folds, 5
  repeats with different group shuffles: 25 scores per metric, reported as
  mean +/- standard deviation.
* Random KFold is also run, only to show how much it flatters the models.
* Two feature sets: **setup** (known before bending, so usable for
  compensation) and **setup + process** (adds force and torque features
  measured during the bend, for in-process monitoring).
* Baselines: the training-fold mean (what a constant correction from trial
  bends does), a ridge regression, and the physics estimate from
  pipeforge.mechanics, which needs no training at all.
* Hyperparameters are fixed in advance, not tuned on the test folds.

Outputs go to artifacts/springback/: metrics, out-of-fold predictions, the
closed-loop yield table used by the kaizen simulation, plots, and the final
models saved as XGBoost JSON (no pickle in the deployed app).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import RidgeCV
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold, KFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBRegressor

from ..materials import MATERIALS
from ..mechanics import springback_band
from .load import DERIVED, DESIGN_COLS

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts" / "springback"
RUNS = DERIVED / "runs.csv"

SETUP = DESIGN_COLS + ["Mandrel position", "Clamp-die lateral position", "Pressure-die lateral position"]
META = {"group", "comment"}
LABELS = {"springback_deg", "angle_measured", "angle_arc_end", "ovality_arc_max_pct", "collapse_arc_max_mm",
          "leg1_radius", "leg2_radius", "leg1_slices_dropped", "leg2_slices_dropped", "Wiper-die shortening"}
TOL_DEG = 0.5
REPEATS = 5
FOLDS = 5
TUBE = {"od": 22.0, "wall": 1.0, "clr": 33.0, "angle": 47.0}
#: TubeBEND says "stainless steel" without a grade; the physics baseline assumes SUS304 minimum properties.
PHYSICS_MATERIAL = "SUS304"


def load_runs() -> pd.DataFrame:
    if not RUNS.exists():
        raise FileNotFoundError(f"{RUNS} missing: run `python -m pipeforge.springback_ml.features` first")
    return pd.read_csv(RUNS, index_col="exp")


def process_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c not in META and c not in LABELS and c not in SETUP
            and pd.api.types.is_numeric_dtype(df[c]) and df[c].std() > 0]


def models() -> dict:
    return {
        "mean": lambda: DummyRegressor(strategy="mean"),
        "ridge": lambda: make_pipeline(StandardScaler(), RidgeCV(alphas=np.logspace(-3, 3, 13))),
        "random_forest": lambda: RandomForestRegressor(n_estimators=400, min_samples_leaf=2, random_state=0, n_jobs=-1),
        "xgboost": lambda: XGBRegressor(n_estimators=400, max_depth=3, learning_rate=0.03, subsample=0.8,
                                        colsample_bytree=0.8, min_child_weight=3, reg_lambda=1.0, random_state=0,
                                        n_jobs=4),
    }


def physics_estimate() -> dict:
    band = springback_band(TUBE["angle"], TUBE["clr"], TUBE["od"], TUBE["wall"], MATERIALS[PHYSICS_MATERIAL])
    return {"low": band.low.springback_deg, "mid": band.mid.springback_deg, "high": band.high.springback_deg}


def _scores(y: np.ndarray, p: np.ndarray) -> dict:
    return {"mae": float(mean_absolute_error(y, p)), "rmse": float(math.sqrt(mean_squared_error(y, p))),
            "r2": float(r2_score(y, p))}


def cross_validate(df: pd.DataFrame, target: str, features: list[str], name: str, grouped: bool = True) -> dict:
    """Repeated (Group)KFold; returns per-fold scores and out-of-fold predictions per repeat."""
    x = df[features].to_numpy(float)
    y = df[target].to_numpy(float)
    groups = df["group"].to_numpy()
    fold_scores = []
    oof = np.zeros((REPEATS, len(y)))
    for r in range(REPEATS):
        if grouped:
            splits = GroupKFold(n_splits=FOLDS, shuffle=True, random_state=r).split(x, y, groups)
        else:
            splits = KFold(n_splits=FOLDS, shuffle=True, random_state=r).split(x)
        for tr, te in splits:
            m = models()[name]()
            m.fit(x[tr], y[tr])
            p = m.predict(x[te])
            oof[r, te] = p
            fold_scores.append(_scores(y[te], p))
    summary = {k: {"mean": float(np.mean([s[k] for s in fold_scores])), "sd": float(np.std([s[k] for s in fold_scores], ddof=1))}
               for k in ("mae", "rmse", "r2")}
    pooled = [_scores(y, oof[r]) for r in range(REPEATS)]
    summary["pooled_mae"] = float(np.mean([p["mae"] for p in pooled]))
    summary["pooled_r2"] = float(np.mean([p["r2"] for p in pooled]))
    return {"summary": summary, "oof": oof, "n_folds": len(fold_scores)}


def fpy(errors: np.ndarray, tol: float = TOL_DEG) -> float:
    return float(np.mean(np.abs(errors) <= tol))


def run(write: bool = True) -> dict:
    df = load_runs()
    proc = process_columns(df)
    feature_sets = {"setup": SETUP, "setup+process": SETUP + proc}
    y = df["springback_deg"].to_numpy()
    results: dict = {"n_runs": len(df), "n_groups": int(df["group"].nunique()), "folds": FOLDS, "repeats": REPEATS,
                     "target_mean": float(y.mean()), "target_sd": float(y.std(ddof=1)), "springback": {},
                     "springback_random_kfold": {}, "ovality": {}, "physics": physics_estimate(),
                     "n_process_features": len(proc)}
    oofs: dict = {}
    for fs_name, feats in feature_sets.items():
        for mname in models():
            if mname == "mean" and fs_name != "setup":
                continue
            key = f"{mname} | {fs_name}"
            cv = cross_validate(df, "springback_deg", feats, mname)
            results["springback"][key] = cv["summary"]
            oofs[key] = cv["oof"]
            if mname in ("ridge", "xgboost"):
                results["springback_random_kfold"][key] = cross_validate(df, "springback_deg", feats, mname,
                                                                         grouped=False)["summary"]
        for mname in ("mean", "xgboost"):
            if mname == "mean" and fs_name != "setup":
                continue
            results["ovality"][f"{mname} | {fs_name}"] = cross_validate(df, "ovality_arc_max_pct", feats, mname)["summary"]
    phys = results["physics"]["mid"]
    results["springback"]["physics (SUS304 assumed) | none"] = {
        **{k: v for k, v in _scores(y, np.full_like(y, phys)).items()}, "note": "no training; constant for this tube"}

    # closed loop on real runs: error after compensating with each policy (out-of-fold, repeat 0)
    best_setup = min((k for k in results["springback"] if k.endswith("| setup") and not k.startswith("mean")),
                     key=lambda k: results["springback"][k]["mae"]["mean"])
    best_proc = min((k for k in results["springback"] if k.endswith("setup+process")),
                    key=lambda k: results["springback"][k]["mae"]["mean"])
    policies = {
        "none": y - 0.0,
        "physics": y - phys,
        "offset": y - oofs["mean | setup"][0],
        "ml": y - oofs[best_setup][0],
        "ml_in_process": y - oofs[best_proc][0],
    }
    tols = [0.1, 0.2, 0.25, 0.3, 0.5]
    closed = {
        "tolerance_deg": TOL_DEG,
        "baseline_policy": "offset",
        "fpy": {k: fpy(v) for k, v in policies.items()},
        "fpy_by_tolerance": {k: {str(t): fpy(v, t) for t in tols} for k, v in policies.items()},
        "mae_after": {k: float(np.mean(np.abs(v))) for k, v in policies.items()},
        "models": {"ml": best_setup, "ml_in_process": best_proc},
        "source": "out-of-fold predictions on 315 real TubeBEND runs (GroupKFold by setup, repeat 0)",
    }
    resid = np.abs(policies["ml"])
    closed["ml_interval90_deg"] = float(np.quantile(resid, 0.9))
    results["closed_loop"] = closed
    results["best"] = {"setup": best_setup, "setup+process": best_proc}

    if write:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "metrics.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        (OUT / "closed_loop.json").write_text(json.dumps(closed, indent=2), encoding="utf-8")
        oof_df = pd.DataFrame({"exp": df.index, "group": df["group"], "springback_deg": y,
                               **{k: v[0] for k, v in oofs.items()}})
        oof_df.to_csv(OUT / "oof_predictions.csv", index=False)
        _write_markdown(results)
        fit_final(df, proc, best_setup, best_proc, closed)
        plots(df, oofs, best_setup, best_proc, proc)
    return results


def fit_final(df: pd.DataFrame, proc: list[str], best_setup: str, best_proc: str, closed: dict) -> None:
    """Fit XGBoost on all runs and save as JSON with its domain of validity."""
    meta: dict = {"trained_on": "TubeBEND (CC BY 4.0), 315 runs, 22 x 1 mm stainless, CLR 33 mm, 47 deg target",
                  "valid_only_for": "this tube, material, tooling and target angle", "models": {}}
    for name, feats, target in (("springback_setup", SETUP, "springback_deg"),
                                ("springback_process", SETUP + proc, "springback_deg"),
                                ("ovality_setup", SETUP, "ovality_arc_max_pct")):
        m = models()["xgboost"]()
        m.fit(df[feats].to_numpy(float), df[target].to_numpy(float))
        m.get_booster().save_model(str(OUT / f"{name}.json"))
        meta["models"][name] = {"features": feats, "target": target,
                                "ranges": {f: [float(df[f].min()), float(df[f].max())] for f in feats}}
    meta["setup_levels"] = {c: sorted(float(v) for v in df[c].unique()) for c in DESIGN_COLS}
    meta["interval90_deg"] = closed["ml_interval90_deg"]
    meta["cv_best"] = {"setup": best_setup, "setup+process": best_proc}
    (OUT / "model_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


def _write_markdown(r: dict) -> None:
    lines = [f"Springback, {r['n_runs']} runs, {r['n_groups']} setup groups, GroupKFold {r['folds']} folds x "
             f"{r['repeats']} repeats (mean +/- sd over {r['folds'] * r['repeats']} folds).",
             f"Target: mean {r['target_mean']:.3f} deg, sd {r['target_sd']:.3f} deg.", "",
             "| Model - features | MAE (deg) | RMSE (deg) | R2 |", "|---|---|---|---|"]
    for k, s in r["springback"].items():
        if "note" in s:
            lines.append(f"| {k} | {s['mae']:.3f} | {s['rmse']:.3f} | {s['r2']:.2f} |")
        else:
            lines.append(f"| {k} | {s['mae']['mean']:.3f} +/- {s['mae']['sd']:.3f} | "
                         f"{s['rmse']['mean']:.3f} +/- {s['rmse']['sd']:.3f} | {s['r2']['mean']:.2f} +/- {s['r2']['sd']:.2f} |")
    lines += ["", "Random KFold (replicates leak across folds; shown only for comparison):", "",
              "| Model - features | MAE (deg) | R2 |", "|---|---|---|"]
    for k, s in r["springback_random_kfold"].items():
        lines.append(f"| {k} | {s['mae']['mean']:.3f} +/- {s['mae']['sd']:.3f} | {s['r2']['mean']:.2f} +/- {s['r2']['sd']:.2f} |")
    lines += ["", "Ovality (max out-of-roundness on the arc, % of OD):", "", "| Model - features | MAE (%) | R2 |", "|---|---|---|"]
    for k, s in r["ovality"].items():
        lines.append(f"| {k} | {s['mae']['mean']:.3f} +/- {s['mae']['sd']:.3f} | {s['r2']['mean']:.2f} +/- {s['r2']['sd']:.2f} |")
    c = r["closed_loop"]
    lines += ["", f"Closed loop on real runs (share of bends within +/-{c['tolerance_deg']} deg after compensation):", "",
              "| Policy | Within tolerance | Mean abs. error (deg) |", "|---|---|---|"]
    names = {"none": "No compensation", "physics": "Physics estimate (SUS304 assumed)",
             "offset": "Constant offset from trial bends", "ml": f"ML, setup only ({c['models']['ml']})",
             "ml_in_process": f"ML with process signals ({c['models']['ml_in_process']})"}
    for k, v in c["fpy"].items():
        lines.append(f"| {names[k]} | {100 * v:.1f}% | {c['mae_after'][k]:.3f} |")
    p = r["physics"]
    lines += ["", f"Physics estimate for this tube: {p['low']:.2f} / {p['mid']:.2f} / {p['high']:.2f} deg "
              "(flow stress = yield / mean / tensile)."]
    (OUT / "metrics.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def plots(df: pd.DataFrame, oofs: dict, best_setup: str, best_proc: str, proc: list[str]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import shap
    import xgboost as xgb

    y = df["springback_deg"].to_numpy()
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.4))
    for ax, key in zip(axes, (best_setup, best_proc), strict=True):
        p = oofs[key][0]
        ax.scatter(y, p, s=12, alpha=0.6, color="#B23A0B")
        lo, hi = min(y.min(), p.min()) - 0.05, max(y.max(), p.max()) + 0.05
        ax.plot([lo, hi], [lo, hi], color="#16181B", lw=1)
        ax.fill_between([lo, hi], [lo - TOL_DEG, hi - TOL_DEG], [lo + TOL_DEG, hi + TOL_DEG], color="#E8501A", alpha=0.08,
                        label=f"+/-{TOL_DEG} deg")
        ax.set_xlabel("measured springback (deg)")
        ax.set_ylabel("predicted, out-of-fold (deg)")
        ax.set_title(key, fontsize=10)
        ax.legend(loc="upper left", fontsize=8)
    fig.suptitle("TubeBEND springback: parity, GroupKFold by setup", fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT / "parity.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6, 3.6))
    res = y - oofs[best_setup][0]
    ax.scatter(oofs[best_setup][0], res, s=12, alpha=0.6, color="#B23A0B")
    ax.axhline(0, color="#16181B", lw=1)
    ax.set_xlabel("predicted springback (deg)")
    ax.set_ylabel("residual (deg)")
    ax.set_title(f"Residuals, {best_setup}", fontsize=10)
    fig.tight_layout()
    fig.savefig(OUT / "residuals.png", dpi=150)
    plt.close(fig)

    for name, feats in (("setup", SETUP), ("process", SETUP + proc)):
        booster = xgb.Booster()
        booster.load_model(str(OUT / f"springback_{name}.json"))
        x = df[feats].to_numpy(float)
        contrib = booster.predict(xgb.DMatrix(x, feature_names=feats), pred_contribs=True)
        expl = shap.Explanation(values=contrib[:, :-1], base_values=contrib[:, -1], data=x, feature_names=feats)
        plt.figure()
        shap.plots.beeswarm(expl, max_display=12, show=False)
        plt.title(f"SHAP, springback model ({name} features)", fontsize=10)
        plt.tight_layout()
        plt.savefig(OUT / f"shap_beeswarm_{name}.png", dpi=150, bbox_inches="tight")
        plt.close("all")
        plt.figure()
        shap.plots.waterfall(expl[int(np.argmax(y))], max_display=10, show=False)
        plt.title(f"SHAP for run {int(df.index[int(np.argmax(y))])} (largest springback)", fontsize=10)
        plt.savefig(OUT / f"shap_waterfall_{name}.png", dpi=150, bbox_inches="tight")
        plt.close("all")
        mean_abs = np.abs(contrib[:, :-1]).mean(axis=0)
        order = np.argsort(mean_abs)[::-1]
        (OUT / f"shap_importance_{name}.json").write_text(
            json.dumps([{"feature": feats[i], "mean_abs_shap_deg": float(mean_abs[i])} for i in order]), encoding="utf-8")


if __name__ == "__main__":
    out = run()
    print((OUT / "metrics.md").read_text(encoding="utf-8"))
