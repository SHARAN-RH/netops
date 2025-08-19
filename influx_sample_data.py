#!/usr/bin/env python3
import os
from datetime import datetime, timedelta
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# InfluxDB connection
client = InfluxDBClient(
    url=os.getenv("INFLUX_URL", "http://localhost:8086"),
    token=os.getenv("INFLUX_TOKEN"),
    org=os.getenv("INFLUX_ORG", "netops")
)

write_api = client.write_api(write_options=SYNCHRONOUS)
bucket = os.getenv("INFLUX_BUCKET", "telemetry")

# Test connection first
try:
    buckets = client.buckets_api().find_buckets()
    print(f"Connected to InfluxDB. Found {len(buckets.buckets)} buckets.")
except Exception as e:
    print(f"Connection failed: {e}")
    exit(1)

# Generate sample data for last 24 hours
routers = ["R1", "R2", "R3", "R4", "R5"]
now = datetime.utcnow()

print("Inserting sample telemetry data...")

for router in routers:
    for i in range(144):  # 24 hours * 6 (every 10 minutes)
        timestamp = now - timedelta(minutes=i*10)
        
        # CPU usage (varies by router)
        cpu_base = {"R1": 45, "R2": 60, "R3": 35, "R4": 55, "R5": 40}
        cpu_usage = cpu_base[router] + (i % 20) - 10  # ±10% variation
        
        # Memory free percentage
        mem_base = {"R1": 65, "R2": 40, "R3": 75, "R4": 50, "R5": 70}
        mem_free = mem_base[router] + (i % 15) - 7  # ±7% variation
        
        # Critical errors (occasional spikes)
        critical_errors = 1 if i % 30 == 0 else 0
        
        # Write CPU measurement
        point_cpu = Point("cpu") \
            .tag("router_id", router) \
            .field("usage_percent", max(0, min(100, cpu_usage))) \
            .time(timestamp)
        
        # Write Memory measurement
        point_mem = Point("mem") \
            .tag("router_id", router) \
            .field("free_percent", max(0, min(100, mem_free))) \
            .time(timestamp)
        
        # Write Error measurement
        point_err = Point("errors") \
            .tag("router_id", router) \
            .tag("severity", "critical") \
            .field("count", critical_errors) \
            .time(timestamp)
        
        write_api.write(bucket=bucket, record=[point_cpu, point_mem, point_err])

print(f"Sample data inserted for {len(routers)} routers over 24 hours")
client.close()
