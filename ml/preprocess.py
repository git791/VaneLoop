import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from typing import Tuple, List

# Standard 14 informative sensors for FD001
FD001_SENSORS = [
    's2', 's3', 's4', 's7', 's8', 's9', 's11', 's12', 
    's13', 's14', 's15', 's17', 's20', 's21'
]

def load_and_prep_train(filepath: str, sensors: List[str] = FD001_SENSORS) -> Tuple[pd.DataFrame, StandardScaler]:
    """Loads training data, calculates capped RUL, and fits scaler."""
    cols = ['unit', 'cycle', 'op1', 'op2', 'op3'] + [f's{i}' for i in range(1, 22)]
    df = pd.read_csv(filepath, sep=r"\s+", header=None, names=cols)
    
    # RUL calculation with cap
    max_cycles = df.groupby('unit')['cycle'].max()
    df['rul_true'] = df.apply(lambda row: max_cycles[row['unit']] - row['cycle'], axis=1)
    df['rul_true'] = df['rul_true'].clip(upper=125)
    
    # Scale features
    scaler = StandardScaler()
    df[sensors] = scaler.fit_transform(df[sensors])
    
    return df, scaler

def load_and_prep_test(filepath: str, rul_filepath: str, scaler: StandardScaler, sensors: List[str] = FD001_SENSORS) -> pd.DataFrame:
    """Loads test data, applies fitted scaler, and attaches true RUL to the LAST cycle."""
    cols = ['unit', 'cycle', 'op1', 'op2', 'op3'] + [f's{i}' for i in range(1, 22)]
    df = pd.read_csv(filepath, sep=r"\s+", header=None, names=cols)
    
    # Scale features using training scaler
    df[sensors] = scaler.transform(df[sensors])
    
    # Load true RULs
    true_rul = pd.read_csv(rul_filepath, sep=r"\s+", header=None, names=['rul_true'])
    true_rul['unit'] = true_rul.index + 1
    
    # Attach true RUL only to the last cycle of each unit (as per test requirements)
    max_cycles = df.groupby('unit')['cycle'].max().reset_index()
    max_cycles = max_cycles.merge(true_rul, on='unit')
    
    # Merge back to df, leaving earlier cycles as NaN
    df = df.merge(max_cycles[['unit', 'cycle', 'rul_true']], on=['unit', 'cycle'], how='left')
    return df

def generate_rolling_features(df: pd.DataFrame, sensors: List[str]) -> pd.DataFrame:
    """Generates rolling window statistics (mean, std) for baseline LightGBM model."""
    out = df.copy()
    for w in [5, 10, 30]:
        rolled = df.groupby('unit')[sensors].rolling(window=w, min_periods=1)
        means = rolled.mean().reset_index(level=0, drop=True)
        stds = rolled.std().reset_index(level=0, drop=True).fillna(0)
        
        for s in sensors:
            out[f'{s}_mean_{w}'] = means[s]
            out[f'{s}_std_{w}'] = stds[s]
            
    return out
