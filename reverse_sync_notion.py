#!/usr/bin/env python3
# reverse_sync_notion.py - Obsidian → Notion Sync

import os
import json
import requests
from pathlib import Path
from datetime import datetime
from notion_client import Client
import frontmatter
import re

class ObsidianToNotion:
    def __init__(self):
        self.notion_token = os.getenv('NOTION_TOKEN')
        self.obsidian_path = Path(os.getenv('OBSIDIAN_PATH', '/shared/obsidian'))
        self.notion_database_id = os.getenv('NOTION_DATABASE_ID', '')
        
        if not self.notion_token:
            raise ValueError("NOTION_TOKEN ist nicht gesetzt!")
        
        self.notion = Client(auth=self.notion_token)
        
        # Database-Setup ist optional - Fallback auf direkte Page-Updates
        self.database_available = False
        if not self.notion_database_id:
            try:
                self.notion_database_id = self.create_or_find_database()
                self.database_available = True
            except Exception as e:
                print(f"⚠️ Database-Setup fehlgeschlagen: {e}")
                print("🔄 Verwende direktes Page-Update ohne Database")
                self.database_available = False
        else:
            # Prüfe ob Database existiert
            self.database_available = self.verify_database_access()
    
    def create_or_find_database(self):
        """Notion Database für Obsidian-Sync erstellen oder finden"""
        try:
            print("🔍 Suche nach existierender 'Obsidian Sync' Database...")
            
            # Suche nach existierender Database
            search_result = self.notion.search(
                query="Obsidian Sync",
                filter={"property": "object", "value": "database"}
            )
            
            if search_result['results']:
                db_id = search_result['results'][0]['id']
                print(f"✅ Existierende Database gefunden: {db_id[:8]}...")
                return db_id
            
            print("📄 Keine 'Obsidian Sync' Database gefunden")
            print("🔄 Versuche neue Database zu erstellen...")
            
            # Root page finden (Parent für neue Database)
            pages = self.notion.search(
                filter={"property": "object", "value": "page"}
            )
            
            if not pages['results']:
                raise Exception("❌ Keine Notion Pages gefunden für Database-Parent. Erstelle zuerst eine Page in Notion.")
            
            parent_page_id = pages['results'][0]['id']
            parent_page_title = "Unbekannte Page"
            
            # Versuche Parent-Page Titel zu extrahieren
            try:
                parent_page = self.notion.pages.retrieve(parent_page_id)
                parent_props = parent_page.get('properties', {})
                for prop_name, prop_data in parent_props.items():
                    if prop_data.get('type') == 'title':
                        parent_page_title = prop_data.get('title', [{}])[0].get('plain_text', 'Unbekannt')
                        break
            except:
                pass
            
            print(f"🎯 Parent Page für Database: {parent_page_title}")
            
            # Database Schema
            database_properties = {
                "Title": {"title": {}},
                "Source": {
                    "select": {
                        "options": [
                            {"name": "Obsidian", "color": "blue"},
                            {"name": "Notion", "color": "green"},
                            {"name": "Claude", "color": "purple"}
                        ]
                    }
                },
                "Folder": {"rich_text": {}},
                "Created By": {"rich_text": {}},
                "Sync Status": {
                    "select": {
                        "options": [
                            {"name": "Pending", "color": "yellow"},
                            {"name": "Synced", "color": "green"},
                            {"name": "Error", "color": "red"}
                        ]
                    }
                },
                "Last Updated": {"date": {}},
                "Obsidian Path": {"rich_text": {}}
            }
            
            # Database erstellen
            new_database = self.notion.databases.create(
                parent={"page_id": parent_page_id},
                title=[{"type": "text", "text": {"content": "Obsidian Sync"}}],
                properties=database_properties
            )
            
            db_id = new_database['id']
            print(f"✅ Neue Database erstellt: {db_id}")
            
            # Database ID für nächstes Mal speichern
            with open('/app/.notion_db_id', 'w') as f:
                f.write(db_id)
            
            return db_id
            
        except Exception as e:
            print(f"❌ Fehler beim Database-Setup: {e}")
            raise
    
    def verify_database_access(self) -> bool:
        """Prüft ob Database zugänglich ist"""
        try:
            if not self.notion_database_id:
                return False
                
            # Teste Database-Zugriff
            self.notion.databases.query(
                database_id=self.notion_database_id,
                page_size=1
            )
            print(f"✅ Database verfügbar: {self.notion_database_id[:8]}...")
            return True
            
        except Exception as e:
            print(f"❌ Database nicht verfügbar: {e}")
            return False
    
    def markdown_to_notion_blocks(self, content: str) -> list:
        """Markdown Content zu Notion Blocks konvertieren"""
        blocks = []
        lines = content.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            if not line:
                i += 1
                continue
            
            # Headings
            if line.startswith('# '):
                blocks.append({
                    "object": "block",
                    "type": "heading_1",
                    "heading_1": {
                        "rich_text": [{"type": "text", "text": {"content": line[2:]}}]
                    }
                })
            elif line.startswith('## '):
                blocks.append({
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": line[3:]}}]
                    }
                })
            elif line.startswith('### '):
                blocks.append({
                    "object": "block",
                    "type": "heading_3",
                    "heading_3": {
                        "rich_text": [{"type": "text", "text": {"content": line[4:]}}]
                    }
                })
            
            # Bulleted Lists
            elif line.startswith('- '):
                blocks.append({
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{"type": "text", "text": {"content": line[2:]}}]
                    }
                })
            
            # Numbered Lists
            elif re.match(r'^\d+\.\s', line):
                content_text = re.sub(r'^\d+\.\s', '', line)
                blocks.append({
                    "object": "block",
                    "type": "numbered_list_item",
                    "numbered_list_item": {
                        "rich_text": [{"type": "text", "text": {"content": content_text}}]
                    }
                })
            
            # Code Blocks
            elif line.startswith('```'):
                code_content = []
                i += 1
                
                while i < len(lines) and not lines[i].strip().startswith('```'):
                    code_content.append(lines[i])
                    i += 1
                
                language = line[3:] if len(line) > 3 else "plain"
                
                blocks.append({
                    "object": "block",
                    "type": "code",
                    "code": {
                        "rich_text": [{"type": "text", "text": {"content": '\n'.join(code_content)}}],
                        "language": language
                    }
                })
            
            # Quotes
            elif line.startswith('> '):
                blocks.append({
                    "object": "block",
                    "type": "quote",
                    "quote": {
                        "rich_text": [{"type": "text", "text": {"content": line[2:]}}]
                    }
                })
            
            # Dividers
            elif line == '---':
                blocks.append({
                    "object": "block",
                    "type": "divider",
                    "divider": {}
                })
            
            # Regular Paragraphs
            else:
                # Collect paragraph lines
                paragraph_lines = [line]
                i += 1
                
                while i < len(lines) and lines[i].strip() and not self.is_special_line(lines[i]):
                    paragraph_lines.append(lines[i].strip())
                    i += 1
                
                paragraph_text = ' '.join(paragraph_lines)
                
                if paragraph_text:
                    blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"type": "text", "text": {"content": paragraph_text}}]
                        }
                    })
                
                continue  # Skip increment da wir schon increment haben
            
            i += 1
        
        return blocks
    
    def is_special_line(self, line: str) -> bool:
        """Prüft ob Zeile ein spezielles Markdown-Element ist"""
        line = line.strip()
        return (line.startswith('#') or 
                line.startswith('-') or 
                line.startswith('>') or 
                line.startswith('```') or
                line == '---' or
                re.match(r'^\d+\.\s', line))
    
    def create_notion_page(self, title: str, content: str, metadata: dict, filepath: str):
        """Neue Notion Page erstellen"""
        try:
            if not self.database_available:
                raise Exception("Database nicht verfügbar")
                
            # Blocks aus Markdown generieren
            blocks = self.markdown_to_notion_blocks(content)
            
            # Page Properties
            properties = {
                "Title": {
                    "title": [{"type": "text", "text": {"content": title}}]
                },
                "Source": {
                    "select": {"name": metadata.get('created_by', 'Obsidian')}
                },
                "Folder": {
                    "rich_text": [{"type": "text", "text": {"content": str(Path(filepath).parent)}}]
                },
                "Created By": {
                    "rich_text": [{"type": "text", "text": {"content": metadata.get('created_by', 'Unknown')}}]
                },
                "Sync Status": {
                    "select": {"name": "Synced"}
                },
                "Last Updated": {
                    "date": {"start": datetime.now().isoformat()}
                },
                "Obsidian Path": {
                    "rich_text": [{"type": "text", "text": {"content": filepath}}]
                }
            }
            
            # Page erstellen
            new_page = self.notion.pages.create(
                parent={"database_id": self.notion_database_id},
                properties=properties,
                children=blocks
            )
            
            return new_page['id']
        
        except Exception as e:
            print(f"❌ Fehler beim Erstellen der Notion Page: {e}")
            # Database als nicht verfügbar markieren
            self.database_available = False
            raise
    
    def update_notion_page(self, page_id: str, title: str, content: str, metadata: dict):
        """Bestehende Notion Page aktualisieren"""
        try:
            # Properties aktualisieren
            properties = {
                "Title": {
                    "title": [{"type": "text", "text": {"content": title}}]
                },
                "Sync Status": {
                    "select": {"name": "Synced"}
                },
                "Last Updated": {
                    "date": {"start": datetime.now().isoformat()}
                }
            }
            
            # Page Properties updaten
            self.notion.pages.update(page_id=page_id, properties=properties)
            
            # Content aktualisieren (alle Blocks löschen und neu erstellen)
            # Existierende Blocks holen
            existing_blocks = self.notion.blocks.children.list(block_id=page_id)
            
            # Alle Blocks löschen
            for block in existing_blocks['results']:
                self.notion.blocks.delete(block_id=block['id'])
            
            # Neue Blocks hinzufügen
            new_blocks = self.markdown_to_notion_blocks(content)
            
            if new_blocks:
                self.notion.blocks.children.append(
                    block_id=page_id,
                    children=new_blocks
                )
            
            return page_id
        
        except Exception as e:
            print(f"❌ Fehler beim Aktualisieren der Notion Page: {e}")
            raise
    
    def update_original_notion_page(self, page_id: str, title: str, content: str, metadata: dict):
        """🚨 DEAKTIVIERT: Direkte Updates zu gefährlich - Fallback zu Database Entry"""
        print(f"🚨 SICHERHEITSMODUS: Ursprüngliche Pages werden NICHT modifiziert!")
        print(f"🔄 Fallback: Erstelle sicheren Database Entry statt direktem Update...")
        
        # SICHERHEITS-FALLBACK: Erstelle Database Entry statt destruktivem Update
        try:
            return self.create_notion_page(title, content, metadata, f"safe_fallback_{page_id[:8]}")
        except Exception as e:
            print(f"❌ Auch Fallback fehlgeschlagen: {e}")
            print(f"⚠️ Überspringe {title} - zu gefährlich für Update")
            raise Exception(f"SICHERHEITSMODUS: Kein Update möglich für {title}")
    
    def find_existing_page(self, filepath: str, notion_id: str = None):
        """Existierende Notion Page für Obsidian-Datei finden"""
        try:
            # 1. Priorisiere: Original Notion Page via notion_id (aus Frontmatter)
            if notion_id:
                try:
                    # Prüfe ob die ursprüngliche Notion Page noch existiert
                    original_page = self.notion.pages.retrieve(page_id=notion_id)
                    if original_page:
                        print(f"🎯 Ursprüngliche Notion Page gefunden: {notion_id[:8]}...")
                        return notion_id, 'original_page'
                except Exception as e:
                    print(f"⚠️ Ursprüngliche Notion Page nicht mehr verfügbar: {e}")
            
            # 2. Fallback: Suche in Sync-Database nach Obsidian Path (nur wenn Database verfügbar)
            if self.database_available:
                try:
                    query_result = self.notion.databases.query(
                        database_id=self.notion_database_id,
                        filter={
                            "property": "Obsidian Path",
                            "rich_text": {
                                "equals": filepath
                            }
                        }
                    )
                    
                    if query_result['results']:
                        database_page_id = query_result['results'][0]['id']
                        print(f"📊 Database Entry gefunden: {database_page_id[:8]}...")
                        return database_page_id, 'database_entry'
                        
                except Exception as e:
                    print(f"⚠️ Database-Suche fehlgeschlagen: {e}")
                    self.database_available = False
            
            # 3. Keine existierende Page gefunden
            return None, None
        
        except Exception as e:
            print(f"❌ Fehler bei Page-Suche: {e}")
            return None, None
    
    def sync_pending_files(self):
        """Alle pending Obsidian-Dateien zu Notion syncen"""
        print("🚀 Starte Obsidian → Notion Sync...")
        
        # Alle Dateien mit sync_status = pending finden
        pending_files = []
        
        for file_path in self.obsidian_path.glob("**/*.md"):
            if 'archive' in str(file_path):
                continue
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    post = frontmatter.load(f)
                
                # Nur Dateien mit pending status oder Claude-erstellte Dateien
                if (post.metadata.get('sync_status') == 'pending' or 
                    post.metadata.get('sync_direction') == 'to_notion'):
                    
                    relative_path = file_path.relative_to(self.obsidian_path)
                    pending_files.append({
                        'filepath': str(relative_path),
                        'full_path': file_path,
                        'post': post
                    })
            
            except Exception as e:
                print(f"⚠️ Fehler beim Lesen von {file_path}: {e}")
                continue
        
        print(f"📄 {len(pending_files)} Dateien zum Syncen gefunden")
        
        synced_count = 0
        
        for file_info in pending_files:
            try:
                filepath = file_info['filepath']
                post = file_info['post']
                
                title = post.metadata.get('title', Path(filepath).stem)
                content = post.content
                metadata = post.metadata
                
                print(f"🔄 Synce: {filepath}")
                
                # Prüfe ob Page bereits existiert (mit Notion-ID aus Frontmatter)
                notion_id = metadata.get('notion_id')
                existing_page_id, page_type = self.find_existing_page(filepath, notion_id)
                
                if existing_page_id:
                    # Update bestehende Page
                    if page_type == 'original_page':
                        # 🚨 SICHERHEITSMODUS: Keine direkten Updates der ursprünglichen Pages!
                        print(f"🚨 SICHERHEIT: Überspringe direktes Update der ursprünglichen Page: {title}")
                        print(f"💡 Tipp: Bearbeite die Page direkt in Notion oder erstelle eine neue Database Entry")
                        # Markiere trotzdem als synced, damit keine endlose Wiederholung
                        self.mark_file_synced(file_info['full_path'], post)
                        continue
                    else:
                        # Update Database Entry (SICHER)
                        self.update_notion_page(existing_page_id, title, content, metadata)
                        print(f"✅ Database Entry Updated (SICHER): {title}")
                else:
                    # Neue Page erstellen - aber nur wenn Database verfügbar
                    if self.database_available:
                        new_page_id = self.create_notion_page(title, content, metadata, filepath)
                        print(f"✅ New Database Entry Created (SICHER): {title}")
                    else:
                        print(f"⚠️ Überspringe {title} - keine Database verfügbar")
                        # Markiere als synced um endlose Wiederholung zu vermeiden
                        self.mark_file_synced(file_info['full_path'], post)
                        continue  # Skip diese Datei
                
                # Obsidian-Datei als gesynct markieren
                self.mark_file_synced(file_info['full_path'], post)
                
                synced_count += 1
                
            except Exception as e:
                print(f"❌ Fehler bei {filepath}: {e}")
                continue
        
        print(f"🎉 Reverse-Sync abgeschlossen! {synced_count} Dateien zu Notion gesynct.")
    
    def mark_file_synced(self, file_path: Path, post: frontmatter.Post):
        """Obsidian-Datei als gesynct markieren"""
        post.metadata['sync_status'] = 'synced'
        post.metadata['synced_to_notion_at'] = datetime.now().isoformat()
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(frontmatter.dumps(post))

def main():
    """Main function für Reverse Sync"""
    try:
        syncer = ObsidianToNotion()
        syncer.sync_pending_files()
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"⏰ Letzter Reverse-Sync: {timestamp}")
        
    except Exception as e:
        print(f"💥 Reverse-Sync Fehler: {e}")
        exit(1)

if __name__ == "__main__":
    main()