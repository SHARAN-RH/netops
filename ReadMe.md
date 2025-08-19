mcp-network-upgrader/
├─ docker-compose.yml
├─ .env.example
├─ ansible/
│  ├─ inventory.ini
│  ├─ group_vars/all.yml
│  ├─ playbooks/
│  │  ├─ upgrade.yml
│  │  └─ rollback.yml
├─ servers/
│  ├─ mcp_postgres/
│  │  ├─ server.py
│  │  ├─ requirements.txt
│  │  └─ sql/
│  │     ├─ init.sql
│  ├─ mcp_influx/
│  │  ├─ server.py
│  │  └─ requirements.txt
│  └─ mcp_ansible/
│     ├─ server.py
│     └─ requirements.txt
├─ agent/
│  ├─ decision_agent.py
│  ├─ requirements.txt
│  └─ policy.yaml
├─ interfaces/
│  ├─ telegram_bot.py
│  └─ web_ui.py
└─ README.md
