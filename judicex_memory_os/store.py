from __future__ import annotations

import json
import re
import shutil
import sqlite3
import hashlib
import difflib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .atomizer import compile_document_atoms, document_version_id
from .matter_analysis import analyze_matter_context, list_builtin_workflow_packs, load_workflow_pack
from .matter_memory import (
    extract_matter_facts,
    make_matter_document_id,
    make_matter_id,
    read_private_document_file,
    sha256_text,
)
from .models import Document, Edge, Entity, LegalAtom, Matter, MatterDocument, MatterFact
from .official_sources import make_document_id


class LegalMemoryStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA busy_timeout = 5000")
        self.conn.execute("PRAGMA foreign_keys = ON")
        try:
            self.conn.execute("PRAGMA journal_mode = WAL")
        except sqlite3.OperationalError:
            pass
        self.fts_enabled = False
        try:
            self.init_schema()
        except sqlite3.OperationalError as exc:
            self.conn.close()
            raise RuntimeError(
                f"Cannot initialize SQLite store at {self.db_path}. "
                "Close other Judicex processes using the database and ensure the file is writable."
            ) from exc

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "LegalMemoryStore":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def init_schema(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                kind TEXT NOT NULL,
                area TEXT NOT NULL,
                source_type TEXT NOT NULL DEFAULT 'official',
                source_ref TEXT NOT NULL DEFAULT '',
                authority TEXT NOT NULL DEFAULT '',
                effective_from TEXT NOT NULL DEFAULT '',
                effective_to TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS entities (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                kind TEXT NOT NULL,
                area TEXT NOT NULL,
                summary TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS edges (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                relation TEXT NOT NULL,
                weight REAL NOT NULL DEFAULT 1.0,
                summary TEXT NOT NULL DEFAULT '',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY (source_id) REFERENCES entities(id),
                FOREIGN KEY (target_id) REFERENCES entities(id)
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS document_versions (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                content_sha256 TEXT NOT NULL,
                title TEXT NOT NULL,
                source_ref TEXT NOT NULL DEFAULT '',
                effective_from TEXT NOT NULL DEFAULT '',
                effective_to TEXT NOT NULL DEFAULT '',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                UNIQUE(document_id, content_sha256),
                FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS legal_atoms (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                document_version_id TEXT NOT NULL,
                area TEXT NOT NULL,
                atom_type TEXT NOT NULL,
                subject TEXT NOT NULL,
                action TEXT NOT NULL,
                value TEXT NOT NULL DEFAULT '',
                unit TEXT NOT NULL DEFAULT '',
                temporal_anchor TEXT NOT NULL DEFAULT '',
                condition_text TEXT NOT NULL DEFAULT '',
                source_quote TEXT NOT NULL DEFAULT '',
                confidence REAL NOT NULL DEFAULT 1.0,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
                FOREIGN KEY (document_version_id) REFERENCES document_versions(id) ON DELETE CASCADE
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS matters (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                client_name TEXT NOT NULL DEFAULT '',
                area TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'open',
                summary TEXT NOT NULL DEFAULT '',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS matter_documents (
                id TEXT PRIMARY KEY,
                matter_id TEXT NOT NULL,
                title TEXT NOT NULL,
                kind TEXT NOT NULL,
                folder_id TEXT NOT NULL DEFAULT '',
                source_path TEXT NOT NULL DEFAULT '',
                content_sha256 TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (matter_id) REFERENCES matters(id) ON DELETE CASCADE
            )
            """
        )
        self._ensure_column("matter_documents", "folder_id", "TEXT NOT NULL DEFAULT ''")
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS matter_facts (
                id TEXT PRIMARY KEY,
                matter_id TEXT NOT NULL,
                document_id TEXT NOT NULL,
                fact_type TEXT NOT NULL,
                label TEXT NOT NULL,
                text TEXT NOT NULL,
                value TEXT NOT NULL DEFAULT '',
                unit TEXT NOT NULL DEFAULT '',
                date_value TEXT NOT NULL DEFAULT '',
                confidence REAL NOT NULL DEFAULT 1.0,
                source_quote TEXT NOT NULL DEFAULT '',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY (matter_id) REFERENCES matters(id) ON DELETE CASCADE,
                FOREIGN KEY (document_id) REFERENCES matter_documents(id) ON DELETE CASCADE
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS matter_folders (
                id TEXT PRIMARY KEY,
                matter_id TEXT NOT NULL,
                name TEXT NOT NULL,
                parent_id TEXT NOT NULL DEFAULT '',
                sort_order INTEGER NOT NULL DEFAULT 0,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (matter_id) REFERENCES matters(id) ON DELETE CASCADE
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS matter_document_versions (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                matter_id TEXT NOT NULL,
                version_number INTEGER NOT NULL,
                title TEXT NOT NULL,
                kind TEXT NOT NULL,
                folder_id TEXT NOT NULL DEFAULT '',
                content_sha256 TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY (document_id) REFERENCES matter_documents(id) ON DELETE CASCADE,
                FOREIGN KEY (matter_id) REFERENCES matters(id) ON DELETE CASCADE
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS document_edits (
                id TEXT PRIMARY KEY,
                matter_id TEXT NOT NULL,
                document_id TEXT NOT NULL,
                title TEXT NOT NULL,
                original_content TEXT NOT NULL,
                revised_content TEXT NOT NULL,
                diff_json TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'proposed',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                applied_at TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (document_id) REFERENCES matter_documents(id) ON DELETE CASCADE,
                FOREIGN KEY (matter_id) REFERENCES matters(id) ON DELETE CASCADE
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tabular_reviews (
                id TEXT PRIMARY KEY,
                matter_id TEXT NOT NULL,
                title TEXT NOT NULL,
                query TEXT NOT NULL DEFAULT '',
                columns_json TEXT NOT NULL DEFAULT '[]',
                rows_json TEXT NOT NULL DEFAULT '[]',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (matter_id) REFERENCES matters(id) ON DELETE CASCADE
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS custom_workflow_packs (
                id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                version TEXT NOT NULL DEFAULT '',
                definition_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS custom_workflow_versions (
                id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                version_number INTEGER NOT NULL,
                label TEXT NOT NULL,
                definition_json TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (workflow_id) REFERENCES custom_workflow_packs(id) ON DELETE CASCADE
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tabular_review_views (
                id TEXT PRIMARY KEY,
                review_id TEXT NOT NULL,
                matter_id TEXT NOT NULL,
                name TEXT NOT NULL,
                filter_text TEXT NOT NULL DEFAULT '',
                sort_key TEXT NOT NULL DEFAULT '',
                sort_dir TEXT NOT NULL DEFAULT 'asc',
                columns_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (review_id) REFERENCES tabular_reviews(id) ON DELETE CASCADE,
                FOREIGN KEY (matter_id) REFERENCES matters(id) ON DELETE CASCADE
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS document_annotations (
                id TEXT PRIMARY KEY,
                matter_id TEXT NOT NULL,
                document_id TEXT NOT NULL,
                page_number INTEGER NOT NULL DEFAULT 1,
                x REAL NOT NULL DEFAULT 0,
                y REAL NOT NULL DEFAULT 0,
                width REAL NOT NULL DEFAULT 0,
                height REAL NOT NULL DEFAULT 0,
                color TEXT NOT NULL DEFAULT '#facc15',
                note TEXT NOT NULL DEFAULT '',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (document_id) REFERENCES matter_documents(id) ON DELETE CASCADE,
                FOREIGN KEY (matter_id) REFERENCES matters(id) ON DELETE CASCADE
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS document_comments (
                id TEXT PRIMARY KEY,
                matter_id TEXT NOT NULL,
                document_id TEXT NOT NULL,
                anchor TEXT NOT NULL DEFAULT '',
                body TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (document_id) REFERENCES matter_documents(id) ON DELETE CASCADE,
                FOREIGN KEY (matter_id) REFERENCES matters(id) ON DELETE CASCADE
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS custom_draft_templates (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                required_params_json TEXT NOT NULL DEFAULT '[]',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                matter_id TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'open',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_memories (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                scope TEXT NOT NULL DEFAULT 'global',
                matter_id TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                tags_json TEXT NOT NULL DEFAULT '[]',
                importance REAL NOT NULL DEFAULT 0.5,
                source TEXT NOT NULL DEFAULT '',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS generated_artifacts (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL DEFAULT '',
                matter_id TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL,
                format TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_cache (
                key TEXT PRIMARY KEY,
                model TEXT NOT NULL,
                kind TEXT NOT NULL,
                response TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS answer_audit (
                id TEXT PRIMARY KEY,
                ts TEXT NOT NULL,
                question TEXT NOT NULL,
                question_hash TEXT NOT NULL,
                context_hash TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                signature TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL DEFAULT '',
                area TEXT NOT NULL DEFAULT '',
                matter_id TEXT NOT NULL DEFAULT '',
                as_of_date TEXT NOT NULL DEFAULT '',
                payload_json TEXT NOT NULL
            )
            """
        )
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_area ON documents(area)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_source_type ON documents(source_type)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_effective_from ON documents(effective_from)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_effective_to ON documents(effective_to)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_cache_model ON llm_cache(model)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_answer_audit_ts ON answer_audit(ts)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_answer_audit_matter ON answer_audit(matter_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_entities_area ON entities(area)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_relation ON edges(relation)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_document_versions_document ON document_versions(document_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_legal_atoms_document ON legal_atoms(document_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_legal_atoms_area ON legal_atoms(area)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_legal_atoms_type ON legal_atoms(atom_type)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_legal_atoms_action ON legal_atoms(action)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_matters_area ON matters(area)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_matters_status ON matters(status)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_matter_documents_matter ON matter_documents(matter_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_matter_documents_folder ON matter_documents(folder_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_matter_documents_sha ON matter_documents(content_sha256)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_matter_facts_matter ON matter_facts(matter_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_matter_facts_document ON matter_facts(document_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_matter_facts_type ON matter_facts(fact_type)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_matter_folders_matter ON matter_folders(matter_id)")
        self.conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_matter_document_versions_unique ON matter_document_versions(document_id, version_number)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_document_edits_document ON document_edits(document_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_tabular_reviews_matter ON tabular_reviews(matter_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_custom_workflow_packs_label ON custom_workflow_packs(label)")
        self.conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_custom_workflow_versions_unique ON custom_workflow_versions(workflow_id, version_number)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_tabular_review_views_review ON tabular_review_views(review_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_document_annotations_document ON document_annotations(document_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_document_comments_document ON document_comments(document_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_custom_draft_templates_name ON custom_draft_templates(name)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_status ON chat_sessions(status)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_updated ON chat_sessions(updated_at)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_created ON chat_messages(created_at)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_app_settings_updated ON app_settings(updated_at)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_memories_kind ON agent_memories(kind)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_memories_scope ON agent_memories(scope)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_memories_matter ON agent_memories(matter_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_memories_updated ON agent_memories(updated_at)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_generated_artifacts_session ON generated_artifacts(session_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_generated_artifacts_matter ON generated_artifacts(matter_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_generated_artifacts_created ON generated_artifacts(created_at)")
        self._ensure_fts()
        self.conn.commit()

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        columns = {
            str(row["name"])
            for row in self.conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _ensure_fts(self) -> None:
        try:
            self.conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts USING fts5(
                    id,
                    title,
                    content,
                    area,
                    source_ref,
                    content='documents',
                    content_rowid='rowid'
                )
                """
            )
            self.conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
                    INSERT INTO docs_fts(rowid, id, title, content, area, source_ref)
                    VALUES (new.rowid, new.id, new.title, new.content, new.area, new.source_ref);
                END
                """
            )
            self.conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
                    INSERT INTO docs_fts(docs_fts, rowid, id, title, content, area, source_ref)
                    VALUES ('delete', old.rowid, old.id, old.title, old.content, old.area, old.source_ref);
                END
                """
            )
            self.conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
                    INSERT INTO docs_fts(docs_fts, rowid, id, title, content, area, source_ref)
                    VALUES ('delete', old.rowid, old.id, old.title, old.content, old.area, old.source_ref);
                    INSERT INTO docs_fts(rowid, id, title, content, area, source_ref)
                    VALUES (new.rowid, new.id, new.title, new.content, new.area, new.source_ref);
                END
                """
            )
            self.conn.execute("INSERT INTO docs_fts(docs_fts) VALUES ('rebuild')")
            self.conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts USING fts5(
                    id,
                    name,
                    summary,
                    area,
                    content='entities',
                    content_rowid='rowid'
                )
                """
            )
            self.conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS entities_ai AFTER INSERT ON entities BEGIN
                    INSERT INTO entities_fts(rowid, id, name, summary, area)
                    VALUES (new.rowid, new.id, new.name, new.summary, new.area);
                END
                """
            )
            self.conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS entities_ad AFTER DELETE ON entities BEGIN
                    INSERT INTO entities_fts(entities_fts, rowid, id, name, summary, area)
                    VALUES ('delete', old.rowid, old.id, old.name, old.summary, old.area);
                END
                """
            )
            self.conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS entities_au AFTER UPDATE ON entities BEGIN
                    INSERT INTO entities_fts(entities_fts, rowid, id, name, summary, area)
                    VALUES ('delete', old.rowid, old.id, old.name, old.summary, old.area);
                    INSERT INTO entities_fts(rowid, id, name, summary, area)
                    VALUES (new.rowid, new.id, new.name, new.summary, new.area);
                END
                """
            )
            self.conn.execute("INSERT INTO entities_fts(entities_fts) VALUES ('rebuild')")
            self.conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS legal_atoms_fts USING fts5(
                    id,
                    document_id,
                    atom_type,
                    subject,
                    action,
                    value,
                    unit,
                    temporal_anchor,
                    condition_text,
                    source_quote,
                    area,
                    content='legal_atoms',
                    content_rowid='rowid'
                )
                """
            )
            self.conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS legal_atoms_ai AFTER INSERT ON legal_atoms BEGIN
                    INSERT INTO legal_atoms_fts(
                        rowid, id, document_id, atom_type, subject, action, value, unit,
                        temporal_anchor, condition_text, source_quote, area
                    )
                    VALUES (
                        new.rowid, new.id, new.document_id, new.atom_type, new.subject, new.action,
                        new.value, new.unit, new.temporal_anchor, new.condition_text, new.source_quote, new.area
                    );
                END
                """
            )
            self.conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS legal_atoms_ad AFTER DELETE ON legal_atoms BEGIN
                    INSERT INTO legal_atoms_fts(
                        legal_atoms_fts, rowid, id, document_id, atom_type, subject, action, value, unit,
                        temporal_anchor, condition_text, source_quote, area
                    )
                    VALUES (
                        'delete', old.rowid, old.id, old.document_id, old.atom_type, old.subject, old.action,
                        old.value, old.unit, old.temporal_anchor, old.condition_text, old.source_quote, old.area
                    );
                END
                """
            )
            self.conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS legal_atoms_au AFTER UPDATE ON legal_atoms BEGIN
                    INSERT INTO legal_atoms_fts(
                        legal_atoms_fts, rowid, id, document_id, atom_type, subject, action, value, unit,
                        temporal_anchor, condition_text, source_quote, area
                    )
                    VALUES (
                        'delete', old.rowid, old.id, old.document_id, old.atom_type, old.subject, old.action,
                        old.value, old.unit, old.temporal_anchor, old.condition_text, old.source_quote, old.area
                    );
                    INSERT INTO legal_atoms_fts(
                        rowid, id, document_id, atom_type, subject, action, value, unit,
                        temporal_anchor, condition_text, source_quote, area
                    )
                    VALUES (
                        new.rowid, new.id, new.document_id, new.atom_type, new.subject, new.action,
                        new.value, new.unit, new.temporal_anchor, new.condition_text, new.source_quote, new.area
                    );
                END
                """
            )
            self.conn.execute("INSERT INTO legal_atoms_fts(legal_atoms_fts) VALUES ('rebuild')")
            self.conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS matter_documents_fts USING fts5(
                    id,
                    matter_id,
                    title,
                    kind,
                    content,
                    content='matter_documents',
                    content_rowid='rowid'
                )
                """
            )
            self.conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS matter_documents_ai AFTER INSERT ON matter_documents BEGIN
                    INSERT INTO matter_documents_fts(rowid, id, matter_id, title, kind, content)
                    VALUES (new.rowid, new.id, new.matter_id, new.title, new.kind, new.content);
                END
                """
            )
            self.conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS matter_documents_ad AFTER DELETE ON matter_documents BEGIN
                    INSERT INTO matter_documents_fts(matter_documents_fts, rowid, id, matter_id, title, kind, content)
                    VALUES ('delete', old.rowid, old.id, old.matter_id, old.title, old.kind, old.content);
                END
                """
            )
            self.conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS matter_documents_au AFTER UPDATE ON matter_documents BEGIN
                    INSERT INTO matter_documents_fts(matter_documents_fts, rowid, id, matter_id, title, kind, content)
                    VALUES ('delete', old.rowid, old.id, old.matter_id, old.title, old.kind, old.content);
                    INSERT INTO matter_documents_fts(rowid, id, matter_id, title, kind, content)
                    VALUES (new.rowid, new.id, new.matter_id, new.title, new.kind, new.content);
                END
                """
            )
            self.conn.execute("INSERT INTO matter_documents_fts(matter_documents_fts) VALUES ('rebuild')")
            self.conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS matter_facts_fts USING fts5(
                    id,
                    matter_id,
                    document_id,
                    fact_type,
                    label,
                    text,
                    value,
                    unit,
                    date_value,
                    source_quote,
                    content='matter_facts',
                    content_rowid='rowid'
                )
                """
            )
            self.conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS matter_facts_ai AFTER INSERT ON matter_facts BEGIN
                    INSERT INTO matter_facts_fts(
                        rowid, id, matter_id, document_id, fact_type, label, text,
                        value, unit, date_value, source_quote
                    )
                    VALUES (
                        new.rowid, new.id, new.matter_id, new.document_id, new.fact_type,
                        new.label, new.text, new.value, new.unit, new.date_value, new.source_quote
                    );
                END
                """
            )
            self.conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS matter_facts_ad AFTER DELETE ON matter_facts BEGIN
                    INSERT INTO matter_facts_fts(
                        matter_facts_fts, rowid, id, matter_id, document_id, fact_type, label, text,
                        value, unit, date_value, source_quote
                    )
                    VALUES (
                        'delete', old.rowid, old.id, old.matter_id, old.document_id, old.fact_type,
                        old.label, old.text, old.value, old.unit, old.date_value, old.source_quote
                    );
                END
                """
            )
            self.conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS matter_facts_au AFTER UPDATE ON matter_facts BEGIN
                    INSERT INTO matter_facts_fts(
                        matter_facts_fts, rowid, id, matter_id, document_id, fact_type, label, text,
                        value, unit, date_value, source_quote
                    )
                    VALUES (
                        'delete', old.rowid, old.id, old.matter_id, old.document_id, old.fact_type,
                        old.label, old.text, old.value, old.unit, old.date_value, old.source_quote
                    );
                    INSERT INTO matter_facts_fts(
                        rowid, id, matter_id, document_id, fact_type, label, text,
                        value, unit, date_value, source_quote
                    )
                    VALUES (
                        new.rowid, new.id, new.matter_id, new.document_id, new.fact_type,
                        new.label, new.text, new.value, new.unit, new.date_value, new.source_quote
                    );
                END
                """
            )
            self.conn.execute("INSERT INTO matter_facts_fts(matter_facts_fts) VALUES ('rebuild')")
            self.fts_enabled = True
        except sqlite3.OperationalError:
            self.fts_enabled = False

    def _dump_json(self, value: dict[str, Any]) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    def _load_json(self, raw: str) -> dict[str, Any]:
        if not raw:
            return {}
        return json.loads(raw)

    def _load_json_list(self, raw: str) -> list[Any]:
        if not raw:
            return []
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _normalize_limit(self, top_k: int, *, max_value: int = 20) -> int:
        return max(1, min(int(top_k or 5), max_value))

    _STOPWORDS_IT = frozenset({
        "il", "lo", "la", "i", "gli", "le", "un", "uno", "una",
        "di", "del", "dello", "della", "dei", "degli", "delle",
        "a", "al", "allo", "alla", "ai", "agli", "alle",
        "da", "dal", "dallo", "dalla", "dai", "dagli", "dalle",
        "in", "nel", "nello", "nella", "nei", "negli", "nelle",
        "su", "sul", "sullo", "sulla", "sui", "sugli", "sulle",
        "con", "per", "tra", "fra", "che", "chi", "cui",
        "e", "ed", "o", "od", "ma", "se", "non", "ne", "ci", "vi",
        "sono", "sei", "siamo", "siete", "essere", "stato", "stata",
        "ho", "hai", "ha", "abbiamo", "avete", "hanno", "avere",
        "quale", "quali", "quanto", "quanta", "quanti", "quante",
        "come", "cosa", "dove", "quando", "perche", "perché",
        "questo", "questa", "questi", "queste", "quello", "quella",
        "mio", "tuo", "suo", "nostro", "vostro", "loro",
        "anche", "ancora", "gia", "già", "poi", "solo", "molto", "piu", "più",
    })

    def _query_tokens(self, text: str) -> list[str]:
        tokens = re.findall(r"[0-9A-Za-zÀ-ÿ_]+", text.lower())
        return [
            token for token in tokens
            if len(token) > 2 and token not in self._STOPWORDS_IT
        ]

    def _fts_query(self, text: str) -> str:
        clean = self._query_tokens(text)[:12]
        if not clean:
            return ""
        return " OR ".join(f'"{token}"' for token in clean)

    def _question_fragments(self, question: str) -> list[str]:
        compact = re.sub(r"\s+", " ", question.strip())
        if not compact:
            return []

        fragments = [compact]
        for part in re.split(r"[;:\?\n]+|,\s+(?:e\s+)?", compact):
            part = part.strip(" .")
            if len(self._query_tokens(part)) >= 2:
                fragments.append(part)

        action_markers = (
            "notific", "oppos", "ademp", "pag", "consegn", "prescr",
            "decorr", "emett", "deposit", "esecut", "sospend", "compet",
            "prova", "mora", "interess",
        )
        for part in list(fragments):
            marker_count = sum(1 for marker in action_markers if marker in part.lower())
            if marker_count < 2:
                continue
            for chunk in re.split(r"\s+(?:e|oppure|ovvero|nonche|nonché)\s+", part):
                chunk = chunk.strip(" .")
                if len(self._query_tokens(chunk)) >= 2:
                    fragments.append(chunk)

        return self._unique_texts(fragments, max_items=8)

    @staticmethod
    def _unique_texts(values: list[str], *, max_items: int) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for value in values:
            normalized = re.sub(r"\s+", " ", value.strip())
            key = normalized.lower()
            if not normalized or key in seen:
                continue
            seen.add(key)
            out.append(normalized)
            if len(out) >= max_items:
                break
        return out

    _LEGAL_QUERY_HINTS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
        (("notific",), ("notificazione", "notifica", "notificato", "termine", "giorni", "pronuncia")),
        (("oppos",), ("opposizione", "opporsi", "proporre", "termine", "intimato", "ricorrente")),
        (("termin", "giorn", "entro", "scad"), ("termine", "giorni", "decorsi", "decorrenza", "scadenza")),
        (("decreto", "ingiun"), ("decreto", "ingiunzione", "ingiuntivo", "intimato", "ricorrente")),
        (("provvisori", "esecut"), ("esecuzione", "provvisoria", "ordinanza", "cauzione")),
        (("prescr",), ("prescrizione", "diritto", "decorso", "anni")),
        (("mora",), ("mora", "intimazione", "richiesta", "debitore", "creditore")),
        (("prova",), ("prova", "scritta", "documenti", "crediti")),
        (("compet",), ("competenza", "giudice", "tribunale", "ufficio")),
        (("interess",), ("interessi", "saggio", "legale", "crediti")),
    )

    def _query_hints(self, fragment: str) -> list[str]:
        lowered = fragment.lower()
        hints: list[str] = []
        for markers, terms in self._LEGAL_QUERY_HINTS:
            if any(marker in lowered for marker in markers):
                hints.extend(terms)
        return self._unique_texts(hints, max_items=16)

    def _article_queries(self, question: str) -> list[str]:
        queries: list[str] = []
        for article in re.findall(r"\b(?:art\.?|articolo)\s*([0-9]+(?:[- ][a-z]+)?)", question, re.IGNORECASE):
            normalized = re.sub(r"\s+", "", article.lower())
            queries.append(f"art {normalized} articolo {normalized}")
        return self._unique_texts(queries, max_items=6)

    def _retrieval_queries(self, question: str) -> list[str]:
        queries: list[str] = []
        for fragment in self._question_fragments(question):
            queries.append(fragment)
            hints = self._query_hints(fragment)
            if hints:
                queries.append(" ".join(hints + [fragment]))
        queries.extend(self._article_queries(question))
        return self._unique_texts(queries, max_items=14)

    def _candidate_score(
        self,
        doc: dict[str, Any],
        *,
        question: str,
        queries: list[str],
        reasons: list[str],
    ) -> float:
        question_tokens = set(self._query_tokens(question))
        title = doc.get("title", "")
        content = doc.get("content") or doc.get("excerpt") or ""
        title_tokens = set(self._query_tokens(title))
        content_tokens = set(self._query_tokens(content))

        score = 0.0
        score += 4.0 * len(question_tokens & title_tokens)
        score += 1.0 * len(question_tokens & content_tokens)
        score += 1.5 * len(set(reasons))
        score += 0.5 * len(queries)

        lowered_question = question.lower()
        lowered_title = title.lower()
        lowered_content = content.lower()
        for stem in (
            "notific", "oppos", "termin", "giorn", "decreto", "ingiun",
            "prescr", "mora", "prova", "compet", "esecut", "interess",
        ):
            if stem not in lowered_question:
                continue
            if stem in lowered_title:
                score += 5.0
            elif stem in lowered_content:
                score += 2.0

        if any(reason.startswith("entity") for reason in reasons):
            score += 3.0

        temporal_stems = ("giorn", "termine", "entro", "decors", "decorren", "scad")
        action_stems = (
            "notific", "oppos", "ademp", "pag", "consegn", "prescr",
            "emett", "deposit", "esecut", "sospend", "compet", "prova",
            "mora", "interess",
        )
        active_temporal_stems = [stem for stem in temporal_stems if stem in lowered_question]
        active_action_stems = [stem for stem in action_stems if stem in lowered_question]
        sentence_supported_actions: set[str] = set()
        if active_temporal_stems and active_action_stems:
            for action_stem in active_action_stems:
                action_positions = [match.start() for match in re.finditer(re.escape(action_stem), lowered_content)]
                if not action_positions:
                    continue
                for temporal_stem in active_temporal_stems:
                    temporal_positions = [
                        match.start() for match in re.finditer(re.escape(temporal_stem), lowered_content)
                    ]
                    if not temporal_positions:
                        continue
                    if any(abs(action_pos - temporal_pos) <= 320 for action_pos in action_positions for temporal_pos in temporal_positions):
                        score += 7.0
                    else:
                        score += 1.0
            for sentence in re.split(r"[.;\n]+", lowered_content):
                if not any(temporal_stem in sentence for temporal_stem in active_temporal_stems):
                    continue
                for action_stem in active_action_stems:
                    if action_stem in sentence:
                        sentence_supported_actions.add(action_stem)
                        score += 8.0
            if any(marker in lowered_question for marker in ("quant", "giorn", "entro", "termine")):
                for action_stem in active_action_stems:
                    if action_stem in lowered_title and action_stem not in sentence_supported_actions:
                        score -= 8.0

        exception_markers = (
            ("tardiv", "tardiv"),
            ("provvisori", "provvisori"),
            ("pendenza", "pendenz"),
            ("esecutor", "esecutor"),
            ("sospension", "sospend"),
            ("rigetto", "rigett"),
            ("parziale", "parzial"),
        )
        for title_marker, question_marker in exception_markers:
            if title_marker in lowered_title and question_marker not in lowered_question:
                score -= 40.0

        for article_query in self._article_queries(question):
            article_tokens = self._query_tokens(article_query)
            if not article_tokens:
                continue
            article_number = article_tokens[0]
            compact_id = doc.get("id", "").lower().replace("_", "")
            compact_title = lowered_title.replace(" ", "")
            if f"art{article_number}" in compact_id or f"art.{article_number}" in compact_title:
                score += 12.0

        return score

    def _document_row_to_dict(self, row: sqlite3.Row, *, full: bool = False) -> dict[str, Any]:
        payload = {
            "id": row["id"],
            "title": row["title"],
            "kind": row["kind"],
            "area": row["area"],
            "source_type": row["source_type"],
            "source_ref": row["source_ref"],
            "authority": row["authority"],
            "effective_from": row["effective_from"],
            "effective_to": row["effective_to"],
            "metadata": self._load_json(row["metadata_json"]),
        }
        if "score" in row.keys():
            payload["score"] = row["score"]
        if full:
            payload["content"] = row["content"]
        else:
            excerpt = row["content"].strip().replace("\n", " ")
            payload["excerpt"] = excerpt[:420] + ("..." if len(excerpt) > 420 else "")
        return payload

    def _entity_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        payload = {
            "id": row["id"],
            "name": row["name"],
            "kind": row["kind"],
            "area": row["area"],
            "summary": row["summary"],
            "metadata": self._load_json(row["metadata_json"]),
        }
        if "score" in row.keys():
            payload["score"] = row["score"]
        return payload

    def _atom_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        payload = {
            "id": row["id"],
            "document_id": row["document_id"],
            "document_version_id": row["document_version_id"],
            "area": row["area"],
            "atom_type": row["atom_type"],
            "subject": row["subject"],
            "action": row["action"],
            "value": row["value"],
            "unit": row["unit"],
            "temporal_anchor": row["temporal_anchor"],
            "condition_text": row["condition_text"],
            "source_quote": row["source_quote"],
            "confidence": row["confidence"],
            "metadata": self._load_json(row["metadata_json"]),
        }
        if "score" in row.keys():
            payload["score"] = row["score"]
        return payload

    def _matter_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "title": row["title"],
            "client_name": row["client_name"],
            "area": row["area"],
            "status": row["status"],
            "summary": row["summary"],
            "metadata": self._load_json(row["metadata_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _matter_document_row_to_dict(self, row: sqlite3.Row, *, full: bool = False) -> dict[str, Any]:
        payload = {
            "id": row["id"],
            "matter_id": row["matter_id"],
            "title": row["title"],
            "kind": row["kind"],
            "folder_id": row["folder_id"] if "folder_id" in row.keys() else "",
            "source_path": row["source_path"],
            "content_sha256": row["content_sha256"],
            "metadata": self._load_json(row["metadata_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        if "score" in row.keys():
            payload["score"] = row["score"]
        content = self._matter_decrypt(row["content"])
        if full:
            payload["content"] = content
        else:
            excerpt = content.strip().replace("\n", " ")
            payload["excerpt"] = excerpt[:420] + ("..." if len(excerpt) > 420 else "")
        return payload

    def _chat_session_row_to_dict(self, row: sqlite3.Row, *, full: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": row["id"],
            "title": row["title"],
            "matter_id": row["matter_id"],
            "status": row["status"],
            "metadata": self._load_json(row["metadata_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        keys = set(row.keys())
        if "message_count" in keys:
            payload["message_count"] = row["message_count"]
        if "last_message_at" in keys:
            payload["last_message_at"] = row["last_message_at"]
        if full:
            payload["messages"] = self.list_chat_messages(row["id"], top_k=500)
        return payload

    def _chat_message_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "session_id": row["session_id"],
            "role": row["role"],
            "content": row["content"],
            "metadata": self._load_json(row["metadata_json"]),
            "created_at": row["created_at"],
        }

    def _agent_memory_row_to_dict(self, row: sqlite3.Row, *, full: bool = False) -> dict[str, Any]:
        payload = {
            "id": row["id"],
            "kind": row["kind"],
            "scope": row["scope"],
            "matter_id": row["matter_id"],
            "title": row["title"],
            "tags": [str(item) for item in self._load_json_list(row["tags_json"])],
            "importance": float(row["importance"]),
            "source": row["source"],
            "metadata": self._load_json(row["metadata_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        if "score" in row.keys():
            payload["score"] = row["score"]
        if full:
            payload["content"] = row["content"]
        else:
            excerpt = row["content"].strip().replace("\n", " ")
            payload["excerpt"] = excerpt[:420] + ("..." if len(excerpt) > 420 else "")
        return payload

    def _generated_artifact_row_to_dict(self, row: sqlite3.Row, *, full: bool = False) -> dict[str, Any]:
        payload = {
            "id": row["id"],
            "session_id": row["session_id"],
            "matter_id": row["matter_id"],
            "title": row["title"],
            "format": row["format"],
            "metadata": self._load_json(row["metadata_json"]),
            "created_at": row["created_at"],
        }
        if full:
            payload["content"] = row["content"]
        else:
            excerpt = row["content"].strip().replace("\n", " ")
            payload["excerpt"] = excerpt[:520] + ("..." if len(excerpt) > 520 else "")
        return payload

    def _matter_crypto(self) -> Any:
        """Lazy-load the matter encryption helper.

        Cached on the store instance so we hit env / cache once per process.
        """

        crypto = getattr(self, "_matter_crypto_cached", None)
        if crypto is None:
            from .crypto import MatterCrypto

            crypto = MatterCrypto.from_store(self)
            self._matter_crypto_cached = crypto
        return crypto

    def _matter_encrypt(self, plaintext: str) -> str:
        return self._matter_crypto().encrypt(plaintext)

    def _matter_decrypt(self, ciphertext: str) -> str:
        return self._matter_crypto().decrypt(ciphertext)

    def _matter_fact_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        payload = {
            "id": row["id"],
            "matter_id": row["matter_id"],
            "document_id": row["document_id"],
            "fact_type": row["fact_type"],
            "label": row["label"],
            "text": row["text"],
            "value": row["value"],
            "unit": row["unit"],
            "date_value": row["date_value"],
            "confidence": row["confidence"],
            "source_quote": row["source_quote"],
            "metadata": self._load_json(row["metadata_json"]),
            "created_at": row["created_at"],
        }
        if "score" in row.keys():
            payload["score"] = row["score"]
        return payload

    @staticmethod
    def document_entity_id(doc_id: str) -> str:
        return f"entity:document:{doc_id}"

    def _document_summary(self, item: Document) -> str:
        first_line = next((line.strip() for line in item.content.splitlines() if line.strip()), "")
        summary = first_line if len(first_line) <= 180 else first_line[:177] + "..."
        if not summary:
            summary = item.source_ref or item.title
        return summary

    def upsert_document(self, item: Document) -> None:
        self.conn.execute(
            """
            INSERT INTO documents (
                id, title, kind, area, source_type, source_ref, authority,
                effective_from, effective_to, content, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                kind = excluded.kind,
                area = excluded.area,
                source_type = excluded.source_type,
                source_ref = excluded.source_ref,
                authority = excluded.authority,
                effective_from = excluded.effective_from,
                effective_to = excluded.effective_to,
                content = excluded.content,
                metadata_json = excluded.metadata_json
            """,
            (
                item.id,
                item.title,
                item.kind,
                item.area,
                item.source_type,
                item.source_ref,
                item.authority,
                item.effective_from,
                item.effective_to,
                item.content,
                self._dump_json(item.metadata),
                self._now(),
            ),
        )
        self.upsert_entity(
            Entity(
                id=self.document_entity_id(item.id),
                name=item.title,
                kind="document",
                area=item.area,
                summary=self._document_summary(item),
                metadata={
                    "document_id": item.id,
                    "source_ref": item.source_ref,
                    "authority": item.authority,
                    "source_type": item.source_type,
                    "urn": item.metadata.get("urn", ""),
                    "official": bool(item.metadata.get("official", item.source_type == "official")),
                },
            )
        )
        version_id = self.upsert_document_version(item)
        self.replace_document_atoms(item.id, compile_document_atoms(item), document_version_id=version_id)

    def upsert_document_version(self, item: Document) -> str:
        version_id = document_version_id(item)
        content_sha256 = hashlib.sha256(item.content.encode("utf-8")).hexdigest()
        metadata = {
            "authority": item.authority,
            "source_type": item.source_type,
            "urn": item.metadata.get("urn", ""),
            "provider": item.metadata.get("provider", ""),
            "retrieved_at": item.metadata.get("retrieved_at", ""),
        }
        self.conn.execute(
            """
            INSERT INTO document_versions (
                id, document_id, content_sha256, title, source_ref,
                effective_from, effective_to, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(document_id, content_sha256) DO UPDATE SET
                title = excluded.title,
                source_ref = excluded.source_ref,
                effective_from = excluded.effective_from,
                effective_to = excluded.effective_to,
                metadata_json = excluded.metadata_json
            """,
            (
                version_id,
                item.id,
                content_sha256,
                item.title,
                item.source_ref,
                item.effective_from,
                item.effective_to,
                self._dump_json(metadata),
                self._now(),
            ),
        )
        return version_id

    def replace_document_atoms(
        self,
        doc_id: str,
        atoms: list[LegalAtom],
        *,
        document_version_id: str | None = None,
    ) -> None:
        if document_version_id:
            self.conn.execute(
                "DELETE FROM legal_atoms WHERE document_id = ? AND document_version_id = ?",
                (doc_id, document_version_id),
            )
        else:
            self.conn.execute("DELETE FROM legal_atoms WHERE document_id = ?", (doc_id,))
        for atom in atoms:
            self.upsert_legal_atom(atom)

    def upsert_legal_atom(self, item: LegalAtom) -> None:
        self.conn.execute(
            """
            INSERT INTO legal_atoms (
                id, document_id, document_version_id, area, atom_type, subject, action,
                value, unit, temporal_anchor, condition_text, source_quote, confidence,
                metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                document_id = excluded.document_id,
                document_version_id = excluded.document_version_id,
                area = excluded.area,
                atom_type = excluded.atom_type,
                subject = excluded.subject,
                action = excluded.action,
                value = excluded.value,
                unit = excluded.unit,
                temporal_anchor = excluded.temporal_anchor,
                condition_text = excluded.condition_text,
                source_quote = excluded.source_quote,
                confidence = excluded.confidence,
                metadata_json = excluded.metadata_json
            """,
            (
                item.id,
                item.document_id,
                item.document_version_id,
                item.area,
                item.atom_type,
                item.subject,
                item.action,
                item.value,
                item.unit,
                item.temporal_anchor,
                item.condition_text,
                item.source_quote,
                float(item.confidence),
                self._dump_json(item.metadata),
                self._now(),
            ),
        )

    def upsert_entity(self, item: Entity) -> None:
        self.conn.execute(
            """
            INSERT INTO entities (id, name, kind, area, summary, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                kind = excluded.kind,
                area = excluded.area,
                summary = excluded.summary,
                metadata_json = excluded.metadata_json
            """,
            (
                item.id,
                item.name,
                item.kind,
                item.area,
                item.summary,
                self._dump_json(item.metadata),
                self._now(),
            ),
        )

    def upsert_edge(self, item: Edge) -> None:
        self.conn.execute(
            """
            INSERT INTO edges (
                id, source_id, target_id, relation, weight, summary, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                source_id = excluded.source_id,
                target_id = excluded.target_id,
                relation = excluded.relation,
                weight = excluded.weight,
                summary = excluded.summary,
                metadata_json = excluded.metadata_json
            """,
            (
                item.id,
                item.source_id,
                item.target_id,
                item.relation,
                item.weight,
                item.summary,
                self._dump_json(item.metadata),
                self._now(),
            ),
        )

    def replace_document_references(self, doc_id: str, area: str, references: list[dict[str, Any]]) -> None:
        source_entity_id = self.document_entity_id(doc_id)
        self.conn.execute(
            "DELETE FROM edges WHERE source_id = ? AND relation = 'references'",
            (source_entity_id,),
        )

        for ref in references:
            urn = str(ref.get("urn", "")).strip()
            if not urn:
                continue
            target_doc_id = make_document_id(urn)
            target_entity_id = self.document_entity_id(target_doc_id)
            label = str(ref.get("text", "")).strip() or urn
            self.upsert_entity(
                Entity(
                    id=target_entity_id,
                    name=label,
                    kind="document_ref",
                    area=area,
                    summary=urn,
                    metadata={
                        "document_id": target_doc_id,
                        "urn": urn,
                        "source_ref": str(ref.get("source_ref", "")),
                        "stub": True,
                    },
                )
            )
            edge_id = f"edge:references:{source_entity_id}:{target_entity_id}"
            self.upsert_edge(
                Edge(
                    id=edge_id,
                    source_id=source_entity_id,
                    target_id=target_entity_id,
                    relation="references",
                    weight=1.0,
                    summary=label,
                    metadata={"urn": urn, "source_ref": str(ref.get("source_ref", ""))},
                )
            )

    def commit(self) -> None:
        self.conn.commit()

    def ingest_json_file(self, file_path: str | Path) -> dict[str, int | bool]:
        payload = json.loads(Path(file_path).read_text(encoding="utf-8"))
        for raw in payload.get("documents", []):
            document = Document(
                id=raw["id"],
                title=raw["title"],
                kind=raw["kind"],
                area=raw["area"],
                content=raw["content"],
                source_type=raw.get("source_type", "official"),
                source_ref=raw.get("source_ref", ""),
                authority=raw.get("authority", ""),
                effective_from=raw.get("effective_from", ""),
                effective_to=raw.get("effective_to", ""),
                metadata=raw.get("metadata", {}),
            )
            self.upsert_document(document)
            self.replace_document_references(document.id, document.area, document.metadata.get("references", []))
        for raw in payload.get("entities", []):
            self.upsert_entity(
                Entity(
                    id=raw["id"],
                    name=raw["name"],
                    kind=raw["kind"],
                    area=raw["area"],
                    summary=raw["summary"],
                    metadata=raw.get("metadata", {}),
                )
            )
        for raw in payload.get("edges", []):
            self.upsert_edge(
                Edge(
                    id=raw["id"],
                    source_id=raw["source_id"],
                    target_id=raw["target_id"],
                    relation=raw["relation"],
                    weight=float(raw.get("weight", 1.0)),
                    summary=raw.get("summary", ""),
                    metadata=raw.get("metadata", {}),
                )
            )
        self.commit()
        return self.health()

    def upsert_matter(self, item: Matter) -> None:
        now = self._now()
        self.conn.execute(
            """
            INSERT INTO matters (
                id, title, client_name, area, status, summary, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                client_name = excluded.client_name,
                area = excluded.area,
                status = excluded.status,
                summary = excluded.summary,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at
            """,
            (
                item.id,
                item.title.strip(),
                item.client_name.strip(),
                item.area.strip(),
                item.status.strip() or "open",
                item.summary.strip(),
                self._dump_json(item.metadata),
                now,
                now,
            ),
        )

    def create_matter(
        self,
        title: str,
        *,
        client_name: str = "",
        area: str = "",
        status: str = "open",
        summary: str = "",
        metadata: dict[str, Any] | None = None,
        matter_id: str | None = None,
    ) -> dict[str, Any]:
        matter = Matter(
            id=matter_id or make_matter_id(title, client_name=client_name, area=area),
            title=title,
            client_name=client_name,
            area=area,
            status=status,
            summary=summary,
            metadata=metadata or {},
        )
        self.upsert_matter(matter)
        self.commit()
        stored = self.get_matter(matter.id)
        if stored is None:
            raise RuntimeError(f"matter was not stored: {matter.id}")
        return stored

    def get_matter(self, matter_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM matters WHERE id = ?", (matter_id,)).fetchone()
        if row is None:
            return None
        return self._matter_row_to_dict(row)

    def list_matters(
        self,
        *,
        area: str | None = None,
        status: str | None = None,
        top_k: int = 20,
    ) -> list[dict[str, Any]]:
        top_k = self._normalize_limit(top_k, max_value=100)
        sql = "SELECT * FROM matters"
        params: list[Any] = []
        clauses: list[str] = []
        if area:
            clauses.append("area = ?")
            params.append(area)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY updated_at DESC, title LIMIT ?"
        params.append(top_k)
        rows = self.conn.execute(sql, params).fetchall()
        return [self._matter_row_to_dict(row) for row in rows]

    def search_matters(self, query: str, *, top_k: int = 20) -> list[dict[str, Any]]:
        top_k = self._normalize_limit(top_k, max_value=100)
        query = query.strip()
        if not query:
            return self.list_matters(top_k=top_k)
        like = f"%{query.lower()}%"
        rows = self.conn.execute(
            """
            SELECT *
            FROM matters
            WHERE lower(title) LIKE ?
               OR lower(client_name) LIKE ?
               OR lower(area) LIKE ?
               OR lower(summary) LIKE ?
            ORDER BY updated_at DESC, title
            LIMIT ?
            """,
            (like, like, like, like, top_k),
        ).fetchall()
        return [self._matter_row_to_dict(row) for row in rows]

    def delete_matter(self, matter_id: str) -> bool:
        matter_id = matter_id.strip()
        if not matter_id:
            return False
        rows = self.conn.execute(
            "SELECT source_path, metadata_json FROM matter_documents WHERE matter_id = ?",
            (matter_id,),
        ).fetchall()
        self.conn.execute("DELETE FROM chat_sessions WHERE matter_id = ?", (matter_id,))
        self.conn.execute("DELETE FROM answer_audit WHERE matter_id = ?", (matter_id,))
        cursor = self.conn.execute("DELETE FROM matters WHERE id = ?", (matter_id,))
        deleted = cursor.rowcount > 0
        if deleted:
            self.commit()
            self._delete_stored_matter_files(rows)
        return deleted

    def _delete_stored_matter_files(self, rows: list[sqlite3.Row]) -> None:
        try:
            base = self.db_path.parent.resolve()
        except OSError:
            return
        for row in rows:
            metadata = self._load_json(row["metadata_json"])
            raw_path = str(metadata.get("stored_path") or row["source_path"] or "").strip()
            if not raw_path:
                continue
            try:
                path = Path(raw_path).expanduser().resolve()
            except OSError:
                continue
            if not path.is_file() or not (path == base or base in path.parents):
                continue
            try:
                path.unlink()
            except OSError:
                pass

    def create_chat_session(
        self,
        *,
        title: str = "",
        matter_id: str = "",
        status: str = "open",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        clean_title = title.strip() or "Nuova chat"
        session_id = f"chat:{sha256_text(f'{clean_title}:{matter_id}:{now}')[:18]}"
        self.conn.execute(
            """
            INSERT INTO chat_sessions (
                id, title, matter_id, status, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                clean_title[:120],
                matter_id.strip(),
                status.strip() or "open",
                self._dump_json(metadata or {}),
                now,
                now,
            ),
        )
        self.commit()
        session = self.get_chat_session(session_id, full=True)
        if session is None:
            raise RuntimeError(f"chat session was not stored: {session_id}")
        return session

    def list_chat_sessions(
        self,
        *,
        status: str | None = "open",
        top_k: int = 100,
    ) -> list[dict[str, Any]]:
        top_k = self._normalize_limit(top_k, max_value=200)
        params: list[Any] = []
        where = ""
        if status:
            where = "WHERE s.status = ?"
            params.append(status)
        params.append(top_k)
        rows = self.conn.execute(
            f"""
            SELECT
                s.*,
                COUNT(m.id) AS message_count,
                MAX(m.created_at) AS last_message_at
            FROM chat_sessions s
            LEFT JOIN chat_messages m ON m.session_id = s.id
            {where}
            GROUP BY s.id
            ORDER BY COALESCE(MAX(m.created_at), s.updated_at) DESC, s.updated_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [self._chat_session_row_to_dict(row) for row in rows]

    def get_chat_session(self, session_id: str, *, full: bool = False) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            return None
        return self._chat_session_row_to_dict(row, full=full)

    def update_chat_session(
        self,
        session_id: str,
        *,
        title: str | None = None,
        matter_id: str | None = None,
        status: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        current = self.get_chat_session(session_id)
        if current is None:
            return None
        next_metadata = dict(current.get("metadata") or {})
        if metadata:
            next_metadata.update(metadata)
        self.conn.execute(
            """
            UPDATE chat_sessions
            SET title = ?, matter_id = ?, status = ?, metadata_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                (title.strip() if title is not None else current["title"])[:120] or "Nuova chat",
                matter_id.strip() if matter_id is not None else current["matter_id"],
                status.strip() if status is not None else current["status"],
                self._dump_json(next_metadata),
                self._now(),
                session_id,
            ),
        )
        self.commit()
        return self.get_chat_session(session_id, full=True)

    def delete_chat_session(self, session_id: str) -> bool:
        cursor = self.conn.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
        self.commit()
        return cursor.rowcount > 0

    def add_chat_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session = self.get_chat_session(session_id)
        if session is None:
            raise ValueError(f"Chat non trovata: {session_id}")
        clean_role = role.strip().lower() or "assistant"
        if clean_role not in {"user", "assistant", "system", "tool"}:
            clean_role = "assistant"
        clean_content = content.strip()
        if not clean_content:
            raise ValueError("Messaggio vuoto.")
        now = self._now()
        message_id = f"msg:{sha256_text(f'{session_id}:{clean_role}:{clean_content}:{now}')[:22]}"
        self.conn.execute(
            """
            INSERT INTO chat_messages (
                id, session_id, role, content, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                session_id,
                clean_role,
                clean_content,
                self._dump_json(metadata or {}),
                now,
            ),
        )
        next_title = session["title"]
        if clean_role == "user" and next_title.strip().lower() in {"", "nuova chat"}:
            next_title = re.sub(r"\s+", " ", clean_content)[:70] or "Nuova chat"
        self.conn.execute(
            "UPDATE chat_sessions SET title = ?, updated_at = ? WHERE id = ?",
            (next_title, now, session_id),
        )
        self.commit()
        row = self.conn.execute("SELECT * FROM chat_messages WHERE id = ?", (message_id,)).fetchone()
        if row is None:
            raise RuntimeError(f"chat message was not stored: {message_id}")
        return self._chat_message_row_to_dict(row)

    def list_chat_messages(self, session_id: str, *, top_k: int = 500) -> list[dict[str, Any]]:
        top_k = self._normalize_limit(top_k, max_value=500)
        rows = self.conn.execute(
            """
            SELECT * FROM chat_messages
            WHERE session_id = ?
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (session_id, top_k),
        ).fetchall()
        return [self._chat_message_row_to_dict(row) for row in rows]

    def search_chat_sessions(self, query: str, *, top_k: int = 20) -> list[dict[str, Any]]:
        top_k = self._normalize_limit(top_k, max_value=100)
        query = query.strip()
        if not query:
            return self.list_chat_sessions(status=None, top_k=top_k)
        like = f"%{query.lower()}%"
        rows = self.conn.execute(
            """
            SELECT
                s.*,
                COUNT(m.id) AS message_count,
                MAX(m.created_at) AS last_message_at
            FROM chat_sessions s
            LEFT JOIN chat_messages m ON m.session_id = s.id
            WHERE lower(s.title) LIKE ?
               OR lower(s.status) LIKE ?
            GROUP BY s.id
            ORDER BY COALESCE(MAX(m.created_at), s.updated_at) DESC, s.updated_at DESC
            LIMIT ?
            """,
            (like, like, top_k),
        ).fetchall()
        return [self._chat_session_row_to_dict(row) for row in rows]

    def search_chat_messages(self, query: str, *, top_k: int = 20) -> list[dict[str, Any]]:
        top_k = self._normalize_limit(top_k, max_value=100)
        query = query.strip()
        params: list[Any] = []
        where = ""
        if query:
            like = f"%{query.lower()}%"
            where = "WHERE lower(m.content) LIKE ? OR lower(s.title) LIKE ?"
            params.extend([like, like])
        params.append(top_k)
        rows = self.conn.execute(
            f"""
            SELECT
                m.*,
                s.title AS session_title,
                s.matter_id AS matter_id,
                s.status AS session_status
            FROM chat_messages m
            JOIN chat_sessions s ON s.id = m.session_id
            {where}
            ORDER BY m.created_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        messages = []
        for row in rows:
            item = self._chat_message_row_to_dict(row)
            item["session_title"] = row["session_title"]
            item["matter_id"] = row["matter_id"]
            item["session_status"] = row["session_status"]
            messages.append(item)
        return messages

    def get_app_setting(self, key: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM app_settings WHERE key = ?", (key,)).fetchone()
        if row is None:
            return None
        payload = self._load_json(row["value_json"])
        payload["_key"] = row["key"]
        payload["_created_at"] = row["created_at"]
        payload["_updated_at"] = row["updated_at"]
        return payload

    def set_app_setting(self, key: str, value: dict[str, Any]) -> dict[str, Any]:
        now = self._now()
        self.conn.execute(
            """
            INSERT INTO app_settings (key, value_json, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value_json = excluded.value_json,
                updated_at = excluded.updated_at
            """,
            (key.strip(), self._dump_json(value), now, now),
        )
        self.commit()
        stored = self.get_app_setting(key)
        if stored is None:
            raise RuntimeError(f"setting was not stored: {key}")
        return stored

    def list_app_settings(self) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM app_settings ORDER BY key").fetchall()
        settings = []
        for row in rows:
            value = self._load_json(row["value_json"])
            value["_key"] = row["key"]
            value["_created_at"] = row["created_at"]
            value["_updated_at"] = row["updated_at"]
            settings.append(value)
        return settings

    # ------------------------------------------------------------------
    # Agent memory
    # ------------------------------------------------------------------

    def add_agent_memory(
        self,
        *,
        kind: str,
        title: str,
        content: str,
        scope: str = "global",
        matter_id: str = "",
        tags: list[str] | None = None,
        importance: float = 0.5,
        source: str = "",
        metadata: dict[str, Any] | None = None,
        memory_id: str | None = None,
    ) -> dict[str, Any]:
        clean_kind = re.sub(r"[^a-z0-9_:-]+", "_", kind.strip().lower()) or "note"
        clean_scope = re.sub(r"[^a-z0-9_:-]+", "_", scope.strip().lower()) or "global"
        clean_title = re.sub(r"\s+", " ", title.strip())[:180] or "Nota memoria"
        clean_content = content.strip()
        if not clean_content:
            raise ValueError("Contenuto memoria vuoto.")
        clean_tags = _clean_tag_list(tags or [])
        now = self._now()
        final_id = memory_id or f"memory:{sha256_text(f'{clean_kind}:{clean_scope}:{matter_id}:{clean_title}:{clean_content}')[:22]}"
        self.conn.execute(
            """
            INSERT INTO agent_memories (
                id, kind, scope, matter_id, title, content, tags_json, importance,
                source, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                kind = excluded.kind,
                scope = excluded.scope,
                matter_id = excluded.matter_id,
                title = excluded.title,
                content = excluded.content,
                tags_json = excluded.tags_json,
                importance = excluded.importance,
                source = excluded.source,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at
            """,
            (
                final_id,
                clean_kind,
                clean_scope,
                matter_id.strip(),
                clean_title,
                clean_content,
                json.dumps(clean_tags, ensure_ascii=False),
                max(0.0, min(float(importance), 1.0)),
                source.strip(),
                self._dump_json(metadata or {}),
                now,
                now,
            ),
        )
        self.commit()
        stored = self.get_agent_memory(final_id, full=True)
        if stored is None:
            raise RuntimeError(f"agent memory was not stored: {final_id}")
        return stored

    def get_agent_memory(self, memory_id: str, *, full: bool = True) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM agent_memories WHERE id = ?", (memory_id.strip(),)).fetchone()
        if row is None:
            return None
        return self._agent_memory_row_to_dict(row, full=full)

    def list_agent_memories(
        self,
        *,
        kind: str | None = None,
        scope: str | None = None,
        matter_id: str | None = None,
        top_k: int = 50,
        full: bool = False,
    ) -> list[dict[str, Any]]:
        top_k = self._normalize_limit(top_k, max_value=200)
        clauses: list[str] = []
        params: list[Any] = []
        if kind:
            clauses.append("kind = ?")
            params.append(kind.strip())
        if scope:
            clauses.append("scope = ?")
            params.append(scope.strip())
        if matter_id is not None:
            clauses.append("matter_id = ?")
            params.append(matter_id.strip())
        sql = "SELECT * FROM agent_memories"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY importance DESC, updated_at DESC LIMIT ?"
        params.append(top_k)
        rows = self.conn.execute(sql, params).fetchall()
        return [self._agent_memory_row_to_dict(row, full=full) for row in rows]

    def search_agent_memories(
        self,
        query: str = "",
        *,
        kind: str | None = None,
        scope: str | None = None,
        matter_id: str | None = None,
        include_global: bool = True,
        top_k: int = 8,
        full: bool = False,
    ) -> list[dict[str, Any]]:
        top_k = self._normalize_limit(top_k, max_value=50)
        clean_query = query.strip()
        if not clean_query:
            clauses: list[str] = []
            params: list[Any] = []
            if kind:
                clauses.append("kind = ?")
                params.append(kind.strip())
            if scope:
                clauses.append("scope = ?")
                params.append(scope.strip())
            if matter_id is not None:
                if include_global and matter_id.strip():
                    clauses.append("(matter_id = ? OR matter_id = '')")
                    params.append(matter_id.strip())
                else:
                    clauses.append("matter_id = ?")
                    params.append(matter_id.strip())
            sql = "SELECT * FROM agent_memories"
            if clauses:
                sql += " WHERE " + " AND ".join(clauses)
            sql += " ORDER BY importance DESC, updated_at DESC LIMIT ?"
            params.append(top_k)
            rows = self.conn.execute(sql, params).fetchall()
            return [self._agent_memory_row_to_dict(row, full=full) for row in rows]

        clauses: list[str] = []
        params: list[Any] = []
        if kind:
            clauses.append("kind = ?")
            params.append(kind.strip())
        if scope:
            clauses.append("scope = ?")
            params.append(scope.strip())
        if matter_id is not None:
            if include_global and matter_id.strip():
                clauses.append("(matter_id = ? OR matter_id = '')")
                params.append(matter_id.strip())
            else:
                clauses.append("matter_id = ?")
                params.append(matter_id.strip())

        sql = "SELECT * FROM agent_memories"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        rows = self.conn.execute(sql, params).fetchall()
        tokens = self._query_tokens(clean_query)
        scored: list[tuple[float, dict[str, Any]]] = []
        for row in rows:
            memory = self._agent_memory_row_to_dict(row, full=True)
            haystack = " ".join(
                [
                    memory.get("title", ""),
                    memory.get("content", ""),
                    memory.get("kind", ""),
                    memory.get("scope", ""),
                    " ".join(memory.get("tags") or []),
                ]
            ).lower()
            score = 0.0
            importance = float(memory.get("importance") or 0.0)
            matched = False
            for token in tokens:
                if token in haystack:
                    score += 1.0
                    matched = True
            if clean_query.lower() in haystack:
                score += 4.0
                matched = True
            if matched:
                score += importance * 2.0
            elif memory.get("kind") in {"preference", "instruction", "style"}:
                score += importance
            else:
                continue
            if memory.get("matter_id") and matter_id and memory["matter_id"] == matter_id.strip():
                score += 2.0
            if score <= 0.0:
                continue
            scored.append((score, memory))
        scored.sort(key=lambda item: (item[0], str(item[1].get("updated_at") or "")), reverse=True)
        selected: list[dict[str, Any]] = []
        for score, memory in scored[:top_k]:
            item = dict(memory)
            item["score"] = score
            if not full:
                content = str(item.pop("content", "")).strip().replace("\n", " ")
                item["excerpt"] = content[:420] + ("..." if len(content) > 420 else "")
            selected.append(item)
        return selected

    def delete_agent_memory(self, memory_id: str) -> bool:
        cursor = self.conn.execute("DELETE FROM agent_memories WHERE id = ?", (memory_id.strip(),))
        self.commit()
        return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # Generated artifacts
    # ------------------------------------------------------------------

    def create_generated_artifact(
        self,
        *,
        title: str,
        content: str,
        format: str = "docx",
        session_id: str = "",
        matter_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        clean_title = re.sub(r"\s+", " ", title.strip())[:180] or "Documento Judicex"
        clean_content = str(content or "").strip()
        if not clean_content:
            raise ValueError("Contenuto documento vuoto.")
        clean_format = re.sub(r"[^a-z0-9]+", "", format.strip().lower()) or "docx"
        if clean_format not in {"docx", "pdf", "txt", "md"}:
            clean_format = "docx"
        now = self._now()
        artifact_id = f"artifact:{sha256_text(f'{session_id}:{matter_id}:{clean_title}:{clean_format}:{clean_content}:{now}')[:22]}"
        self.conn.execute(
            """
            INSERT INTO generated_artifacts (
                id, session_id, matter_id, title, format, content, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                artifact_id,
                session_id.strip(),
                matter_id.strip(),
                clean_title,
                clean_format,
                clean_content,
                self._dump_json(metadata or {}),
                now,
            ),
        )
        self.commit()
        stored = self.get_generated_artifact(artifact_id, full=True)
        if stored is None:
            raise RuntimeError(f"generated artifact was not stored: {artifact_id}")
        return stored

    def get_generated_artifact(self, artifact_id: str, *, full: bool = True) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM generated_artifacts WHERE id = ?", (artifact_id.strip(),)).fetchone()
        if row is None:
            return None
        return self._generated_artifact_row_to_dict(row, full=full)

    def list_generated_artifacts(
        self,
        *,
        session_id: str | None = None,
        matter_id: str | None = None,
        top_k: int = 30,
        full: bool = False,
    ) -> list[dict[str, Any]]:
        top_k = self._normalize_limit(top_k, max_value=100)
        clauses: list[str] = []
        params: list[Any] = []
        if session_id is not None:
            clauses.append("session_id = ?")
            params.append(session_id.strip())
        if matter_id is not None:
            clauses.append("matter_id = ?")
            params.append(matter_id.strip())
        sql = "SELECT * FROM generated_artifacts"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(top_k)
        rows = self.conn.execute(sql, params).fetchall()
        return [self._generated_artifact_row_to_dict(row, full=full) for row in rows]

    def delete_generated_artifact(self, artifact_id: str) -> bool:
        cursor = self.conn.execute("DELETE FROM generated_artifacts WHERE id = ?", (artifact_id.strip(),))
        self.commit()
        return cursor.rowcount > 0

    def upsert_matter_document(self, item: MatterDocument) -> None:
        now = self._now()
        content_sha256 = item.content_sha256 or sha256_text(item.content)
        stored_content = self._matter_encrypt(item.content)
        folder_id = str((item.metadata or {}).get("folder_id") or "").strip()
        self.conn.execute(
            """
            INSERT INTO matter_documents (
                id, matter_id, title, kind, folder_id, source_path, content_sha256,
                content, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                matter_id = excluded.matter_id,
                title = excluded.title,
                kind = excluded.kind,
                folder_id = excluded.folder_id,
                source_path = excluded.source_path,
                content_sha256 = excluded.content_sha256,
                content = excluded.content,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at
            """,
            (
                item.id,
                item.matter_id,
                item.title.strip(),
                item.kind.strip() or "document",
                folder_id,
                item.source_path,
                content_sha256,
                stored_content,
                self._dump_json(item.metadata),
                now,
                now,
            ),
        )
        self.conn.execute("UPDATE matters SET updated_at = ? WHERE id = ?", (now, item.matter_id))

    def get_matter_document(self, document_id: str, *, full: bool = True) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM matter_documents WHERE id = ?", (document_id,)).fetchone()
        if row is None:
            return None
        return self._matter_document_row_to_dict(row, full=full)

    def add_matter_document(
        self,
        matter_id: str,
        *,
        title: str,
        kind: str = "document",
        content: str,
        source_path: str = "",
        metadata: dict[str, Any] | None = None,
        document_id: str | None = None,
    ) -> dict[str, Any]:
        if self.get_matter(matter_id) is None:
            return {"error": f"matter not found: {matter_id}"}
        item = MatterDocument(
            id=document_id or make_matter_document_id(matter_id, title, content),
            matter_id=matter_id,
            title=title,
            kind=kind,
            source_path=source_path,
            content=content,
            content_sha256=sha256_text(content),
            metadata=metadata or {},
        )
        self.upsert_matter_document(item)
        facts = extract_matter_facts(item)
        self.replace_matter_facts(item.id, item.matter_id, facts)
        self.create_matter_document_version(item.id, reason="ingest")
        self.commit()
        stored = self.get_matter_document(item.id, full=False)
        return {
            "document": stored,
            "facts": [self._matter_fact_row_to_dict(row) for row in self._matter_fact_rows(document_id=item.id)],
            "facts_count": len(facts),
        }

    def add_matter_document_file(
        self,
        matter_id: str,
        file_path: str | Path,
        *,
        title: str | None = None,
        kind: str = "document",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        path = Path(file_path)
        ingestion = read_private_document_file(path)
        stored_path, binary_sha256 = self._store_matter_attachment(matter_id, path)
        document_metadata = dict(metadata or {})
        document_metadata.update(ingestion.metadata)
        document_metadata.setdefault("original_filename", path.name)
        document_metadata["stored_path"] = str(stored_path)
        document_metadata["binary_sha256"] = binary_sha256
        final_kind = kind.strip() or "document"
        if final_kind == "document" and ingestion.suggested_kind != "document":
            final_kind = ingestion.suggested_kind
        return self.add_matter_document(
            matter_id,
            title=title or path.stem,
            kind=final_kind,
            content=ingestion.content,
            source_path=str(stored_path),
            metadata=document_metadata,
        )

    def _store_matter_attachment(self, matter_id: str, path: Path) -> tuple[Path, str]:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        safe_matter_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", matter_id).strip("_") or "matter"
        suffix = path.suffix.lower()
        storage_dir = self.db_path.parent / f"{self.db_path.stem}_files" / "matters" / safe_matter_id
        storage_dir.mkdir(parents=True, exist_ok=True)
        target = storage_dir / f"{digest[:24]}{suffix}"
        if not target.exists():
            shutil.copy2(path, target)
        return target, digest

    def list_matter_folders(self, matter_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT f.*, COUNT(md.id) AS document_count
            FROM matter_folders f
            LEFT JOIN matter_documents md ON md.folder_id = f.id
            WHERE f.matter_id = ?
            GROUP BY f.id
            ORDER BY f.sort_order, lower(f.name)
            """,
            (matter_id,),
        ).fetchall()
        return [
            {
                "id": row["id"],
                "matter_id": row["matter_id"],
                "name": row["name"],
                "parent_id": row["parent_id"],
                "sort_order": row["sort_order"],
                "metadata": self._load_json(row["metadata_json"]),
                "document_count": int(row["document_count"] or 0),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def create_matter_folder(
        self,
        matter_id: str,
        name: str,
        *,
        parent_id: str = "",
        sort_order: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.get_matter(matter_id) is None:
            return {"error": f"matter not found: {matter_id}"}
        clean_name = name.strip()
        if not clean_name:
            return {"error": "folder name is required"}
        now = self._now()
        folder_id = f"folder:{matter_id}:{sha256_text(parent_id + ':' + clean_name)[:16]}"
        self.conn.execute(
            """
            INSERT INTO matter_folders (
                id, matter_id, name, parent_id, sort_order, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                parent_id = excluded.parent_id,
                sort_order = excluded.sort_order,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at
            """,
            (
                folder_id,
                matter_id,
                clean_name,
                parent_id.strip(),
                int(sort_order or 0),
                self._dump_json(metadata or {}),
                now,
                now,
            ),
        )
        self.conn.execute("UPDATE matters SET updated_at = ? WHERE id = ?", (now, matter_id))
        self.commit()
        folders = self.list_matter_folders(matter_id)
        return next((folder for folder in folders if folder["id"] == folder_id), folders[-1] if folders else {})

    def update_matter_folder(
        self,
        folder_id: str,
        *,
        name: str | None = None,
        parent_id: str | None = None,
        sort_order: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM matter_folders WHERE id = ?", (folder_id,)).fetchone()
        if row is None:
            return None
        current_meta = self._load_json(row["metadata_json"])
        if metadata:
            current_meta.update(metadata)
        now = self._now()
        self.conn.execute(
            """
            UPDATE matter_folders
            SET name = ?, parent_id = ?, sort_order = ?, metadata_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                (name if name is not None else row["name"]).strip(),
                (parent_id if parent_id is not None else row["parent_id"]).strip(),
                int(sort_order if sort_order is not None else row["sort_order"]),
                self._dump_json(current_meta),
                now,
                folder_id,
            ),
        )
        self.conn.execute("UPDATE matters SET updated_at = ? WHERE id = ?", (now, row["matter_id"]))
        self.commit()
        return next((folder for folder in self.list_matter_folders(row["matter_id"]) if folder["id"] == folder_id), None)

    def assign_matter_document_folder(self, document_id: str, folder_id: str = "") -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM matter_documents WHERE id = ?", (document_id,)).fetchone()
        if row is None:
            return None
        folder_id = folder_id.strip()
        if folder_id:
            folder = self.conn.execute("SELECT * FROM matter_folders WHERE id = ?", (folder_id,)).fetchone()
            if folder is None or folder["matter_id"] != row["matter_id"]:
                return {"error": f"folder not found for matter: {folder_id}"}
        metadata = self._load_json(row["metadata_json"])
        if folder_id:
            metadata["folder_id"] = folder_id
        else:
            metadata.pop("folder_id", None)
        now = self._now()
        self.conn.execute(
            "UPDATE matter_documents SET folder_id = ?, metadata_json = ?, updated_at = ? WHERE id = ?",
            (folder_id, self._dump_json(metadata), now, document_id),
        )
        self.conn.execute("UPDATE matters SET updated_at = ? WHERE id = ?", (now, row["matter_id"]))
        self.commit()
        return self.get_matter_document(document_id, full=False)

    def list_matter_document_versions(self, document_id: str, *, full: bool = False) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM matter_document_versions WHERE document_id = ? ORDER BY version_number DESC",
            (document_id,),
        ).fetchall()
        return [self._matter_document_version_row_to_dict(row, full=full) for row in rows]

    def create_matter_document_version(
        self,
        document_id: str,
        *,
        reason: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM matter_documents WHERE id = ?", (document_id,)).fetchone()
        if row is None:
            return None
        content = self._matter_decrypt(row["content"])
        current = self.conn.execute(
            "SELECT COALESCE(MAX(version_number), 0) FROM matter_document_versions WHERE document_id = ?",
            (document_id,),
        ).fetchone()[0]
        version_number = int(current or 0) + 1
        version_id = f"mdv:{document_id}:{version_number:04d}"
        now = self._now()
        self.conn.execute(
            """
            INSERT INTO matter_document_versions (
                id, document_id, matter_id, version_number, title, kind, folder_id,
                content_sha256, content, reason, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                version_id,
                document_id,
                row["matter_id"],
                version_number,
                row["title"],
                row["kind"],
                row["folder_id"] if "folder_id" in row.keys() else "",
                row["content_sha256"],
                self._matter_encrypt(content),
                reason.strip(),
                self._dump_json(metadata or {}),
                now,
            ),
        )
        version_row = self.conn.execute(
            "SELECT * FROM matter_document_versions WHERE id = ?",
            (version_id,),
        ).fetchone()
        return self._matter_document_version_row_to_dict(version_row, full=False) if version_row else None

    def _matter_document_version_row_to_dict(self, row: sqlite3.Row, *, full: bool = False) -> dict[str, Any]:
        payload = {
            "id": row["id"],
            "document_id": row["document_id"],
            "matter_id": row["matter_id"],
            "version_number": row["version_number"],
            "title": row["title"],
            "kind": row["kind"],
            "folder_id": row["folder_id"],
            "content_sha256": row["content_sha256"],
            "reason": row["reason"],
            "metadata": self._load_json(row["metadata_json"]),
            "created_at": row["created_at"],
        }
        content = self._matter_decrypt(row["content"])
        if full:
            payload["content"] = content
        else:
            excerpt = content.strip().replace("\n", " ")
            payload["excerpt"] = excerpt[:420] + ("..." if len(excerpt) > 420 else "")
        return payload

    def update_matter_document(
        self,
        document_id: str,
        *,
        title: str | None = None,
        kind: str | None = None,
        content: str | None = None,
        folder_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        reason: str = "update",
    ) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM matter_documents WHERE id = ?", (document_id,)).fetchone()
        if row is None:
            return None
        current = self._matter_document_row_to_dict(row, full=True)
        if not self.list_matter_document_versions(document_id):
            self.create_matter_document_version(document_id, reason="snapshot")
        new_title = (title if title is not None else current["title"]).strip() or current["title"]
        new_kind = (kind if kind is not None else current["kind"]).strip() or "document"
        new_content = current["content"] if content is None else str(content)
        new_folder_id = current.get("folder_id", "") if folder_id is None else folder_id.strip()
        if new_folder_id:
            folder = self.conn.execute("SELECT * FROM matter_folders WHERE id = ?", (new_folder_id,)).fetchone()
            if folder is None or folder["matter_id"] != current["matter_id"]:
                return {"error": f"folder not found for matter: {new_folder_id}"}
        new_metadata = dict(current.get("metadata") or {})
        if metadata:
            new_metadata.update(metadata)
        if new_folder_id:
            new_metadata["folder_id"] = new_folder_id
        else:
            new_metadata.pop("folder_id", None)
        now = self._now()
        new_sha = sha256_text(new_content)
        self.conn.execute(
            """
            UPDATE matter_documents
            SET title = ?, kind = ?, folder_id = ?, content_sha256 = ?, content = ?,
                metadata_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                new_title,
                new_kind,
                new_folder_id,
                new_sha,
                self._matter_encrypt(new_content),
                self._dump_json(new_metadata),
                now,
                document_id,
            ),
        )
        if new_content != current["content"]:
            item = MatterDocument(
                id=document_id,
                matter_id=current["matter_id"],
                title=new_title,
                kind=new_kind,
                source_path=current.get("source_path", ""),
                content=new_content,
                content_sha256=new_sha,
                metadata=new_metadata,
            )
            self.replace_matter_facts(document_id, current["matter_id"], extract_matter_facts(item))
        self.conn.execute("UPDATE matters SET updated_at = ? WHERE id = ?", (now, current["matter_id"]))
        self.create_matter_document_version(document_id, reason=reason)
        self.commit()
        return self.get_matter_document(document_id, full=True)

    def list_document_edits(self, document_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM document_edits WHERE document_id = ? ORDER BY created_at DESC",
            (document_id,),
        ).fetchall()
        return [self._document_edit_row_to_dict(row, full=False) for row in rows]

    def create_document_edit(
        self,
        document_id: str,
        revised_content: str,
        *,
        title: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        document = self.get_matter_document(document_id, full=True)
        if document is None:
            return None
        original = str(document.get("content") or "")
        revised = str(revised_content)
        diff = list(
            difflib.unified_diff(
                original.splitlines(),
                revised.splitlines(),
                fromfile="originale",
                tofile="revisionato",
                lineterm="",
            )
        )
        now = self._now()
        edit_id = f"edit:{document_id}:{sha256_text(revised + now)[:16]}"
        self.conn.execute(
            """
            INSERT INTO document_edits (
                id, matter_id, document_id, title, original_content, revised_content,
                diff_json, status, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                edit_id,
                document["matter_id"],
                document_id,
                title.strip() or f"Revisione {document['title']}",
                self._matter_encrypt(original),
                self._matter_encrypt(revised),
                json.dumps(diff, ensure_ascii=False),
                "proposed",
                self._dump_json(metadata or {}),
                now,
            ),
        )
        self.commit()
        row = self.conn.execute("SELECT * FROM document_edits WHERE id = ?", (edit_id,)).fetchone()
        return self._document_edit_row_to_dict(row, full=True) if row else None

    def get_document_edit(self, edit_id: str, *, full: bool = True) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM document_edits WHERE id = ?", (edit_id,)).fetchone()
        return self._document_edit_row_to_dict(row, full=full) if row else None

    def apply_document_edit(self, edit_id: str) -> dict[str, Any] | None:
        edit = self.get_document_edit(edit_id, full=True)
        if edit is None:
            return None
        if edit["status"] == "applied":
            return edit
        updated = self.update_matter_document(
            edit["document_id"],
            content=edit["revised_content"],
            reason=f"edit:{edit_id}",
        )
        now = self._now()
        self.conn.execute(
            "UPDATE document_edits SET status = 'applied', applied_at = ? WHERE id = ?",
            (now, edit_id),
        )
        self.commit()
        return {"edit": self.get_document_edit(edit_id, full=True), "document": updated}

    def _document_edit_row_to_dict(self, row: sqlite3.Row, *, full: bool = False) -> dict[str, Any]:
        payload = {
            "id": row["id"],
            "matter_id": row["matter_id"],
            "document_id": row["document_id"],
            "title": row["title"],
            "diff": json.loads(row["diff_json"] or "[]"),
            "status": row["status"],
            "metadata": self._load_json(row["metadata_json"]),
            "created_at": row["created_at"],
            "applied_at": row["applied_at"],
        }
        original = self._matter_decrypt(row["original_content"])
        revised = self._matter_decrypt(row["revised_content"])
        if full:
            payload["original_content"] = original
            payload["revised_content"] = revised
        else:
            payload["excerpt"] = revised.strip().replace("\n", " ")[:420]
        return payload

    def create_tabular_review(
        self,
        matter_id: str,
        *,
        title: str = "",
        query: str = "",
    ) -> dict[str, Any]:
        matter = self.get_matter(matter_id)
        if matter is None:
            return {"error": f"matter not found: {matter_id}"}
        documents = self.search_matter_documents(query, matter_id=matter_id, top_k=50)
        if query and not documents:
            documents = self.search_matter_documents("", matter_id=matter_id, top_k=50)
        facts = self.search_matter_facts(query, matter_id=matter_id, top_k=200)
        if query and not facts:
            facts = self.search_matter_facts("", matter_id=matter_id, top_k=200)
        facts_by_doc: dict[str, list[dict[str, Any]]] = {}
        for fact in facts:
            facts_by_doc.setdefault(str(fact.get("document_id") or ""), []).append(fact)

        def join_facts(document_id: str, fact_type: str) -> str:
            values = []
            for fact in facts_by_doc.get(document_id, []):
                if fact.get("fact_type") != fact_type:
                    continue
                value = str(fact.get("value") or fact.get("date_value") or fact.get("text") or "").strip()
                label = str(fact.get("label") or "").strip()
                values.append(f"{label}: {value}" if label and value else value or label)
            return "; ".join(dict.fromkeys(item for item in values if item))

        columns = [
            {"key": "document", "label": "Documento"},
            {"key": "kind", "label": "Tipo"},
            {"key": "parties", "label": "Parti"},
            {"key": "amounts", "label": "Importi"},
            {"key": "dates", "label": "Date"},
            {"key": "deadlines", "label": "Scadenze"},
            {"key": "excerpt", "label": "Estratto"},
        ]
        rows = [
            {
                "document_id": doc["id"],
                "document": doc.get("title", ""),
                "kind": doc.get("kind", ""),
                "parties": join_facts(doc["id"], "party"),
                "amounts": join_facts(doc["id"], "amount"),
                "dates": join_facts(doc["id"], "date"),
                "deadlines": join_facts(doc["id"], "deadline"),
                "excerpt": doc.get("excerpt", ""),
            }
            for doc in documents
        ]
        now = self._now()
        review_title = title.strip() or f"Revisione tabellare - {matter['title']}"
        review_id = f"review:{matter_id}:{sha256_text(review_title + query + now)[:16]}"
        self.conn.execute(
            """
            INSERT INTO tabular_reviews (
                id, matter_id, title, query, columns_json, rows_json, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                review_id,
                matter_id,
                review_title,
                query.strip(),
                json.dumps(columns, ensure_ascii=False),
                json.dumps(rows, ensure_ascii=False),
                self._dump_json({"document_count": len(documents), "fact_count": len(facts)}),
                now,
                now,
            ),
        )
        self.conn.execute("UPDATE matters SET updated_at = ? WHERE id = ?", (now, matter_id))
        self.commit()
        return self.get_tabular_review(review_id) or {"error": f"review not stored: {review_id}"}

    def list_tabular_reviews(self, matter_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM tabular_reviews WHERE matter_id = ? ORDER BY updated_at DESC",
            (matter_id,),
        ).fetchall()
        return [self._tabular_review_row_to_dict(row, full=False) for row in rows]

    def get_tabular_review(self, review_id: str, *, full: bool = True) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM tabular_reviews WHERE id = ?", (review_id,)).fetchone()
        return self._tabular_review_row_to_dict(row, full=full) if row else None

    def _tabular_review_row_to_dict(self, row: sqlite3.Row, *, full: bool = True) -> dict[str, Any]:
        payload = {
            "id": row["id"],
            "matter_id": row["matter_id"],
            "title": row["title"],
            "query": row["query"],
            "columns": json.loads(row["columns_json"] or "[]"),
            "metadata": self._load_json(row["metadata_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        rows = json.loads(row["rows_json"] or "[]")
        if full:
            payload["rows"] = rows
        else:
            payload["row_count"] = len(rows)
        return payload

    def update_tabular_review(
        self,
        review_id: str,
        *,
        rows: list[dict[str, Any]] | None = None,
        columns: list[dict[str, Any]] | None = None,
        title: str | None = None,
    ) -> dict[str, Any] | None:
        review = self.get_tabular_review(review_id, full=True)
        if review is None:
            return None
        next_rows = rows if rows is not None else review.get("rows", [])
        next_columns = columns if columns is not None else review.get("columns", [])
        now = self._now()
        self.conn.execute(
            """
            UPDATE tabular_reviews
            SET title = ?, columns_json = ?, rows_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                (title if title is not None else review["title"]).strip() or review["title"],
                json.dumps(next_columns, ensure_ascii=False),
                json.dumps(next_rows, ensure_ascii=False),
                now,
                review_id,
            ),
        )
        self.commit()
        return self.get_tabular_review(review_id, full=True)

    def update_tabular_review_cell(self, review_id: str, row_index: int, key: str, value: Any) -> dict[str, Any] | None:
        review = self.get_tabular_review(review_id, full=True)
        if review is None:
            return None
        rows = list(review.get("rows") or [])
        if row_index < 0 or row_index >= len(rows):
            return {"error": f"row index out of range: {row_index}"}
        rows[row_index] = {**rows[row_index], key: value}
        return self.update_tabular_review(review_id, rows=rows)

    def list_tabular_review_views(self, review_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM tabular_review_views WHERE review_id = ? ORDER BY updated_at DESC, lower(name)",
            (review_id,),
        ).fetchall()
        return [self._tabular_review_view_row_to_dict(row) for row in rows]

    def save_tabular_review_view(
        self,
        review_id: str,
        *,
        name: str,
        filter_text: str = "",
        sort_key: str = "",
        sort_dir: str = "asc",
        columns: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        review = self.get_tabular_review(review_id, full=True)
        if review is None:
            return None
        clean_name = name.strip() or "Vista"
        now = self._now()
        view_id = f"view:{review_id}:{sha256_text(clean_name)[:12]}"
        self.conn.execute(
            """
            INSERT INTO tabular_review_views (
                id, review_id, matter_id, name, filter_text, sort_key, sort_dir,
                columns_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                filter_text = excluded.filter_text,
                sort_key = excluded.sort_key,
                sort_dir = excluded.sort_dir,
                columns_json = excluded.columns_json,
                updated_at = excluded.updated_at
            """,
            (
                view_id,
                review_id,
                review["matter_id"],
                clean_name,
                filter_text.strip(),
                sort_key.strip(),
                "desc" if sort_dir == "desc" else "asc",
                json.dumps(columns if columns is not None else review.get("columns", []), ensure_ascii=False),
                now,
                now,
            ),
        )
        self.commit()
        row = self.conn.execute("SELECT * FROM tabular_review_views WHERE id = ?", (view_id,)).fetchone()
        return self._tabular_review_view_row_to_dict(row) if row else None

    def _tabular_review_view_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "review_id": row["review_id"],
            "matter_id": row["matter_id"],
            "name": row["name"],
            "filter_text": row["filter_text"],
            "sort_key": row["sort_key"],
            "sort_dir": row["sort_dir"],
            "columns": json.loads(row["columns_json"] or "[]"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def get_matter_document_version(self, version_id: str, *, full: bool = True) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM matter_document_versions WHERE id = ?", (version_id,)).fetchone()
        return self._matter_document_version_row_to_dict(row, full=full) if row else None

    def restore_matter_document_version(self, document_id: str, version_id: str) -> dict[str, Any] | None:
        version = self.get_matter_document_version(version_id, full=True)
        if version is None or version["document_id"] != document_id:
            return None
        return self.update_matter_document(
            document_id,
            title=version["title"],
            kind=version["kind"],
            content=version.get("content", ""),
            folder_id=version.get("folder_id", ""),
            reason=f"restore:{version_id}",
        )

    def compare_matter_document_versions(
        self,
        document_id: str,
        left_version_id: str,
        right_version_id: str = "",
    ) -> dict[str, Any] | None:
        left = self.get_matter_document_version(left_version_id, full=True)
        if left is None or left["document_id"] != document_id:
            return None
        if right_version_id:
            right = self.get_matter_document_version(right_version_id, full=True)
            if right is None or right["document_id"] != document_id:
                return None
            right_label = f"v{right['version_number']}"
            right_content = right.get("content", "")
        else:
            current = self.get_matter_document(document_id, full=True)
            if current is None:
                return None
            right = {"id": "current", "version_number": "current"}
            right_label = "corrente"
            right_content = current.get("content", "")
        diff = list(
            difflib.unified_diff(
                str(left.get("content", "")).splitlines(),
                str(right_content).splitlines(),
                fromfile=f"v{left['version_number']}",
                tofile=right_label,
                lineterm="",
            )
        )
        return {"left": left, "right": right, "diff": diff}

    def list_document_annotations(self, document_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM document_annotations WHERE document_id = ? ORDER BY page_number, created_at",
            (document_id,),
        ).fetchall()
        return [self._document_annotation_row_to_dict(row) for row in rows]

    def add_document_annotation(
        self,
        document_id: str,
        *,
        page_number: int = 1,
        x: float = 0,
        y: float = 0,
        width: float = 0,
        height: float = 0,
        color: str = "#facc15",
        note: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        document = self.get_matter_document(document_id, full=False)
        if document is None:
            return None
        now = self._now()
        annotation_id = f"ann:{document_id}:{sha256_text(note + str(page_number) + now)[:16]}"
        self.conn.execute(
            """
            INSERT INTO document_annotations (
                id, matter_id, document_id, page_number, x, y, width, height,
                color, note, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                annotation_id,
                document["matter_id"],
                document_id,
                max(1, int(page_number or 1)),
                float(x or 0),
                float(y or 0),
                float(width or 0),
                float(height or 0),
                color.strip() or "#facc15",
                note.strip(),
                self._dump_json(metadata or {}),
                now,
                now,
            ),
        )
        self.commit()
        row = self.conn.execute("SELECT * FROM document_annotations WHERE id = ?", (annotation_id,)).fetchone()
        return self._document_annotation_row_to_dict(row) if row else None

    def update_document_annotation(self, annotation_id: str, **updates: Any) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM document_annotations WHERE id = ?", (annotation_id,)).fetchone()
        if row is None:
            return None
        metadata = self._load_json(row["metadata_json"])
        if isinstance(updates.get("metadata"), dict):
            metadata.update(updates["metadata"])
        now = self._now()
        self.conn.execute(
            """
            UPDATE document_annotations
            SET page_number = ?, x = ?, y = ?, width = ?, height = ?, color = ?,
                note = ?, metadata_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                int(updates.get("page_number", row["page_number"]) or 1),
                float(updates.get("x", row["x"]) or 0),
                float(updates.get("y", row["y"]) or 0),
                float(updates.get("width", row["width"]) or 0),
                float(updates.get("height", row["height"]) or 0),
                str(updates.get("color", row["color"])).strip() or "#facc15",
                str(updates.get("note", row["note"])).strip(),
                self._dump_json(metadata),
                now,
                annotation_id,
            ),
        )
        self.commit()
        row = self.conn.execute("SELECT * FROM document_annotations WHERE id = ?", (annotation_id,)).fetchone()
        return self._document_annotation_row_to_dict(row) if row else None

    def delete_document_annotation(self, annotation_id: str) -> bool:
        cur = self.conn.execute("DELETE FROM document_annotations WHERE id = ?", (annotation_id,))
        self.commit()
        return cur.rowcount > 0

    def _document_annotation_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "matter_id": row["matter_id"],
            "document_id": row["document_id"],
            "page_number": row["page_number"],
            "x": row["x"],
            "y": row["y"],
            "width": row["width"],
            "height": row["height"],
            "color": row["color"],
            "note": row["note"],
            "metadata": self._load_json(row["metadata_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list_document_comments(self, document_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM document_comments WHERE document_id = ? ORDER BY created_at DESC",
            (document_id,),
        ).fetchall()
        return [self._document_comment_row_to_dict(row) for row in rows]

    def add_document_comment(
        self,
        document_id: str,
        *,
        body: str,
        anchor: str = "",
        status: str = "open",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        document = self.get_matter_document(document_id, full=False)
        if document is None:
            return None
        clean_body = body.strip()
        if not clean_body:
            return {"error": "comment body is required"}
        now = self._now()
        comment_id = f"comment:{document_id}:{sha256_text(clean_body + now)[:16]}"
        self.conn.execute(
            """
            INSERT INTO document_comments (
                id, matter_id, document_id, anchor, body, status, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                comment_id,
                document["matter_id"],
                document_id,
                anchor.strip(),
                clean_body,
                status.strip() or "open",
                self._dump_json(metadata or {}),
                now,
                now,
            ),
        )
        self.commit()
        row = self.conn.execute("SELECT * FROM document_comments WHERE id = ?", (comment_id,)).fetchone()
        return self._document_comment_row_to_dict(row) if row else None

    def update_document_comment(self, comment_id: str, *, body: str | None = None, status: str | None = None) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM document_comments WHERE id = ?", (comment_id,)).fetchone()
        if row is None:
            return None
        now = self._now()
        self.conn.execute(
            "UPDATE document_comments SET body = ?, status = ?, updated_at = ? WHERE id = ?",
            (
                str(body if body is not None else row["body"]).strip(),
                str(status if status is not None else row["status"]).strip() or "open",
                now,
                comment_id,
            ),
        )
        self.commit()
        row = self.conn.execute("SELECT * FROM document_comments WHERE id = ?", (comment_id,)).fetchone()
        return self._document_comment_row_to_dict(row) if row else None

    def _document_comment_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "matter_id": row["matter_id"],
            "document_id": row["document_id"],
            "anchor": row["anchor"],
            "body": row["body"],
            "status": row["status"],
            "metadata": self._load_json(row["metadata_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list_custom_draft_templates(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT id, name, title, required_params_json, metadata_json, created_at, updated_at FROM custom_draft_templates ORDER BY updated_at DESC, lower(title)"
        ).fetchall()
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "title": row["title"],
                "required_params": json.loads(row["required_params_json"] or "[]"),
                "metadata": self._load_json(row["metadata_json"]),
                "source": "sqlite",
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def get_custom_draft_template(self, template_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM custom_draft_templates WHERE id = ? OR name = ?", (template_id, template_id)).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "name": row["name"],
            "title": row["title"],
            "body": row["body"],
            "required_params": json.loads(row["required_params_json"] or "[]"),
            "metadata": self._load_json(row["metadata_json"]),
            "source": "sqlite",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def save_custom_draft_template(
        self,
        *,
        name: str,
        title: str,
        body: str,
        required_params: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        clean_name = self._slugify(name or title)
        template_id = f"tpl:{clean_name}"
        now = self._now()
        self.conn.execute(
            """
            INSERT INTO custom_draft_templates (
                id, name, title, body, required_params_json, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                title = excluded.title,
                body = excluded.body,
                required_params_json = excluded.required_params_json,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at
            """,
            (
                template_id,
                clean_name,
                title.strip() or clean_name,
                body,
                json.dumps([str(item).strip() for item in (required_params or []) if str(item).strip()], ensure_ascii=False),
                self._dump_json(metadata or {}),
                now,
                now,
            ),
        )
        self.commit()
        stored = self.get_custom_draft_template(template_id)
        if stored is None:
            raise RuntimeError(f"custom template not stored: {template_id}")
        return stored

    def replace_matter_facts(
        self,
        document_id: str,
        matter_id: str,
        facts: list[MatterFact],
    ) -> None:
        self.conn.execute(
            "DELETE FROM matter_facts WHERE matter_id = ? AND document_id = ?",
            (matter_id, document_id),
        )
        for fact in facts:
            self.upsert_matter_fact(fact)

    def upsert_matter_fact(self, item: MatterFact) -> None:
        self.conn.execute(
            """
            INSERT INTO matter_facts (
                id, matter_id, document_id, fact_type, label, text, value, unit,
                date_value, confidence, source_quote, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                matter_id = excluded.matter_id,
                document_id = excluded.document_id,
                fact_type = excluded.fact_type,
                label = excluded.label,
                text = excluded.text,
                value = excluded.value,
                unit = excluded.unit,
                date_value = excluded.date_value,
                confidence = excluded.confidence,
                source_quote = excluded.source_quote,
                metadata_json = excluded.metadata_json
            """,
            (
                item.id,
                item.matter_id,
                item.document_id,
                item.fact_type,
                item.label,
                item.text,
                item.value,
                item.unit,
                item.date_value,
                float(item.confidence),
                item.source_quote,
                self._dump_json(item.metadata),
                self._now(),
            ),
        )

    def _matter_fact_rows(
        self,
        *,
        matter_id: str | None = None,
        document_id: str | None = None,
        fact_type: str | None = None,
        limit: int = 100,
    ) -> list[sqlite3.Row]:
        sql = "SELECT * FROM matter_facts"
        params: list[Any] = []
        clauses: list[str] = []
        if matter_id:
            clauses.append("matter_id = ?")
            params.append(matter_id)
        if document_id:
            clauses.append("document_id = ?")
            params.append(document_id)
        if fact_type:
            clauses.append("fact_type = ?")
            params.append(fact_type)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY date_value, label, value LIMIT ?"
        params.append(self._normalize_limit(limit, max_value=500))
        return self.conn.execute(sql, params).fetchall()

    def search_matter_documents(
        self,
        query: str,
        *,
        matter_id: str | None = None,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        top_k = self._normalize_limit(top_k, max_value=50)
        query = query.strip()
        if not query:
            sql = "SELECT * FROM matter_documents"
            params: list[Any] = []
            if matter_id:
                sql += " WHERE matter_id = ?"
                params.append(matter_id)
            sql += " ORDER BY updated_at DESC, title LIMIT ?"
            params.append(top_k)
            rows = self.conn.execute(sql, params).fetchall()
            return [self._matter_document_row_to_dict(row) for row in rows]

        crypto_enabled = self._matter_crypto().enabled
        fts_query = self._fts_query(query)
        # When at-rest encryption is on, the FTS index sees ciphertext and is
        # therefore useless for lexical recall on the document body. Fall
        # back to a Python-side decrypt+match scan so search still works.
        if self.fts_enabled and fts_query and not crypto_enabled:
            sql = (
                "SELECT md.*, bm25(matter_documents_fts, 1.0, 0.5, 2.5, 1.2, 1.0) AS score "
                "FROM matter_documents_fts JOIN matter_documents md ON matter_documents_fts.rowid = md.rowid "
                "WHERE matter_documents_fts MATCH ?"
            )
            params = [fts_query]
            if matter_id:
                sql += " AND md.matter_id = ?"
                params.append(matter_id)
            sql += " ORDER BY score LIMIT ?"
            params.append(top_k)
            rows = self.conn.execute(sql, params).fetchall()
            return [self._matter_document_row_to_dict(row) for row in rows]

        like = f"%{query.lower()}%"
        if crypto_enabled:
            # Title/kind are not encrypted, so let SQL filter on those first
            # to keep the candidate set small; the body is then decrypted in
            # Python and matched in-memory.
            sql = "SELECT * FROM matter_documents"
            params: list[Any] = []
            if matter_id:
                sql += " WHERE matter_id = ?"
                params.append(matter_id)
            rows = self.conn.execute(sql, params).fetchall()
            scored: list[tuple[int, dict[str, Any]]] = []
            for row in rows:
                title_match = query.lower() in (row["title"] or "").lower()
                kind_match = query.lower() in (row["kind"] or "").lower()
                try:
                    plaintext = self._matter_decrypt(row["content"])
                except Exception:
                    plaintext = row["content"]
                content_match = query.lower() in plaintext.lower()
                if not (title_match or kind_match or content_match):
                    continue
                score = 0 if title_match else (1 if kind_match else 2)
                scored.append((score, self._matter_document_row_to_dict(row)))
            scored.sort(key=lambda pair: pair[0])
            return [entry[1] for entry in scored[:top_k]]

        sql = (
            "SELECT *, CASE WHEN lower(title) LIKE ? THEN 0 ELSE 1 END AS score "
            "FROM matter_documents WHERE (lower(title) LIKE ? OR lower(kind) LIKE ? OR lower(content) LIKE ?)"
        )
        params = [like, like, like, like]
        if matter_id:
            sql += " AND matter_id = ?"
            params.append(matter_id)
        sql += " ORDER BY score, updated_at DESC LIMIT ?"
        params.append(top_k)
        rows = self.conn.execute(sql, params).fetchall()
        return [self._matter_document_row_to_dict(row) for row in rows]

    def search_matter_facts(
        self,
        query: str,
        *,
        matter_id: str | None = None,
        fact_type: str | None = None,
        top_k: int = 20,
    ) -> list[dict[str, Any]]:
        top_k = self._normalize_limit(top_k, max_value=100)
        query = query.strip()
        if not query:
            rows = self._matter_fact_rows(matter_id=matter_id, fact_type=fact_type, limit=top_k)
            return [self._matter_fact_row_to_dict(row) for row in rows]

        fts_query = self._fts_query(query)
        if self.fts_enabled and fts_query:
            sql = (
                "SELECT mf.*, bm25(matter_facts_fts, 1.0, 0.5, 0.5, 1.0, 2.0, 2.5, 2.5, 1.2, 1.8, 1.0) AS score "
                "FROM matter_facts_fts JOIN matter_facts mf ON matter_facts_fts.rowid = mf.rowid "
                "WHERE matter_facts_fts MATCH ?"
            )
            params = [fts_query]
            if matter_id:
                sql += " AND mf.matter_id = ?"
                params.append(matter_id)
            if fact_type:
                sql += " AND mf.fact_type = ?"
                params.append(fact_type)
            sql += " ORDER BY score, mf.confidence DESC LIMIT ?"
            params.append(top_k)
            rows = self.conn.execute(sql, params).fetchall()
            return [self._matter_fact_row_to_dict(row) for row in rows]

        like = f"%{query.lower()}%"
        sql = (
            "SELECT *, CASE WHEN lower(label) LIKE ? OR lower(value) LIKE ? THEN 0 ELSE 1 END AS score "
            "FROM matter_facts WHERE ("
            "lower(label) LIKE ? OR lower(text) LIKE ? OR lower(value) LIKE ? OR "
            "lower(unit) LIKE ? OR lower(date_value) LIKE ? OR lower(source_quote) LIKE ?"
            ")"
        )
        params = [like, like, like, like, like, like, like, like]
        if matter_id:
            sql += " AND matter_id = ?"
            params.append(matter_id)
        if fact_type:
            sql += " AND fact_type = ?"
            params.append(fact_type)
        sql += " ORDER BY score, confidence DESC LIMIT ?"
        params.append(top_k)
        rows = self.conn.execute(sql, params).fetchall()
        return [self._matter_fact_row_to_dict(row) for row in rows]

    def build_matter_context(
        self,
        matter_id: str,
        query: str = "",
        *,
        document_k: int = 6,
        fact_k: int = 20,
    ) -> dict[str, Any]:
        matter = self.get_matter(matter_id)
        if matter is None:
            return {"error": f"matter not found: {matter_id}"}

        documents = self.search_matter_documents(query, matter_id=matter_id, top_k=document_k)
        facts = self.search_matter_facts(query, matter_id=matter_id, top_k=fact_k)
        if query and not facts:
            facts = self.search_matter_facts("", matter_id=matter_id, top_k=fact_k)

        timeline = self.search_matter_facts("", matter_id=matter_id, fact_type="date", top_k=100)
        timeline = sorted(timeline, key=lambda item: item.get("date_value") or "9999-99-99")
        parties = self.search_matter_facts("", matter_id=matter_id, fact_type="party", top_k=50)
        amounts = self.search_matter_facts("", matter_id=matter_id, fact_type="amount", top_k=50)
        deadlines = self.search_matter_facts("", matter_id=matter_id, fact_type="deadline", top_k=50)

        return {
            "matter": matter,
            "query": query,
            "documents": documents,
            "facts": facts,
            "timeline": timeline,
            "parties": parties,
            "amounts": amounts,
            "deadlines": deadlines,
            "coverage": {
                "documents": len(documents),
                "facts": len(facts),
                "timeline_events": len(timeline),
                "parties": len(parties),
                "amounts": len(amounts),
                "deadlines": len(deadlines),
            },
        }

    def analyze_matter(
        self,
        matter_id: str,
        thesis: str,
        *,
        workflow_pack: str | Path | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        matter = self.get_matter(matter_id)
        if matter is None:
            return {"status": "error", "error": f"matter not found: {matter_id}", "thesis": thesis}

        context = self.build_matter_context(
            matter_id,
            query=thesis,
            document_k=50,
            fact_k=100,
        )
        all_documents = self.search_matter_documents("", matter_id=matter_id, top_k=50)
        all_facts = self.search_matter_facts("", matter_id=matter_id, top_k=200)
        context["documents"] = self._unique_payloads_by_id(context.get("documents", []) + all_documents)
        context["facts"] = self._unique_payloads_by_id(context.get("facts", []) + all_facts)
        context["coverage"] = {
            **(context.get("coverage") or {}),
            "documents_total": len(all_documents),
            "facts_total": len(all_facts),
        }
        return analyze_matter_context(context, thesis, workflow_pack=self._resolve_workflow_pack(workflow_pack))

    def list_workflow_packs(self) -> list[dict[str, Any]]:
        packs: list[dict[str, Any]] = []
        for pack in list_builtin_workflow_packs():
            packs.append({**pack, "source": "builtin"})
        packs.extend(self.list_custom_workflow_packs())
        return packs

    def list_custom_workflow_packs(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT id, label, version, metadata_json, created_at, updated_at FROM custom_workflow_packs ORDER BY updated_at DESC, lower(label)"
        ).fetchall()
        return [
            {
                "id": row["id"],
                "version": row["version"],
                "label": row["label"],
                "source": "sqlite",
                "metadata": self._load_json(row["metadata_json"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def get_custom_workflow_pack(self, pack_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM custom_workflow_packs WHERE id = ?",
            (pack_id,),
        ).fetchone()
        if row is None:
            return None
        definition = json.loads(row["definition_json"])
        return {
            "id": row["id"],
            "label": row["label"],
            "version": row["version"],
            "source": "sqlite",
            "definition": definition,
            "metadata": self._load_json(row["metadata_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def create_custom_workflow_pack(
        self,
        *,
        label: str,
        requirements: list[dict[str, Any]],
        pack_id: str = "",
        profile_label: str = "",
        match_terms: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        clean_label = label.strip()
        if not clean_label:
            return {"error": "workflow label is required"}
        clean_requirements = self._normalize_workflow_requirements(requirements)
        if not clean_requirements:
            return {"error": "workflow must contain at least one requirement"}
        safe_id = pack_id.strip() or f"custom:{self._slugify(clean_label)}"
        if not safe_id.startswith("custom:"):
            safe_id = f"custom:{self._slugify(safe_id)}"
        profile_id = f"{self._slugify(clean_label)}_profile"
        definition = {
            "schema_version": "1.0",
            "id": safe_id,
            "version": self._now()[:10],
            "label": clean_label,
            "default_profile_id": profile_id,
            "source": "sqlite",
            "profiles": [
                {
                    "id": profile_id,
                    "label": profile_label.strip() or clean_label,
                    "match_terms": self._clean_terms(match_terms or [clean_label]),
                    "requirements": clean_requirements,
                }
            ],
        }
        try:
            load_workflow_pack(definition)
        except Exception as exc:
            return {"error": str(exc)}
        now = self._now()
        self.conn.execute(
            """
            INSERT INTO custom_workflow_packs (
                id, label, version, definition_json, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                label = excluded.label,
                version = excluded.version,
                definition_json = excluded.definition_json,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at
            """,
            (
                safe_id,
                clean_label,
                str(definition["version"]),
                json.dumps(definition, ensure_ascii=False, sort_keys=True),
                self._dump_json(metadata or {}),
                now,
                now,
            ),
        )
        self.commit()
        self._snapshot_custom_workflow(safe_id, reason="save")
        self.commit()
        stored = self.get_custom_workflow_pack(safe_id)
        if stored is None:
            return {"error": f"workflow not stored: {safe_id}"}
        return stored

    def update_custom_workflow_pack(
        self,
        workflow_id: str,
        *,
        label: str | None = None,
        requirements: list[dict[str, Any]] | None = None,
        profile_label: str = "",
        match_terms: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        reason: str = "update",
    ) -> dict[str, Any] | None:
        current = self.get_custom_workflow_pack(workflow_id)
        if current is None:
            return None
        definition = dict(current["definition"])
        clean_label = (label if label is not None else current["label"]).strip() or current["label"]
        profile = dict((definition.get("profiles") or [{}])[0])
        next_requirements = (
            self._normalize_workflow_requirements(requirements)
            if requirements is not None
            else list(profile.get("requirements") or [])
        )
        if not next_requirements:
            return {"error": "workflow must contain at least one requirement"}
        profile["label"] = profile_label.strip() or profile.get("label") or clean_label
        if match_terms is not None:
            profile["match_terms"] = self._clean_terms(match_terms)
        profile["requirements"] = next_requirements
        definition["label"] = clean_label
        definition["version"] = self._now()[:19]
        definition["profiles"] = [profile]
        try:
            load_workflow_pack(definition)
        except Exception as exc:
            return {"error": str(exc)}
        current_meta = dict(current.get("metadata") or {})
        if metadata:
            current_meta.update(metadata)
        now = self._now()
        self.conn.execute(
            """
            UPDATE custom_workflow_packs
            SET label = ?, version = ?, definition_json = ?, metadata_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                clean_label,
                str(definition["version"]),
                json.dumps(definition, ensure_ascii=False, sort_keys=True),
                self._dump_json(current_meta),
                now,
                workflow_id,
            ),
        )
        self._snapshot_custom_workflow(workflow_id, reason=reason)
        self.commit()
        return self.get_custom_workflow_pack(workflow_id)

    def duplicate_custom_workflow_pack(self, workflow_id: str, *, label: str = "") -> dict[str, Any] | None:
        current = self.get_custom_workflow_pack(workflow_id)
        if current is None:
            try:
                builtin = load_workflow_pack(workflow_id)
            except Exception:
                return None
            profile = next((item for item in builtin.profiles if item.id == builtin.default_profile_id), builtin.profiles[0])
            requirements = [
                {
                    "id": req.id,
                    "label": req.label,
                    "description": req.description,
                    "required": req.required,
                    "fact_types": list(req.fact_types),
                    "labels": list(req.labels),
                    "fact_terms": list(req.fact_terms),
                    "document_terms": list(req.document_terms),
                    "suggestion": req.suggestion,
                }
                for req in profile.requirements
            ]
            new_label = label.strip() or f"{builtin.label} copia"
            return self.create_custom_workflow_pack(
                label=new_label,
                profile_label=profile.label,
                match_terms=list(profile.match_terms),
                requirements=requirements,
                metadata={"duplicated_from": workflow_id, "source": "builtin"},
            )
        definition = dict(current["definition"])
        new_label = label.strip() or f"{current['label']} copia"
        definition["id"] = f"custom:{self._slugify(new_label)}"
        definition["label"] = new_label
        definition["version"] = self._now()[:19]
        if definition.get("profiles"):
            definition["profiles"][0]["label"] = new_label
        return self.create_custom_workflow_pack(
            label=new_label,
            pack_id=definition["id"],
            profile_label=new_label,
            match_terms=list((definition.get("profiles") or [{}])[0].get("match_terms") or [new_label]),
            requirements=list((definition.get("profiles") or [{}])[0].get("requirements") or []),
            metadata={"duplicated_from": workflow_id},
        )

    def delete_custom_workflow_pack(self, workflow_id: str) -> bool:
        cur = self.conn.execute("DELETE FROM custom_workflow_packs WHERE id = ?", (workflow_id,))
        self.commit()
        return cur.rowcount > 0

    def list_custom_workflow_versions(self, workflow_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM custom_workflow_versions WHERE workflow_id = ? ORDER BY version_number DESC",
            (workflow_id,),
        ).fetchall()
        return [self._custom_workflow_version_row_to_dict(row) for row in rows]

    def _snapshot_custom_workflow(self, workflow_id: str, *, reason: str = "") -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM custom_workflow_packs WHERE id = ?", (workflow_id,)).fetchone()
        if row is None:
            return None
        version_number = int(
            self.conn.execute(
                "SELECT COALESCE(MAX(version_number), 0) FROM custom_workflow_versions WHERE workflow_id = ?",
                (workflow_id,),
            ).fetchone()[0]
            or 0
        ) + 1
        version_id = f"wfv:{workflow_id}:{version_number:04d}"
        self.conn.execute(
            """
            INSERT INTO custom_workflow_versions (
                id, workflow_id, version_number, label, definition_json, reason, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                version_id,
                workflow_id,
                version_number,
                row["label"],
                row["definition_json"],
                reason.strip(),
                self._now(),
            ),
        )
        version_row = self.conn.execute("SELECT * FROM custom_workflow_versions WHERE id = ?", (version_id,)).fetchone()
        return self._custom_workflow_version_row_to_dict(version_row) if version_row else None

    def _custom_workflow_version_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "workflow_id": row["workflow_id"],
            "version_number": row["version_number"],
            "label": row["label"],
            "definition": json.loads(row["definition_json"] or "{}"),
            "reason": row["reason"],
            "created_at": row["created_at"],
        }

    def _resolve_workflow_pack(self, workflow_pack: str | Path | dict[str, Any] | None) -> str | Path | dict[str, Any] | None:
        if isinstance(workflow_pack, dict) or workflow_pack is None:
            return workflow_pack
        workflow_id = str(workflow_pack).strip()
        if not workflow_id:
            return None
        custom = self.get_custom_workflow_pack(workflow_id)
        if custom:
            definition = dict(custom["definition"])
            definition["source"] = "sqlite"
            return definition
        return workflow_pack

    @staticmethod
    def _slugify(value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
        return slug[:48] or hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _clean_terms(raw: Any) -> list[str]:
        if isinstance(raw, str):
            parts = re.split(r"[,;\n]+", raw)
        else:
            parts = list(raw or [])
        return [str(part).strip().lower() for part in parts if str(part).strip()]

    def _normalize_workflow_requirements(self, requirements: list[dict[str, Any]]) -> list[dict[str, Any]]:
        clean: list[dict[str, Any]] = []
        for index, raw in enumerate(requirements or [], start=1):
            if not isinstance(raw, dict):
                continue
            label = str(raw.get("label") or raw.get("id") or "").strip()
            if not label:
                continue
            item = {
                "id": str(raw.get("id") or f"req_{index}_{self._slugify(label)}").strip(),
                "label": label,
                "description": str(raw.get("description", "")).strip(),
                "required": bool(raw.get("required", True)),
                "fact_types": self._clean_terms(raw.get("fact_types", [])),
                "labels": self._clean_terms(raw.get("labels", [])),
                "fact_terms": self._clean_terms(raw.get("fact_terms", [])),
                "document_terms": self._clean_terms(raw.get("document_terms", [])),
                "suggestion": str(raw.get("suggestion", "")).strip(),
            }
            clean.append(item)
        return clean

    def build_matter_visualizations(self, matter_id: str) -> dict[str, Any]:
        context = self.build_matter_context(matter_id, document_k=50, fact_k=200)
        if "error" in context:
            return context
        documents = self.search_matter_documents("", matter_id=matter_id, top_k=50)
        facts = self.search_matter_facts("", matter_id=matter_id, top_k=200)
        folders = self.list_matter_folders(matter_id)

        def count_by(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
            counts: dict[str, int] = {}
            for item in items:
                value = str(item.get(key) or "senza valore").strip() or "senza valore"
                counts[value] = counts.get(value, 0) + 1
            return [{"label": label, "value": value} for label, value in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))]

        timeline = sorted(
            [
                {
                    "date": fact.get("date_value", ""),
                    "label": fact.get("label", ""),
                    "text": fact.get("text", ""),
                    "document_id": fact.get("document_id", ""),
                }
                for fact in facts
                if fact.get("date_value")
            ],
            key=lambda item: item["date"],
        )
        amount_values: list[float] = []
        for fact in facts:
            if fact.get("fact_type") != "amount":
                continue
            raw = str(fact.get("value") or "")
            normalized = raw.replace(".", "").replace(",", ".")
            try:
                amount_values.append(float(re.sub(r"[^0-9.]", "", normalized)))
            except ValueError:
                pass
        return {
            "matter": context.get("matter", {}),
            "kpis": {
                "documents": len(documents),
                "facts": len(facts),
                "folders": len(folders),
                "parties": len([fact for fact in facts if fact.get("fact_type") == "party"]),
                "amounts": len([fact for fact in facts if fact.get("fact_type") == "amount"]),
                "deadlines": len([fact for fact in facts if fact.get("fact_type") == "deadline"]),
                "amount_total": round(sum(amount_values), 2),
            },
            "documents_by_kind": count_by(documents, "kind"),
            "facts_by_type": count_by(facts, "fact_type"),
            "folders": folders,
            "timeline": timeline[:30],
        }

    @staticmethod
    def _unique_payloads_by_id(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for item in items:
            item_id = str(item.get("id", "")).strip()
            if item_id and item_id in seen:
                continue
            if item_id:
                seen.add(item_id)
            out.append(item)
        return out

    def get_document(self, doc_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if row is None:
            return None
        return self._document_row_to_dict(row, full=True)

    def get_entity(self, entity_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
        if row is None:
            return None
        return self._entity_row_to_dict(row)

    @staticmethod
    def _temporal_clause(alias: str = "") -> str:
        """SQL fragment that constrains a documents-shaped row to be vigent at :as_of_date.

        An empty `effective_from` means "no lower bound" (the norm is treated
        as always-effective in the past). An empty `effective_to` means "no
        upper bound" (the norm is still in force). When `:as_of_date` is the
        empty string the clause is a no-op so callers may pass it
        unconditionally.
        """

        prefix = f"{alias}." if alias else ""
        return (
            f"(:as_of_date = '' "
            f" OR (({prefix}effective_from = '' OR {prefix}effective_from <= :as_of_date) "
            f"     AND ({prefix}effective_to = '' OR {prefix}effective_to >= :as_of_date)))"
        )

    def search_documents(
        self,
        query: str,
        area: str | None = None,
        top_k: int = 5,
        *,
        as_of_date: str = "",
    ) -> list[dict[str, Any]]:
        top_k = self._normalize_limit(top_k)
        query = query.strip()
        as_of = (as_of_date or "").strip()
        cross = self._search_documents_filtered(
            query=query, area=None, top_k=max(top_k * 3, 12), as_of=as_of
        )
        if area:
            primary = [doc for doc in cross if doc.get("area") == area]
            secondary = [doc for doc in cross if doc.get("area") != area]
            merged: list[dict[str, Any]] = []
            i = 0
            j = 0
            while len(merged) < top_k and (i < len(primary) or j < len(secondary)):
                if i < len(primary):
                    merged.append(primary[i])
                    i += 1
                    if len(merged) >= top_k:
                        break
                if j < len(secondary):
                    merged.append(secondary[j])
                    j += 1
            return merged
        return cross[:top_k]

    def _search_documents_filtered(
        self,
        *,
        query: str,
        area: str | None,
        top_k: int,
        as_of: str,
    ) -> list[dict[str, Any]]:
        if not query:
            sql = "SELECT * FROM documents WHERE " + self._temporal_clause()
            params: dict[str, Any] = {"as_of_date": as_of}
            if area:
                sql += " AND area = :area"
                params["area"] = area
            sql += " ORDER BY source_type DESC, title LIMIT :top_k"
            params["top_k"] = top_k
            rows = self.conn.execute(sql, params).fetchall()
            return [self._document_row_to_dict(row) for row in rows]

        fts_query = self._fts_query(query)
        if self.fts_enabled and fts_query:
            sql = (
                "SELECT d.*, bm25(docs_fts, 2.5, 1.0, 1.5, 0.5, 0.2) AS score "
                "FROM docs_fts JOIN documents d ON docs_fts.rowid = d.rowid "
                "WHERE docs_fts MATCH :fts AND " + self._temporal_clause("d")
            )
            params = {"fts": fts_query, "as_of_date": as_of}
            if area:
                sql += " AND d.area = :area"
                params["area"] = area
            sql += " ORDER BY score LIMIT :top_k"
            params["top_k"] = top_k
            rows = self.conn.execute(sql, params).fetchall()
            return [self._document_row_to_dict(row) for row in rows]

        like = f"%{query.lower()}%"
        sql = (
            "SELECT *, CASE WHEN lower(title) LIKE :like THEN 0 ELSE 1 END AS score "
            "FROM documents WHERE (lower(title) LIKE :like OR lower(content) LIKE :like OR lower(source_ref) LIKE :like) "
            "AND " + self._temporal_clause()
        )
        params = {"like": like, "as_of_date": as_of}
        if area:
            sql += " AND area = :area"
            params["area"] = area
        sql += " ORDER BY score, title LIMIT :top_k"
        params["top_k"] = top_k
        rows = self.conn.execute(sql, params).fetchall()
        return [self._document_row_to_dict(row) for row in rows]

    def search_entities(self, query: str, area: str | None = None, top_k: int = 5) -> list[dict[str, Any]]:
        top_k = self._normalize_limit(top_k)
        query = query.strip()
        if not query:
            sql = "SELECT * FROM entities"
            params: list[Any] = []
            if area:
                sql += " WHERE area = ?"
                params.append(area)
            sql += " ORDER BY name LIMIT ?"
            params.append(top_k)
            rows = self.conn.execute(sql, params).fetchall()
            return [self._entity_row_to_dict(row) for row in rows]

        fts_query = self._fts_query(query)
        if self.fts_enabled and fts_query:
            sql = (
                "SELECT e.*, bm25(entities_fts, 2.0, 1.5, 0.8, 0.4) AS score "
                "FROM entities_fts JOIN entities e ON entities_fts.rowid = e.rowid "
                "WHERE entities_fts MATCH ?"
            )
            params = [fts_query]
            if area:
                sql += " AND e.area = ?"
                params.append(area)
            sql += " ORDER BY score LIMIT ?"
            params.append(top_k)
            rows = self.conn.execute(sql, params).fetchall()
            return [self._entity_row_to_dict(row) for row in rows]

        like = f"%{query.lower()}%"
        sql = (
            "SELECT *, CASE WHEN lower(name) LIKE ? THEN 0 ELSE 1 END AS score "
            "FROM entities WHERE (lower(name) LIKE ? OR lower(summary) LIKE ?)"
        )
        params = [like, like, like]
        if area:
            sql += " AND area = ?"
            params.append(area)
        sql += " ORDER BY score, name LIMIT ?"
        params.append(top_k)
        rows = self.conn.execute(sql, params).fetchall()
        return [self._entity_row_to_dict(row) for row in rows]

    def search_atoms(
        self,
        query: str,
        area: str | None = None,
        top_k: int = 8,
        atom_type: str | None = None,
    ) -> list[dict[str, Any]]:
        top_k = self._normalize_limit(top_k, max_value=50)
        query = query.strip()
        if not query:
            sql = "SELECT * FROM legal_atoms"
            params: list[Any] = []
            clauses: list[str] = []
            if area:
                clauses.append("area = ?")
                params.append(area)
            if atom_type:
                clauses.append("atom_type = ?")
                params.append(atom_type)
            if clauses:
                sql += " WHERE " + " AND ".join(clauses)
            sql += " ORDER BY confidence DESC, action, subject LIMIT ?"
            params.append(top_k)
            rows = self.conn.execute(sql, params).fetchall()
            return [self._atom_row_to_dict(row) for row in rows]

        fts_query = self._fts_query(query)
        if self.fts_enabled and fts_query:
            sql = (
                "SELECT a.*, bm25(legal_atoms_fts, 1.0, 1.0, 1.8, 2.2, 2.0, 1.0, 1.5, 1.5, 1.3, 1.0, 0.5) AS score "
                "FROM legal_atoms_fts JOIN legal_atoms a ON legal_atoms_fts.rowid = a.rowid "
                "WHERE legal_atoms_fts MATCH ?"
            )
            params = [fts_query]
            if area:
                sql += " AND a.area = ?"
                params.append(area)
            if atom_type:
                sql += " AND a.atom_type = ?"
                params.append(atom_type)
            sql += " ORDER BY score, a.confidence DESC LIMIT ?"
            params.append(top_k)
            rows = self.conn.execute(sql, params).fetchall()
            return [self._atom_row_to_dict(row) for row in rows]

        like = f"%{query.lower()}%"
        sql = (
            "SELECT *, CASE WHEN lower(action) LIKE ? OR lower(subject) LIKE ? THEN 0 ELSE 1 END AS score "
            "FROM legal_atoms WHERE ("
            "lower(subject) LIKE ? OR lower(action) LIKE ? OR lower(value) LIKE ? OR "
            "lower(temporal_anchor) LIKE ? OR lower(condition_text) LIKE ? OR lower(source_quote) LIKE ?"
            ")"
        )
        params = [like, like, like, like, like, like, like, like]
        if area:
            sql += " AND area = ?"
            params.append(area)
        if atom_type:
            sql += " AND atom_type = ?"
            params.append(atom_type)
        sql += " ORDER BY score, confidence DESC LIMIT ?"
        params.append(top_k)
        rows = self.conn.execute(sql, params).fetchall()
        return [self._atom_row_to_dict(row) for row in rows]

    def rebuild_legal_atoms(self, area: str | None = None) -> dict[str, int]:
        sql = "SELECT * FROM documents"
        params: list[Any] = []
        if area:
            sql += " WHERE area = ?"
            params.append(area)
        rows = self.conn.execute(sql, params).fetchall()
        documents = [self._document_row_to_dict(row, full=True) for row in rows]
        document_count = 0
        atom_count = 0
        for raw in documents:
            document = Document(
                id=raw["id"],
                title=raw["title"],
                kind=raw["kind"],
                area=raw["area"],
                content=raw["content"],
                source_type=raw["source_type"],
                source_ref=raw["source_ref"],
                authority=raw["authority"],
                effective_from=raw["effective_from"],
                effective_to=raw["effective_to"],
                metadata=raw["metadata"],
            )
            version_id = self.upsert_document_version(document)
            atoms = compile_document_atoms(document)
            self.replace_document_atoms(document.id, atoms, document_version_id=version_id)
            document_count += 1
            atom_count += len(atoms)
        self.commit()
        return {"documents": document_count, "legal_atoms": atom_count}

    def get_neighbors(
        self,
        entity_id: str,
        relation: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        limit = self._normalize_limit(limit, max_value=50)
        sql = (
            "SELECT "
            "e.id, e.source_id, e.target_id, e.relation, e.weight, e.summary, e.metadata_json, "
            "src.name AS source_name, src.kind AS source_kind, src.area AS source_area, src.metadata_json AS source_metadata_json, "
            "dst.name AS target_name, dst.kind AS target_kind, dst.area AS target_area, dst.metadata_json AS target_metadata_json "
            "FROM edges e "
            "JOIN entities src ON src.id = e.source_id "
            "JOIN entities dst ON dst.id = e.target_id "
            "WHERE (e.source_id = ? OR e.target_id = ?)"
        )
        params: list[Any] = [entity_id, entity_id]
        if relation:
            sql += " AND e.relation = ?"
            params.append(relation)
        sql += " ORDER BY e.weight DESC, e.id LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            direction = "outgoing" if row["source_id"] == entity_id else "incoming"
            out.append(
                {
                    "id": row["id"],
                    "direction": direction,
                    "relation": row["relation"],
                    "weight": row["weight"],
                    "summary": row["summary"],
                    "source": {
                        "id": row["source_id"],
                        "name": row["source_name"],
                        "kind": row["source_kind"],
                        "area": row["source_area"],
                        "metadata": self._load_json(row["source_metadata_json"]),
                    },
                    "target": {
                        "id": row["target_id"],
                        "name": row["target_name"],
                        "kind": row["target_kind"],
                        "area": row["target_area"],
                        "metadata": self._load_json(row["target_metadata_json"]),
                    },
                    "metadata": self._load_json(row["metadata_json"]),
                }
            )
        return out

    def get_document_reference_graph(self, doc_ids: list[str], limit: int = 8) -> list[dict[str, Any]]:
        if not doc_ids:
            return []
        entity_ids = [self.document_entity_id(doc_id) for doc_id in doc_ids]
        placeholders = ",".join("?" for _ in entity_ids)
        sql = (
            "SELECT "
            "e.id, e.source_id, e.target_id, e.relation, e.weight, e.summary, e.metadata_json, "
            "src.name AS source_name, src.kind AS source_kind, src.area AS source_area, src.metadata_json AS source_metadata_json, "
            "dst.name AS target_name, dst.kind AS target_kind, dst.area AS target_area, dst.metadata_json AS target_metadata_json "
            "FROM edges e "
            "JOIN entities src ON src.id = e.source_id "
            "JOIN entities dst ON dst.id = e.target_id "
            f"WHERE e.relation = 'references' AND (e.source_id IN ({placeholders}) OR e.target_id IN ({placeholders})) "
            "ORDER BY e.id LIMIT ?"
        )
        params: list[Any] = entity_ids + entity_ids + [self._normalize_limit(limit, max_value=50)]
        rows = self.conn.execute(sql, params).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            out.append(
                {
                    "id": row["id"],
                    "relation": row["relation"],
                    "weight": row["weight"],
                    "summary": row["summary"],
                    "source": {
                        "id": row["source_id"],
                        "name": row["source_name"],
                        "kind": row["source_kind"],
                        "area": row["source_area"],
                        "metadata": self._load_json(row["source_metadata_json"]),
                    },
                    "target": {
                        "id": row["target_id"],
                        "name": row["target_name"],
                        "kind": row["target_kind"],
                        "area": row["target_area"],
                        "metadata": self._load_json(row["target_metadata_json"]),
                    },
                    "metadata": self._load_json(row["metadata_json"]),
                }
            )
        return out

    def list_areas(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT area, COUNT(*) AS documents
            FROM documents
            GROUP BY area
            ORDER BY area
            """
        ).fetchall()
        return [{"area": row["area"], "documents": row["documents"]} for row in rows]

    def build_context(
        self,
        question: str,
        area: str | None = None,
        doc_k: int = 6,
        entity_k: int = 8,
        neighbor_k: int = 6,
        *,
        as_of_date: str = "",
    ) -> dict[str, Any]:
        doc_k = self._normalize_limit(doc_k, max_value=10)
        entity_k = self._normalize_limit(entity_k, max_value=20)
        as_of = (as_of_date or "").strip()
        queries = self._retrieval_queries(question) or [question]
        fragments = self._question_fragments(question) or [question]
        discovery_doc_k = self._normalize_limit(max(doc_k * 3, 10), max_value=20)
        discovery_entity_k = self._normalize_limit(max(entity_k * 2, 10), max_value=20)

        candidates: dict[str, dict[str, Any]] = {}
        candidate_meta: dict[str, dict[str, Any]] = {}
        entity_hits: dict[str, dict[str, Any]] = {}
        atom_hits: dict[str, dict[str, Any]] = {}
        excluded_by_date: list[dict[str, str]] = []

        def add_candidate(doc_id: str, *, reason: str, query: str) -> None:
            doc = self.get_document(doc_id)
            if doc is None:
                return
            if as_of and not self._is_doc_vigent(doc, as_of):
                excluded_by_date.append(
                    {
                        "id": doc.get("id", ""),
                        "title": doc.get("title", ""),
                        "effective_from": doc.get("effective_from", ""),
                        "effective_to": doc.get("effective_to", ""),
                        "as_of_date": as_of,
                    }
                )
                return
            candidates[doc_id] = doc
            meta = candidate_meta.setdefault(
                doc_id,
                {"reasons": [], "queries": []},
            )
            if reason not in meta["reasons"]:
                meta["reasons"].append(reason)
            if query not in meta["queries"]:
                meta["queries"].append(query)

        for query in queries:
            for item in self.search_documents(query, area=area, top_k=discovery_doc_k, as_of_date=as_of):
                add_candidate(item["id"], reason="document_search", query=query)

            for entity in self.search_entities(query, area=area, top_k=discovery_entity_k):
                entity_hits.setdefault(entity["id"], entity)
                metadata = entity.get("metadata") or {}
                doc_id = str(metadata.get("document_id", "")).strip()
                if doc_id:
                    add_candidate(doc_id, reason="entity_search", query=query)

            for atom in self.search_atoms(query, area=area, top_k=discovery_entity_k):
                atom_hits.setdefault(atom["id"], atom)
                add_candidate(atom["document_id"], reason="atom_search", query=query)

        scored: list[tuple[float, str]] = []
        for doc_id, doc in candidates.items():
            meta = candidate_meta[doc_id]
            score = self._candidate_score(
                doc,
                question=question,
                queries=meta["queries"],
                reasons=meta["reasons"],
            )
            meta["score"] = score
            scored.append((score, doc_id))
        scored.sort(key=lambda item: (-item[0], item[1]))

        selected_ids: list[str] = []
        for fragment in fragments[1:]:
            fragment_candidates = [
                (
                    self._candidate_score(
                        candidates[doc_id],
                        question=fragment,
                        queries=[fragment],
                        reasons=candidate_meta[doc_id].get("reasons", []),
                    ),
                    doc_id,
                )
                for doc_id in candidates
                if fragment in candidate_meta[doc_id].get("queries", [])
            ]
            if not fragment_candidates:
                continue
            fragment_candidates.sort(key=lambda item: (-item[0], item[1]))
            best_id = fragment_candidates[0][1]
            if best_id not in selected_ids:
                selected_ids.append(best_id)
            if len(selected_ids) >= doc_k:
                break

        for _, doc_id in scored:
            if doc_id not in selected_ids:
                selected_ids.append(doc_id)
            if len(selected_ids) >= doc_k:
                break

        primary_docs = [candidates[doc_id] for doc_id in selected_ids]
        entities = list(entity_hits.values())[:entity_k]
        selected_atoms = [
            atom for atom in atom_hits.values()
            if atom["document_id"] in set(selected_ids)
        ][: max(entity_k * 2, 8)]
        relationships = self.get_document_reference_graph([doc["id"] for doc in primary_docs], limit=neighbor_k)

        related_docs: list[dict[str, Any]] = []
        seen_doc_ids = {doc["id"] for doc in primary_docs}
        for edge in relationships:
            for side in ("source", "target"):
                metadata = edge[side].get("metadata", {})
                related_doc_id = metadata.get("document_id")
                if not related_doc_id or related_doc_id in seen_doc_ids:
                    continue
                related_doc = self.get_document(related_doc_id)
                if related_doc is None:
                    continue
                seen_doc_ids.add(related_doc_id)
                related_docs.append(related_doc)

        evidence_docs = primary_docs + related_docs
        official_docs = [doc for doc in evidence_docs if doc["source_type"] == "official"]
        return {
            "question": question,
            "area": area,
            "as_of_date": as_of,
            "documents": primary_docs,
            "related_documents": related_docs,
            "entities": entities,
            "legal_atoms": selected_atoms,
            "relationships": relationships,
            "excluded_by_date": excluded_by_date,
            "coverage": {
                "documents_total": len(evidence_docs),
                "documents_primary": len(primary_docs),
                "documents_related": len(related_docs),
                "official_documents": len(official_docs),
                "candidate_documents": len(candidates),
                "retrieval_queries": len(queries),
                "legal_atoms": len(selected_atoms),
                "excluded_by_date": len(excluded_by_date),
            },
            "retrieval": {
                "queries": queries,
                "selected_documents": [
                    {
                        "id": doc_id,
                        "score": round(float(candidate_meta[doc_id].get("score", 0.0)), 3),
                        "reasons": candidate_meta[doc_id].get("reasons", []),
                        "matched_queries": candidate_meta[doc_id].get("queries", []),
                    }
                    for doc_id in selected_ids
                ],
            },
            "citations": [
                {
                    "id": doc["id"],
                    "title": doc["title"],
                    "source_ref": doc["source_ref"],
                    "authority": doc["authority"],
                    "effective_from": doc["effective_from"],
                    "effective_to": doc["effective_to"],
                }
                for doc in evidence_docs
            ],
        }

    @staticmethod
    def _is_doc_vigent(doc: dict[str, Any], as_of_date: str) -> bool:
        """Return True if `doc` is in force at the given ISO date.

        A document with empty `effective_from`/`effective_to` is treated as
        unconstrained on that bound, which is the right default for the
        Normattiva imports that omit explicit dates.
        """

        if not as_of_date:
            return True
        eff_from = (doc.get("effective_from") or "").strip()
        eff_to = (doc.get("effective_to") or "").strip()
        if eff_from and eff_from > as_of_date:
            return False
        if eff_to and eff_to < as_of_date:
            return False
        return True

    # ------------------------------------------------------------------
    # Citator (Shepardize)
    # ------------------------------------------------------------------

    def shepardize(self, document_id: str, as_of_date: str = "") -> dict[str, Any]:
        """Return vigency status, citing references and abrogation chain.

        Walks the typed `edges` graph backed by the legal ontology populated
        by the entity extractor. A document is considered abrogated if there
        exists at least one inbound edge with relation `abroga` whose source
        document is itself vigent at `as_of_date`.
        """

        doc = self.get_document(document_id)
        if doc is None:
            return {
                "document_id": document_id,
                "status": "unknown",
                "reason": "document not found",
            }

        as_of = (as_of_date or "").strip()
        target_entity = self._document_entity_id(document_id)

        inbound_rows = self.conn.execute(
            """
            SELECT e.relation, e.source_id, e.summary, e.metadata_json,
                   ent.metadata_json AS source_metadata
            FROM edges e
            JOIN entities ent ON ent.id = e.source_id
            WHERE e.target_id = ?
            """,
            (target_entity,),
        ).fetchall()

        cited_by: list[dict[str, Any]] = []
        abrogations: list[dict[str, Any]] = []
        derogations: list[dict[str, Any]] = []
        modifications: list[dict[str, Any]] = []
        conflicts: list[dict[str, Any]] = []
        applications: list[dict[str, Any]] = []
        for row in inbound_rows:
            source_meta = self._load_json(row["source_metadata"]) if row["source_metadata"] else {}
            source_doc_id = str(source_meta.get("document_id") or "").strip()
            edge_meta = self._load_json(row["metadata_json"]) if row["metadata_json"] else {}
            payload = {
                "source_document_id": source_doc_id,
                "source_entity_id": row["source_id"],
                "evidence_quote": edge_meta.get("evidence_quote", ""),
                "summary": row["summary"],
            }
            relation = row["relation"]
            if relation == "abroga":
                abrogations.append(payload)
            elif relation == "deroga":
                derogations.append(payload)
            elif relation == "modifica":
                modifications.append(payload)
            elif relation == "confligge_con":
                conflicts.append(payload)
            elif relation == "applica_principio":
                applications.append(payload)
            elif relation == "cita":
                cited_by.append(payload)

        status = "vigente" if self._is_doc_vigent(doc, as_of) else "non_vigente_per_data"
        active_abrogations: list[dict[str, Any]] = []
        for abrogation in abrogations:
            source_doc_id = abrogation.get("source_document_id")
            if not source_doc_id:
                continue
            source_doc = self.get_document(source_doc_id)
            if source_doc is None:
                continue
            if as_of and not self._is_doc_vigent(source_doc, as_of):
                continue
            abrogation = {**abrogation, "source_title": source_doc.get("title", "")}
            active_abrogations.append(abrogation)

        if active_abrogations:
            status = "abrogato"

        return {
            "document_id": document_id,
            "title": doc.get("title", ""),
            "as_of_date": as_of,
            "status": status,
            "effective_from": doc.get("effective_from", ""),
            "effective_to": doc.get("effective_to", ""),
            "cited_by": cited_by,
            "abrogations": abrogations,
            "active_abrogations": active_abrogations,
            "derogations": derogations,
            "modifications": modifications,
            "conflicts": conflicts,
            "applications": applications,
        }

    @staticmethod
    def _document_entity_id(document_id: str) -> str:
        """Stable entity id used to anchor a document inside the typed graph."""

        return f"doc:{document_id}"

    # ------------------------------------------------------------------
    # Multi-hop graph traversal
    # ------------------------------------------------------------------

    def traverse_graph(
        self,
        start_doc_id: str,
        *,
        relations: tuple[str, ...] | None = None,
        direction: str = "outbound",
        max_depth: int = 3,
        as_of_date: str = "",
        max_nodes: int = 200,
    ) -> dict[str, Any]:
        """BFS over the typed citation graph from a starting document.

        - `relations` restricts traversal to a subset of edge types (e.g.
          ("cita", "applica_principio")). None means all typed relations.
        - `direction` selects outbound (start → others), inbound (others
          → start), or both.
        - `as_of_date` filters out edges where either endpoint is a
          document not vigent at that date.
        - `max_depth` and `max_nodes` are safety caps.

        Returns a graph slice consumable by the agent: nodes, typed edges,
        and the sequence of paths discovered (useful for explanations like
        "art. X cita art. Y che applica Cass. Z").
        """

        if direction not in {"outbound", "inbound", "both"}:
            raise ValueError(f"invalid direction: {direction}")
        max_depth = max(0, min(int(max_depth), 6))
        max_nodes = max(1, min(int(max_nodes), 1000))
        as_of = (as_of_date or "").strip()

        start_entity = self._document_entity_id(start_doc_id)
        start_doc = self.get_document(start_doc_id)
        if start_doc is None:
            return {
                "start_doc_id": start_doc_id,
                "as_of_date": as_of,
                "nodes": [],
                "edges": [],
                "paths": [],
                "warning": "start document not found",
            }
        # Make sure the entity exists; cheap and idempotent.
        self.upsert_document_entity(start_doc)

        from .entity_extractor import VALID_RELATIONS

        relation_filter = tuple(relations) if relations else tuple(VALID_RELATIONS)
        relation_set = set(relation_filter)

        nodes: dict[str, dict[str, Any]] = {}
        edges: list[dict[str, Any]] = []
        seen_edge_ids: set[str] = set()
        paths: list[list[str]] = []

        def enqueue_node(entity_id: str) -> None:
            if entity_id in nodes:
                return
            row = self.conn.execute(
                "SELECT * FROM entities WHERE id = ?", (entity_id,)
            ).fetchone()
            if row is None:
                nodes[entity_id] = {"id": entity_id, "kind": "unknown", "name": entity_id}
                return
            entity = self._entity_row_to_dict(row)
            doc_id = str((entity.get("metadata") or {}).get("document_id") or "")
            doc_payload: dict[str, Any] | None = None
            if doc_id:
                doc_payload = self.get_document(doc_id)
            if as_of and doc_payload is not None and not self._is_doc_vigent(doc_payload, as_of):
                # Surfacing the node is fine — we just mark vigency.
                pass
            nodes[entity_id] = {
                "id": entity_id,
                "kind": entity.get("kind", ""),
                "name": entity.get("name", ""),
                "area": entity.get("area", ""),
                "document_id": doc_id,
                "vigent_at_as_of": (
                    self._is_doc_vigent(doc_payload, as_of) if (doc_payload and as_of) else None
                ),
            }

        enqueue_node(start_entity)
        frontier: list[tuple[str, int, list[str]]] = [(start_entity, 0, [start_entity])]
        while frontier:
            current, depth, path = frontier.pop(0)
            if depth >= max_depth:
                continue
            if len(nodes) >= max_nodes:
                break

            outbound_rows: list[Any] = []
            inbound_rows: list[Any] = []
            placeholders = ",".join(["?"] * len(relation_filter))
            if direction in {"outbound", "both"} and relation_filter:
                outbound_rows = self.conn.execute(
                    f"SELECT id, source_id, target_id, relation, summary, metadata_json "
                    f"FROM edges WHERE source_id = ? AND relation IN ({placeholders})",
                    (current, *relation_filter),
                ).fetchall()
            if direction in {"inbound", "both"} and relation_filter:
                inbound_rows = self.conn.execute(
                    f"SELECT id, source_id, target_id, relation, summary, metadata_json "
                    f"FROM edges WHERE target_id = ? AND relation IN ({placeholders})",
                    (current, *relation_filter),
                ).fetchall()

            for row in [*outbound_rows, *inbound_rows]:
                edge_id = row["id"]
                if edge_id in seen_edge_ids:
                    continue
                seen_edge_ids.add(edge_id)
                source_id = row["source_id"]
                target_id = row["target_id"]
                metadata = self._load_json(row["metadata_json"]) if row["metadata_json"] else {}
                edges.append(
                    {
                        "id": edge_id,
                        "source": source_id,
                        "target": target_id,
                        "relation": row["relation"],
                        "summary": row["summary"],
                        "metadata": metadata,
                    }
                )
                next_id = target_id if source_id == current else source_id
                enqueue_node(next_id)
                next_path = path + [row["relation"], next_id]
                paths.append(next_path)
                frontier.append((next_id, depth + 1, next_path))
                if len(nodes) >= max_nodes:
                    break

        return {
            "start_doc_id": start_doc_id,
            "as_of_date": as_of,
            "direction": direction,
            "relations": list(relation_filter),
            "max_depth": max_depth,
            "nodes": list(nodes.values()),
            "edges": edges,
            "paths": paths,
            "node_count": len(nodes),
            "edge_count": len(edges),
        }

    def upsert_document_entity(self, doc: dict[str, Any]) -> str:
        """Materialise a `documents` row as an `entities` node, idempotently."""

        from .models import Entity

        entity_id = self._document_entity_id(doc["id"])
        existing = self.conn.execute(
            "SELECT id FROM entities WHERE id = ?", (entity_id,)
        ).fetchone()
        if existing is not None:
            return entity_id
        metadata = {
            "document_id": doc["id"],
            "kind": doc.get("kind", ""),
            "source_ref": doc.get("source_ref", ""),
            "effective_from": doc.get("effective_from", ""),
            "effective_to": doc.get("effective_to", ""),
        }
        entity = Entity(
            id=entity_id,
            name=doc.get("title", doc["id"]),
            kind="document",
            area=doc.get("area", ""),
            summary=(doc.get("title") or "")[:500],
            metadata=metadata,
        )
        self.upsert_entity(entity)
        return entity_id

    # ------------------------------------------------------------------
    # LLM cache
    # ------------------------------------------------------------------

    def cache_get(self, key: str) -> str | None:
        row = self.conn.execute(
            "SELECT response, expires_at FROM llm_cache WHERE key = ?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        expires_at = (row["expires_at"] or "").strip()
        if expires_at and expires_at < self._now():
            self.conn.execute("DELETE FROM llm_cache WHERE key = ?", (key,))
            self.conn.commit()
            return None
        return row["response"]

    def cache_put(
        self,
        key: str,
        response: str,
        *,
        model: str = "",
        kind: str = "",
        ttl_seconds: int | None = None,
    ) -> None:
        expires_at = ""
        if ttl_seconds and ttl_seconds > 0:
            from datetime import datetime, timedelta, timezone

            expires_at = (
                datetime.now(timezone.utc).replace(microsecond=0) + timedelta(seconds=ttl_seconds)
            ).isoformat()
        self.conn.execute(
            """
            INSERT INTO llm_cache (key, model, kind, response, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                model = excluded.model,
                kind = excluded.kind,
                response = excluded.response,
                created_at = excluded.created_at,
                expires_at = excluded.expires_at
            """,
            (key, model, kind, response, self._now(), expires_at),
        )
        self.conn.commit()

    # ------------------------------------------------------------------
    # Audit log
    # ------------------------------------------------------------------

    def record_answer_audit(self, record: dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT INTO answer_audit (
                id, ts, question, question_hash, context_hash, payload_hash,
                signature, status, model, area, matter_id, as_of_date, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["id"],
                record["ts"],
                record.get("question", ""),
                record["question_hash"],
                record["context_hash"],
                record["payload_hash"],
                record["signature"],
                record.get("status", ""),
                record.get("model", ""),
                record.get("area", ""),
                record.get("matter_id", ""),
                record.get("as_of_date", ""),
                record.get("payload_json", "{}"),
            ),
        )
        self.conn.commit()

    def list_answer_audit(self, *, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM answer_audit ORDER BY ts DESC LIMIT ?",
            (max(1, min(int(limit), 500)),),
        ).fetchall()
        return [
            {
                "id": row["id"],
                "ts": row["ts"],
                "question": row["question"],
                "question_hash": row["question_hash"],
                "context_hash": row["context_hash"],
                "payload_hash": row["payload_hash"],
                "signature": row["signature"],
                "status": row["status"],
                "model": row["model"],
                "area": row["area"],
                "matter_id": row["matter_id"],
                "as_of_date": row["as_of_date"],
            }
            for row in rows
        ]

    def health(self) -> dict[str, int | bool]:
        doc_count = self.conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        official_count = self.conn.execute(
            "SELECT COUNT(*) FROM documents WHERE source_type = 'official'"
        ).fetchone()[0]
        entity_count = self.conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        edge_count = self.conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        version_count = self.conn.execute("SELECT COUNT(*) FROM document_versions").fetchone()[0]
        atom_count = self.conn.execute("SELECT COUNT(*) FROM legal_atoms").fetchone()[0]
        matter_count = self.conn.execute("SELECT COUNT(*) FROM matters").fetchone()[0]
        matter_document_count = self.conn.execute("SELECT COUNT(*) FROM matter_documents").fetchone()[0]
        matter_fact_count = self.conn.execute("SELECT COUNT(*) FROM matter_facts").fetchone()[0]
        agent_memory_count = self.conn.execute("SELECT COUNT(*) FROM agent_memories").fetchone()[0]
        generated_artifact_count = self.conn.execute("SELECT COUNT(*) FROM generated_artifacts").fetchone()[0]
        return {
            "documents": int(doc_count),
            "official_documents": int(official_count),
            "entities": int(entity_count),
            "edges": int(edge_count),
            "document_versions": int(version_count),
            "legal_atoms": int(atom_count),
            "matters": int(matter_count),
            "matter_documents": int(matter_document_count),
            "matter_facts": int(matter_fact_count),
            "agent_memories": int(agent_memory_count),
            "generated_artifacts": int(generated_artifact_count),
            "fts_enabled": self.fts_enabled,
        }


def _clean_tag_list(tags: list[str]) -> list[str]:
    seen: set[str] = set()
    clean: list[str] = []
    for tag in tags:
        text = re.sub(r"\s+", "_", str(tag or "").strip().lower())
        text = re.sub(r"[^0-9a-zà-ÿ_:-]+", "", text)
        if not text or text in seen:
            continue
        seen.add(text)
        clean.append(text[:40])
        if len(clean) >= 12:
            break
    return clean
