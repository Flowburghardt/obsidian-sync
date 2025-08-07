#!/bin/bash
# sync_cron.sh - Einfacher bidirektionaler Sync via Cron

cd /app

echo "$(date): Starte Notion↔Obsidian Sync..."

# Environment variables
export NOTION_TOKEN="${NOTION_TOKEN}"
export OBSIDIAN_PATH="${OBSIDIAN_PATH}"

# Bidirektionaler Sync
python3 master_sync.py once

echo "$(date): Sync abgeschlossen"