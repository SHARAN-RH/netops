# Database Configuration
PG_HOST=localhost
PG_PORT=5432
PG_DB=netops
PG_USER=postgres
PG_PASSWORD=postgres

# InfluxDB Configuration  
INFLUX_URL=http://localhost:8086
INFLUX_TOKEN=netops-token-123
INFLUX_ORG=netops
INFLUX_BUCKET=telemetry
INFLUX_USER=admin
INFLUX_PASSWORD=password

# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379

# AI/LLM Configuration
ANTHROPIC_API_KEY=sk-ant-your-key-here
OPENAI_API_KEY=sk-your-key-here

# Telegram Bot Configuration
TELEGRAM_TOKEN=your-telegram-bot-token

# Network Device Access (for Ansible)
NETWORK_USERNAME=admin
NETWORK_PASSWORD=password

# Logging Configuration
LOG_LEVEL=INFO

# Security Configuration
JWT_SECRET=your-jwt-secret-key
API_RATE_LIMIT=100

# Development Configuration
DEBUG=true