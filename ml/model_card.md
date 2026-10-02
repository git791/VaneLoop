# VaneLoop RUL Model Card

## Model Details
* **Version:** 1.0.0
* **Architecture:** LightGBM Gradient Boosting Trees (Quantile Regression)
* **Date:** 2026-10-02

## Intended Use
* **Primary Use Case:** Predicting Remaining Useful Life (RUL) of turbofan engines based on time-series telemetry.
* **Limitations:** Simulated data only (NASA C-MAPSS). Valid primarily for single-fault mode (HPC degradation) as seen in FD001. Capped at 125 cycles. Cannot be used for real-world aircraft maintenance.

## Data & Preprocessing
* **Dataset:** NASA C-MAPSS FD001
* **Input Features:** Rolling means and standard deviations (windows: 5, 10, 30 cycles) of the 14 informative sensors (s2, s3, s4, s7, s8, s9, s11, s12, s13, s14, s15, s17, s20, s21).
* **Target:** RUL (Remaining cycles to failure), piecewise capped at 125.
* **Scaling:** StandardScaler fit only on training engines to prevent data leakage.

## Evaluation Metrics (FD001 Test Set - Last Cycle)
* **RMSE:** Evaluated using the p50 predictions against true test RUL.
* **NASA Score:** Asymmetric scoring function penalizing over-predictions (late maintenance) more heavily than under-predictions.
* **Prediction Interval Coverage:** Target 80% coverage (p10 to p90).

## Ethical Considerations
Model estimates uncertainty, but must remain supervised by a domain expert. No automatic dispatch/grounding decisions should be made based purely on this output.
