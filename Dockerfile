# Dockerfile - Streamlined Obsidian-Sync (ohne MCP-Server)
FROM python:3.11-slim

# System packages
RUN apt-get update && apt-get install -y \
    cron \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python dependencies (minimal)
COPY requirements-sync.txt .
RUN pip install --no-cache-dir -r requirements-sync.txt

# Nur Sync-Scripts
COPY enhanced_notion_sync.py .
COPY reverse_sync_notion.py .
COPY master_sync.py .
COPY sync_cron.sh .
COPY sync_start.sh .

# Permissions
RUN chmod +x sync_cron.sh sync_start.sh

# Cron setup - Bidirektionaler Sync alle 15 Min
RUN echo "*/15 * * * * /app/sync_cron.sh >> /var/log/sync.log 2>&1" | crontab -

# Environment variables (NOTION_TOKEN wird sicher über .env geladen)
ENV OBSIDIAN_PATH="/shared/obsidian"
ENV SYNC_INTERVAL_MINUTES="15"

# Start script
CMD ["/app/sync_start.sh"]