import json
from .main import app

def export():
    openapi_schema = app.openapi()
    print(json.dumps(openapi_schema, indent=2))

if __name__ == "__main__":
    export()
