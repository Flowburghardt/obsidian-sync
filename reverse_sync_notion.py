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
        
        # Wenn keine Database ID gesetzt, versuche automatisch zu erstellen
        if not self.notion_database_id:
            self.notion_database_id = self.create_or_find_database()
    
    def create_or_find_database(self):
        """Notion Database für Obsidian-Sync erstellen oder finden"""
        try:
            # Suche nach existierender Database
            search_result = self.notion.search(
                query="Obsidian Sync",
                filter={"property": "object", "value": "database"}
            )
            
            if search_result['results']:
                db_id = search_result['results'][0]['id']
                print(f"✅ Existierende Database gefunden: {db_id}")
                return db_id
            
            # Erstelle neue Database
            print("🔄 Erstelle neue Notion Database...")
            
            # Root page finden (Parent für neue Database)
            pages = self.notion.search(
                filter={"property": "object", "value": "page"}
            )
            
            if not pages['results']:
                raise Exception("Keine Notion Pages gefunden. Erstelle zuerst eine Page in Notion.")
            
            parent_page_id = pages['results'][0]['id']
            
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
        """Direkte Aktualisierung der ursprünglichen Notion Page"""
        try:
            print(f"🎯 Aktualisiere ursprüngliche Notion Page: {page_id[:8]}...")
            
            # 1. Prüfe ob Page einen Titel-Property hat und aktualisiere ihn
            try:
                page_info = self.notion.pages.retrieve(page_id=page_id)
                properties = page_info.get('properties', {})
                
                # Suche nach Title-Property
                title_property = None
                for prop_name, prop_data in properties.items():
                    if prop_data.get('type') == 'title':
                        title_property = prop_name
                        break
                
                # Aktualisiere Titel falls Property existiert
                if title_property:
                    self.notion.pages.update(
                        page_id=page_id,
                        properties={
                            title_property: {
                                "title": [{"type": "text", "text": {"content": title}}]
                            }
                        }
                    )
                    print(f"✅ Titel aktualisiert: {title}")
            
            except Exception as e:
                print(f"⚠️ Titel-Update fehlgeschlagen (nicht kritisch): {e}")
            
            # 2. Content aktualisieren (alle Blocks ersetzen)
            # Existierende Blocks holen
            existing_blocks = self.notion.blocks.children.list(block_id=page_id)
            
            # Alle bestehenden Blocks löschen
            for block in existing_blocks['results']:
                try:
                    self.notion.blocks.delete(block_id=block['id'])
                except Exception as e:
                    print(f"⚠️ Fehler beim Löschen von Block {block['id']}: {e}")
            
            # Neue Blocks aus Markdown generieren und hinzufügen
            new_blocks = self.markdown_to_notion_blocks(content)
            
            if new_blocks:
                # Blocks in kleineren Batches hinzufügen (Notion API Limit)
                batch_size = 100
                for i in range(0, len(new_blocks), batch_size):
                    batch = new_blocks[i:i + batch_size]
                    self.notion.blocks.children.append(
                        block_id=page_id,
                        children=batch
                    )
                
                print(f"✅ Content aktualisiert: {len(new_blocks)} Blocks")
            
            # 3. Metadaten in Obsidian aktualisieren
            # Hier könnten wir zusätzliche Sync-Metadaten hinzufügen
            # Das passiert bereits in mark_file_synced()
            
            return page_id
            
        except Exception as e:
            print(f"❌ Fehler beim Aktualisieren der ursprünglichen Notion Page: {e}")
            # Fallback: Erstelle Database Entry statt zu versagen
            print("🔄 Fallback: Erstelle Database Entry...")
            return self.create_notion_page(title, content, metadata, f"fallback_{page_id[:8]}")
            raise
    
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
            
            # 2. Fallback: Suche in Sync-Database nach Obsidian Path
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
                        # Direktes Update der ursprünglichen Notion Page
                        self.update_original_notion_page(existing_page_id, title, content, metadata)
                        print(f"✅ Original Page Updated: {title}")
                    else:
                        # Update Database Entry
                        self.update_notion_page(existing_page_id, title, content, metadata)
                        print(f"✅ Database Entry Updated: {title}")
                else:
                    # Erstelle neue Page in Database
                    new_page_id = self.create_notion_page(title, content, metadata, filepath)
                    print(f"✅ New Database Entry Created: {title}")
                
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