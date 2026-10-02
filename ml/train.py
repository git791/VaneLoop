import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import root_mean_squared_error
from ml.preprocess import load_and_prep_train, load_and_prep_test, generate_rolling_features, FD001_SENSORS
import os

def nasa_score(y_true, y_pred):
    """Calculates the NASA asymmetric scoring function."""
    d = y_pred - y_true
    score = np.where(d < 0, np.exp(-d / 13.0) - 1, np.exp(d / 10.0) - 1)
    return np.sum(score)

def train_baseline():
    print("Loading and preprocessing data...")
    train_file = "data/raw/train_FD001.txt"
    test_file = "data/raw/test_FD001.txt"
    rul_file = "data/raw/RUL_FD001.txt"
    
    if not os.path.exists(train_file):
        print("Data not found. Please run ingest first.")
        return
        
    df_train, scaler = load_and_prep_train(train_file)
    df_train = generate_rolling_features(df_train, FD001_SENSORS)
    
    # Exclude base columns, keep rolling features for baseline
    feature_cols = [c for c in df_train.columns if any(c.startswith(s) for s in FD001_SENSORS)]
    
    # Split by Engine (GroupShuffleSplit)
    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    train_idx, val_idx = next(gss.split(df_train, groups=df_train['unit']))
    
    X_train, y_train = df_train.iloc[train_idx][feature_cols], df_train.iloc[train_idx]['rul_true']
    X_val, y_val = df_train.iloc[val_idx][feature_cols], df_train.iloc[val_idx]['rul_true']
    
    print("Training LightGBM Baseline (Quantile Regression)...")
    models = {}
    for q, alpha in [('p10', 0.1), ('p50', 0.5), ('p90', 0.9)]:
        model = LGBMRegressor(objective='quantile', alpha=alpha, n_estimators=100, random_state=42)
        model.fit(X_train, y_train, eval_set=[(X_val, y_val)])
        models[q] = model
        
    print("Evaluating on FD001 Test set (Last cycle only)...")
    df_test = load_and_prep_test(test_file, rul_file, scaler)
    df_test = generate_rolling_features(df_test, FD001_SENSORS)
    
    # Extract last cycle for each test engine
    df_test_last = df_test.dropna(subset=['rul_true'])
    X_test = df_test_last[feature_cols]
    y_test = df_test_last['rul_true']
    
    preds = {q: models[q].predict(X_test) for q in models}
    
    rmse = root_mean_squared_error(y_test, preds['p50'])
    score = nasa_score(y_test, preds['p50'])
    
    # Coverage calculation
    coverage = np.mean((y_test >= preds['p10']) & (y_test <= preds['p90'])) * 100
    
    print(f"--- Results ---")
    print(f"RMSE: {rmse:.2f}")
    print(f"NASA Score: {score:.2f}")
    print(f"80% Interval Coverage: {coverage:.1f}%")
    
    from ml.export import export_model_to_onnx
    print("Exporting models and metadata...")
    export_model_to_onnx(models, scaler, feature_cols, output_dir="ml/artifacts")
    
if __name__ == "__main__":
    train_baseline()
