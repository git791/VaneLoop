import time
import psutil
import pandas as pd
from api.app.store import Store
from api.app.ingest import parse_cmapss_file, generate_insert_statements

def run_benchmark(store: Store, dataset_file: str):
    start_time = time.time()
    
    # Ingest data
    df = parse_cmapss_file(dataset_file)
    records = generate_insert_statements(df, dataset_file)
    
    # Simulate ingestion to store
    rows_inserted = store.upsert_readings(records)
    
    end_time = time.time()
    
    # Collect metrics
    metrics = {
        "dataset": "FD001",
        "rows_inserted": rows_inserted,
        "time_taken": end_time - start_time,
        "memory_usage_mb": psutil.Process().memory_info().rss / (1024 * 1024),
    }
    
    return metrics
