"""
Supabase / Postgres integration tests for the activity-monitor bot.

Run from the project root:

    # Part 1 always runs (offline, uses a throwaway SQLite file):
    python tests/supabase_test.py

    # Full integration against your Supabase project:
    SUPABASE_DB_URL="postgresql://postgres.xxxx:PAROL@aws-0-region.pooler.supabase.com:6543/postgres" \
        python tests/supabase_test.py

    # Optional: validate the DDL against a LOCAL Postgres (e.g. docker):
    POSTGRES_TEST_URL="postgresql://postgres:postgres@localhost:5432/postgres" \
        python tests/supabase_test.py

Parts
-----
PART 1 — Backend parity: the full CRUD matrix through the SQLite backend
         (offline; never touches the developer's real bot.db).

PART 2 — DDL smoke (optional): runs app/database.py SCHEMA against a local
         Postgres and verifies tables / indexes / the bot_settings seed.

PART 3 — Live integration (optional, needs SUPABASE_DB_URL): launched as a
         CHILD PROCESS so ``app.config`` snapshots the URL at import time
         exactly like production does.  Verifies the backend auto-selects
         Postgres, the remote schema exists (7 tables), the same CRUD
         matrix passes on Supabase, and the importer marker is queryable.
         Test rows are wiped before AND after, so re-runs are safe.

NOTE: the Postgres backend expects the Supabase *pooler* URI (port 6543,
transaction mode).  The code sets ``statement_cache_size=0`` for that
reason — the direct URI (port 5432) works too.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

PASS = "\u2705"

# ---------------------------------------------------------------------------
# Process setup: keep the throwaway DB + separate the LIVE url.
# ---------------------------------------------------------------------------
if "--live" in sys.argv:
    # Child mode: config must see the real SUPABASE_DB_URL (already in env).
    _tmpdir = tempfile.mkdtemp(prefix="bot_supabase_live_")
    os.environ["DB_PATH"] = str(Path(_tmpdir) / "live.db")
else:
    # Parent mode: force SQLite for Part 1 (never touch the real bot.db).
    os.environ.setdefault("BOT_TOKEN", "123456:TEST-TOKEN")
    os.environ.setdefault("ADMIN_ID", "111111111")
    _tmpdir = tempfile.mkdtemp(prefix="bot_supabase_test_")
    os.environ["DB_PATH"] = str(Path(_tmpdir) / "offline.db")
    # Remove BEFORE app.config is imported anywhere in this process.
    _LIVE_URL = os.environ.pop("SUPABASE_DB_URL", None)

# Shared test ids (also used by the live part for easy cleanup).
TEST_USER = 910001
TEST_CHAT = 555001


# ---------------------------------------------------------------------------
# Part 1 – parity suite (against whatever backend `db` auto-selects)
# ---------------------------------------------------------------------------
async def run_crud_suite(backend_name: str) -> None:
    """The full CRUD matrix every handler relies on."""
    from app.database import db

    await db.init()
    try:
        # -- users & access ---------------------------------------------------
        await db.upsert_user(TEST_USER, "parityuser", "Parity", None)
        row = await db.get_user(TEST_USER)
        assert row is not None, "upsert_user did not insert"
        assert row["access_status"] == "pending", row["access_status"]
        assert row["is_banned"] in (0, False)
        await db.touch_user(TEST_USER)
        assert (await db.get_user(TEST_USER))["last_activity"] is not None

        await db.set_access(TEST_USER, "approved", 111111111)
        assert (await db.get_user(TEST_USER))["access_status"] == "approved"
        assert not any(
            u["user_id"] == TEST_USER for u in await db.pending_access_users()
        )

        # -- premium ------------------------------------------------------------
        until = await db.extend_premium(TEST_USER, 30)
        assert until is not None
        await db.set_premium(TEST_USER, None)
        assert (await db.get_user(TEST_USER))["premium_until"] is None

        # -- plans --------------------------------------------------------------
        plan_id = await db.create_plan("Parity plan", 30, 9000, "desc")
        plan = await db.get_plan(plan_id)
        assert plan["price"] == 9000 and plan["duration_days"] == 30
        await db.update_plan(plan_id, price=7777, title="Parity v2")
        assert (await db.get_plan(plan_id))["price"] == 7777
        await db.set_plan_active(plan_id, False)
        assert not any(p["id"] == plan_id for p in await db.active_plans())

        # -- payments -------------------------------------------------------------
        pay_id = await db.create_payment(TEST_USER, plan_id, "receipt_parity")
        joined = await db.payment_with_plan(pay_id)
        assert joined["duration_days"] == 30
        await db.set_payment_status(pay_id, "approved", 111111111)
        assert all(p["id"] != pay_id for p in await db.pending_payments())

        # -- events -----------------------------------------------------------------
        await db.add_event(
            TEST_USER, "edit", "old -> new",
            chat_id=TEST_CHAT, message_id=101, sender_id=TEST_USER,
        )
        found = await db.get_event_by_message(TEST_CHAT, 101)
        assert found is not None and found["event_type"] == "edit"
        assert found["sender_id"] == TEST_USER
        assert await db.update_event_details(TEST_CHAT, 101, "old -> newer")
        assert (await db.get_event_by_message(TEST_CHAT, 101))["details"] == (
            "old -> newer"
        )
        await db.prune_events(keep=200_000)  # must not raise

        # -- connections ----------------------------------------------------------
        await db.upsert_connection("bc_parity", TEST_USER, True, user_chat_id=TEST_USER)
        conn = await db.get_connection("bc_parity")
        assert conn["is_enabled"] in (1, True) and conn["connected_at"]
        await db.upsert_connection("bc_parity", TEST_USER, False)
        conn = await db.get_connection("bc_parity")
        assert not conn["is_enabled"] and conn["disconnected_at"]
        await db.upsert_connection("bc_parity", TEST_USER, True)
        assert not (await db.get_connection("bc_parity"))["disconnected_at"]

        # -- bot settings ----------------------------------------------------------
        await db.set_setting("test_flag", "1")
        assert await db.get_setting("test_flag") == "1"
        assert await db.get_setting("premium_enabled", "") in ("0", "1")
        assert await db.get_setting("missing_key", "fallback") == "fallback"

        # -- statistics ----------------------------------------------------------------
        assert await db.count_user_events(TEST_USER, "edit") >= 1
        assert await db.count_events() >= 0
        print(f"  [{backend_name}] CRUD matrix OK")
    finally:
        await db.close()


async def part1_parity() -> None:
    print("PART 1: SQLite backend parity suite...")
    await run_crud_suite("sqlite")
    print("PART 1 (SQLite parity) PASSED " + PASS)


# ---------------------------------------------------------------------------
# Part 2 – local Postgres DDL smoke (POSTGRES_TEST_URL, e.g. docker)
# ---------------------------------------------------------------------------
async def part2_ddl_smoke() -> None:
    url = os.getenv("POSTGRES_TEST_URL")
    if not url:
        print("PART 2 SKIPPED (POSTGRES_TEST_URL not set)")
        return
    import asyncpg

    from app.database import SCHEMA

    conn = await asyncpg.connect(url)
    try:
        await conn.execute(SCHEMA)
        # The seed row must exist exactly once.
        n = await conn.fetchval(
            "SELECT COUNT(*) FROM bot_settings WHERE key = 'premium_enabled'"
        )
        assert n == 1, f"premium_enabled seed count = {n}"
        # The hot-path indexes must exist.
        idx = await conn.fetchval(
            """
            SELECT COUNT(*) FROM pg_indexes
            WHERE tablename = 'events'
              AND indexname IN ('idx_events_chat_message', 'idx_events_time')
            """
        )
        assert idx == 2, f"expected 2 event indexes, found {idx}"
        print("PART 2 (Postgres DDL smoke) PASSED " + PASS)
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Part 3 – live Supabase (child process: `python tests/supabase_test.py --live`)
# ---------------------------------------------------------------------------
async def _wipe_test_rows(conn: Any) -> None:
    """Remove every row the test creates (idempotent re-runs)."""
    await conn.execute("DELETE FROM events WHERE user_id = $1", TEST_USER)
    await conn.execute("DELETE FROM connections WHERE user_id = $1", TEST_USER)
    await conn.execute("DELETE FROM payments WHERE user_id = $1", TEST_USER)
    await conn.execute("DELETE FROM plans WHERE title LIKE 'Parity%'")
    await conn.execute("DELETE FROM bot_settings WHERE key = 'test_flag'")
    await conn.execute("DELETE FROM users WHERE user_id = $1", TEST_USER)


async def part3_live() -> None:
    from app.database import db

    # The backend must now choose Postgres automatically.
    await db.init()
    try:
        assert type(db._backend).__name__ == "PostgresDatabase", (
            f"expected PostgresDatabase, got {type(db._backend).__name__}"
        )
        print("  backend auto-selected: PostgresDatabase " + PASS)

        # 1) Schema must exist on the remote database.
        async with db._backend.pool.acquire() as conn:
            tables = await conn.fetchval(
                """
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN
                      ('users','plans','payments','events','connections',
                       'bot_settings','supabase_migrations')
                """
            )
            assert tables == 7, f"expected 7 tables, found {tables}"
        print("  remote schema verified (7 tables) " + PASS)

        # 2) Clean start (in case a previous run left rows behind)...
        async with db._backend.pool.acquire() as conn:
            await _wipe_test_rows(conn)

        # 3) Every write path the bot uses at runtime.
        await run_crud_suite("supabase-live")
        print("  live CRUD matrix PASSED " + PASS)

        # 4) The importer marker must be queryable (0 = not imported yet,
        #    1 = bot.db has been copied over at least once).
        applied = await db._backend._fetchval(
            "SELECT COUNT(*) FROM supabase_migrations WHERE name = 'sqlite_import_v1'"
        )
        assert applied >= 0

        # 5) Cleanup (leave the production database as we found it).
        async with db._backend.pool.acquire() as conn:
            await _wipe_test_rows(conn)
        print("PART 3 (live Supabase) PASSED " + PASS)
    finally:
        await db.close()


def launch_live_child() -> int:
    """Re-run this file in a child process with SUPABASE_DB_URL restored."""
    assert _LIVE_URL, "internal error: no live URL"
    env = {**os.environ, "SUPABASE_DB_URL": _LIVE_URL}
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--live"],
        env=env,
        cwd=str(Path(__file__).resolve().parent.parent),
    )
    return proc.returncode


async def main() -> None:
    await part1_parity()
    await part2_ddl_smoke()
    if _LIVE_URL:
        print("PART 3: live Supabase integration (child process)...")
        code = launch_live_child()
        if code != 0:
            raise SystemExit("PART 3 FAILED (see child output above)")
    else:
        print("PART 3 SKIPPED (SUPABASE_DB_URL not set)")
    print("ALL SUPABASE TESTS PASSED " + PASS)


if __name__ == "__main__":
    if "--live" in sys.argv:
        # Child process: run ONLY the live Supabase part.
        asyncio.run(part3_live())
    else:
        asyncio.run(main())
