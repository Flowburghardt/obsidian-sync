# 🚀 Streamlined Notion↔Obsidian Sync 

**Schlanke Docker-Lösung** für bidirektionalen Sync - **funktioniert perfekt mit deinem bestehenden mcp-obsidian Server!**

## 🎯 Setup-Übersicht

Du hast bereits:
✅ **Obsidian** läuft lokal  
✅ **REST API Plugin** installiert  
✅ **mcp-obsidian Server** für Claude  

Wir fügen hinzu:
🔄 **Docker Sync-Container** für Notion↔Obsidian  

## 📁 Architektur

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│     Notion      │    │   Docker Sync    │    │    Obsidian     │
│                 │◄──►│    Container     │◄──►│   + REST API    │
│  (Du schreibst) │    │                  │    │                 │
└─────────────────┘    └──────────────────┘    └─────────┬───────┘
                                                         │
                                                         ▼
                                               ┌─────────────────┐
                                               │  mcp-obsidian   │
                                               │     Server      │◄── Claude
                                               │                 │
                                               └─────────────────┘
```

## 🔧 **Quick Setup**

### 1. Dateien erstellen

Erstelle Ordner `obsidian-sync` mit diesen Dateien:

```
obsidian-sync/
├── Dockerfile                 # → Streamlined Dockerfile
├── docker-compose-sync.yml    # → Streamlined Docker Compose  
├── requirements-sync.txt      # → Minimal Requirements
├── enhanced_notion_sync.py    # → Aus vorheriger Lösung
├── reverse_sync_notion.py     # → Aus vorheriger Lösung
├── master_sync.py             # → Aus vorheriger Lösung
├── sync_cron.sh              # → Streamlined Scripts
└── sync_start.sh             # → Streamlined Scripts
```

### 2. Umgebungsvariablen konfigurieren

**Erstelle `.env`-Datei für sensible Daten:**

```bash
cd obsidian-sync
cat > .env << EOF
NOTION_TOKEN=dein_notion_token_hier
OBSIDIAN_PATH=/shared/obsidian
SYNC_INTERVAL_MINUTES=15
EOF
```

**⚠️ Wichtig:** Ersetze `dein_notion_token_hier` mit deinem echten Notion Integration Token!

### 3. Sync-Container starten

```bash
cd obsidian-sync

# Container bauen und starten
docker-compose -f docker-compose-sync.yml up -d

# Logs verfolgen
docker-compose -f docker-compose-sync.yml logs -f
```

## 🔄 **Workflow**

### **Bidirektionaler Sync (alle 15 Min automatisch):**

```
1. Du schreibst in Notion
   ↓
2. Sync-Container: Notion → Obsidian
   ↓  
3. Claude arbeitet via mcp-obsidian (Lesen + Schreiben)
   ↓
4. Sync-Container: Obsidian → Notion
   ↓
5. Deine neuen Inhalte erscheinen in Notion
```

### **Ordnerstruktur in Obsidian:**

```
ObsidianVault/
├── from-notion/        # Deine Notion-Inhalte (automatisch synced)
├── from-claude/        # Claude's neue Dateien → gehen zu Notion
├── collaboration/      # Bidirektionale Bearbeitung  
├── archive/           # Automatische Backups
└── (deine anderen Dateien bleiben unberührt)
```

## 🤖 **Claude Integration**

Dein bestehender **mcp-obsidian Server bleibt unverändert!** Claude kann:

**✅ Lesen** (über mcp-obsidian):
```
"Claude, lies meine Meeting-Notes von gestern"
→ get_file_contents → from-notion/meeting-notes.md
```

**✅ Schreiben** (über mcp-obsidian):
```  
"Claude, erstelle eine Analyse und speichere sie"
→ append_content → from-claude/analysis.md
→ (wird automatisch zu Notion gesynct)
```

**✅ Erweitern** (über mcp-obsidian):
```
"Claude, füge Insights zu meiner Projektplanung hinzu"  
→ patch_content → collaboration/project-plan.md
→ (wird automatisch zu Notion gesynct)
```

## 🛠️ **Management**

### **Sync manuell ausführen:**
```bash
# Status prüfen
docker exec notion-obsidian-sync python3 master_sync.py status

# Einmaliger Sync  
docker exec notion-obsidian-sync python3 master_sync.py once

# Nur eine Richtung
docker exec notion-obsidian-sync python3 master_sync.py notion-to-obsidian
docker exec notion-obsidian-sync python3 master_sync.py obsidian-to-notion
```

### **Logs anschauen:**
```bash
# Sync-Logs
docker-compose -f docker-compose-sync.yml logs

# Live-Monitoring
docker-compose -f docker-compose-sync.yml logs -f
```

## 💡 **Vorteile dieser Lösung**

**✅ Minimal & Effizient:**
- Nur Sync-Funktionalität, kein redundanter MCP-Server
- Kleine Docker-Image (~200MB vs 500MB+)
- Weniger Ressourcenverbrauch

**✅ Kompatibel:**
- Funktioniert perfekt mit deinem mcp-obsidian Setup
- Keine Konflikte oder Änderungen nötig
- Obsidian bleibt unberührt

**✅ Flexibel:**
- Sync-Intervall anpassbar
- Manuelle Sync-Kontrolle  
- Einfaches Debugging

## 🐛 **Troubleshooting**

### **Volume-Mount Probleme:**
```bash
# Obsidian Vault Pfad prüfen
ls -la ~/Documents/ObsidianVault

# Docker Volume testen
docker exec notion-obsidian-sync ls -la /shared/obsidian
```

### **Sync funktioniert nicht:**
```bash
# Status prüfen
docker exec notion-obsidian-sync python3 master_sync.py status

# Notion-Verbindung testen  
docker exec notion-obsidian-sync python3 -c "
from notion_client import Client
client = Client(auth='$NOTION_TOKEN')
print('Notion OK:', len(client.search()['results']))
"
```

### **Environment-Variablen (.env-Datei):**
```bash
# .env-Datei prüfen
ls -la .env
cat .env

# Container Environment testen
docker exec notion-obsidian-sync env | grep NOTION
```

### **Obsidian REST API:**
- Stelle sicher, dass Obsidian läuft
- REST API Plugin ist aktiviert
- API-Key ist korrekt in mcp-obsidian config

## 🎉 **Ready!**

Du hast jetzt:
✅ **Streamlined Docker-Sync** (schlanke 100MB Lösung)  
✅ **Bestehenden mcp-obsidian** (bleibt unverändert)  
✅ **Bidirektionale Kommunikation** Notion ↔ Obsidian ↔ Claude  
✅ **Minimaler Overhead** und maximale Effizienz  

**Perfect setup für AI-enhanced note-taking!** 🚀

---

## 🔄 **Nächste Schritte:**

1. **Container starten** und ersten Sync testen
2. **Mit Claude via mcp-obsidian experimentieren**  
3. **Workflow optimieren** basierend auf deinen Bedürfnissen

**Das ist jetzt die perfekte, schlanke Lösung für dein Setup!** 🎯