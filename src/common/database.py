"""Database utilities and connection management"""

import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from typing import Dict, List, Any, Generator
from .config import config

class DatabaseManager:
    """PostgreSQL database connection manager"""
    
    def __init__(self):
        self.dsn = config.postgres_dsn
    
    @contextmanager
    def get_connection(self) -> Generator[psycopg2.extensions.connection, None, None]:
        """Get database connection context manager"""
        conn = None
        try:
            conn = psycopg2.connect(self.dsn)
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            raise e
        finally:
            if conn:
                conn.close()
    
    def execute_query(self, query: str, params: tuple = None) -> List[Dict[str, Any]]:
        """Execute SELECT query and return results"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(query, params or ())
                return [dict(row) for row in cur.fetchall()]
    
    def execute_command(self, query: str, params: tuple = None) -> int:
        """Execute INSERT/UPDATE/DELETE and return affected rows"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params or ())
                conn.commit()
                return cur.rowcount
    
    def execute_returning(self, query: str, params: tuple = None) -> Dict[str, Any]:
        """Execute INSERT/UPDATE with RETURNING clause"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(query, params or ())
                conn.commit()
                result = cur.fetchone()
                return dict(result) if result else {}
    
    def init_schema(self):
        """Initialize database schema"""
        schema_sql = """
        CREATE TABLE IF NOT EXISTS routers (
            id TEXT PRIMARY KEY,
            hostname TEXT NOT NULL,
            mgmt_ip INET NOT NULL,
            vendor TEXT NOT NULL,
            model TEXT NOT NULL,
            current_ver TEXT NOT NULL,
            target_ver TEXT,
            maintenance_window TSTZRANGE,
            last_upgrade_at TIMESTAMPTZ,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS upgrade_policies (
            id SERIAL PRIMARY KEY,
            vendor TEXT NOT NULL,
            model TEXT NOT NULL,
            min_free_mem_percent INT DEFAULT 30,
            max_cpu_percent INT DEFAULT 70,
            block_if_critical_errors BOOLEAN DEFAULT true
        );

        CREATE TABLE IF NOT EXISTS upgrades (
            id BIGSERIAL PRIMARY KEY,
            router_id TEXT REFERENCES routers(id),
            requested_by TEXT,
            decision TEXT CHECK (decision IN ('approve','deny')),
            reason TEXT,
            status TEXT DEFAULT 'pending',
            target_ver TEXT,
            started_at TIMESTAMPTZ DEFAULT NOW(),
            finished_at TIMESTAMPTZ
        );

        CREATE TABLE IF NOT EXISTS audit_events (
            ts TIMESTAMPTZ DEFAULT NOW(),
            router_id TEXT,
            event TEXT,
            details JSONB
        );
        """
        self.execute_command(schema_sql)

# Global database manager instance
db = DatabaseManager()