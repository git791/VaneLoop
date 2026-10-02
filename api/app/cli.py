import typer
from .store import Store

app = typer.Typer(help="VaneLoop CLI")

@app.command()
def migrate(
    schema_path: str = typer.Option("infra/cassandra/schema.cql", help="Path to schema.cql")
):
    """Run Cassandra schema migrations."""
    store = Store()
    store.connect()
    try:
        typer.echo(f"Running migrations from {schema_path}...")
        store.migrate(schema_path)
        typer.echo("Migration complete.")
    finally:
        store.disconnect()

from .ingest import parse_cmapss_file, generate_insert_statements

@app.command()
def ingest(
    dataset: str = typer.Option("FD001", help="Dataset name, e.g. FD001"),
    file_path: str = typer.Option("data/raw/train_FD001.txt", help="Path to raw dataset file")
):
    """Ingest dataset into Cassandra."""
    typer.echo(f"Parsing {dataset} from {file_path}...")
    try:
        df = parse_cmapss_file(file_path)
        records = generate_insert_statements(df)
        typer.echo(f"Parsed {len(records)} records for {dataset}.")
        
        store = Store()
        store.connect()
        try:
            for record in records:
                store.insert_engine_reading(record)
            typer.echo(f"Ingestion for {dataset} complete.")
        finally:
            store.disconnect()
    except Exception as e:
        typer.echo(f"Ingestion failed: {e}")

if __name__ == "__main__":
    app()
