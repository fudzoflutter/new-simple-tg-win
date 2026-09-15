"""
Saqlash qatlami – AVTOMATIK backend tanlovi.

* ``.env`` da SUPABASE_DB_URL bor bo'lsa  -> Supabase Postgres (asyncpg)
* yo'q bo'lsa                             -> mahalliy SQLite (zaxira)

Ikkala backend bir xil API beradi (app/storage_sqlite.py bilan solishtiring):
handlerlar qaysi backend ishlayotganini sezmaydi.

Supabase ulanishi (bir marta):
1. Supabase Dashboard -> loyihangiz -> yashil "Connect" tugmasi ->
   "Connection pooling" -> URI ni nusxalang:
   postgresql://postgres.xxxx:PAROL@aws-0-region.pooler.supabase.com:6543/postgres
2. .env ga yozing: SUPABASE_DB_URL=...
3. Botni qayta ishga tushiring — jadvallar avtomatik yaratiladi va mavjud
   bot.db ma'lumotlari BIR MARTA import qilinadi (supabase_migrations da
   belgilanadi).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema – Postgres version of the old SQLite schema.
# "IF NOT EXISTS" makes it safe to run on every startup.
# ---------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id        BIGINT PRIMARY KEY,
    username       TEXT,
    first_name     TEXT,
    last_name      TEXT,
    is_banned      BOOLEAN NOT NULL DEFAULT FALSE,
    access_status  TEXT NOT NULL DEFAULT 'approved',  -- tarixiy ustun; kirish hamma uchun ochiq
    reviewed_by    BIGINT,
    reviewed_at    TEXT,
    is_admin       BOOLEAN NOT NULL DEFAULT FALSE,
    premium_until  TEXT,
    connected_at   TEXT,
    last_activity  TEXT,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS plans (
    id             BIGSERIAL PRIMARY KEY,
    title          TEXT NOT NULL,
    duration_days  INTEGER NOT NULL,
    price          BIGINT NOT NULL,
    description    TEXT NOT NULL DEFAULT '',
    is_active      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS payments (
    id               BIGSERIAL PRIMARY KEY,
    user_id          BIGINT NOT NULL,
    plan_id          BIGINT NOT NULL,
    receipt_file_id  TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'pending',
    created_at       TEXT NOT NULL,
    reviewed_at      TEXT,
    reviewed_by      BIGINT
);

CREATE TABLE IF NOT EXISTS events (
    id           BIGSERIAL PRIMARY KEY,
    user_id      BIGINT NOT NULL,
    sender_id    BIGINT,
    chat_id      BIGINT,
    chat_title   TEXT,
    event_type   TEXT NOT NULL,
    message_id   BIGINT,
    details      TEXT NOT NULL DEFAULT '',
    occurred_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS connections (
    business_connection_id TEXT PRIMARY KEY,
    user_id                BIGINT NOT NULL,
    user_chat_id           BIGINT,
    is_enabled             BOOLEAN NOT NULL DEFAULT TRUE,
    connected_at           TEXT,
    disconnected_at        TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_time   ON events (occurred_at);
CREATE INDEX IF NOT EXISTS idx_events_type   ON events (event_type);
CREATE INDEX IF NOT EXISTS idx_events_user   ON events (user_id);
CREATE INDEX IF NOT EXISTS idx_events_chat_message ON events (chat_id, message_id);
CREATE INDEX IF NOT EXISTS idx_payments_stat ON payments (status);

-- One-time import marker (so we never import the same SQLite file twice).
CREATE TABLE IF NOT EXISTS supabase_migrations (
    name TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);

-- Bot sozlamalari (kalit-qiymat) — masalan, Premium bo'limi yoqilganligi.
CREATE TABLE IF NOT EXISTS bot_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Boshlang'ich qiymat: Premium bo'limi YOPIQ (SQLite backend ham shunday).
INSERT INTO bot_settings (key, value) VALUES ('premium_enabled', '0')
ON CONFLICT (key) DO NOTHING;
"""


def _now() -> str:
    """Current local time as ISO string (same as the SQLite version)."""
    return datetime.now().isoformat(timespec="seconds")


def parse_dt(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO timestamp stored in the DB (None-safe)."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _b(value: Any) -> bool:
    """Normalize ints/bools coming from different drivers to bool."""
    return bool(value)


class Database:
    """Fasad: real ishlarni Postgres yoki SQLite backend bajaradi.

    ``init()`` avtomatik tanlaydi:
    * SUPABASE_DB_URL berilgan bo'lsa  -> Postgres klassi (quyida)
    * aks holda                        -> app/storage_sqlite.SqliteDatabase
    """

    def __init__(self) -> None:
        self._backend: Any = None  # PostgresDatabase | SqliteDatabase
        # Tezlik: sozlamalar (key-value) uchun qisqa TTL kesh — har bir
        # ekran har safar DBga uchib ketmasin (5 sek yetarli).
        self._settings_cache: dict[str, tuple[float, str]] = {}

    # -- lifecycle ---------------------------------------------------------

    async def init(self) -> None:
        """Choose the backend and initialise it."""
        if settings.supabase_db_url:
            self._backend = PostgresDatabase()
            await self._backend.init()
        else:
            # Import here to avoid loading aiosqlite when Supabase is used.
            from app.storage_sqlite import SqliteDatabase

            self._backend = SqliteDatabase()
            await self._backend.init()
            logger.warning(
                "SUPABASE_DB_URL yo'q — hozircha mahalliy SQLite (%s) ishlatiladi. "
                "Supabasega o'tish uchun .env ga SUPABASE_DB_URL qo'shing.",
                settings.db_path,
            )

    async def close(self) -> None:
        if self._backend is not None:
            await self._backend.close()
            self._backend = None

    async def gather(self, *aws: Any) -> list[Any]:
        """Bir nechta DB so'rovini PARALLEL bajarish (tezlik uchun).

        Supabase Sydney ~200 ms uzoqda: 5 ta ketma-ket so'rov = 1 sekund,
        parallel = ~200 ms.  Havola havzasida (pool) parallel ishlaydi.

        Misol: ``user, conns, total = await db.gather(
            db.get_user(uid), db.connections_for_user(uid), db.count_user_events(uid))``
        """
        import asyncio

        return list(await asyncio.gather(*aws))

    # -- delegation -----------------------------------------------------------
    # Har bir metod real backendga yo'naltiriladi.

    async def upsert_user(self, user_id: int, username, first_name, last_name) -> None:
        await self._backend.upsert_user(user_id, username, first_name, last_name)

    async def touch_user(self, user_id: int) -> None:
        await self._backend.touch_user(user_id)

    async def get_user(self, user_id: int) -> Optional[dict]:
        return await self._backend.get_user(user_id)

    async def all_users(self, only_active: bool = False) -> list[dict]:
        return await self._backend.all_users(only_active)

    async def online_users(self, window_seconds: int = 120) -> list[dict]:
        return await self._backend.online_users(window_seconds)

    async def count_users(self, only_active: bool = False) -> int:
        return await self._backend.count_users(only_active)

    async def count_online(self, window_seconds: int = 120) -> int:
        return await self._backend.count_online(window_seconds)

    async def set_banned(self, user_id: int, banned: bool) -> None:
        await self._backend.set_banned(user_id, banned)

    async def set_admin(self, user_id: int, is_admin: bool) -> None:
        await self._backend.set_admin(user_id, is_admin)

    async def all_admins(self) -> list[int]:
        return await self._backend.all_admins()


    async def set_premium(self, user_id: int, until: Optional[datetime]) -> None:
        await self._backend.set_premium(user_id, until)

    async def extend_premium(self, user_id: int, days: int) -> datetime:
        return await self._backend.extend_premium(user_id, days)

    async def premium_users(self) -> list[dict]:
        return await self._backend.premium_users()

    async def expired_premium_users(self) -> list[dict]:
        return await self._backend.expired_premium_users()

    async def create_plan(self, title: str, duration_days: int, price: int, description: str) -> int:
        return await self._backend.create_plan(title, duration_days, price, description)

    async def get_plan(self, plan_id: int) -> Optional[dict]:
        return await self._backend.get_plan(plan_id)

    async def active_plans(self) -> list[dict]:
        return await self._backend.active_plans()

    async def all_plans(self) -> list[dict]:
        return await self._backend.all_plans()

    async def set_plan_active(self, plan_id: int, active: bool) -> None:
        await self._backend.set_plan_active(plan_id, active)

    async def update_plan(self, plan_id: int, **fields) -> None:
        """Tarif maydonlarini yangilash (title, duration_days, price, description)."""
        await self._backend.update_plan(plan_id, **fields)

    async def delete_plan(self, plan_id: int) -> None:
        await self._backend.delete_plan(plan_id)

    async def create_payment(self, user_id: int, plan_id: int, receipt_file_id: str) -> int:
        return await self._backend.create_payment(user_id, plan_id, receipt_file_id)

    async def get_payment(self, payment_id: int) -> Optional[dict]:
        return await self._backend.get_payment(payment_id)

    async def pending_payments(self) -> list[dict]:
        return await self._backend.pending_payments()

    async def payment_with_plan(self, payment_id: int) -> Optional[dict]:
        return await self._backend.payment_with_plan(payment_id)

    async def pending_payments_with_plans(self) -> list[dict]:
        """Kutilayotgan to'lovlar + tarif NOMI (JOIN) — panel ro'yxati uchun."""
        return await self._backend.pending_payments_with_plans()

    async def delete_cached_event(self, event_id: int) -> bool:
        """Keshlangan xabar yozuvini o'chiradi (admin paneldagi "Nusxani o'chirish")."""
        return await self._backend.delete_cached_event(event_id)

    async def set_payment_status(self, payment_id: int, status: str, reviewed_by: int) -> None:
        await self._backend.set_payment_status(payment_id, status, reviewed_by)

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
        await self._backend.add_event(
            user_id, event_type, details, chat_id, chat_title, message_id, sender_id
        )

    async def recent_events(self, limit: int = 20) -> list[dict]:
        return await self._backend.recent_events(limit)

    async def count_events(
        self, event_type: Optional[str] = None, since: Optional[datetime] = None
    ) -> int:
        return await self._backend.count_events(event_type, since)

    async def count_user_events(self, user_id: int, event_type: Optional[str] = None) -> int:
        return await self._backend.count_user_events(user_id, event_type)

    async def count_user_events_since(
        self, user_id: int, since: datetime, event_types: Optional[list[str]] = None
    ) -> int:
        """Foydalanuvchining `since` dan keyingi hodisalari (kunlik limit uchun)."""
        return await self._backend.count_user_events_since(user_id, since, event_types)

    async def get_event_by_message(self, chat_id: int, message_id: int) -> Optional[dict]:
        return await self._backend.get_event_by_message(chat_id, message_id)

    async def update_event_details(
        self, chat_id: int, message_id: int, details: str
    ) -> bool:
        """Shu xabar yozuvining tarkibini yangilaydi (tahrirlash holati).

        True — yozuv topildi va yangilandi. Tahrirlashda chaqiriladi:
        xabar keyin o'chirilsa, hisobotda ENG OXIRGI tarkib ko'rsatiladi.
        """
        return await self._backend.update_event_details(chat_id, message_id, details)

    async def prune_events(self, keep: int = 20_000) -> None:
        await self._backend.prune_events(keep)

    async def upsert_connection(
        self,
        business_connection_id: str,
        user_id: int,
        is_enabled: bool,
        user_chat_id: Optional[int] = None,
    ) -> None:
        await self._backend.upsert_connection(
            business_connection_id, user_id, is_enabled, user_chat_id
        )

    async def get_connection(self, business_connection_id: str) -> Optional[dict]:
        return await self._backend.get_connection(business_connection_id)

    async def connected_user_ids(self) -> list[int]:
        return await self._backend.connected_user_ids()

    async def connections_for_user(self, user_id: int) -> list[dict]:
        return await self._backend.connections_for_user(user_id)

    # -- bot settings (key-value) --------------------------------------------

    async def get_setting(self, key: str, default: str = "") -> str:
        return await self._backend.get_setting(key, default)

    async def get_setting_cached(self, key: str, default: str = "", ttl: float = 5.0) -> str:
        """``get_setting`` + 5 sekundlik kesh (tezlik uchun).

        Ko'p o'qiladigan sozlamalar (masalan ``premium_enabled``) har bir
        tugmada DBga ketmasligi kerak.  ``set_setting`` keshni darhol
        yangilaydi — admin o'zgartirishi 5 sek ichida hammaga ko'rinadi.
        """
        import time as _time

        now = _time.monotonic()
        hit = self._settings_cache.get(key)
        if hit is not None and now - hit[0] < ttl:
            return hit[1]
        value = await self._backend.get_setting(key, default)
        self._settings_cache[key] = (now, value)
        return value

    async def set_setting(self, key: str, value: str) -> None:
        await self._backend.set_setting(key, value)
        import time as _time

        self._settings_cache[key] = (_time.monotonic(), value)


class PostgresDatabase:
    """Supabase Postgres backend (asyncpg)."""

    def __init__(self) -> None:
        self._pool: Any = None  # asyncpg.Pool

    @property
    def pool(self) -> Any:
        if self._pool is None:
            raise RuntimeError("Database is not initialised - call init() first")
        return self._pool

    async def init(self) -> None:
        """Connect to Supabase, create tables, import old SQLite data once."""
        import asyncpg

        # ANIQ XATO usuli: foydalanuvchi ba'zan SUPABASE_DB_URL ga
        # LOYIHA SAYTINI (https://xxxx.supabase.co) yozib qo'yadi.
        # Bu http/https bo'lsa — asyncpg umuman DSN sifatida o'qiy olmaydi.
        # Bu yerda darhol tushunarli xato + tayyor TO'G'RI format beriladi.
        _scheme = settings.supabase_db_url.split(":", 1)[0].lower()
        if _scheme in ("http", "https"):
            _ref = ""
            try:
                from urllib.parse import urlparse

                host = urlparse(settings.supabase_db_url).hostname or ""
                _ref = host.split(".")[0]
            except Exception:  # noqa: BLE001
                pass
            raise RuntimeError(
                "SUPABASE_DB_URL noto'g'ri: bu LOYIHA SAYTI (https://...), "
                "baqa ULANISH MANZILI emas.\n\n"
                "Supabase Dashboard -> CONNECT (yashil tugma) -> "
                "'Connection pooling' -> URI ni nusxalang.  U shu ko'rinishda "
                "bo'ladi:\n\n"
                f"postgresql://postgres.{_ref}:[PAROLINGIZ]@aws-0-region.pooler.supabase.com:6543/postgres\n\n"
                "[PAROLINGIZ] joyiga Supabase bazasi PAROLINI yozing "
                "(unutasangiz: Settings -> Database -> Reset database password). "
                "env.txt dagi SUPABASE_KEY bot tomonidan ISHLATILMAYDI — "
                "uni o'chirishingiz mumkin."
            )

        try:
            self._pool = await asyncpg.create_pool(
                settings.supabase_db_url,
                min_size=2,
                max_size=10,
                timeout=30,
                # Supabase "Connection pooling" URI orqali ulanganda
                # PgBouncer (transaction mode) ishlatiladi — u prepared
                # statementlarni qo'llab-quvvatlamaydi.  Buni o'chirmasak
                # birinchi so'rovdayoq DuplicatePreparedStatementError
                # bilan yiqiladi.
                statement_cache_size=0,
            )
        except Exception as exc:  # noqa: BLE001 – show a human-friendly error
            raise RuntimeError(
                f"Could not connect to Supabase Postgres: {exc}\n"
                "Check SUPABASE_DB_URL in .env (use the 'Connection pooling' URI "
                "from the Supabase Dashboard -> Connect button)."
            ) from exc

        async with self.pool.acquire() as conn:
            await conn.execute(SCHEMA)
            # Eski bazalar uchun migratsiya: xabar KIMdan kelganini saqlash.
            await conn.execute(
                "ALTER TABLE events ADD COLUMN IF NOT EXISTS sender_id BIGINT"
            )
            # Kirish tasdiqlash tizimi olib tashlandi: eski 'pending' yozuvlar
            # ham ochiq bo'lsin (bir martalik, idempotent).
            await conn.execute(
                "UPDATE users SET access_status = 'approved' WHERE access_status = 'pending'"
            )
        await self._import_sqlite_once()
        logger.info("Supabase Postgres ready (%s)", settings.supabase_host)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            logger.info("Supabase connection closed")

    # -- raw helpers ---------------------------------------------------------

    async def _fetch_all(self, sql: str, *params: Any) -> list[dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
        return [dict(r) for r in rows]

    async def _fetch_one(self, sql: str, *params: Any) -> Optional[dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, *params)
        return dict(row) if row else None

    async def _execute(self, sql: str, *params: Any) -> int:
        """Run a write query; returns 0 (auto ids are never needed here).

        Eski versiya HAR BIR INSERTga "RETURNING id" qo'shib yuborardi —
        lekin users / events / connections / bot_settings jadvallarida `id`
        ustuni YO'Q, shu sababli Supabaseda har bir yozuv
        "column \"id\" does not exist" xatosi bilan yiqilardi.  Avto-id
        faqat plans va payments jadvallarida bor va ular
        ``_execute_returning_id()`` dan foydalanadi.
        """
        async with self.pool.acquire() as conn:
            await conn.execute(sql, *params)
        return 0

    async def _execute_returning_id(self, sql: str, *params: Any) -> int:
        """INSERT ... RETURNING id helper (used by plans/payments)."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, *params)
        return row["id"] if row else 0

    async def _fetchval(self, sql: str, *params: Any) -> Any:
        async with self.pool.acquire() as conn:
            return await conn.fetchval(sql, *params)

    # ======================================================================
    # USERS
    # ======================================================================

    async def upsert_user(
        self,
        user_id: int,
        username: Optional[str],
        first_name: Optional[str],
        last_name: Optional[str],
    ) -> None:
        """        Insert the user if new, otherwise refresh profile fields.

        Kirish tasdiqlash tizimi OLIB TASHLANGAN (yangi talab): hamma
        foydalanuvchi botdan bemalol foydalanadi; yagona cheklov — ban.
        Eski 'pending' yozuvlari ham 'approved' qilib yangilanadi.
        """
        now = _now()
        await self._execute(
            """
            INSERT INTO users (user_id, username, first_name, last_name,
                               connected_at, last_activity, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (user_id) DO UPDATE SET
                username   = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                last_name  = EXCLUDED.last_name,
                last_activity = EXCLUDED.last_activity
            """,
            user_id,
            username,
            first_name,
            last_name,
            now,
            now,
            now,
        )

    async def touch_user(self, user_id: int) -> None:
        await self._execute(
            "UPDATE users SET last_activity = $1 WHERE user_id = $2",
            _now(),
            user_id,
        )

    async def get_user(self, user_id: int) -> Optional[dict]:
        return await self._fetch_one("SELECT * FROM users WHERE user_id = $1", user_id)

    async def all_users(self, only_active: bool = False) -> list[dict]:
        """All users, newest first. only_active -> approved & not banned."""
        where = "WHERE is_banned = FALSE AND access_status = 'approved'" if only_active else ""
        return await self._fetch_all(f"SELECT * FROM users {where} ORDER BY created_at DESC")

    async def online_users(self, window_seconds: int = 120) -> list[dict]:
        """Users whose last_activity is within the given window.

        last_activity is ISO TEXT -> compare with generated ISO threshold.
        """
        threshold = (datetime.now() - timedelta(seconds=window_seconds)).isoformat(
            timespec="seconds"
        )
        return await self._fetch_all(
            """
            SELECT * FROM users
            WHERE last_activity >= $1 AND is_banned = FALSE
            ORDER BY last_activity DESC
            """,
            threshold,
        )

    async def count_users(self, only_active: bool = False) -> int:
        where = "WHERE is_banned = FALSE AND access_status = 'approved'" if only_active else ""
        return int(
            await self._fetchval(f"SELECT COUNT(*) FROM users {where}")
        )

    async def count_online(self, window_seconds: int = 120) -> int:
        threshold = (datetime.now() - timedelta(seconds=window_seconds)).isoformat(
            timespec="seconds"
        )
        return int(
            await self._fetchval(
                "SELECT COUNT(*) FROM users WHERE last_activity >= $1 AND is_banned = FALSE",
                threshold,
            )
        )

    async def set_banned(self, user_id: int, banned: bool) -> None:
        await self._execute(
            "UPDATE users SET is_banned = $1 WHERE user_id = $2",
            banned,
            user_id,
        )

    async def set_admin(self, user_id: int, is_admin: bool) -> None:
        await self._execute(
            "UPDATE users SET is_admin = $1 WHERE user_id = $2",
            is_admin,
            user_id,
        )

    async def all_admins(self) -> list[int]:
        rows = await self._fetch_all("SELECT user_id FROM users WHERE is_admin = TRUE")
        ids = {row["user_id"] for row in rows}
        ids.add(settings.admin_id)
        return sorted(ids)

    # -- premium -------------------------------------------------------------

    async def set_premium(self, user_id: int, until: Optional[datetime]) -> None:
        await self._execute(
            "UPDATE users SET premium_until = $1 WHERE user_id = $2",
            until.isoformat(timespec="seconds") if until else None,
            user_id,
        )

    async def extend_premium(self, user_id: int, days: int) -> datetime:
        """Add `days` on top of remaining premium time; returns new deadline."""
        user = await self.get_user(user_id)
        base = parse_dt(user.get("premium_until")) if user else None
        now = datetime.now()
        start = base if base and base > now else now
        until = start + timedelta(days=days)
        await self.set_premium(user_id, until)
        return until

    async def premium_users(self) -> list[dict]:
        return await self._fetch_all(
            "SELECT * FROM users WHERE premium_until IS NOT NULL AND premium_until > $1",
            _now(),
        )

    async def expired_premium_users(self) -> list[dict]:
        return await self._fetch_all(
            "SELECT * FROM users WHERE premium_until IS NOT NULL AND premium_until <= $1",
            _now(),
        )

    # ======================================================================
    # PLANS
    # ======================================================================

    async def create_plan(
        self, title: str, duration_days: int, price: int, description: str
    ) -> int:
        return await self._execute_returning_id(
            """
            INSERT INTO plans (title, duration_days, price, description, created_at)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
            """,
            title,
            duration_days,
            price,
            description,
            _now(),
        )

    async def get_plan(self, plan_id: int) -> Optional[dict]:
        return await self._fetch_one("SELECT * FROM plans WHERE id = $1", plan_id)

    async def active_plans(self) -> list[dict]:
        return await self._fetch_all(
            "SELECT * FROM plans WHERE is_active = TRUE ORDER BY duration_days"
        )

    async def all_plans(self) -> list[dict]:
        return await self._fetch_all("SELECT * FROM plans ORDER BY created_at DESC")

    async def set_plan_active(self, plan_id: int, active: bool) -> None:
        await self._execute(
            "UPDATE plans SET is_active = $1 WHERE id = $2",
            active,
            plan_id,
        )

    async def update_plan(self, plan_id: int, **fields) -> None:
        """Update editable plan fields (edit mode)."""
        allowed = {"title", "duration_days", "price", "description"}
        sets, params = [], []
        n = 1
        for key, value in fields.items():
            if key in allowed:
                sets.append(f"{key} = ${n}")
                params.append(value)
                n += 1
        if not sets:
            return
        params.append(plan_id)
        await self._execute(
            f"UPDATE plans SET {', '.join(sets)} WHERE id = ${n}", *params
        )

    async def delete_plan(self, plan_id: int) -> None:
        await self._execute("DELETE FROM plans WHERE id = $1", plan_id)

    # ======================================================================
    # PAYMENTS
    # ======================================================================

    async def create_payment(self, user_id: int, plan_id: int, receipt_file_id: str) -> int:
        return await self._execute_returning_id(
            """
            INSERT INTO payments (user_id, plan_id, receipt_file_id, created_at)
            VALUES ($1, $2, $3, $4)
            RETURNING id
            """,
            user_id,
            plan_id,
            receipt_file_id,
            _now(),
        )

    async def get_payment(self, payment_id: int) -> Optional[dict]:
        return await self._fetch_one("SELECT * FROM payments WHERE id = $1", payment_id)

    async def pending_payments(self) -> list[dict]:
        return await self._fetch_all(
            "SELECT * FROM payments WHERE status = 'pending' ORDER BY created_at"
        )

    async def payment_with_plan(self, payment_id: int) -> Optional[dict]:
        return await self._fetch_one(
            """
            SELECT p.*, pl.duration_days AS duration_days
            FROM payments p LEFT JOIN plans pl ON pl.id = p.plan_id
            WHERE p.id = $1
            """,
            payment_id,
        )

    async def pending_payments_with_plans(self) -> list[dict]:
        """Kutilayotgan to'lovlar tarif nomi bilan (bitta JOIN so'rovi)."""
        return await self._fetch_all(
            """
            SELECT p.*, pl.title AS plan_title, pl.duration_days AS duration_days
            FROM payments p LEFT JOIN plans pl ON pl.id = p.plan_id
            WHERE p.status = 'pending'
            ORDER BY p.created_at
            """
        )

    async def delete_cached_event(self, event_id: int) -> bool:
        n = await self._fetchval(
            "DELETE FROM events WHERE id = $1 RETURNING 1", event_id
        )
        return bool(n)

    async def set_payment_status(self, payment_id: int, status: str, reviewed_by: int) -> None:
        await self._execute(
            "UPDATE payments SET status = $1, reviewed_at = $2, reviewed_by = $3 WHERE id = $4",
            status,
            _now(),
            reviewed_by,
            payment_id,
        )

    # ======================================================================
    # EVENTS (captured activity)
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
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            user_id,
            chat_id,
            chat_title,
            event_type,
            message_id,
            details,
            sender_id,
            _now(),
        )

    async def recent_events(self, limit: int = 20) -> list[dict]:
        return await self._fetch_all(
            "SELECT * FROM events ORDER BY occurred_at DESC LIMIT $1", limit
        )

    async def count_events(
        self, event_type: Optional[str] = None, since: Optional[datetime] = None
    ) -> int:
        sql = "SELECT COUNT(*) FROM events WHERE TRUE"
        params: list[Any] = []
        if event_type:
            params.append(event_type)
            sql += f" AND event_type = ${len(params)}"
        if since:
            params.append(since.isoformat(timespec="seconds"))
            sql += f" AND occurred_at >= ${len(params)}"
        return int(await self._fetchval(sql, *params))

    async def count_user_events(self, user_id: int, event_type: Optional[str] = None) -> int:
        sql = "SELECT COUNT(*) FROM events WHERE user_id = $1"
        params: list[Any] = [user_id]
        if event_type:
            params.append(event_type)
            sql += f" AND event_type = ${len(params)}"
        return int(await self._fetchval(sql, *params))

    async def count_user_events_since(
        self, user_id: int, since: datetime, event_types: Optional[list[str]] = None
    ) -> int:
        sql = "SELECT COUNT(*) FROM events WHERE user_id = $1 AND occurred_at >= $2"
        params: list[Any] = [user_id, since.isoformat(timespec="seconds")]
        if event_types:
            params.append(list(event_types))
            sql += f" AND event_type = ANY(${len(params)})"
        return int(await self._fetchval(sql, *params))

    async def get_event_by_message(
        self, chat_id: int, message_id: int
    ) -> Optional[dict]:
        return await self._fetch_one(
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
        """Faqat ENG OXIRGI yozuvni yangilaydi (SQLite backend bilan bir xil)."""
        n = await self._fetchval(
            """
            UPDATE events SET details = $3
            WHERE id = (
                SELECT id FROM events
                WHERE chat_id = $1 AND message_id = $2
                ORDER BY id DESC LIMIT 1
            )
            RETURNING 1
            """,
            chat_id,
            message_id,
            details,
        )
        return bool(n)

    async def prune_events(self, keep: int = 20_000) -> None:
        """Housekeeping: keep only the newest `keep` rows."""
        await self._execute(
            """
            DELETE FROM events
            WHERE id NOT IN (
                SELECT id FROM events ORDER BY id DESC LIMIT $1
            )
            """,
            keep,
        )

    # ======================================================================
    # BUSINESS CONNECTIONS
    # ======================================================================

    async def upsert_connection(
        self,
        business_connection_id: str,
        user_id: int,
        is_enabled: bool,
        user_chat_id: Optional[int] = None,
    ) -> None:
        now = _now()
        existing = await self._fetch_one(
            "SELECT * FROM connections WHERE business_connection_id = $1",
            business_connection_id,
        )
        if existing is None:
            await self._execute(
                """
                INSERT INTO connections
                    (business_connection_id, user_id, user_chat_id, is_enabled, connected_at)
                VALUES ($1, $2, $3, $4, $5)
                """,
                business_connection_id,
                user_id,
                user_chat_id,
                is_enabled,
                now,
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
                SET is_enabled = $1, connected_at = $2, disconnected_at = $3,
                    user_chat_id = COALESCE($4, user_chat_id)
                WHERE business_connection_id = $5
                """,
                is_enabled,
                connected_at,
                disconnected_at,
                user_chat_id,
                business_connection_id,
            )

    async def get_connection(self, business_connection_id: str) -> Optional[dict]:
        return await self._fetch_one(
            "SELECT * FROM connections WHERE business_connection_id = $1",
            business_connection_id,
        )

    async def connected_user_ids(self) -> list[int]:
        rows = await self._fetch_all(
            "SELECT DISTINCT user_id FROM connections WHERE is_enabled = TRUE"
        )
        return [row["user_id"] for row in rows]

    async def connections_for_user(self, user_id: int) -> list[dict]:
        return await self._fetch_all(
            "SELECT * FROM connections WHERE user_id = $1 ORDER BY connected_at DESC",
            user_id,
        )

    # -- bot settings -----------------------------------------------------------

    async def get_setting(self, key: str, default: str = "") -> str:
        value = await self._fetchval(
            "SELECT value FROM bot_settings WHERE key = $1", key
        )
        return value if value is not None else default

    async def set_setting(self, key: str, value: str) -> None:
        await self._execute(
            """
            INSERT INTO bot_settings (key, value) VALUES ($1, $2)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            key,
            value,
        )

    # ======================================================================
    # ONE-TIME SQLITE -> SUPABASE IMPORT
    # ======================================================================

    async def _import_sqlite_once(self) -> None:
        """If ./bot.db exists and we haven't imported before, copy data over.

        Kept tolerant: a missing/corrupt SQLite file is skipped with a log
        line, never blocks startup.
        """
        sqlite_path = Path(settings.db_path)
        if not sqlite_path.exists():
            return

        already = await self._fetchval(
            "SELECT COUNT(*) FROM supabase_migrations WHERE name = $1",
            "sqlite_import_v1",
        )
        if already:
            return

        logger.info("Found old bot.db - importing data into Supabase once...")
        try:
            import aiosqlite

            conn = await aiosqlite.connect(settings.db_path)
            conn.row_factory = aiosqlite.Row
            try:
                cursor = await conn.execute("SELECT * FROM users")
                users = [dict(r) for r in await cursor.fetchall()]
                await cursor.close()

                cursor = await conn.execute("SELECT * FROM plans")
                plans = [dict(r) for r in await cursor.fetchall()]
                await cursor.close()

                cursor = await conn.execute("SELECT * FROM payments")
                payments = [dict(r) for r in await cursor.fetchall()]
                await cursor.close()

                cursor = await conn.execute("SELECT * FROM events")
                events = [dict(r) for r in await cursor.fetchall()]
                await cursor.close()

                cursor = await conn.execute("SELECT * FROM connections")
                connections = [dict(r) for r in await cursor.fetchall()]
                await cursor.close()
            finally:
                await conn.close()

            async with self.pool.acquire() as pg:
                for u in users:
                    await pg.execute(
                        """
                        INSERT INTO users (user_id, username, first_name, last_name,
                            is_banned, access_status, reviewed_by, reviewed_at,
                            is_admin, premium_until, connected_at, last_activity, created_at)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
                        ON CONFLICT (user_id) DO NOTHING
                        """,
                        u["user_id"], u.get("username"), u.get("first_name"),
                        u.get("last_name"), bool(u.get("is_banned")),
                        u.get("access_status") or "approved", u.get("reviewed_by"),
                        u.get("reviewed_at"), bool(u.get("is_admin")),
                        u.get("premium_until"), u.get("connected_at"),
                        u.get("last_activity"), u["created_at"],
                    )
                for p in plans:
                    await pg.execute(
                        """
                        INSERT INTO plans (id, title, duration_days, price, description,
                                           is_active, created_at)
                        VALUES ($1,$2,$3,$4,$5,$6,$7)
                        ON CONFLICT (id) DO NOTHING
                        """,
                        p["id"], p["title"], p["duration_days"], p["price"],
                        p.get("description") or "", bool(p.get("is_active")), p["created_at"],
                    )
                # Fix the id sequence after explicit-id inserts.
                await pg.execute(
                    "SELECT setval('plans_id_seq', GREATEST((SELECT COALESCE(MAX(id),1) FROM plans), 1))"
                )
                for p in payments:
                    await pg.execute(
                        """
                        INSERT INTO payments (id, user_id, plan_id, receipt_file_id,
                                              status, created_at, reviewed_at, reviewed_by)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                        ON CONFLICT (id) DO NOTHING
                        """,
                        p["id"], p["user_id"], p["plan_id"], p["receipt_file_id"],
                        p["status"], p["created_at"], p.get("reviewed_at"),
                        p.get("reviewed_by"),
                    )
                await pg.execute(
                    "SELECT setval('payments_id_seq', GREATEST((SELECT COALESCE(MAX(id),1) FROM payments), 1))"
                )
                for e in events:
                    await pg.execute(
                        """
                        INSERT INTO events (user_id, chat_id, chat_title, event_type,
                                            message_id, details, sender_id, occurred_at)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                        """,
                        e["user_id"], e.get("chat_id"), e.get("chat_title"),
                        e["event_type"], e.get("message_id"), e.get("details") or "",
                        e.get("sender_id"), e["occurred_at"],
                    )
                for c in connections:
                    await pg.execute(
                        """
                        INSERT INTO connections (business_connection_id, user_id,
                            user_chat_id, is_enabled, connected_at, disconnected_at)
                        VALUES ($1,$2,$3,$4,$5,$6)
                        ON CONFLICT (business_connection_id) DO NOTHING
                        """,
                        c["business_connection_id"], c["user_id"], c.get("user_chat_id"),
                        bool(c.get("is_enabled")), c.get("connected_at"),
                        c.get("disconnected_at"),
                    )
                await pg.execute(
                    "INSERT INTO supabase_migrations (name, applied_at) "
                    "VALUES ('sqlite_import_v1', $1) ON CONFLICT DO NOTHING",
                    _now(),
                )

            logger.info(
                "Import finished: %s users, %s plans, %s payments, %s events, %s connections",
                len(users), len(plans), len(payments), len(events), len(connections),
            )
        except Exception:  # noqa: BLE001 – never block startup on import
            logger.exception("SQLite import failed (bot continues with Supabase data)")


# Single shared instance – import `db` everywhere.
db = Database()
