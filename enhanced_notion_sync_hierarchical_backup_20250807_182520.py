#!/usr/bin/env python3
# enhanced_notion_sync.py - Notion → Obsidian Sync mit Ordnerstruktur

import os
import json
import re
from datetime import datetime
from pathlib import Path
from notion_client import Client
from markdownify import markdownify
import frontmatter

class EnhancedNotionToObsidian:
    def __init__(self):
        self.notion_token = os.getenv('NOTION_TOKEN')
        self.obsidian_path = Path(os.getenv('OBSIDIAN_PATH', '/shared/obsidian'))
        
        if not self.notion_token:
            raise ValueError("NOTION_TOKEN environment variable ist nicht gesetzt!")
        
        self.notion = Client(auth=self.notion_token)
        self.setup_directories()
        
        # Mapping für Notion Page Sources
        self.folder_mapping = {
            'notion': 'from-notion',
            'claude': 'from-claude',  # Für den Fall dass Notion Pages von Claude erstellt wurden
            'collaboration': 'collaboration'
        }
    
    def setup_directories(self):
        """Ordnerstruktur erstellen"""
        directories = [
            'from-notion',      # Original Notion Content
            'from-claude',      # Von Claude erstellte Inhalte
            'collaboration',    # Bidirektionale Bearbeitung
            'archive'          # Backups und Konflikte
        ]
        
        for dir_name in directories:
            (self.obsidian_path / dir_name).mkdir(parents=True, exist_ok=True)
    
    def determine_target_folder(self, page, existing_filepath=None):
        """Bestimmt Ziel-Ordner für eine Notion Page"""
        
        # Wenn Datei bereits existiert, behalte den Ordner
        if existing_filepath:
            return str(Path(existing_filepath).parent)
        
        # Prüfe Page-Properties für Hinweise
        properties = page.get('properties', {})
        
        # Suche nach Source-Eigenschaft
        for prop_name, prop_value in properties.items():
            if prop_name.lower() in ['source', 'created_by', 'origin']:
                if prop_value.get('type') == 'select':
                    source = prop_value.get('select', {}).get('name', '').lower()
                    return self.folder_mapping.get(source, 'from-notion')
                elif prop_value.get('type') == 'rich_text':
                    rich_text = prop_value.get('rich_text', [])
                    if rich_text:
                        source = rich_text[0].get('text', {}).get('content', '').lower()
                        if 'claude' in source:
                            return 'collaboration'
        
        # Standard: from-notion
        return 'from-notion'
    
    def get_existing_file_by_notion_id(self, notion_id):
        """Finde existierende Obsidian-Datei anhand der Notion ID"""
        for file_path in self.obsidian_path.glob("**/*.md"):
            if 'archive' in str(file_path):
                continue
                
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    post = frontmatter.load(f)
                
                if post.metadata.get('notion_id') == notion_id:
                    return file_path.relative_to(self.obsidian_path)
            
            except Exception:
                continue
        
        return None
    
    def check_for_conflicts(self, file_path, new_content, new_metadata):
        """Prüft auf Konflikte bei Updates"""
        full_path = self.obsidian_path / file_path
        
        if not full_path.exists():
            return False, None
        
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                existing_post = frontmatter.load(f)
            
            # Prüfe ob Datei seit letztem Notion-Update geändert wurde
            last_notion_update = new_metadata.get('updated', '')
            last_local_update = existing_post.metadata.get('updated_at', '')
            local_created_by = existing_post.metadata.get('created_by', '')
            
            # Konflikt wenn:
            # 1. Lokal von Claude modifiziert NACH letztem Notion Update
            # 2. Oder lokal erstellt von Claude
            if (local_created_by == 'claude' and 
                last_local_update and 
                last_local_update > last_notion_update):
                
                return True, existing_post
            
            return False, existing_post
        
        except Exception as e:
            print(f"⚠️ Fehler bei Konfliktprüfung für {file_path}: {e}")
            return False, None
    
    def handle_conflict(self, file_path, existing_post, new_content, new_metadata):
        """Behandelt Merge-Konflikte"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 1. Backup der lokalen Version erstellen
        backup_filename = f"archive/{Path(file_path).stem}_local_backup_{timestamp}.md"
        backup_path = self.obsidian_path / backup_filename
        
        backup_metadata = existing_post.metadata.copy()
        backup_metadata['backup_type'] = 'conflict_resolution'
        backup_metadata['backup_created'] = datetime.now().isoformat()
        backup_metadata['original_path'] = str(file_path)
        
        backup_post = frontmatter.Post(existing_post.content, **backup_metadata)
        
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(frontmatter.dumps(backup_post))
        
        print(f"💾 Konflikt-Backup erstellt: {backup_filename}")
        
        # 2. Merge-Strategie: Notion Content + lokale Ergänzungen
        merged_content = f"{new_content}\n\n---\n\n## Lokale Ergänzungen (von Claude)\n\n{existing_post.content}"
        
        # 3. Merged Metadata
        merged_metadata = new_metadata.copy()
        merged_metadata.update({
            'conflict_resolved': True,
            'conflict_resolved_at': datetime.now().isoformat(),
            'local_backup': str(backup_filename),
            'merge_strategy': 'notion_primary_with_local_additions'
        })
        
        return merged_content, merged_metadata
    
    def get_all_pages(self):
        """Alle Notion Pages abrufen (erweitert)"""
        try:
            # Alle Pages
            all_pages = []
            has_more = True
            next_cursor = None
            
            while has_more:
                query_params = {
                    "filter": {"property": "object", "value": "page"}
                }
                
                if next_cursor:
                    query_params["start_cursor"] = next_cursor
                
                response = self.notion.search(**query_params)
                all_pages.extend(response.get('results', []))
                
                has_more = response.get('has_more', False)
                next_cursor = response.get('next_cursor')
            
            # GEÄNDERT: Alle Pages zurückgeben (inkl. Database-Entries)
            # für hierarchische Sync-Struktur
            return all_pages
            
        except Exception as e:
            print(f"Fehler beim Abrufen der Pages: {e}")
            return []
    
    def get_all_databases(self):
        """Alle Database-Objects abrufen (nicht Pages!)"""
        try:
            # Databases sind eigene Objects in Notion
            response = self.notion.search(filter={"property": "object", "value": "database"})
            databases = response.get('results', [])
            print(f"🗂️ {len(databases)} Database-Objects gefunden")
            return databases
        except Exception as e:
            print(f"❌ Fehler beim Abrufen der Database-Objects: {e}")
            return []
    
    def get_database_entries(self, database_id):
        """Alle Entries einer Database abrufen"""
        try:
            all_entries = []
            has_more = True
            start_cursor = None
            
            while has_more:
                query_params = {"database_id": database_id}
                if start_cursor:
                    query_params["start_cursor"] = start_cursor
                    
                response = self.notion.databases.query(**query_params)
                all_entries.extend(response.get('results', []))
                
                has_more = response.get('has_more', False)
                start_cursor = response.get('next_cursor')
            
            return all_entries
        except Exception as e:
            print(f"⚠️ Fehler beim Abrufen der Database Entries für {database_id}: {e}")
            return []
    
    def categorize_pages_by_database(self, pages):
        """Pages in Database-Entries vs Standalone trennen"""
        database_entries = []  
        standalone_pages = []
        
        for page in pages:
            parent = page.get('parent', {})
            
            if parent.get('type') == 'database_id':
                database_entries.append(page)
            else:
                standalone_pages.append(page)
        
        return database_entries, standalone_pages
    
    def build_database_structure(self):
        """Database-Ordner mit _DatabaseName.md Hauptdateien erstellen"""
        databases = self.get_all_databases()
        database_folders = {}
        
        print("🔄 Erstelle Database-Ordner-Struktur...")
        
        for database in databases:
            try:
                database_id = database['id']
                title = self.extract_text_from_rich_text(database.get('title', []))
                
                if not title:
                    title = f"Database_{database_id[:8]}"
                
                # Ordner-Name und Hauptdatei mit Underscore-Prefix
                folder_name = self.sanitize_filename(title)
                main_filename = f"_{folder_name}.md"
                
                # Pfade  
                target_folder = f"from-notion/{folder_name}"
                main_filepath = f"{target_folder}/{main_filename}"
                
                # Ordner erstellen
                (self.obsidian_path / target_folder).mkdir(parents=True, exist_ok=True)
                
                # Database-Eigenschaften als Markdown
                description = database.get('description', [])
                if description:
                    content = self.extract_text_from_rich_text(description)
                else:
                    content = f"# {title}\n\nDies ist die Hauptseite der Database '{title}'."
                
                # Metadata für Database-Hauptdatei
                metadata = {
                    'notion_id': database_id,
                    'notion_type': 'database_main',
                    'database_name': title,
                    'synced_at': datetime.now().isoformat(),
                    'title': f"Database: {title}"
                }
                
                # _Database.md Datei speichern
                full_path = self.obsidian_path / main_filepath
                self.save_markdown_file(full_path, content, metadata)
                
                # Database-Ordner merken
                database_folders[database_id] = folder_name
                
                print(f"🗂️ Database-Ordner erstellt: {target_folder}/")
                print(f"📄 Hauptdatei erstellt: {main_filename}")
                
            except Exception as e:
                print(f"❌ Fehler bei Database {database.get('id', 'unknown')}: {e}")
        
        return database_folders
    
    def save_markdown_file(self, file_path, content, metadata):
        """Markdown-Datei mit Frontmatter speichern"""
        try:
            # Frontmatter-Post erstellen
            post = frontmatter.Post(content)
            post.metadata = metadata
            
            # Datei schreiben
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(frontmatter.dumps(post))
                
        except Exception as e:
            print(f"⚠️ Fehler beim Speichern von {file_path}: {e}")
    
    def get_page_content(self, page_id):
        """Content einer Notion Page abrufen (erweitert)"""
        try:
            blocks = []
            has_more = True
            next_cursor = None
            
            while has_more:
                query_params = {"block_id": page_id}
                
                if next_cursor:
                    query_params["start_cursor"] = next_cursor
                
                response = self.notion.blocks.children.list(**query_params)
                blocks.extend(response.get('results', []))
                
                has_more = response.get('has_more', False)
                next_cursor = response.get('next_cursor')
            
            return blocks
            
        except Exception as e:
            print(f"Fehler beim Abrufen des Contents für {page_id}: {e}")
            return []
    
    def block_to_markdown(self, block):
        """Einzelnen Block zu Markdown konvertieren (erweitert)"""
        block_type = block.get('type', '')
        
        # Text-basierte Blocks
        if block_type in ['paragraph', 'heading_1', 'heading_2', 'heading_3']:
            text_content = self.extract_text_from_rich_text(
                block.get(block_type, {}).get('rich_text', [])
            )
            
            if block_type == 'heading_1':
                return f"# {text_content}\n\n"
            elif block_type == 'heading_2':
                return f"## {text_content}\n\n"
            elif block_type == 'heading_3':
                return f"### {text_content}\n\n"
            else:  # paragraph
                return f"{text_content}\n\n"
        
        # Listen
        elif block_type == 'bulleted_list_item':
            text = self.extract_text_from_rich_text(
                block.get('bulleted_list_item', {}).get('rich_text', [])
            )
            return f"- {text}\n"
        
        elif block_type == 'numbered_list_item':
            text = self.extract_text_from_rich_text(
                block.get('numbered_list_item', {}).get('rich_text', [])
            )
            return f"1. {text}\n"
        
        # Code block
        elif block_type == 'code':
            code_block = block.get('code', {})
            language = code_block.get('language', '')
            text = self.extract_text_from_rich_text(code_block.get('rich_text', []))
            return f"```{language}\n{text}\n```\n\n"
        
        # Quote
        elif block_type == 'quote':
            text = self.extract_text_from_rich_text(
                block.get('quote', {}).get('rich_text', [])
            )
            return f"> {text}\n\n"
        
        # Divider
        elif block_type == 'divider':
            return "---\n\n"
        
        # To-do
        elif block_type == 'to_do':
            todo = block.get('to_do', {})
            checked = todo.get('checked', False)
            text = self.extract_text_from_rich_text(todo.get('rich_text', []))
            checkbox = "[x]" if checked else "[ ]"
            return f"- {checkbox} {text}\n"
        
        # Toggle (Collapsible)
        elif block_type == 'toggle':
            text = self.extract_text_from_rich_text(
                block.get('toggle', {}).get('rich_text', [])
            )
            return f"<details>\n<summary>{text}</summary>\n\n<!-- Toggle content would go here -->\n</details>\n\n"
        
        # Callout
        elif block_type == 'callout':
            callout = block.get('callout', {})
            text = self.extract_text_from_rich_text(callout.get('rich_text', []))
            icon = callout.get('icon', {}).get('emoji', '💡')
            return f"> {icon} **Callout:** {text}\n\n"
        
        # Andere Block-Typen als Kommentar
        else:
            return f"<!-- Notion Block: {block_type} (nicht unterstützt) -->\n"
    
    def extract_text_from_rich_text(self, rich_text_array):
        """Text aus Notion Rich Text Array extrahieren (erweitert)"""
        text = ""
        for item in rich_text_array:
            content = item.get('text', {}).get('content', '')
            annotations = item.get('annotations', {})
            
            # Links
            if item.get('text', {}).get('link'):
                url = item.get('text', {}).get('link', {}).get('url', '')
                content = f"[{content}]({url})"
            
            # Formatierung anwenden
            if annotations.get('bold'):
                content = f"**{content}**"
            if annotations.get('italic'):
                content = f"*{content}*"
            if annotations.get('code'):
                content = f"`{content}`"
            if annotations.get('strikethrough'):
                content = f"~~{content}~~"
            if annotations.get('underline'):
                content = f"<u>{content}</u>"
            
            text += content
        
        return text
    
    def sanitize_filename(self, filename):
        """Dateinamen für Filesystem bereinigen (erweitert)"""
        # Gefährliche Zeichen entfernen
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        # Mehrfache Leerzeichen/Unterstriche zusammenfassen
        filename = re.sub(r'[_\s]+', '_', filename)
        # Emoji und Sonderzeichen entfernen
        filename = re.sub(r'[^\w\s-]', '', filename)
        # Länge begrenzen
        return filename[:100].strip('_')
    
    def page_to_markdown(self, page):
        """Komplette Page zu Markdown konvertieren (erweitert)"""
        properties = page.get('properties', {})
        page_id = page['id']
        
        # Titel extrahieren
        title_prop = properties.get('title', properties.get('Name', {}))
        title = "Untitled"
        
        if title_prop.get('type') == 'title' and title_prop.get('title'):
            title = self.extract_text_from_rich_text(title_prop['title'])
        elif title_prop.get('type') == 'rich_text' and title_prop.get('rich_text'):
            title = self.extract_text_from_rich_text(title_prop['rich_text'])
        
        # Erweiterte Frontmatter
        frontmatter_data = {
            'notion_id': page_id,
            'created': page.get('created_time'),
            'updated': page.get('last_edited_time'),
            'title': title,
            'sync_status': 'synced',
            'sync_direction': 'from_notion',
            'synced_at': datetime.now().isoformat()
        }
        
        # Content abrufen
        blocks = self.get_page_content(page_id)
        
        # Markdown Content generieren
        markdown_content = f"# {title}\n\n"
        
        for block in blocks:
            markdown_content += self.block_to_markdown(block)
        
        # Frontmatter hinzufügen
        post = frontmatter.Post(markdown_content, **frontmatter_data)
        
        return frontmatter.dumps(post), frontmatter_data
    
    def sync_all_pages(self):
        """KORREKTE HIERARCHIE: Database-Objects + Entries + Standalone Pages"""
        print(f"🚀 Starte korrigierten hierarchischen Sync...")
        print(f"📁 Obsidian Pfad: {self.obsidian_path}")
        
        synced_count = 0
        conflict_count = 0
        
        # 1. Database-Struktur aufbauen (Database-Objects → Ordner + _DatabaseName.md)
        database_folders = self.build_database_structure()
        synced_count += len(database_folders)
        
        # 2. Alle Pages abrufen
        all_pages = self.get_all_pages()
        print(f"📄 {len(all_pages)} Pages insgesamt gefunden")
        
        # 3. Pages kategorisieren  
        database_entries, standalone_pages = self.categorize_pages_by_database(all_pages)
        
        print(f"📋 {len(database_entries)} Database-Entries") 
        print(f"📄 {len(standalone_pages)} Standalone-Pages")
        
        # 4. Database-Entries in entsprechende Ordner sortieren
        print("🔄 Verarbeite Database-Entries...")
        for entry in database_entries:
            try:
                parent_db_id = entry.get('parent', {}).get('database_id')
                folder_name = database_folders.get(parent_db_id, 'Unknown_Database')
                
                # Entry-Titel extrahieren
                title = 'Untitled Entry'
                properties = entry.get('properties', {})
                
                # Suche nach Titel in verschiedenen Property-Namen
                for prop_name in ['Name', 'Title', 'title', 'name']:
                    if prop_name in properties:
                        prop = properties[prop_name]
                        if prop.get('type') == 'title' and prop.get('title'):
                            title = self.extract_text_from_rich_text(prop['title'])
                            break
                        elif prop.get('type') == 'rich_text' and prop.get('rich_text'):
                            title = self.extract_text_from_rich_text(prop['rich_text'])
                            break
                
                if not title or title == 'Untitled Entry':
                    title = f"Entry_{entry['id'][:8]}"
                
                # Entry in Database-Ordner synken
                target_path = f"from-notion/{folder_name}/{self.sanitize_filename(title)}.md"
                
                # Prüfe ob bereits existiert
                existing_filepath = self.get_existing_file_by_notion_id(entry['id'])
                
                if existing_filepath:
                    print(f"🔄 Update Entry: {existing_filepath}")
                    target_path = existing_filepath
                else:
                    print(f"📋 Neue Entry: {target_path}")
                
                # Markdown generieren
                markdown_content, metadata = self.page_to_markdown(entry)
                metadata.update({
                    'notion_id': entry['id'],
                    'notion_type': 'database_entry',
                    'database_folder': folder_name,
                    'parent_database_id': parent_db_id,
                    'synced_at': datetime.now().isoformat()
                })
                
                # Konflikt-Check falls existiert
                if existing_filepath:
                    has_conflict, existing_post = self.check_for_conflicts(
                        existing_filepath, markdown_content, metadata
                    )
                    
                    if has_conflict:
                        print(f"⚠️ Konflikt bei Entry: {existing_filepath}")
                        markdown_content, metadata = self.handle_conflict(
                            existing_filepath, existing_post, markdown_content, metadata
                        )
                        conflict_count += 1
                
                # Datei speichern
                full_path = self.obsidian_path / target_path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                self.save_markdown_file(full_path, markdown_content, metadata)
                
                synced_count += 1
                
            except Exception as e:
                print(f"❌ Fehler bei Entry {entry.get('id', 'unknown')}: {e}")
        
        # 5. Standalone Pages (wie bisher)
        print("🔄 Verarbeite Standalone-Pages...")
        for page in standalone_pages:
            try:
                page_id = page['id']
                
                # Prüfe ob Page bereits existiert
                existing_filepath = self.get_existing_file_by_notion_id(page_id)
                
                # Markdown generieren
                markdown_content, metadata = self.page_to_markdown(page)
                
                # Ziel-Ordner bestimmen
                target_folder = self.determine_target_folder(page, existing_filepath)
                
                if existing_filepath:
                    print(f"🔄 Update Page: {existing_filepath}")
                    
                    # Konflikt-Check
                    has_conflict, existing_post = self.check_for_conflicts(
                        existing_filepath, markdown_content, metadata
                    )
                    
                    if has_conflict:
                        print(f"⚠️ Konflikt bei Page: {existing_filepath}")
                        markdown_content, metadata = self.handle_conflict(
                            existing_filepath, existing_post, markdown_content, metadata
                        )
                        conflict_count += 1
                    
                    # Datei überschreiben
                    full_path = self.obsidian_path / existing_filepath
                    
                else:
                    # Neue Datei erstellen
                    title = metadata.get('title', 'Untitled')
                    filename = f"{self.sanitize_filename(title)}.md"
                    filepath = Path(target_folder) / filename
                    full_path = self.obsidian_path / filepath
                    
                    print(f"✅ Neue Page: {filepath}")
                
                # Metadata erweitern
                metadata.update({
                    'notion_id': page_id,
                    'notion_type': 'standalone_page',
                    'synced_at': datetime.now().isoformat()
                })
                
                # Datei schreiben
                full_path.parent.mkdir(parents=True, exist_ok=True)
                self.save_markdown_file(full_path, markdown_content, metadata)
                
                synced_count += 1
                
            except Exception as e:
                print(f"❌ Fehler bei Page {page.get('id', 'unknown')}: {e}")
        
        print(f"🎉 Korrigierter hierarchischer Sync abgeschlossen!")
        print(f"   📝 {synced_count} Dateien synchronisiert")
        print(f"   🗂️ {len(database_folders)} Database-Ordner erstellt")
        print(f"   ⚠️ {conflict_count} Konflikte behandelt")

def main():
    """Main function"""
    try:
        syncer = EnhancedNotionToObsidian()
        syncer.sync_all_pages()
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"⏰ Letzter Enhanced Sync: {timestamp}")
        
    except Exception as e:
        print(f"💥 Enhanced Sync Fehler: {e}")
        exit(1)

if __name__ == "__main__":
    main()