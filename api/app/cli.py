import typer

from .ingest import generate_insert_statements, parse_cmapss_file
from .store import get_store

app = typer.Typer(help="VaneLoop CLI")


@app.command()
def migrate(
    schema_path: str = typer.Option("infra/cassandra/schema.cql", help="Path to schema.cql"),
):
    """Run Cassandra schema migrations."""
    store = get_store()
    try:
        typer.echo(f"Running migrations from {schema_path}...")
        store.migrate(schema_path)
        typer.echo("Migration complete.")
    finally:
        store.disconnect()


@app.command()
def ingest(
    dataset: str = typer.Option(
        "all", help="Dataset name, e.g. FD001, FD002, FD003, FD004 or 'all'"
    ),
    file_path: str = typer.Option(
        None, help="Path to raw dataset file (optional, defaults to data/raw/train_{dataset}.txt)"
    ),
):
    """Ingest dataset(s) into Cassandra / SQLite."""
    import os

    datasets = ["FD001", "FD002", "FD003", "FD004"] if dataset.lower() == "all" else [dataset]
    store = get_store()
    try:
        total_inserted = 0
        for ds in datasets:
            path = file_path if (file_path and len(datasets) == 1) else f"data/raw/train_{ds}.txt"
            if not os.path.exists(path):
                typer.echo(f"Warning: File {path} does not exist, skipping {ds}.")
                continue
            typer.echo(f"Parsing {ds} from {path}...")
            df = parse_cmapss_file(path)
            records = generate_insert_statements(df, path, dataset=ds)
            typer.echo(f"Parsed {len(records)} records for {ds}.")
            inserted = store.upsert_readings(records)
            typer.echo(f"Ingestion for {ds} complete: {inserted} readings.")
            total_inserted += inserted
        typer.echo(f"Total ingested across datasets: {total_inserted} readings.")
    finally:
        store.disconnect()


if __name__ == "__main__":
    app()
