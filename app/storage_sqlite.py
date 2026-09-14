"""
Zaxira (fallback) saqlash qatlami – mahalliy SQLite.

Supabase sozlanmagan bo'lsa (``.env`` da SUPABASE_DB_URL yo'q), bot shu
backendda to'liq ishlaydi.  URL qo'shilishi bilan keyingi ishga tushirishda
bot avtomatik Supabasega o'tadi va mavjud bot.db ma'lumotlarini bir marta
import qiladi (app/database.py dagi Postgres klassiga qarang).

Metodlar va qaytariladigan ma'lumot shakllari Postgres versiyasi bilan
AYNAN bir xil — handlerlar farqni sezmaydi.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

import aiosqlite

from app.config import settings
from app.utils.timeutils import now_iso, parse_dt

logger = logging.getLogger(__name__)


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id        INTEGER PRIMARY KEY,
    username       TEXT,
    first_name     TEXT,
    last_name      TEXT,
    is_banned      INTEGER NOT NULL DEFAULT 0,
    access_status  TEXT NOT NULL DEFAULT 'pending',
    reviewed_by    INTEGER,
    reviewed_at    TEXT,
    is_admin       INTEGER NOT NULL DEFAULT 0,
    premium_until  TEXT,
    connected_at   TEXT,
    last_activity  TEXT,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS plans (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    title          TEXT NOT NULL,
    duration_days  INTEGER NOT NULL,
    price          INTEGER NOT NULL,
    description    TEXT NOT NULL DEFAULT '',
    is_active      INTEGER NOT NULL DEFAULT 1,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS payments (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          INTEGER NOT NULL,
    plan_id          INTEGER NOT NULL,
    receipt_file_id  TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'pending',
    created_at       TEXT NOT NULL,
    reviewed_at      TEXT,
    reviewed_by      INTEGER
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
CREATE INDEX IF NOT EXISTS idx_payments_stat ON payments (status);

CREATE TABLE IF NOT EXISTS bot_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _b(value: Any) -> bool:
    return bool(value)


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
        # Migration for DBs created before the approval feature existed.
        cursor = await self._conn.execute("PRAGMA table_info(users)")
        cols = {row[1] for row in await cursor.fetchall()}
        await cursor.close()
        if "access_status" not in cols:
            await self._conn.execute(
                "ALTER TABLE users ADD COLUMN access_status TEXT NOT NULL DEFAULT 'approved'"
            )
            await self._conn.execute("ALTER TABLE users ADD COLUMN reviewed_by INTEGER")
            await self._conn.execute("ALTER TABLE users ADD COLUMN reviewed_at TEXT")
        # Migratsiya: xabar KIMdan kelganini saqlash (o'z-o'zini o'chirish).
        cur2 = await self._conn.execute("PRAGMA table_info(events)")
        event_cols = {row[1] for row in await cur2.fetchall()}
        await cur2.close()
        if "sender_id" not in event_cols:
            await self._conn.execute("ALTER TABLE events ADD COLUMN sender_id INTEGER")
        await self._conn.execute(
            "UPDATE users SET access_status = 'approved' WHERE user_id = ?",
            (settings.admin_id,),
        )
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

    async def _fq(self, sql: str, *params: Any) -> list[dict]:
        return await self._fetch_all(self._q(sql), tuple(params))

    async def _fo(self, sql: str, *params: Any) -> Optional[dict]:
        return await self._fetch_one(self._q(sql), tuple(params))

    async def _fv(self, sql: str, *params: Any) -> Any:
        return await self._fetchval(self._q(sql), tuple(params))

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
        if user_id == settings.admin_id:
            await self._execute(
                "UPDATE users SET access_status = 'approved' WHERE user_id = ?",
                (user_id,),
            )

    async def touch_user(self, user_id: int) -> None:
        await self._execute(
            "UPDATE users SET last_activity = ? WHERE user_id = ?",
            (now_iso(), user_id),
        )

    async def get_user(self, user_id: int) -> Optional[dict]:
        return await self._fo("SELECT * FROM users WHERE user_id = $1", user_id)

    async def all_users(self, only_active: bool = False) -> list[dict]:
        where = "WHERE is_banned = 0 AND access_status = 'approved'" if only_active else ""
        return await self._fetch_all(f"SELECT * FROM users {where} ORDER BY created_at DESC")

    async def online_users(self, window_seconds: int = 120) -> list[dict]:
        threshold = (datetime.now() - timedelta(seconds=window_seconds)).isoformat(
            timespec="seconds"
        )
        return await self._fo_all_online(threshold)

    async def _fo_all_online(self, threshold: str) -> list[dict]:
        return await self._fetch_all(
            """
            SELECT * FROM users
            WHERE last_activity >= ? AND is_banned = 0
            ORDER BY last_activity DESC
            """,
            (threshold,),
        )

    async def count_users(self, only_active: bool = False) -> int:
        where = "WHERE is_banned = 0 AND access_status = 'approved'" if only_active else ""
        row = await self._fetch_one(f"SELECT COUNT(*) AS n FROM users {where}")
        return row["n"] if row else 0

    async def count_online(self, window_seconds: int = 120) -> int:
        threshold = (datetime.now() - timedelta(seconds=window_seconds)).isoformat(
            timespec="seconds"
        )
        row = await self._fetch_one(
            "SELECT COUNT(*) AS n FROM users WHERE last_activity >= ? AND is_banned = 0",
            (threshold,),
        )
        return row["n"] if row else 0

    async def set_banned(self, user_id: int, banned: bool) -> None:
        await self._execute(
            "UPDATE users SET is_banned = ? WHERE user_id = ?",
            (1 if banned else 0, user_id),
        )

    async def set_admin(self, user_id: int, is_admin: bool) -> None:
        await self._execute(
            "UPDATE users SET is_admin = ? WHERE user_id = ?",
            (1 if is_admin else 0, user_id),
        )

    async def all_admins(self) -> list[int]:
        rows = await self._fetch_all("SELECT user_id FROM users WHERE is_admin = 1")
        ids = {row["user_id"] for row in rows}
        ids.add(settings.admin_id)
        return sorted(ids)

    # -- access approval --------------------------------------------------------

    async def set_access(self, user_id: int, status: str, reviewed_by: int) -> None:
        await self._execute(
            "UPDATE users SET access_status = ?, reviewed_by = ?, reviewed_at = ? WHERE user_id = ?",
            (status, reviewed_by, now_iso(), user_id),
        )

    async def pending_access_users(self) -> list[dict]:
        return await self._fetch_all(
            """
            SELECT * FROM users
            WHERE access_status = 'pending' AND is_banned = 0 AND user_id != ?
            ORDER BY created_at DESC
            """,
            (settings.admin_id,),
        )

    async def count_pending_access(self) -> int:
        row = await self._fetch_one(
            "SELECT COUNT(*) AS n FROM users WHERE access_status = 'pending' AND user_id != ?",
            (settings.admin_id,),
        )
        return row["n"] if row else 0

    # -- premium ------------------------------------------------------------------

    async def set_premium(self, user_id: int, until: Optional[datetime]) -> None:
        await self._execute(
            "UPDATE users SET premium_until = ? WHERE user_id = ?",
            (until.isoformat(timespec="seconds") if until else None, user_id),
        )

    async def extend_premium(self, user_id: int, days: int) -> datetime:
        user = await self.get_user(user_id)
        base = parse_dt(user.get("premium_until")) if user else None
        now = datetime.now()
        start = base if base and base > now else now
        until = start + timedelta(days=days)
        await self.set_premium(user_id, until)
        return until

    async def premium_users(self) -> list[dict]:
        return await self._fetch_all(
            "SELECT * FROM users WHERE premium_until IS NOT NULL AND premium_until > ?",
            (now_iso(),),
        )

    async def expired_premium_users(self) -> list[dict]:
        return await self._fetch_all(
            "SELECT * FROM users WHERE premium_until IS NOT NULL AND premium_until <= ?",
            (now_iso(),),
        )

    # ======================================================================
    # PLANS
    # ======================================================================

    async def create_plan(
        self, title: str, duration_days: int, price: int, description: str
    ) -> int:
        return await self._execute(
            """
            INSERT INTO plans (title, duration_days, price, description, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (title, duration_days, price, description, now_iso()),
        )

    async def get_plan(self, plan_id: int) -> Optional[dict]:
        return await self._fo("SELECT * FROM plans WHERE id = $1", plan_id)

    async def active_plans(self) -> list[dict]:
        return await self._fetch_all(
            "SELECT * FROM plans WHERE is_active = 1 ORDER BY duration_days"
        )

    async def all_plans(self) -> list[dict]:
        return await self._fetch_all("SELECT * FROM plans ORDER BY created_at DESC")

    async def set_plan_active(self, plan_id: int, active: bool) -> None:
        await self._execute(
            "UPDATE plans SET is_active = ? WHERE id = ?",
            (1 if active else 0, plan_id),
        )

    async def update_plan(self, plan_id: int, **fields) -> None:
        """Tarif maydonlarini yangilash (tahrirlash rejimi)."""
        allowed = {"title", "duration_days", "price", "description"}
        sets, params = [], []
        for key, value in fields.items():
            if key in allowed:
                sets.append(f"{key} = ?")
                params.append(value)
        if not sets:
            return
        params.append(plan_id)
        await self._execute(
            f"UPDATE plans SET {', '.join(sets)} WHERE id = ?", tuple(params)
        )

    async def delete_plan(self, plan_id: int) -> None:
        await self._execute("DELETE FROM plans WHERE id = ?", (plan_id,))

    # ======================================================================
    # PAYMENTS
    # ======================================================================

    async def create_payment(self, user_id: int, plan_id: int, receipt_file_id: str) -> int:
        return await self._execute(
            """
            INSERT INTO payments (user_id, plan_id, receipt_file_id, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, plan_id, receipt_file_id, now_iso()),
        )

    async def get_payment(self, payment_id: int) -> Optional[dict]:
        return await self._fo("SELECT * FROM payments WHERE id = $1", payment_id)

    async def pending_payments(self) -> list[dict]:
        return await self._fetch_all(
            "SELECT * FROM payments WHERE status = 'pending' ORDER BY created_at"
        )

    async def payment_with_plan(self, payment_id: int) -> Optional[dict]:
        return await self._fo(
            """
            SELECT p.*, pl.duration_days AS duration_days
            FROM payments p LEFT JOIN plans pl ON pl.id = p.plan_id
            WHERE p.id = $1
            """,
            payment_id,
        )

    async def set_payment_status(self, payment_id: int, status: str, reviewed_by: int) -> None:
        await self._execute(
            "UPDATE payments SET status = ?, reviewed_at = ?, reviewed_by = ? WHERE id = ?",
            (status, now_iso(), reviewed_by, payment_id),
        )

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
        return await self._fq(
            "SELECT * FROM connections WHERE user_id = $1 ORDER BY connected_at DESC",
            user_id,
        )

    # -- bot settings -----------------------------------------------------------

    async def get_setting(self, key: str, default: str = "") -> str:
        value = await self._fetchval(
            "SELECT value FROM bot_settings WHERE key = ?", (key,)
        )
        return value if value is not None else default

    async def set_setting(self, key: str, value: str) -> None:
        await self._execute(
            """
            INSERT INTO bot_settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
