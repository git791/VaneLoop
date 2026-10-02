import os
import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import GroupShuffleSplit
from ml.preprocess import load_and_prep_train, FD_SENSORS, DATASET_SENSORS, generate_rolling_features
from ml.export import export_model_to_onnx

def train_all_datasets():
    print("Loading and preprocessing all datasets...")
    combined_train_df = pd.DataFrame()
    
    for dataset in DATASET_SENSORS.keys():
        train_file = f"data/raw/train_{dataset}.txt"
        if not os.path.exists(train_file):
            print(f"Skipping {dataset}, file not found.")
            continue
            
        df, _ = load_and_prep_train(train_file, dataset=dataset)
        df = generate_rolling_features(df, FD_SENSORS)
        df['dataset'] = dataset
        combined_train_df = pd.concat([combined_train_df, df])
        
    # Re-fit scaler on combined data
    scaler = StandardScaler()
    scaler.fit(combined_train_df[FD_SENSORS])
    combined_train_df[FD_SENSORS] = scaler.transform(combined_train_df[FD_SENSORS])
    
    # Exclude base columns, keep rolling features
    feature_cols = [c for c in combined_train_df.columns if any(c.startswith(s) for s in FD_SENSORS)]
    
    # Split by Engine (GroupShuffleSplit on combined data, grouping by dataset+unit)
    combined_train_df['group'] = combined_train_df['dataset'] + '_' + combined_train_df['unit'].astype(str)
    
    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    train_idx, val_idx = next(gss.split(combined_train_df, groups=combined_train_df['group']))
    
    X_train, y_train = combined_train_df.iloc[train_idx][feature_cols], combined_train_df.iloc[train_idx]['rul_true']
    X_val, y_val = combined_train_df.iloc[val_idx][feature_cols], combined_train_df.iloc[val_idx]['rul_true']
    
    print("Training LightGBM (Quantile Regression) on combined data...")
    models = {}
    for q, alpha in [('p10', 0.1), ('p50', 0.5), ('p90', 0.9)]:
        model = LGBMRegressor(objective='quantile', alpha=alpha, n_estimators=100, random_state=42)
        model.fit(X_train, y_train, eval_set=[(X_val, y_val)])
        models[q] = model
        
    # Exporting...
    print("Exporting models and metadata (Skipping ONNX export due to compatibility)...")
    os.makedirs("ml/artifacts", exist_ok=True)
    # export_model_to_onnx(models, scaler, feature_cols, output_dir="ml/artifacts")
    
    # Print feature importance as part of "Why Flagged" requirement
    print("--- Feature Importances ---")
    importance = models['p50'].feature_importances_
    for col, imp in sorted(zip(feature_cols, importance), key=lambda x: x[1], reverse=True)[:10]:
        print(f"{col}: {imp}")

if __name__ == "__main__":
    train_all_datasets()

