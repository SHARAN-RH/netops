#!/usr/bin/env python3
import os, math, random
from datetime import datetime, timedelta, timezone
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from dotenv import load_dotenv

load_dotenv()

client = InfluxDBClient(
    url=os.getenv("INFLUX_URL", "http://localhost:8086"),
    token=os.getenv("INFLUX_TOKEN"),
    org=os.getenv("INFLUX_ORG", "netops")
)
write_api = client.write_api(write_options=SYNCHRONOUS)
bucket = os.getenv("INFLUX_BUCKET", "telemetry")

now = datetime.now(timezone.utc)
routers = ["R1","R2","R3","R4","R5","R6","R7","R8"]

# 3h worth of 5-minute samples => 36 samples per router
interval_minutes = 5
samples = int((3*60)/interval_minutes)

print(f"Seeding {samples} samples per router into bucket '{bucket}'...")

for r in routers:
    for i in range(samples):
        ts = now - timedelta(minutes=i*interval_minutes)
        age_hours = i*interval_minutes/60.0

        # Defaults (healthy)
        cpu = 40 + 5*math.sin(i/5)
        mem_free = 70 + 5*math.cos(i/7)
        crit = 0

        # Scenario-specific shaping
        if r == "R1":
            # Healthy -> approve: CPU < 70, mem > 30, no critical in last 2h
            pass
        elif r == "R2":
            # High CPU in last 2h
            if age_hours <= 2:
                cpu = 80 + 5*math.sin(i/3)
        elif r == "R3":
            # Low memory in last 2h
            if age_hours <= 2:
                mem_free = 20 + 5*math.sin(i/4)
        elif r == "R4":
            # Critical errors in last 2h
            if age_hours <= 2 and i % 6 == 0:
                crit = 1
        elif r == "R5":
            # Spike older than 2h (outside decision window)
            if 2 < age_hours <= 3 and i % 6 == 0:
                crit = 1
            # Recent healthy
            cpu = 45; mem_free = 65
        elif r == "R6":
            # Defaults apply, keep it healthy
            cpu = 50; mem_free = 60
        elif r == "R7":
            # Mixed but within limits
            cpu = 60 + 3*math.sin(i/2)
            mem_free = 50 + 3*math.cos(i/2)
        elif r == "R8":
            # Flapping near thresholds (sometimes right below/above)
            cpu = 68 + 4*math.sin(i/2)  # around 70
            mem_free = 32 + 4*math.cos(i/3)  # around 30
            if age_hours <= 2 and i % 18 == 0:
                crit = 0  # keep zero to see borderline approvals depending on instant mean

        # Clamp and cast to integers to match existing field type in bucket
        cpu = int(round(max(0, min(100, float(cpu)))))
        mem_free = int(round(max(0, min(100, float(mem_free)))))

        pt_cpu = Point("cpu").tag("router_id", r).field("usage_percent", cpu).time(ts)
        pt_mem = Point("mem").tag("router_id", r).field("free_percent", mem_free).time(ts)
        pt_err = Point("errors").tag("router_id", r).tag("severity", "critical").field("count", int(crit)).time(ts)

        write_api.write(bucket=bucket, record=[pt_cpu, pt_mem, pt_err])

print("Influx rich seed complete.")
client.close()
