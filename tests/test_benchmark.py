import pytest
from api.app.store import SQLiteStore
from benchmarks.runner import run_benchmark
from pathlib import Path

def test_benchmark_ingestion_metrics():
    # Setup
    db_path = Path("test_benchmark.db")
    store = SQLiteStore(db_path)
    dataset_file = "data/raw/train_FD001.txt"
    
    # Run benchmark
    metrics = run_benchmark(store, dataset_file)
    
    # Verify
    assert metrics["rows_inserted"] > 0
    assert metrics["time_taken"] > 0
    assert "memory_usage_mb" in metrics
    
    # Cleanup
    if db_path.exists():
        db_path.unlink()
