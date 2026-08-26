"""SQLite persistence layer (stdlib only, no ORM)."""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "fleetleads.db"
_DB_LOCK = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    domain       TEXT UNIQUE NOT NULL,
    website      TEXT,
    country      TEXT NOT NULL,
    country_code TEXT NOT NULL,
    city         TEXT,
    category     TEXT NOT NULL,
    description  TEXT,
    employees    INTEGER,
    founded      INTEGER,
    linkedin_url TEXT,
    tags         TEXT,
    blocked      INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT DEFAULT (datetime('now'))
);

-- Organisations the user wants excluded from the data warehouse.
-- `domain` is optional (a pattern to also block future lookups/discoveries).
CREATE TABLE IF NOT EXISTS blocklist (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    domain     TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(name)
);

-- Every scrape attempt, one row per company.
CREATE TABLE IF NOT EXISTS scrapes (
    company_id    INTEGER PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
    status        TEXT NOT NULL,             -- ok | partial | failed
    message       TEXT,
    pages_checked INTEGER DEFAULT 0,
    base_url      TEXT,
    scraped_at    TEXT DEFAULT (datetime('now'))
);

-- Real emails published on the company's own website.
CREATE TABLE IF NOT EXISTS emails (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id  INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    email       TEXT NOT NULL,
    category    TEXT,
    source_url  TEXT,
    mx_status   TEXT,
    smtp_status TEXT,
    disposable  TEXT,
    catchall    TEXT,
    verdict     TEXT,
    verified_at TEXT,
    UNIQUE(company_id, email)
);

-- Real phone numbers published on the company's own website.
CREATE TABLE IF NOT EXISTS phones (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    phone      TEXT NOT NULL,
    label      TEXT,
    source_url TEXT,
    UNIQUE(company_id, phone)
);

-- Social profiles linked from the company's website.
CREATE TABLE IF NOT EXISTS socials (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    network    TEXT NOT NULL,
    url        TEXT NOT NULL,
    UNIQUE(company_id, network)
);

-- Named people (e.g. leadership) published via structured data / team pages.
CREATE TABLE IF NOT EXISTS people (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id    INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    name          TEXT NOT NULL,
    title         TEXT,
    email         TEXT,
    email_status  TEXT,
    phone         TEXT,
    phone_label   TEXT,
    linkedin_url  TEXT,
    linkedin_type TEXT,
    mx_status     TEXT,
    smtp_status   TEXT,
    disposable    TEXT,
    catchall      TEXT,
    verified_at   TEXT,
    source_url    TEXT,
    UNIQUE(company_id, name)
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- Continuous worker state (survives restarts).
CREATE TABLE IF NOT EXISTS worker_state (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- Live activity feed for the discovery worker (trimmed to last N rows).
CREATE TABLE IF NOT EXISTS worker_log (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT DEFAULT (datetime('now')),
    job     TEXT,
    level   TEXT,
    message TEXT,
    payload TEXT
);

CREATE INDEX IF NOT EXISTS idx_emails_company ON emails(company_id);
CREATE INDEX IF NOT EXISTS idx_phones_company ON phones(company_id);
CREATE INDEX IF NOT EXISTS idx_socials_company ON socials(company_id);
CREATE INDEX IF NOT EXISTS idx_people_company ON people(company_id);
CREATE INDEX IF NOT EXISTS idx_companies_country ON companies(country);
CREATE INDEX IF NOT EXISTS idx_companies_category ON companies(category);
"""


def get_conn() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.commit()
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns introduced after the initial release (keeps existing data)."""
    people_cols = {r[1] for r in conn.execute("PRAGMA table_info(people)")}
    for col in ("email", "email_status", "phone", "phone_label", "linkedin_url",
                "linkedin_type", "mx_status", "smtp_status", "disposable",
                "verified_at", "catchall"):
        if col not in people_cols:
            conn.execute(f"ALTER TABLE people ADD COLUMN {col} TEXT")

    email_cols = {r[1] for r in conn.execute("PRAGMA table_info(emails)")}
    for col in ("mx_status", "smtp_status", "disposable", "verified_at", "catchall", "verdict"):
        if col not in email_cols:
            conn.execute(f"ALTER TABLE emails ADD COLUMN {col} TEXT")

    comp_cols = {r[1] for r in conn.execute("PRAGMA table_info(companies)")}
    if "blocked" not in comp_cols:
        conn.execute("ALTER TABLE companies ADD COLUMN blocked INTEGER NOT NULL DEFAULT 0")


def get_setting(key: str, default: str | None = None) -> str | None:
    conn = get_conn()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default
    finally:
        conn.close()


def set_setting(key: str, value: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()
    finally:
        conn.close()


def all_settings() -> dict[str, str]:
    conn = get_conn()
    try:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}
    finally:
        conn.close()


def worker_get(key: str, default: str | None = None) -> str | None:
    conn = get_conn()
    try:
        row = conn.execute("SELECT value FROM worker_state WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default
    finally:
        conn.close()


def worker_set(key: str, value: str) -> None:
    with _DB_LOCK:
        conn = get_conn()
        try:
            conn.execute(
                "INSERT INTO worker_state(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            conn.commit()
        finally:
            conn.close()


def worker_log(job: str, message: str, level: str = "info", payload: dict | None = None) -> None:
    """Append one line to the live discovery feed (keeps the last 300)."""
    with _DB_LOCK:
        conn = get_conn()
        try:
            conn.execute(
                "INSERT INTO worker_log(job, level, message, payload) VALUES (?,?,?,?)",
                (job, level, message, json.dumps(payload) if payload else None),
            )
            conn.execute(
                "DELETE FROM worker_log WHERE id NOT IN "
                "(SELECT id FROM worker_log ORDER BY id DESC LIMIT 300)"
            )
            conn.commit()
        finally:
            conn.close()


def worker_log_tail(limit: int = 80) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, ts, job, level, message, payload FROM worker_log "
            "ORDER BY id DESC LIMIT ?",
            (max(1, min(limit, 300)),),
        ).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            if item.get("payload"):
                try:
                    item["payload"] = json.loads(item["payload"])
                except json.JSONDecodeError:
                    pass
            out.append(item)
        return out
    finally:
        conn.close()
