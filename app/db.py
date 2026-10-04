"""Postgres (Supabase) connection + schema setup."""

import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]


def get_connection():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS packages (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        requirement_text TEXT NOT NULL,
        test_cases_text TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS findings (
        id SERIAL PRIMARY KEY,
        package_id INTEGER NOT NULL REFERENCES packages(id),
        level TEXT NOT NULL,
        category TEXT NOT NULL,
        test_id TEXT,
        source_quote TEXT NOT NULL,
        explanation TEXT NOT NULL,
        priority TEXT NOT NULL,
        source TEXT NOT NULL DEFAULT 'ai',
        status TEXT NOT NULL DEFAULT 'pending',
        reference_valid INTEGER NOT NULL DEFAULT 1,
        validation_problems TEXT NOT NULL DEFAULT '[]',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS clarification_questions (
        id SERIAL PRIMARY KEY,
        package_id INTEGER NOT NULL REFERENCES packages(id),
        question TEXT NOT NULL,
        requirement_ref TEXT NOT NULL,
        answer TEXT,
        status TEXT NOT NULL DEFAULT 'unanswered',
        source TEXT NOT NULL DEFAULT 'ai',
        reference_valid INTEGER NOT NULL DEFAULT 1,
        validation_problems TEXT NOT NULL DEFAULT '[]'
    );

    CREATE TABLE IF NOT EXISTS rtm_entries (
        id SERIAL PRIMARY KEY,
        package_id INTEGER NOT NULL REFERENCES packages(id),
        requirement_rule TEXT NOT NULL,
        test_ids TEXT NOT NULL,
        coverage_status TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS review_decisions (
        id SERIAL PRIMARY KEY,
        finding_id INTEGER NOT NULL REFERENCES findings(id),
        reviewer_id TEXT NOT NULL DEFAULT 'dev',
        decision TEXT NOT NULL,
        final_text TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cur.execute("ALTER TABLE packages ADD COLUMN IF NOT EXISTS audit_status TEXT NOT NULL DEFAULT 'complete'")
    cur.execute("ALTER TABLE packages ADD COLUMN IF NOT EXISTS audit_note TEXT")

    conn.commit()
    cur.close()
    conn.close()