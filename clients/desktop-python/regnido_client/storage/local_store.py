import sqlite3
from pathlib import Path
from typing import Any


class LocalStore:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pending_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_event_id TEXT NOT NULL UNIQUE,
                bambino_id TEXT NOT NULL,
                dispositivo_id TEXT NOT NULL,
                tipo_evento TEXT NOT NULL,
                timestamp_evento TEXT NOT NULL,
                error_message TEXT,
                last_try_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self._conn.commit()

    def set_setting(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self._conn.commit()

    def get_setting(self, key: str, default: str = "") -> str:
        row = self._conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if not row:
            return default
        return str(row["value"])

    def enqueue_event(self, event: dict[str, str]) -> None:
        self._conn.execute(
            """
            INSERT OR IGNORE INTO pending_events(
                client_event_id,
                bambino_id,
                dispositivo_id,
                tipo_evento,
                timestamp_evento
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                event["client_event_id"],
                event["bambino_id"],
                event["dispositivo_id"],
                event["tipo_evento"],
                event["timestamp_evento"],
            ),
        )
        self._conn.commit()

    def list_pending_events(self, limit: int = 200) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT id, client_event_id, bambino_id, dispositivo_id, tipo_evento, timestamp_evento,
                   error_message, last_try_at, created_at
            FROM pending_events
            ORDER BY id ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def mark_event_error(self, client_event_id: str, error_message: str) -> None:
        self._conn.execute(
            "UPDATE pending_events SET error_message = ?, last_try_at = CURRENT_TIMESTAMP WHERE client_event_id = ?",
            (error_message[:400], client_event_id),
        )
        self._conn.commit()

    def remove_events(self, client_event_ids: list[str]) -> None:
        if not client_event_ids:
            return
        placeholders = ",".join("?" for _ in client_event_ids)
        self._conn.execute(
            f"DELETE FROM pending_events WHERE client_event_id IN ({placeholders})",
            tuple(client_event_ids),
        )
        self._conn.commit()

    def count_pending(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS n FROM pending_events").fetchone()
        return int(row["n"]) if row else 0
