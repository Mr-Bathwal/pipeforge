# Model card: TubeBEND springback and ovality models

## What it predicts

| Item | Value |
|---|---|
| **Primary target** | Springback (degrees) of a rotary-draw bend: the 47° target angle minus the measured angle between the two straight legs. |
| **Secondary target** | Maximum ovality on the arc (% of OD), from the dataset's out-of-roundness values. |
| **Inputs, "setup" model** | The four designed factors: collet boost, pressure-die distance, pressure-die boost and mandrel retraction timing. Plus three positions that drift slightly between runs: mandrel position, clamp-die lateral position and pressure-die lateral position. These are known before bending, so they can drive compensation. |
| **Inputs, "setup + process" model** | Adds 52 features from the bend window: peak, mean, impulse, rise time and end value of the three force sensors (100 Hz) and six axis torques (20 Hz); bend duration and speed; a bending-work proxy; the measured boost ratio. This model is for in-process monitoring. |
| **Models** | Mean baseline, ridge, random forest and XGBoost, with fixed hyperparameters (not tuned on the test folds). Final models are saved as XGBoost JSON, so no pickle is loaded in the app. |

## Data

- **Dataset:** TubeBEND (Oz, Knoche, Yazdani, Engel, Van Laerhoven, 2025).
  - Zenodo [10.5281/zenodo.18458823](https://zenodo.org/records/18458823), licence **CC BY 4.0**.
  - Paper: [arXiv:2509.10272](https://arxiv.org/abs/2509.10272).
- **Runs:** 318 bends on a WAFIOS RBV 35. Three failed runs (1, 48, 166) are dropped, leaving **315 runs**.
- **Tube:** 22 × 1 mm stainless (grade not stated), CLR 33 mm (1.5D), target 47°.
- **Design:** **67 combinations** of the four designed factors. Most have 3–5 replicates; two repeat sets have 54 and 29 runs.
- **Loading:** the raw pickle is loaded with a restricted unpickler that resolves only the 10 pandas/numpy classes the file uses. The md5 is checked against the Zenodo record.

### Label: a "virtual CMM" on the scans

The dataset has no springback column.
- **Method:** each straight leg is scanned as 2 mm cross-section slices. PipeForge fits a circle to each slice, then a line through the circle centres (with outlier rejection). The bend angle is the angle between the two leg axes, the paper's definition.
- **Agreement:** the label agrees with the dataset's own arc end angle (Pearson r = 0.99).
- **Replicate scatter:** about **0.07°**. A single principal axis fitted to each whole leg point cloud gave 0.36°, which is why the slice method is used.
- **Result:** springback = 2.60° ± 0.28° (range 1.94–2.95°).

## Evaluation

- **Scheme:** GroupKFold by setup combination, 5 folds × 5 repeats with shuffled groups, 25 scores per metric. Every score is for a machine setting the model never saw.

| Model, features | MAE (°) | RMSE (°) | R² |
|---|---|---|---|
| Mean (constant), setup | 0.245 ± 0.040 | 0.297 | −0.22 |
| Ridge, setup | 0.165 ± 0.024 | 0.186 | 0.49 |
| Random forest, setup | 0.053 ± 0.015 | 0.078 | 0.90 |
| **XGBoost, setup** | **0.050 ± 0.016** | 0.073 | **0.91 ± 0.08** |
| Ridge, setup + process | 0.048 ± 0.029 | 0.064 | 0.89 |
| XGBoost, setup + process | 0.059 ± 0.028 | 0.080 | 0.86 |
| Physics estimate (SUS304 minimums), no training | 2.245 | 2.263 | −62.9 |

**Random KFold is optimistic.** It puts replicates of a setup in both training and test. It would report 0.033° MAE for XGBoost on setup features and R² 0.96; that is shown in `artifacts/springback/metrics.md` but never quoted as the result.

**Ovality**, XGBoost on setup features: MAE 0.20 ± 0.03 percentage points of OD, R² 0.93, against 1.07 for the mean baseline.

**Uncertainty.** 90% of held-out runs fell within **±0.12°** of the setup model's prediction (the 90th percentile of the absolute out-of-fold error). The app shows this interval with every prediction.

### Explanation (SHAP, exact TreeSHAP from XGBoost)

| Feature | Mean \|effect\| on springback |
|---|---|
| Mandrel retraction timing | 0.207° |
| Collet boost | 0.048° |
| Pressure-die distance | 0.043° |
| Mandrel position | 0.022° |
| Pressure-die boost | 0.006° |

**Caution on mandrel position.** It is not a designed factor; it drifts by about 2 mm between runs. Part of its effect may be a time-order effect (tooling wear or temperature) rather than physics. Grouping by setup does not remove a trend over time.

## Closed loop on real runs

The out-of-fold errors on the 315 runs are used as if each prediction had compensated that bend:

| Policy | Within ±0.5° | Within ±0.25° | Mean abs. error |
|---|---|---|---|
| No compensation | 0% | 0% | 2.60° |
| Physics estimate | 0% | 0% | 2.25° |
| One constant offset for every setup | 88.3% | 57.8% | 0.25° |
| **ML, setup features** | **99.7%** | **99.0%** | 0.054° |
| ML with process signals | 100% | 95.9% | 0.063° |

**Read this fairly.**
- The ML model essentially predicts each setup's springback, which is what trial bends at every changeover would also find.
- Its value is **first-part-right after a changeover, without the trial bends**, which also feeds the SMED kaizen.
- Against a careful per-setup re-teach it would add little.

## Intended use and limits

- **Valid only for the TubeBEND tube, material and tooling:** 22 × 1 mm stainless, CLR 33 mm, mandrel and wiper, WAFIOS RBV 35, around 47°.
- **Other angles:** `pipeline.py` scales the 47° prediction linearly with angle, a documented assumption (springback grows linearly with target angle, per Lee & Van Tyne). Far from 47° this is extrapolation.
- **Not valid** for other materials, diameters, radii or machines. There the app falls back to the physics estimate or a measured trial-bend value, and says so.
- **Tested with the real labels:** cross-validation used the real measured labels, but the model has never driven a real bender. This is a self-directed study, not an industrial deployment.
- **Positions encode run conditions:** the three drifting positions encode run conditions. A new machine or tooling set would need retraining.

## How to reproduce

```
python -m pipeforge.springback_ml.download     # 797 MB pickle, md5 checked
python -m pipeforge.springback_ml.features     # data/tubebend/derived/runs.csv
python -m pipeforge.springback_ml.train        # artifacts/springback/*
```

The derived `runs.csv` is committed, so `train` runs in CI without the raw data.
