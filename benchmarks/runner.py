import time

import psutil

from api.app.ingest import (
    detect_dataset_from_filename,
    generate_insert_statements,
    parse_cmapss_file,
)
from api.app.store import Store


def run_benchmark(store: Store, dataset_file: str):
    store.migrate()
    start_time = time.time()

    # Ingest data
    df = parse_cmapss_file(dataset_file)
    records = generate_insert_statements(df, dataset_file)

    # Simulate ingestion to store
    rows_inserted = store.upsert_readings(records)

    end_time = time.time()

    # Collect metrics
    dataset_name = detect_dataset_from_filename(dataset_file)
    metrics = {
        "dataset": dataset_name,
        "rows_inserted": rows_inserted,
        "time_taken": end_time - start_time,
        "memory_usage_mb": psutil.Process().memory_info().rss / (1024 * 1024),
    }
    store.close()
    return metrics
