# VaneLoop RUL Model Card

## Model Details
* **Version:** 1.0.0
* **Architecture:** LightGBM Gradient Boosting Trees (Quantile Regression: $\alpha \in \{0.10, 0.50, 0.90\}$)
* **Export Format:** ONNX (`ml/artifacts/model_p10.onnx`, `model_p50.onnx`, `model_p90.onnx`)
* **Date:** 2026-10-13

## Intended Use
* **Primary Use Case:** Predicting Remaining Useful Life (RUL) of turbofan engines based on multivariate time-series telemetry.
* **Limitations:** Simulated data only (NASA C-MAPSS FD001–FD004). Capped at 125 cycles. Cannot be used for real-world aircraft maintenance or airworthiness decisions.

## Data & Preprocessing
* **Datasets:** NASA C-MAPSS FD001, FD002, FD003, FD004
* **Input Features:** Base readings plus rolling means and standard deviations (windows: 5, 10, 30 cycles) of the 14 informative sensors (`s2, s3, s4, s7, s8, s9, s11, s12, s13, s14, s15, s17, s20, s21`) — 98 features total.
* **Target:** RUL (Remaining cycles to failure), piecewise capped at 125.
* **Scaling & Splitting:** `StandardScaler` fit on training sets; validation split strictly by engine unit (`GroupShuffleSplit`) to prevent trajectory leakage.

## Verified Evaluation Metrics (Last Observed Test Cycle, Capped at 125)
Reproduced via `uv run python -m ml.train` (stored in `ml/artifacts/metrics.json`):

| Dataset | Test Engines | RMSE (cycles) | MAE (cycles) | 80% Interval Coverage ($p_{10}\text{--}p_{90}$) | NASA PHM08 Score | RUL Accuracy ($1 - \text{MAE}/125$) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **FD001** | 100 | 20.47 | 14.00 | 85.0% | 2,095.24 | 88.8% |
| **FD002** | 259 | 23.59 | 16.82 | 87.3% | 9,268.98 | 86.6% |
| **FD003** | 100 | 19.18 | 12.68 | 75.0% | 2,131.34 | 89.8% |
| **FD004** | 248 | 22.66 | 16.19 | 85.9% | 4,077.90 | 87.1% |

## Ethical Considerations
Model estimates uncertainty bounds, but must remain supervised by a domain expert. No automatic dispatch or grounding decisions should be made based on this simulation output.
