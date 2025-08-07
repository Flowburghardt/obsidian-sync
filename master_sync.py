#!/usr/bin/env python3
# master_sync.py - Koordiniert bidirektionale Synchronisation

import os
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path
import subprocess
import time

class MasterSyncController:
    def __init__(self):
        self.obsidian_path = Path(os.getenv('OBSIDIAN_PATH', '/shared/obsidian'))
        self.sync_interval = int(os.getenv('SYNC_INTERVAL_MINUTES', '15'))
        self.state_file = self.obsidian_path / '.sync_state.json'
        
        self.load_sync_state()
    
    def load_sync_state(self):
        """Sync-Status laden"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    self.state = json.load(f)
            except Exception as e:
                print(f"⚠️ Fehler beim Laden des Sync-Status: {e}")
                self.state = self.create_default_state()
        else:
            self.state = self.create_default_state()
    
    def create_default_state(self):
        """Standard Sync-Status erstellen"""
        return {
            'last_notion_to_obsidian': None,
            'last_obsidian_to_notion': None,
            'last_full_sync': None,
            'sync_count': 0,
            'error_count': 0,
            'last_error': None
        }
    
    def save_sync_state(self):
        """Sync-Status speichern"""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            print(f"⚠️ Fehler beim Speichern des Sync-Status: {e}")
    
    def run_script(self, script_name, description):
        """Python-Script ausführen"""
        try:
            print(f"🔄 Starte {description}...")
            
            result = subprocess.run([
                'python3', f'/app/{script_name}'
            ], capture_output=True, text=True, timeout=300)  # 5 Min Timeout
            
            if result.returncode == 0:
                print(f"✅ {description} erfolgreich")
                if result.stdout:
                    print(f"📝 Output: {result.stdout[-500:]}")  # Letzte 500 Zeichen
                return True
            else:
                print(f"❌ {description} fehlgeschlagen")
                print(f"❌ Error: {result.stderr}")
                self.state['error_count'] += 1
                self.state['last_error'] = {
                    'script': script_name,
                    'error': result.stderr,
                    'timestamp': datetime.now().isoformat()
                }
                return False
        
        except subprocess.TimeoutExpired:
            print(f"⏰ {description} Timeout (>5 Min)")
            return False
        except Exception as e:
            print(f"💥 Unerwarteter Fehler bei {description}: {e}")
            return False
    
    def check_pending_files(self):
        """Prüft ob Dateien auf Sync warten"""
        pending_count = 0
        
        for file_path in self.obsidian_path.glob("**/*.md"):
            if 'archive' in str(file_path):
                continue
            
            try:
                import frontmatter
                with open(file_path, 'r', encoding='utf-8') as f:
                    post = frontmatter.load(f)
                
                if post.metadata.get('sync_status') == 'pending':
                    pending_count += 1
            
            except Exception:
                continue
        
        return pending_count
    
    def sync_notion_to_obsidian(self):
        """Notion → Obsidian Sync ausführen"""
        success = self.run_script(
            'enhanced_notion_sync.py',
            'Notion → Obsidian Sync'
        )
        
        if success:
            self.state['last_notion_to_obsidian'] = datetime.now().isoformat()
        
        return success
    
    def sync_obsidian_to_notion(self):
        """Obsidian → Notion Sync ausführen"""
        # Prüfe zuerst ob pending Dateien existieren
        pending_count = self.check_pending_files()
        
        if pending_count == 0:
            print("📄 Keine pending Dateien für Obsidian → Notion Sync")
            return True
        
        print(f"📄 {pending_count} Dateien warten auf Notion-Sync")
        
        success = self.run_script(
            'reverse_sync_notion.py',
            'Obsidian → Notion Sync'
        )
        
        if success:
            self.state['last_obsidian_to_notion'] = datetime.now().isoformat()
        
        return success
    
    def run_full_sync(self):
        """Kompletten bidirektionalen Sync ausführen"""
        print("🚀 Starte vollständigen bidirektionalen Sync...")
        start_time = datetime.now()
        
        # 1. Notion → Obsidian (neue Inhalte holen)
        notion_success = self.sync_notion_to_obsidian()
        
        # Kurze Pause zwischen Syncs
        time.sleep(2)
        
        # 2. Obsidian → Notion (lokale Änderungen pushen)
        obsidian_success = self.sync_obsidian_to_notion()
        
        # Status aktualisieren
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        self.state['sync_count'] += 1
        self.state['last_full_sync'] = end_time.isoformat()
        
        if notion_success and obsidian_success:
            print(f"🎉 Vollständiger Sync erfolgreich in {duration:.1f}s")
            return True
        else:
            print(f"⚠️ Sync teilweise fehlgeschlagen nach {duration:.1f}s")
            return False
    
    def run_single_sync(self):
        """Einmaliger Sync (für manuelle Ausführung)"""
        print("🎯 Führe einmaligen bidirektionalen Sync aus...")
        
        success = self.run_full_sync()
        self.save_sync_state()
        
        # Status-Report
        self.print_sync_status()
        
        return success
    
    def run_daemon_mode(self):
        """Daemon-Modus: kontinuierlicher Sync alle X Minuten"""
        print(f"🔄 Starte Sync-Daemon (Intervall: {self.sync_interval} Min)")
        
        while True:
            try:
                print(f"\n{'='*50}")
                print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Sync-Cycle")
                
                success = self.run_full_sync()
                self.save_sync_state()
                
                if not success:
                    print("⚠️ Sync-Fehler - warte trotzdem bis zum nächsten Interval")
                
                # Warte bis zum nächsten Sync
                print(f"😴 Warte {self.sync_interval} Minuten bis zum nächsten Sync...")
                time.sleep(self.sync_interval * 60)
                
            except KeyboardInterrupt:
                print("\n🛑 Sync-Daemon gestoppt durch Benutzer")
                break
            except Exception as e:
                print(f"💥 Unerwarteter Fehler im Daemon: {e}")
                print("😴 Warte 5 Minuten vor Neustart...")
                time.sleep(300)  # 5 Min warten bei Fehlern
    
    def print_sync_status(self):
        """Sync-Status ausgeben"""
        print("\n📊 Sync-Status:")
        print(f"   📈 Sync-Zyklen: {self.state['sync_count']}")
        print(f"   ❌ Fehler: {self.state['error_count']}")
        
        if self.state['last_notion_to_obsidian']:
            print(f"   📥 Letzter Notion→Obsidian: {self.state['last_notion_to_obsidian']}")
        
        if self.state['last_obsidian_to_notion']:
            print(f"   📤 Letzter Obsidian→Notion: {self.state['last_obsidian_to_notion']}")
        
        if self.state['last_full_sync']:
            print(f"   🔄 Letzter Full-Sync: {self.state['last_full_sync']}")
        
        if self.state['last_error']:
            error = self.state['last_error']
            print(f"   🚨 Letzter Fehler: {error['timestamp']} in {error['script']}")
    
    def cleanup_old_files(self):
        """Alte Archive-Dateien bereinigen (älter als 30 Tage)"""
        archive_path = self.obsidian_path / 'archive'
        if not archive_path.exists():
            return
        
        cutoff_date = datetime.now() - timedelta(days=30)
        cleaned_count = 0
        
        for file_path in archive_path.glob("*.md"):
            try:
                file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                if file_time < cutoff_date:
                    file_path.unlink()
                    cleaned_count += 1
            except Exception as e:
                print(f"⚠️ Fehler beim Bereinigen von {file_path}: {e}")
        
        if cleaned_count > 0:
            print(f"🧹 {cleaned_count} alte Archive-Dateien bereinigt")

def main():
    """Main function mit Command-Line Interface"""
    controller = MasterSyncController()
    
    # Command-line Argumente verarbeiten
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == 'once':
            # Einmaliger Sync
            success = controller.run_single_sync()
            sys.exit(0 if success else 1)
        
        elif command == 'daemon':
            # Daemon-Modus
            controller.run_daemon_mode()
        
        elif command == 'status':
            # Status anzeigen
            controller.print_sync_status()
        
        elif command == 'notion-to-obsidian':
            # Nur Notion → Obsidian
            success = controller.sync_notion_to_obsidian()
            controller.save_sync_state()
            sys.exit(0 if success else 1)
        
        elif command == 'obsidian-to-notion':
            # Nur Obsidian → Notion
            success = controller.sync_obsidian_to_notion()
            controller.save_sync_state()
            sys.exit(0 if success else 1)
        
        elif command == 'cleanup':
            # Archive bereinigen
            controller.cleanup_old_files()
        
        else:
            print(f"❌ Unbekannter Command: {command}")
            print_usage()
            sys.exit(1)
    
    else:
        # Standard: Einmaliger Sync
        print("🎯 Führe Standard-Sync aus (verwende 'daemon' für kontinuierlichen Sync)")
        success = controller.run_single_sync()
        sys.exit(0 if success else 1)

def print_usage():
    """Usage-Information ausgeben"""
    print("""
🔄 Master Sync Controller - Bidirektionale Notion↔Obsidian Synchronisation

Usage:
    python3 master_sync.py [command]

Commands:
    once                    Einmaliger bidirektionaler Sync (Standard)
    daemon                  Kontinuierlicher Sync alle 15 Min
    status                  Sync-Status anzeigen
    notion-to-obsidian      Nur Notion → Obsidian
    obsidian-to-notion      Nur Obsidian → Notion
    cleanup                 Alte Archive-Dateien bereinigen

Environment Variables:
    SYNC_INTERVAL_MINUTES   Sync-Intervall in Minuten (Standard: 15)
    NOTION_TOKEN           Notion API Token
    OBSIDIAN_PATH          Pfad zum Obsidian Vault
    """)

if __name__ == "__main__":
    main()