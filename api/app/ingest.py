from typing import Any

import pandas as pd


def parse_cmapss_file(filepath: str) -> pd.DataFrame:
    """Parse a C-MAPSS dataset file."""
    # 26 columns: unit, cycle, op1, op2, op3, s1..s21
    columns = ["unit", "cycle", "op1", "op2", "op3"] + [f"s{i}" for i in range(1, 22)]
    df = pd.read_csv(filepath, sep=r"\s+", header=None, names=columns)

    # Calculate RUL for train sets
    if "train" in filepath:
        max_cycles = df.groupby("unit")["cycle"].max()
        df["rul_true"] = df.apply(lambda row: max_cycles[row["unit"]] - row["cycle"], axis=1)
        # Cap RUL at 125
        df["rul_true"] = df["rul_true"].clip(upper=125)
    else:
        df["rul_true"] = None

    return df


def detect_dataset_from_filename(filename: str) -> str:
    """Extract dataset name from C-MAPSS filename."""
    # Example: 'train_FD001.txt' → 'FD001'
    parts = filename.split("_")
    return parts[1].split(".")[0]


def generate_insert_statements(
    df: pd.DataFrame, filepath: str, dataset: str | None = None
) -> list[dict[str, Any]]:
    """Convert dataframe rows to dicts for ingestion."""
    records = []
    ds = dataset or detect_dataset_from_filename(filepath)
    for _, row in df.iterrows():
        record = row.to_dict()
        record["dataset"] = ds
        records.append(record)
    return records
