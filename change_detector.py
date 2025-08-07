#!/usr/bin/env python3
# change_detector.py - Intelligente Erkennung von Obsidian-Änderungen für Reverse-Sync

import os
import json
import hashlib
from datetime import datetime
from pathlib import Path
import frontmatter

class ObsidianChangeDetector:
    def __init__(self):
        self.obsidian_path = Path(os.getenv('OBSIDIAN_PATH', '/shared/obsidian'))
        self.state_file = self.obsidian_path / '.change_detection_state.json'
        self.load_state()
    
    def load_state(self):
        """Lade Change Detection State"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    self.state = json.load(f)
            except Exception as e:
                print(f"⚠️ Fehler beim Laden des Change Detection State: {e}")
                self.state = {}
        else:
            self.state = {}
    
    def save_state(self):
        """Speichere Change Detection State"""
        try:
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            print(f"⚠️ Fehler beim Speichern des Change Detection State: {e}")
    
    def calculate_content_hash(self, content: str) -> str:
        """Berechne Content-Hash für Änderungserkennung"""
        # Normalisiere Content (entferne Whitespace-Unterschiede)
        normalized = content.strip().replace('\r\n', '\n')
        return hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:16]
    
    def should_track_file(self, file_path: Path) -> bool:
        """Prüft ob Datei für Change Detection relevant ist"""
        relative_path = str(file_path.relative_to(self.obsidian_path))
        
        # Nur Dateien aus from-notion/ tracken (diese können zu Notion zurück gesynct werden)
        if not relative_path.startswith('from-notion/'):
            return False
        
        # Archive-Dateien ignorieren
        if 'archive' in relative_path:
            return False
        
        # Backup-Dateien ignorieren
        if '_backup_' in relative_path or relative_path.startswith('.'):
            return False
            
        return True
    
    def get_file_info(self, file_path: Path) -> dict:
        """Extrahiere relevante Datei-Informationen"""
        try:
            # File System Info
            stat = file_path.stat()
            modified_time = datetime.fromtimestamp(stat.st_mtime).isoformat()
            
            # Frontmatter und Content
            with open(file_path, 'r', encoding='utf-8') as f:
                post = frontmatter.load(f)
            
            # Content Hash für Änderungserkennung
            content_hash = self.calculate_content_hash(post.content)
            
            return {
                'modified_time': modified_time,
                'content_hash': content_hash,
                'notion_id': post.metadata.get('notion_id'),
                'sync_status': post.metadata.get('sync_status', 'synced'),
                'synced_at': post.metadata.get('synced_at'),
                'title': post.metadata.get('title', file_path.stem)
            }
            
        except Exception as e:
            print(f"⚠️ Fehler beim Lesen von {file_path}: {e}")
            return None
    
    def detect_changes(self) -> list:
        """Erkenne alle geänderten Dateien"""
        changed_files = []
        current_time = datetime.now().isoformat()
        
        print("🔍 Scanne nach geänderten Dateien...")
        
        # Durchsuche alle .md Dateien
        for file_path in self.obsidian_path.glob("**/*.md"):
            if not self.should_track_file(file_path):
                continue
            
            relative_path = str(file_path.relative_to(self.obsidian_path))
            current_info = self.get_file_info(file_path)
            
            if not current_info:
                continue
            
            # Vergleiche mit letztem State
            last_info = self.state.get(relative_path, {})
            
            # Prüfe auf Änderungen
            is_changed = False
            change_reason = []
            
            # 1. Neue Datei (noch nie getrackt)
            if not last_info:
                is_changed = True
                change_reason.append("new_file")
            
            # 2. Content Hash geändert (echte Inhalts-Änderung)
            elif current_info['content_hash'] != last_info.get('content_hash'):
                is_changed = True
                change_reason.append("content_changed")
            
            # 3. Datei wurde nach letztem Sync modifiziert
            elif (current_info['modified_time'] > current_info.get('synced_at', '') and
                  current_info['sync_status'] != 'pending'):
                is_changed = True
                change_reason.append("modified_after_sync")
            
            if is_changed:
                changed_files.append({
                    'filepath': relative_path,
                    'full_path': file_path,
                    'current_info': current_info,
                    'last_info': last_info,
                    'change_reason': change_reason,
                    'detected_at': current_time
                })
                
                print(f"📝 Änderung erkannt: {relative_path} ({', '.join(change_reason)})")
            
            # Update State für diese Datei
            self.state[relative_path] = current_info
        
        print(f"🔍 Change Detection abgeschlossen: {len(changed_files)} Änderungen gefunden")
        return changed_files
    
    def mark_file_as_pending(self, file_path: Path, change_info: dict) -> bool:
        """Markiert Datei als pending für Reverse-Sync"""
        try:
            # Datei laden
            with open(file_path, 'r', encoding='utf-8') as f:
                post = frontmatter.load(f)
            
            # Metadata aktualisieren
            post.metadata['sync_status'] = 'pending'
            post.metadata['sync_direction'] = 'to_notion'
            post.metadata['change_detected_at'] = change_info['detected_at']
            post.metadata['change_reason'] = ', '.join(change_info['change_reason'])
            post.metadata['needs_sync'] = True
            
            # Backup der ursprünglichen synced_at Zeit (falls vorhanden)
            if 'synced_at' in post.metadata:
                post.metadata['last_synced_at'] = post.metadata['synced_at']
            
            # Datei zurückschreiben
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(frontmatter.dumps(post))
            
            print(f"✅ Als pending markiert: {file_path.name}")
            return True
            
        except Exception as e:
            print(f"❌ Fehler beim Markieren von {file_path}: {e}")
            return False
    
    def process_changes(self) -> int:
        """Hauptfunktion: Erkenne Änderungen und markiere als pending"""
        print("🚀 Starte intelligente Change Detection...")
        
        # Erkenne Änderungen
        changed_files = self.detect_changes()
        
        if not changed_files:
            print("✅ Keine Änderungen gefunden - alle Dateien sind up-to-date")
            self.save_state()
            return 0
        
        # Markiere geänderte Dateien als pending
        marked_count = 0
        
        for change_info in changed_files:
            if self.mark_file_as_pending(change_info['full_path'], change_info):
                marked_count += 1
        
        # State speichern
        self.save_state()
        
        print(f"🎉 Change Detection abgeschlossen!")
        print(f"   📝 {len(changed_files)} Änderungen erkannt")
        print(f"   ✅ {marked_count} Dateien als pending markiert")
        print(f"   🔄 Bereit für Reverse-Sync zu Notion")
        
        return marked_count
    
    def reset_tracking(self):
        """Reset Change Detection State (für Debugging)"""
        print("🔄 Setze Change Detection State zurück...")
        self.state = {}
        self.save_state()
        print("✅ State zurückgesetzt")
    
    def show_status(self):
        """Zeige Change Detection Status"""
        print("📊 Change Detection Status:")
        print(f"   📁 Tracked Files: {len(self.state)}")
        print(f"   📍 State File: {self.state_file}")
        
        # Pending Files zählen
        pending_count = 0
        for file_path in self.obsidian_path.glob("**/*.md"):
            if not self.should_track_file(file_path):
                continue
                
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    post = frontmatter.load(f)
                
                if post.metadata.get('sync_status') == 'pending':
                    pending_count += 1
            except:
                continue
        
        print(f"   ⏳ Pending Files: {pending_count}")

def main():
    """Main function mit Command-Line Interface"""
    import sys
    
    detector = ObsidianChangeDetector()
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == 'detect':
            # Nur Änderungen erkennen, nicht markieren
            changes = detector.detect_changes()
            detector.save_state()
            print(f"Found {len(changes)} changes")
            
        elif command == 'process':
            # Änderungen erkennen und als pending markieren
            marked = detector.process_changes()
            sys.exit(0 if marked >= 0 else 1)
            
        elif command == 'reset':
            # State zurücksetzen
            detector.reset_tracking()
            
        elif command == 'status':
            # Status anzeigen
            detector.show_status()
            
        else:
            print(f"❌ Unbekannter Command: {command}")
            print_usage()
            sys.exit(1)
    else:
        # Standard: Änderungen verarbeiten
        marked = detector.process_changes()
        sys.exit(0 if marked >= 0 else 1)

def print_usage():
    """Usage Information"""
    print("""
🔍 Obsidian Change Detector - Intelligente Erkennung von Datei-Änderungen

Usage:
    python3 change_detector.py [command]

Commands:
    process     Erkenne Änderungen und markiere als pending (Standard)
    detect      Nur Änderungen erkennen (ohne Markierung)
    status      Zeige Change Detection Status
    reset       Setze Change Detection State zurück

Environment Variables:
    OBSIDIAN_PATH   Pfad zum Obsidian Vault (Standard: /shared/obsidian)
    """)

if __name__ == "__main__":
    main()