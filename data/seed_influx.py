#!/usr/bin/env python3

"""
InfluxDB Data Seeder
Seeds InfluxDB with sample telemetry data
"""

import sys
import random
import time
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from common import config, logger
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

def create_sample_data():
    """Create sample telemetry data for routers"""
    
    routers = ['R1', 'R2', 'R3', 'R4', 'R5']
    points = []
    
    # Generate data for the last 24 hours
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=24)
    
    current_time = start_time
    
    while current_time <= end_time:
        for router_id in routers:
            # Generate realistic but varied metrics
            base_cpu = 30 + random.uniform(-10, 40)  # 20-70% base range
            base_mem = 60 + random.uniform(-20, 30)  # 40-90% base range
            
            # Add some spikes for R1 to make it interesting
            if router_id == 'R1' and random.random() < 0.1:
                base_cpu = min(95, base_cpu + random.uniform(20, 40))
                base_mem = max(15, base_mem - random.uniform(20, 40))
            
            # CPU metrics
            cpu_point = Point("cpu") \
                .tag("router_id", router_id) \
                .field("usage_percent", max(0, min(100, base_cpu))) \
                .time(current_time)
            points.append(cpu_point)
            
            # Memory metrics
            mem_point = Point("mem") \
                .tag("router_id", router_id) \
                .field("free_percent", max(0, min(100, base_mem))) \
                .time(current_time)
            points.append(mem_point)
            
            # Error metrics (occasional critical errors for R1)
            error_count = 0
            if router_id == 'R1' and random.random() < 0.05:  # 5% chance
                error_count = random.randint(1, 3)
            elif random.random() < 0.02:  # 2% chance for others
                error_count = 1
            
            error_point = Point("errors") \
                .tag("router_id", router_id) \
                .tag("severity", "critical") \
                .field("count", error_count) \
                .time(current_time)
            points.append(error_point)
            
            # Interface metrics
            interface_point = Point("interfaces") \
                .tag("router_id", router_id) \
                .tag("interface", "GigabitEthernet0/0/0") \
                .field("rx_packets", random.randint(1000, 10000)) \
                .field("tx_packets", random.randint(1000, 10000)) \
                .field("errors", random.randint(0, 5)) \
                .time(current_time)
            points.append(interface_point)
        
        # Move to next time point (5 minute intervals)
        current_time += timedelta(minutes=5)
    
    return points

def seed_influxdb():
    """Seed InfluxDB with sample data"""
    
    try:
        # Create InfluxDB client
        client = InfluxDBClient(
            url=config.influxdb.url,
            token=config.influxdb.token,
            org=config.influxdb.org
        )
        
        # Test connection
        health = client.health()
        if health.status != "pass":
            raise Exception(f"InfluxDB health check failed: {health.status}")
        
        logger.info(f"✅ Connected to InfluxDB at {config.influxdb.url}")
        
        # Create write API
        write_api = client.write_api(write_options=SYNCHRONOUS)
        
        # Generate and write sample data
        logger.info("🌱 Generating sample telemetry data...")
        points = create_sample_data()
        
        logger.info(f"📊 Writing {len(points)} data points to bucket '{config.influxdb.bucket}'...")
        
        # Write data in batches
        batch_size = 1000
        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]
            write_api.write(bucket=config.influxdb.bucket, record=batch)
            logger.info(f"Wrote batch {i//batch_size + 1}/{(len(points) + batch_size - 1)//batch_size}")
        
        # Verify data was written
        query_api = client.query_api()
        
        verification_query = f'''
            from(bucket: "{config.influxdb.bucket}")
                |> range(start: -25h)
                |> group()
                |> count()
        '''
        
        result = query_api.query(verification_query)
        
        total_points = 0
        for table in result:
            for record in table.records:
                total_points += record.get_value()
        
        logger.info(f"✅ Verification: {total_points} points written to InfluxDB")
        
        # Close client
        client.close()
        logger.info("🎉 InfluxDB data seeding completed successfully!")
        
    except Exception as e:
        logger.error(f"❌ InfluxDB seeding failed: {e}")
        sys.exit(1)

def main():
    """Main seeding function"""
    logger.info("🌱 Starting InfluxDB data seeding...")
    
    if not config.influxdb.token:
        logger.error("❌ InfluxDB token not configured. Please set INFLUX_TOKEN environment variable.")
        sys.exit(1)
    
    seed_influxdb()

if __name__ == "__main__":
    main()