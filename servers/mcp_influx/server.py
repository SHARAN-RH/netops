from fastapi import FastAPI
from pydantic import BaseModel
import os
from datetime import timedelta
from influxdb_client import InfluxDBClient
from dotenv import load_dotenv

# Load .env from project root regardless of current working directory
ENV_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
load_dotenv(dotenv_path=ENV_PATH)

app = FastAPI(title="MCP Influx")

client = InfluxDBClient(
    url=os.getenv("INFLUX_URL", "http://localhost:8086"),
    token=os.getenv("INFLUX_TOKEN"),
    org=os.getenv("INFLUX_ORG", "netops")
)
bucket = os.getenv("INFLUX_BUCKET", "telemetry")

class Windowed(BaseModel):
    router_id: str
    window: str = "1h"  # Influx duration literal

def q(query: str):
    return client.query_api().query(org=client.org, query=query)

@app.post("/tool/cpu_avg")
def cpu_avg(p: Windowed):
    data = q(f'''
    from(bucket:"{bucket}")
      |> range(start: -{p.window})
      |> filter(fn:(r)=> r._measurement=="cpu" and r.router_id=="{p.router_id}" and r._field=="usage_percent")
      |> mean()
    ''')
    v = next((r.records[0].values.get("_value") for r in data if r.records), None)
    return {"avg_cpu": v}

@app.post("/tool/mem_free_min")
def mem_free_min(p: Windowed):
    data = q(f'''
    from(bucket:"{bucket}")
      |> range(start: -{p.window})
      |> filter(fn:(r)=> r._measurement=="mem" and r.router_id=="{p.router_id}" and r._field=="free_percent")
      |> min()
    ''')
    v = next((r.records[0].values.get("_value") for r in data if r.records), None)
    return {"min_free_mem": v}

@app.post("/tool/critical_error_count")
def critical_error_count(p: Windowed):
    data = q(f'''
    from(bucket:"{bucket}")
      |> range(start: -{p.window})
      |> filter(fn:(r)=> r._measurement=="errors" and r.router_id=="{p.router_id}" and r.severity=="critical" and r._field=="count")
      |> sum()
    ''')
    v = next((r.records[0].values.get("_value") for r in data if r.records), 0)
    return {"critical_errors": v or 0}

if __name__ == "__main__":
    import uvicorn, os
    # Use a dedicated env var for this service's port to avoid conflicts
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("INFLUX_SERVER_PORT","7002")))
