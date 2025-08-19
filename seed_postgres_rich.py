#!/usr/bin/env python3
import os
import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv

HERE = os.path.dirname(__file__)
SQL_FILE = os.path.join(HERE, "sample_data_rich.sql")

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv("PG_HOST", "localhost"),
    port=os.getenv("PG_PORT", "5432"),
    dbname=os.getenv("PG_DB", "netops"),
    user=os.getenv("PG_USER", "postgres"),
    password=os.getenv("PG_PASSWORD", "password"),
)

with conn, conn.cursor() as cur:
    with open(SQL_FILE, "r", encoding="utf-8") as f:
        sql_text = f.read()
    cur.execute(sql_text)
    print("Postgres rich seed applied.")

conn.close()
