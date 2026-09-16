"""
Zaxira (fallback) saqlash qatlami – mahalliy SQLite.

Supabase sozlanmagan bo'lsa (``.env`` da SUPABASE_DB_URL yo'q), bot shu
backendda to'liq ishlaydi.  URL qo'shilishi bilan keyingi ishga tushirishda
bot avtomatik Supabasega o'tadi va mavjud bot.db ma'lumotlarini bir marta
import qiladi (app/database.py dagi Postgres klassiga qarang).

Metodlar va qaytariladigan ma'lumot shakllari Postgres versiyasi bilan
AYNAN bir xil — handlerlar farqni sezmaydi.

Bot jadvallari: ``users``, ``events``, ``connections`` va ``access``
(kirish nazorati).  Premium/obuna OLIB TASHLANGAN.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

import aiosqlite

from app.config import settings
from app.utils.timeutils import now_iso

logger = logging.getLogger(__name__)


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id        INTEGER PRIMARY KEY,
    username       TEXT,
    first_name     TEXT,
    last_name      TEXT,
    connected_at   TEXT,
    last_activity  TEXT,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    sender_id    INTEGER,
    chat_id      INTEGER,
    chat_title   TEXT,
    event_type   TEXT NOT NULL,
    message_id   INTEGER,
    details      TEXT NOT NULL DEFAULT '',
    occurred_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS connections (
    business_connection_id TEXT PRIMARY KEY,
    user_id                INTEGER NOT NULL,
    user_chat_id           INTEGER,
    is_enabled             INTEGER NOT NULL DEFAULT 1,
    connected_at           TEXT,
    disconnected_at        TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_time   ON events (occurred_at);
CREATE INDEX IF NOT EXISTS idx_events_type   ON events (event_type);
CREATE INDEX IF NOT EXISTS idx_events_user   ON events (user_id);
CREATE INDEX IF NOT EXISTS idx_events_chat_message ON events (chat_id, message_id);

CREATE TABLE IF NOT EXISTS access (
    user_id     INTEGER PRIMARY KEY,
    status      TEXT NOT NULL,
    username    TEXT,
    first_name  TEXT,
    decided_by  INTEGER,
    created_at  TEXT NOT NULL,
    decided_at  TEXT
);
"""


class SqliteDatabase:
    """Local SQLite backend (fallback).  Same API as the Postgres one."""

    def __init__(self) -> None:
        self._conn: Optional[aiosqlite.Connection] = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database is not initialised - call init() first")
        return self._conn

    async def init(self) -> None:
        self._conn = await aiosqlite.connect(settings.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA busy_timeout=5000")
        await self._conn.executescript(SCHEMA)
        # Migratsiya: eski bot.db da 'sender_id' ustuni bo'lmasligi mumkin
        # (xabar KIMdan kelganini saqlash — o'z-o'zini o'chirish uchun).
        cursor = await self._conn.execute("PRAGMA table_info(events)")
        event_cols = {row[1] for row in await cursor.fetchall()}
        await cursor.close()
        if "sender_id" not in event_cols:
            await self._conn.execute("ALTER TABLE events ADD COLUMN sender_id INTEGER")
        await self._conn.commit()
        logger.info("SQLite ready at %s (Supabase not configured)", settings.db_path)

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
            logger.info("SQLite closed")

    # -- raw helpers ----------------------------------------------------------

    async def _fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        cursor = await self.conn.execute(sql, params)
        rows = await cursor.fetchall()
        await cursor.close()
        return [dict(r) for r in rows]

    async def _fetch_one(self, sql: str, params: tuple = ()) -> Optional[dict]:
        cursor = await self.conn.execute(sql, params)
        row = await cursor.fetchone()
        await cursor.close()
        return dict(row) if row else None

    async def _fetchval(self, sql: str, params: tuple = ()) -> Any:
        cursor = await self.conn.execute(sql, params)
        row = await cursor.fetchone()
        await cursor.close()
        return row[0] if row else None

    async def _execute(self, sql: str, params: tuple = ()) -> int:
        cursor = await self.conn.execute(sql, params)
        await self._conn.commit()
        return cursor.lastrowid or 0

    def _q(self, sql: str) -> str:
        """Convert a $n-placeholder query to SQLite '?' style."""
        out = sql
        for i in range(20, 0, -1):
            out = out.replace(f"${i}", "?")
        return out

    async def _fo(self, sql: str, *params: Any) -> Optional[dict]:
        return await self._fetch_one(self._q(sql), tuple(params))

    # ======================================================================
    # USERS  (query bodies mirror app/database.py — keep them in sync)
    # ======================================================================

    async def upsert_user(
        self,
        user_id: int,
        username: Optional[str],
        first_name: Optional[str],
        last_name: Optional[str],
    ) -> None:
        now = now_iso()
        await self._execute(
            """
            INSERT INTO users (user_id, username, first_name, last_name,
                               connected_at, last_activity, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username   = excluded.username,
                first_name = excluded.first_name,
                last_name  = excluded.last_name,
                last_activity = excluded.last_activity
            """,
            (user_id, username, first_name, last_name, now, now, now),
        )

    async def touch_user(self, user_id: int) -> None:
        await self._execute(
            "UPDATE users SET last_activity = ? WHERE user_id = ?",
            (now_iso(), user_id),
        )

    async def get_user(self, user_id: int) -> Optional[dict]:
        return await self._fo("SELECT * FROM users WHERE user_id = $1", user_id)

    async def all_users(self) -> list[dict]:
        return await self._fetch_all("SELECT * FROM users ORDER BY created_at DESC")

    async def online_users(self, window_seconds: int = 120) -> list[dict]:
        threshold = (datetime.now() - timedelta(seconds=window_seconds)).isoformat(
            timespec="seconds"
        )
        return await self._fetch_all(
            """
            SELECT * FROM users
            WHERE last_activity >= ?
            ORDER BY last_activity DESC
            """,
            (threshold,),
        )

    async def count_users(self) -> int:
        row = await self._fetch_one("SELECT COUNT(*) AS n FROM users")
        return row["n"] if row else 0

    async def count_online(self, window_seconds: int = 120) -> int:
        threshold = (datetime.now() - timedelta(seconds=window_seconds)).isoformat(
            timespec="seconds"
        )
        row = await self._fetch_one(
            "SELECT COUNT(*) AS n FROM users WHERE last_activity >= ?",
            (threshold,),
        )
        return row["n"] if row else 0

    async def user_stats(self, user_id: int) -> dict:
        """Statistika ekranining barcha raqamlari — BITTA so'rov
        (Postgres backenddagisi bilan AYNAN bir xil natija)."""
        row = await self._fetch_one(
            """
            SELECT
              (SELECT COUNT(*) FROM users)                        AS users_total,
              (SELECT COUNT(*) FROM events WHERE user_id = ?)     AS events_total,
              (SELECT COUNT(*) FROM events
                 WHERE user_id = ? AND event_type = 'edit')       AS edits,
              (SELECT COUNT(*) FROM events
                 WHERE user_id = ? AND event_type = 'delete')     AS deletes,
              (SELECT COUNT(*) FROM events
                 WHERE user_id = ? AND event_type = 'delete_media') AS deletes_media,
              (SELECT COUNT(*) FROM connections
                 WHERE user_id = ? AND is_enabled = 1)            AS active_connections
            """,
            (user_id, user_id, user_id, user_id, user_id),
        )
        row = row or {}
        return {
            "users_total": int(row.get("users_total") or 0),
            "events_total": int(row.get("events_total") or 0),
            "edits": int(row.get("edits") or 0),
            "deletes": int(row.get("deletes") or 0),
            "deletes_media": int(row.get("deletes_media") or 0),
            "active_connections": int(row.get("active_connections") or 0),
        }

    async def has_active_connection(self, user_id: int) -> bool:
        """/start uchun: faol biznes-ulanish bormi (1 so'rov)."""
        value = await self._fetchval(
            "SELECT EXISTS(SELECT 1 FROM connections WHERE user_id = ? AND is_enabled = 1)",
            (user_id,),
        )
        return bool(value)

    # ======================================================================
    # EVENTS
    # ======================================================================

    async def add_event(
        self,
        user_id: int,
        event_type: str,
        details: str,
        chat_id: Optional[int] = None,
        chat_title: Optional[str] = None,
        message_id: Optional[int] = None,
        sender_id: Optional[int] = None,
    ) -> None:
        await self._execute(
            """
            INSERT INTO events (user_id, chat_id, chat_title, event_type,
                                message_id, details, sender_id, occurred_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, chat_id, chat_title, event_type, message_id, details,
             sender_id, now_iso()),
        )

    async def recent_events(self, limit: int = 20) -> list[dict]:
        return await self._fetch_all(
            "SELECT * FROM events ORDER BY occurred_at DESC LIMIT ?", (limit,)
        )

    async def count_events(
        self, event_type: Optional[str] = None, since: Optional[datetime] = None
    ) -> int:
        sql = "SELECT COUNT(*) AS n FROM events WHERE 1=1"
        params: list[Any] = []
        if event_type:
            sql += " AND event_type = ?"
            params.append(event_type)
        if since:
            sql += " AND occurred_at >= ?"
            params.append(since.isoformat(timespec="seconds"))
        row = await self._fetch_one(sql, tuple(params))
        return row["n"] if row else 0

    async def count_user_events(self, user_id: int, event_type: Optional[str] = None) -> int:
        sql = "SELECT COUNT(*) AS n FROM events WHERE user_id = ?"
        params: list[Any] = [user_id]
        if event_type:
            sql += " AND event_type = ?"
            params.append(event_type)
        row = await self._fetch_one(sql, tuple(params))
        return row["n"] if row else 0

    async def get_event_by_message(self, chat_id: int, message_id: int) -> Optional[dict]:
        return await self._fo(
            """
            SELECT * FROM events
            WHERE chat_id = $1 AND message_id = $2
            ORDER BY id DESC LIMIT 1
            """,
            chat_id,
            message_id,
        )

    async def update_event_details(
        self, chat_id: int, message_id: int, details: str
    ) -> bool:
        """Shu xabar yozuvini joyida yangilash (tahrirlash holati)."""
        cursor = await self.conn.execute(
            """
            UPDATE events SET details = ?
            WHERE id = (
                SELECT id FROM events
                WHERE chat_id = ? AND message_id = ?
                ORDER BY id DESC LIMIT 1
            )
            """,
            (details, chat_id, message_id),
        )
        await self._conn.commit()
        return (cursor.rowcount or 0) > 0

    async def prune_events(self, keep: int = 20_000) -> None:
        await self._execute(
            """
            DELETE FROM events WHERE id NOT IN (
                SELECT id FROM events ORDER BY id DESC LIMIT ?
            )
            """,
            (keep,),
        )

    # ======================================================================
    # CONNECTIONS
    # ======================================================================

    async def upsert_connection(
        self,
        business_connection_id: str,
        user_id: int,
        is_enabled: bool,
        user_chat_id: Optional[int] = None,
    ) -> None:
        now = now_iso()
        existing = await self._fo(
            "SELECT * FROM connections WHERE business_connection_id = $1",
            business_connection_id,
        )
        if existing is None:
            await self._execute(
                """
                INSERT INTO connections
                    (business_connection_id, user_id, user_chat_id, is_enabled, connected_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (business_connection_id, user_id, user_chat_id, 1 if is_enabled else 0, now),
            )
        else:
            connected_at = existing.get("connected_at")
            disconnected_at = existing.get("disconnected_at")
            if is_enabled:
                disconnected_at = None
                connected_at = connected_at or now
            else:
                disconnected_at = now
            await self._execute(
                """
                UPDATE connections
                SET is_enabled = ?, connected_at = ?, disconnected_at = ?,
                    user_chat_id = COALESCE(?, user_chat_id)
                WHERE business_connection_id = ?
                """,
                (1 if is_enabled else 0, connected_at, disconnected_at, user_chat_id,
                 business_connection_id),
            )

    async def get_connection(self, business_connection_id: str) -> Optional[dict]:
        return await self._fo(
            "SELECT * FROM connections WHERE business_connection_id = $1",
            business_connection_id,
        )

    async def connected_user_ids(self) -> list[int]:
        rows = await self._fetch_all(
            "SELECT DISTINCT user_id FROM connections WHERE is_enabled = 1"
        )
        return [row["user_id"] for row in rows]

    async def connections_for_user(self, user_id: int) -> list[dict]:
        return await self._fetch_all(
            "SELECT * FROM connections WHERE user_id = ? ORDER BY connected_at DESC",
            (user_id,),
        )

    # ======================================================================
    # ACCESS (allow / deny / ban) — app/services/access.py keshga yuklaydi
    # ======================================================================

    async def access_rows(self) -> list[dict]:
        """Barcha kirish yozuvlari (ishga tushishda bir marta o'qiladi)."""
        return await self._fetch_all("SELECT * FROM access")

    async def set_access(
        self,
        user_id: int,
        status: str,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        decided_by: Optional[int] = None,
    ) -> None:
        """Yozuvni yaratadi yoki holatini yangilaydi (bitta so'rov)."""
        now = now_iso()
        decided_at = now if decided_by else None
        await self._execute(
            """
            INSERT INTO access (user_id, status, username, first_name,
                                decided_by, created_at, decided_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                status     = excluded.status,
                username   = COALESCE(excluded.username, access.username),
                first_name = COALESCE(excluded.first_name, access.first_name),
                decided_by = excluded.decided_by,
                decided_at = excluded.decided_at
            """,
            (user_id, status, username, first_name, decided_by, now, decided_at),
        )
