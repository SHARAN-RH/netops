#!/usr/bin/env python3

"""
PostgreSQL Data Seeder
Seeds the database with sample router data and policies
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from common import db, logger

def seed_routers():
    """Seed router data"""
    routers = [
        {
            'id': 'R1',
            'hostname': 'core-router-01',
            'mgmt_ip': '10.0.0.10',
            'vendor': 'cisco',
            'model': 'ISR4331',
            'current_ver': '16.09.04',
            'target_ver': '16.12.03',
            'notes': 'Core router - critical infrastructure'
        },
        {
            'id': 'R2',
            'hostname': 'edge-router-01',
            'mgmt_ip': '10.0.0.11',
            'vendor': 'cisco',
            'model': 'ISR4321',
            'current_ver': '16.09.04',
            'target_ver': '16.12.03',
            'notes': 'Edge router - moderate importance'
        },
        {
            'id': 'R3',
            'hostname': 'branch-router-01',
            'mgmt_ip': '10.0.0.12',
            'vendor': 'cisco',
            'model': 'ISR4221',
            'current_ver': '16.09.04',
            'target_ver': '16.12.03',
            'notes': 'Branch router - low criticality'
        },
        {
            'id': 'R4',
            'hostname': 'wan-router-01',
            'mgmt_ip': '10.0.0.13',
            'vendor': 'juniper',
            'model': 'SRX300',
            'current_ver': '18.4R2',
            'target_ver': '20.4R3',
            'notes': 'WAN edge router'
        },
        {
            'id': 'R5',
            'hostname': 'backup-router-01',
            'mgmt_ip': '10.0.0.14',
            'vendor': 'arista',
            'model': '7050SX3',
            'current_ver': '4.24.2F',
            'target_ver': '4.26.1F',
            'notes': 'Backup router - low priority'
        }
    ]
    
    for router in routers:
        try:
            db.execute_command("""
                INSERT INTO routers (id, hostname, mgmt_ip, vendor, model, current_ver, target_ver, notes)
                VALUES (%(id)s, %(hostname)s, %(mgmt_ip)s, %(vendor)s, %(model)s, %(current_ver)s, %(target_ver)s, %(notes)s)
                ON CONFLICT (id) DO UPDATE SET
                    hostname = EXCLUDED.hostname,
                    mgmt_ip = EXCLUDED.mgmt_ip,
                    vendor = EXCLUDED.vendor,
                    model = EXCLUDED.model,
                    current_ver = EXCLUDED.current_ver,
                    target_ver = EXCLUDED.target_ver,
                    notes = EXCLUDED.notes
            """, router)
            logger.info(f"✅ Seeded router: {router['id']}")
        except Exception as e:
            logger.error(f"❌ Failed to seed router {router['id']}: {e}")

def seed_policies():
    """Seed upgrade policies"""
    policies = [
        {
            'vendor': 'cisco',
            'model': 'ISR4331',
            'min_free_mem_percent': 25,
            'max_cpu_percent': 75,
            'block_if_critical_errors': True
        },
        {
            'vendor': 'cisco',
            'model': 'ISR4321',
            'min_free_mem_percent': 30,
            'max_cpu_percent': 70,
            'block_if_critical_errors': True
        },
        {
            'vendor': 'cisco',
            'model': 'ISR4221',
            'min_free_mem_percent': 35,
            'max_cpu_percent': 65,
            'block_if_critical_errors': True
        },
        {
            'vendor': 'juniper',
            'model': 'SRX300',
            'min_free_mem_percent': 30,
            'max_cpu_percent': 70,
            'block_if_critical_errors': True
        },
        {
            'vendor': 'arista',
            'model': '7050SX3',
            'min_free_mem_percent': 25,
            'max_cpu_percent': 80,
            'block_if_critical_errors': True
        }
    ]
    
    for policy in policies:
        try:
            db.execute_command("""
                INSERT INTO upgrade_policies (vendor, model, min_free_mem_percent, max_cpu_percent, block_if_critical_errors)
                VALUES (%(vendor)s, %(model)s, %(min_free_mem_percent)s, %(max_cpu_percent)s, %(block_if_critical_errors)s)
                ON CONFLICT (vendor, model) DO UPDATE SET
                    min_free_mem_percent = EXCLUDED.min_free_mem_percent,
                    max_cpu_percent = EXCLUDED.max_cpu_percent,
                    block_if_critical_errors = EXCLUDED.block_if_critical_errors
            """, policy)
            logger.info(f"✅ Seeded policy: {policy['vendor']} {policy['model']}")
        except Exception as e:
            logger.error(f"❌ Failed to seed policy {policy['vendor']} {policy['model']}: {e}")

def add_unique_constraints():
    """Add unique constraints to tables"""
    try:
        db.execute_command("""
            ALTER TABLE upgrade_policies 
            ADD CONSTRAINT IF NOT EXISTS unique_vendor_model 
            UNIQUE (vendor, model)
        """)
        logger.info("✅ Added unique constraints")
    except Exception as e:
        logger.error(f"❌ Failed to add constraints: {e}")

def main():
    """Main seeding function"""
    logger.info("🌱 Starting PostgreSQL data seeding...")
    
    try:
        # Initialize schema first
        db.init_schema()
        logger.info("✅ Database schema initialized")
        
        # Add constraints
        add_unique_constraints()
        
        # Seed data
        seed_routers()
        seed_policies()
        
        logger.info("🎉 PostgreSQL data seeding completed successfully!")
        
        # Verify data
        routers = db.execute_query("SELECT COUNT(*) as count FROM routers")
        policies = db.execute_query("SELECT COUNT(*) as count FROM upgrade_policies")
        
        logger.info(f"📊 Seeded {routers[0]['count']} routers and {policies[0]['count']} policies")
        
    except Exception as e:
        logger.error(f"❌ Data seeding failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()