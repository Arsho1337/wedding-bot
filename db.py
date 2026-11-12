"""SQLite storage. Small, synchronous, single-process — fine for one studio.

Call `init_db()` once at startup; every helper then reuses that connection.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path

import config

_conn: sqlite3.Connection | None = None
_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    code          TEXT    NOT NULL UNIQUE,
    customer_name TEXT    NOT NULL,
    stage         INTEGER NOT NULL DEFAULT 0,
    delivery_date TEXT,
    note          TEXT,
    cust_tg_id    INTEGER UNIQUE,
    created_at    TEXT    NOT NULL,
    updated_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS media (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    url        TEXT    NOT NULL,
    label      TEXT,
    created_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    actor      TEXT,
    kind       TEXT    NOT NULL,
    detail     TEXT,
    created_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS staff (
    tg_id      INTEGER PRIMARY KEY,
    role       TEXT    NOT NULL DEFAULT 'crew',
    project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    added_at   TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_media_project ON media(project_id);
CREATE INDEX IF NOT EXISTS idx_events_project ON events(project_id);
"""


def _now() -> str:
    return datetime.now(config.TZ).isoformat(timespec="seconds")


def init_db(path: str | None = None) -> None:
    """Open (or create) the database. Safe to call twice."""
    global _conn
    target = path or config.DB_PATH
    Path(target).parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        if _conn is not None:
            return
        conn = sqlite3.connect(target, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(SCHEMA)
        conn.commit()
        _conn = conn


def _db() -> sqlite3.Connection:
    if _conn is None:
        raise RuntimeError("db.init_db() was not called")
    return _conn


def close() -> None:
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
            _conn = None


# --------------------------------------------------------------------------
# Projects
# --------------------------------------------------------------------------
def create_project(code: str, customer_name: str) -> sqlite3.Row:
    ts = _now()
    with _lock:
        _db().execute(
            "INSERT INTO projects (code, customer_name, stage, created_at, updated_at)"
            " VALUES (?, ?, 0, ?, ?)",
            (code, customer_name, ts, ts),
        )
        _db().commit()
    return project_by_code(code)


def project_by_code(code: str) -> sqlite3.Row | None:
    return _db().execute(
        "SELECT * FROM projects WHERE code = ?", (code,)
    ).fetchone()


def project_by_id(project_id: int) -> sqlite3.Row | None:
    return _db().execute(
        "SELECT * FROM projects WHERE id = ?", (int(project_id),)
    ).fetchone()


def project_by_customer(tg_id: int) -> sqlite3.Row | None:
    return _db().execute(
        "SELECT * FROM projects WHERE cust_tg_id = ?", (int(tg_id),)
    ).fetchone()


def project_by_name(name: str) -> sqlite3.Row | None:
    """Exact match first, then a lenient substring match."""
    name = (name or "").strip()
    if not name:
        return None
    row = _db().execute(
        "SELECT * FROM projects WHERE lower(customer_name) = lower(?)", (name,)
    ).fetchone()
    if row:
        return row
    return _db().execute(
        "SELECT * FROM projects WHERE lower(customer_name) LIKE lower(?)"
        " ORDER BY id DESC LIMIT 1",
        (f"%{name}%",),
    ).fetchone()


def list_projects() -> list[sqlite3.Row]:
    return _db().execute(
        "SELECT * FROM projects ORDER BY id DESC"
    ).fetchall()


def bind_customer(project_id: int, tg_id: int) -> bool:
    """Attach a Telegram account to a project, only if still unclaimed.

    Returns False when the project was already claimed or the account is
    already attached elsewhere (UNIQUE(cust_tg_id)).
    """
    with _lock:
        try:
            cur = _db().execute(
                "UPDATE projects SET cust_tg_id = ?, updated_at = ?"
                " WHERE id = ? AND cust_tg_id IS NULL",
                (int(tg_id), _now(), int(project_id)),
            )
            _db().commit()
        except sqlite3.IntegrityError:
            _db().rollback()
            return False
        return cur.rowcount == 1


def reset_customer(project_id: int) -> bool:
    with _lock:
        cur = _db().execute(
            "UPDATE projects SET cust_tg_id = NULL, updated_at = ? WHERE id = ?"
            " AND cust_tg_id IS NOT NULL",
            (_now(), int(project_id)),
        )
        _db().commit()
        return cur.rowcount == 1


def set_stage(project_id: int, stage: int) -> None:
    with _lock:
        _db().execute(
            "UPDATE projects SET stage = ?, updated_at = ? WHERE id = ?",
            (int(stage), _now(), int(project_id)),
        )
        _db().commit()


def set_note(project_id: int, note: str | None) -> None:
    with _lock:
        _db().execute(
            "UPDATE projects SET note = ?, updated_at = ? WHERE id = ?",
            (note, _now(), int(project_id)),
        )
        _db().commit()


def set_delivery(project_id: int, date: str) -> None:
    with _lock:
        _db().execute(
            "UPDATE projects SET delivery_date = ?, updated_at = ? WHERE id = ?",
            (date, _now(), int(project_id)),
        )
        _db().commit()


# --------------------------------------------------------------------------
# Media
# --------------------------------------------------------------------------
def add_media(project_id: int, url: str, label: str | None = None) -> None:
    with _lock:
        _db().execute(
            "INSERT INTO media (project_id, url, label, created_at) VALUES (?, ?, ?, ?)",
            (int(project_id), url, label, _now()),
        )
        _db().commit()


def list_media(project_id: int) -> list[sqlite3.Row]:
    return _db().execute(
        "SELECT * FROM media WHERE project_id = ? ORDER BY id DESC",
        (int(project_id),),
    ).fetchall()


# --------------------------------------------------------------------------
# Audit trail
# --------------------------------------------------------------------------
def log_event(project_id: int, actor: str | None, kind: str, detail: str | None = None) -> None:
    with _lock:
        _db().execute(
            "INSERT INTO events (project_id, actor, kind, detail, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (int(project_id), actor, kind, detail, _now()),
        )
        _db().commit()


def recent_events(project_id: int, limit: int = 20) -> list[sqlite3.Row]:
    return _db().execute(
        "SELECT * FROM events WHERE project_id = ? ORDER BY id DESC LIMIT ?",
        (int(project_id), int(limit)),
    ).fetchall()


# --------------------------------------------------------------------------
# Staff (crew accounts)
# --------------------------------------------------------------------------
def add_staff(tg_id: int, project_id: int | None = None, role: str = "crew") -> None:
    with _lock:
        _db().execute(
            "INSERT INTO staff (tg_id, role, project_id, added_at) VALUES (?, ?, ?, ?)"
            " ON CONFLICT(tg_id) DO UPDATE SET role = excluded.role,"
            " project_id = excluded.project_id",
            (int(tg_id), role, project_id, _now()),
        )
        _db().commit()


def get_staff(tg_id: int) -> sqlite3.Row | None:
    return _db().execute(
        "SELECT * FROM staff WHERE tg_id = ?", (int(tg_id),)
    ).fetchone()


def remove_staff(tg_id: int) -> bool:
    with _lock:
        cur = _db().execute("DELETE FROM staff WHERE tg_id = ?", (int(tg_id),))
        _db().commit()
        return cur.rowcount == 1


def list_staff() -> list[sqlite3.Row]:
    return _db().execute(
        "SELECT s.*, p.code AS project_code, p.customer_name AS customer_name"
        " FROM staff s LEFT JOIN projects p ON p.id = s.project_id"
        " ORDER BY s.tg_id"
    ).fetchall()
