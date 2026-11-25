Springback, 315 runs, 67 setup groups, GroupKFold 5 folds x 5 repeats (mean +/- sd over 25 folds).
Target: mean 2.598 deg, sd 0.284 deg.

| Model - features | MAE (deg) | RMSE (deg) | R2 |
|---|---|---|---|
| mean | setup | 0.245 +/- 0.040 | 0.297 +/- 0.041 | -0.22 +/- 0.42 |
| ridge | setup | 0.165 +/- 0.024 | 0.186 +/- 0.025 | 0.49 +/- 0.26 |
| random_forest | setup | 0.053 +/- 0.015 | 0.078 +/- 0.027 | 0.90 +/- 0.09 |
| xgboost | setup | 0.050 +/- 0.016 | 0.073 +/- 0.028 | 0.91 +/- 0.08 |
| ridge | setup+process | 0.048 +/- 0.029 | 0.064 +/- 0.036 | 0.89 +/- 0.21 |
| random_forest | setup+process | 0.061 +/- 0.024 | 0.081 +/- 0.034 | 0.87 +/- 0.15 |
| xgboost | setup+process | 0.059 +/- 0.028 | 0.080 +/- 0.037 | 0.86 +/- 0.20 |
| physics (SUS304 assumed) | none | 2.245 | 2.263 | -62.86 |

Random KFold (replicates leak across folds; shown only for comparison):

| Model - features | MAE (deg) | R2 |
|---|---|---|
| ridge | setup | 0.135 +/- 0.012 | 0.65 +/- 0.09 |
| xgboost | setup | 0.033 +/- 0.005 | 0.96 +/- 0.03 |
| ridge | setup+process | 0.030 +/- 0.003 | 0.98 +/- 0.01 |
| xgboost | setup+process | 0.032 +/- 0.005 | 0.97 +/- 0.01 |

Ovality (max out-of-roundness on the arc, % of OD):

| Model - features | MAE (%) | R2 |
|---|---|---|
| mean | setup | 1.070 +/- 0.160 | -0.22 +/- 0.22 |
| xgboost | setup | 0.201 +/- 0.033 | 0.93 +/- 0.04 |
| xgboost | setup+process | 0.206 +/- 0.032 | 0.94 +/- 0.03 |

Closed loop on real runs (share of bends within +/-0.5 deg after compensation):

| Policy | Within tolerance | Mean abs. error (deg) |
|---|---|---|
| No compensation | 0.0% | 2.598 |
| Physics estimate (SUS304 assumed) | 0.0% | 2.245 |
| Constant offset from trial bends | 88.3% | 0.248 |
| ML, setup only (xgboost | setup) | 99.7% | 0.054 |
| ML with process signals (ridge | setup+process) | 100.0% | 0.063 |

Physics estimate for this tube: 0.20 / 0.35 / 0.51 deg (flow stress = yield / mean / tensile).
