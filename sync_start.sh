#!/bin/bash
# sync_start.sh - Einfacher Container Start

echo "🚀 Starte Notion↔Obsidian Sync Container..."

# Environment prüfen
if [ -z "$NOTION_TOKEN" ]; then
    echo "❌ NOTION_TOKEN ist nicht gesetzt!"
    exit 1
fi

echo "✅ Environment OK"
echo "📁 Obsidian Path: $OBSIDIAN_PATH"
echo "⏰ Sync Interval: ${SYNC_INTERVAL_MINUTES} Minuten"

# Obsidian Ordner prüfen
if [ ! -d "$OBSIDIAN_PATH" ]; then
    echo "❌ Obsidian Vault nicht gefunden: $OBSIDIAN_PATH"
    echo "💡 Stelle sicher, dass der Volume-Mount korrekt ist!"
    exit 1
fi

# Ordnerstruktur erstellen
mkdir -p "$OBSIDIAN_PATH"/{from-notion,from-claude,collaboration,archive}

# Initialer Sync
echo "🔄 Initialer bidirektionaler Sync..."
python3 master_sync.py once

# Sync-Status
echo "📊 Sync-Status:"
python3 master_sync.py status

# Cron starten
echo "⏰ Starte Cron für automatischen Sync..."
cron

# Container läuft und wartet
echo "✅ Sync-Container läuft!"
echo "📝 Logs: docker-compose logs -f"
echo "🔧 Status: docker exec notion-obsidian-sync python3 master_sync.py status"

# Keep container running
tail -f /var/log/sync.log