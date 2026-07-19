import sqlite3
import os
from datetime import datetime
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "instance", "zetech_voting.sqlite3")

SCHEMA = """
CREATE TABLE IF NOT EXISTS candidates (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    docket        TEXT NOT NULL,
    course_code   TEXT NOT NULL,
    photo_filename TEXT,
    votes         INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS voted_admissions (
    admission_number TEXT PRIMARY KEY,
    voted_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS admin_users (
    username      TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL
);
"""

DEFAULT_ADMIN_USERNAME = "returning_officer"
DEFAULT_ADMIN_PASSWORD = "ZetechVotes2026"  # change this immediately after first login


def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    try:
        conn.executescript(SCHEMA)
        row = conn.execute("SELECT COUNT(*) AS n FROM admin_users").fetchone()
        if row["n"] == 0:
            conn.execute(
                "INSERT INTO admin_users (username, password_hash) VALUES (?, ?)",
                (DEFAULT_ADMIN_USERNAME, generate_password_hash(DEFAULT_ADMIN_PASSWORD)),
            )
        conn.commit()
    finally:
        conn.close()


def now_iso():
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"
