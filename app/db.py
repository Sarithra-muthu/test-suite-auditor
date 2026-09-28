"""SQLite connection + schema setup."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "auditor.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # lets us access columns by name, not just index
    return conn


def init_db():
    conn = get_connection()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS packages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        requirement_text TEXT NOT NULL,
        test_cases_text TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS findings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        package_id INTEGER NOT NULL REFERENCES packages(id),
        level TEXT NOT NULL,
        category TEXT NOT NULL,
        test_id TEXT,
        source_quote TEXT NOT NULL,
        explanation TEXT NOT NULL,
        priority TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        reference_valid INTEGER NOT NULL DEFAULT 1,
        validation_problems TEXT NOT NULL DEFAULT '[]',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS clarification_questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        package_id INTEGER NOT NULL REFERENCES packages(id),
        question TEXT NOT NULL,
        requirement_ref TEXT NOT NULL,
        answer TEXT,
        status TEXT NOT NULL DEFAULT 'unanswered',
        reference_valid INTEGER NOT NULL DEFAULT 1,
        validation_problems TEXT NOT NULL DEFAULT '[]'
    );

    CREATE TABLE IF NOT EXISTS rtm_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        package_id INTEGER NOT NULL REFERENCES packages(id),
        requirement_rule TEXT NOT NULL,
        test_ids TEXT NOT NULL,
        coverage_status TEXT NOT NULL
    );
    """)
    conn.commit()
    conn.close()