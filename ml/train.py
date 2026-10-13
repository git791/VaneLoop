import math
import os

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.metrics import mean_squared_error
from sklearn.model_selection import GroupShuffleSplit
from sklearn.preprocessing import StandardScaler

from ml.export import export_model_to_onnx
from ml.preprocess import (
    DATASET_SENSORS,
    FD_SENSORS,
    generate_rolling_features,
    load_and_prep_test,
    load_and_prep_train,
)


def compute_nasa_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Compute asymmetric NASA PHM08 score: d = pred - true."""
    d = y_pred - y_true
    scores = np.where(d < 0, np.exp(-d / 13.0) - 1.0, np.exp(d / 10.0) - 1.0)
    return float(np.sum(scores))


def evaluate_on_test_sets(
    models: dict[str, LGBMRegressor],
    scalers: dict[str, StandardScaler],
    feature_cols: list[str],
) -> dict[str, dict]:
    """Evaluate trained quantile models on the last cycle of each test unit (FD001-FD004)."""
    results: dict[str, dict] = {}
    for dataset in DATASET_SENSORS:
        test_file = f"data/raw/test_{dataset}.txt"
        rul_file = f"data/raw/RUL_{dataset}.txt"
        if not (os.path.exists(test_file) and os.path.exists(rul_file)) or dataset not in scalers:
            continue

        test_df = load_and_prep_test(test_file, rul_file, scalers[dataset], dataset=dataset)
        test_df = generate_rolling_features(test_df, FD_SENSORS)

        # Evaluate at the last observed cycle of each test engine (where rul_true is attached)
        last_cycles = test_df.dropna(subset=["rul_true"]).copy()
        X_test = last_cycles[feature_cols]
        y_true_raw = last_cycles["rul_true"].to_numpy(dtype=float)
        y_true_capped = np.minimum(y_true_raw, 125.0)

        p10 = np.clip(models["p10"].predict(X_test), 0.0, 125.0)
        p50 = np.clip(models["p50"].predict(X_test), 0.0, 125.0)
        p90 = np.clip(models["p90"].predict(X_test), 0.0, 125.0)

        # Ensure quantile monotonicity
        p10 = np.minimum(p10, p50)
        p90 = np.maximum(p90, p50)

        rmse_capped = math.sqrt(mean_squared_error(y_true_capped, p50))
        rmse_raw = math.sqrt(mean_squared_error(y_true_raw, p50))
        nasa_score = compute_nasa_score(y_true_capped, p50)
        in_band = (y_true_capped >= p10) & (y_true_capped <= p90)
        coverage_80 = float(np.mean(in_band))

        # Normalized RUL accuracy (1 - MAE / 125)
        mae = float(np.mean(np.abs(y_true_capped - p50)))
        accuracy = round(max(0.0, 1.0 - (mae / 125.0)), 4)

        results[dataset] = {
            "dataset": dataset,
            "num_test_engines": len(last_cycles),
            "rmse": round(rmse_capped, 2),
            "rmse_uncapped": round(rmse_raw, 2),
            "mae": round(mae, 2),
            "nasa_score": round(nasa_score, 2),
            "coverage_80": round(coverage_80, 4),
            "accuracy": accuracy,
        }
        print(
            f"[{dataset}] Test Evaluation -> RMSE: {rmse_capped:.2f} cycles | "
            f"80% Coverage: {coverage_80 * 100:.1f}% | NASA Score: {nasa_score:.1f} | "
            f"Accuracy: {accuracy * 100:.1f}%"
        )
    return results


def train_all_datasets() -> dict[str, dict]:
    print("Loading and preprocessing all datasets...")
    combined_train_df = pd.DataFrame()
    scalers: dict[str, StandardScaler] = {}

    for dataset in DATASET_SENSORS:
        train_file = f"data/raw/train_{dataset}.txt"
        if not os.path.exists(train_file):
            print(f"Skipping {dataset}, file not found.")
            continue

        df, ds_scaler = load_and_prep_train(train_file, dataset=dataset)
        scalers[dataset] = ds_scaler
        df = generate_rolling_features(df, FD_SENSORS)
        df["dataset"] = dataset
        combined_train_df = pd.concat([combined_train_df, df], ignore_index=True)

    # Fit global scaler metadata for artifact bundle (using FD001 primary scaler if available)
    primary_scaler = scalers.get("FD001") or next(iter(scalers.values()))

    # Keep sensor features + rolling window features (windows: 5, 10, 30)
    feature_cols = [
        c for c in combined_train_df.columns if any(c.startswith(s) for s in FD_SENSORS)
    ]

    # Split by Engine (GroupShuffleSplit on combined data, grouping by dataset+unit)
    combined_train_df["group"] = (
        combined_train_df["dataset"] + "_" + combined_train_df["unit"].astype(str)
    )

    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    train_idx, val_idx = next(gss.split(combined_train_df, groups=combined_train_df["group"]))

    X_train, y_train = (
        combined_train_df.iloc[train_idx][feature_cols],
        combined_train_df.iloc[train_idx]["rul_true"],
    )
    X_val, y_val = (
        combined_train_df.iloc[val_idx][feature_cols],
        combined_train_df.iloc[val_idx]["rul_true"],
    )

    print("Training LightGBM (Quantile Regression) on combined data...")
    models: dict[str, LGBMRegressor] = {}
    for q, alpha in [("p10", 0.1), ("p50", 0.5), ("p90", 0.9)]:
        model = LGBMRegressor(
            objective="quantile",
            alpha=alpha,
            n_estimators=100,
            random_state=42,
            verbose=-1,
        )
        model.fit(X_train, y_train, eval_set=[(X_val, y_val)])
        models[q] = model

    eval_metrics = evaluate_on_test_sets(models, scalers, feature_cols)

    print("Exporting ONNX models and metadata to ml/artifacts...")
    os.makedirs("ml/artifacts", exist_ok=True)
    export_model_to_onnx(
        models,
        primary_scaler,
        feature_cols,
        output_dir="ml/artifacts",
        metrics=eval_metrics,
    )

    # Print feature importance as part of "Why Flagged" requirement
    print("--- Feature Importances ---")
    importance = models["p50"].feature_importances_
    for col, imp in sorted(zip(feature_cols, importance), key=lambda x: x[1], reverse=True)[:10]:
        print(f"{col}: {imp}")

    return eval_metrics


if __name__ == "__main__":
    train_all_datasets()
