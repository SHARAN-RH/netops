"""Configuration management for MCP Network Upgrader"""

import os
from typing import Dict, Any
from dotenv import load_dotenv
from pydantic import BaseSettings, Field

load_dotenv()

class DatabaseConfig(BaseSettings):
    host: str = Field(default="localhost", env="PG_HOST")
    port: int = Field(default=5432, env="PG_PORT")
    database: str = Field(default="netops", env="PG_DB")
    user: str = Field(default="postgres", env="PG_USER")
    password: str = Field(default="postgres", env="PG_PASSWORD")

class InfluxDBConfig(BaseSettings):
    url: str = Field(default="http://localhost:8086", env="INFLUX_URL")
    token: str = Field(default="", env="INFLUX_TOKEN")
    org: str = Field(default="netops", env="INFLUX_ORG")
    bucket: str = Field(default="telemetry", env="INFLUX_BUCKET")
    user: str = Field(default="admin", env="INFLUX_USER")
    password: str = Field(default="password", env="INFLUX_PASSWORD")

class RedisConfig(BaseSettings):
    host: str = Field(default="localhost", env="REDIS_HOST")
    port: int = Field(default=6379, env="REDIS_PORT")

class AIConfig(BaseSettings):
    anthropic_api_key: str = Field(default="", env="ANTHROPIC_API_KEY")
    openai_api_key: str = Field(default="", env="OPENAI_API_KEY")

class NetworkConfig(BaseSettings):
    username: str = Field(default="admin", env="NETWORK_USERNAME")
    password: str = Field(default="password", env="NETWORK_PASSWORD")

class AppConfig(BaseSettings):
    debug: bool = Field(default=False, env="DEBUG")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    jwt_secret: str = Field(default="secret", env="JWT_SECRET")
    api_rate_limit: int = Field(default=100, env="API_RATE_LIMIT")
    telegram_token: str = Field(default="", env="TELEGRAM_TOKEN")

class Config:
    """Main configuration class"""
    
    def __init__(self):
        self.database = DatabaseConfig()
        self.influxdb = InfluxDBConfig()
        self.redis = RedisConfig()
        self.ai = AIConfig()
        self.network = NetworkConfig()
        self.app = AppConfig()
    
    @property
    def postgres_dsn(self) -> str:
        return f"postgresql://{self.database.user}:{self.database.password}@{self.database.host}:{self.database.port}/{self.database.database}"

# Global config instance
config = Config()