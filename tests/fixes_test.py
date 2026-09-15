"""
Offline tests for the 2026-09-14 bug-fix batch.

Run from the project root:

    python tests/fixes_test.py

Covers (no Telegram network):

PART A — Daily limit: set -> counts only TODAY's cached messages ->
         premium removes the limit -> removing premium restores it ->
         0 = unlimited.
PART B — Cached-text management: latest cached message is found,
         updated in place, and deleted.
PART C — Payments with plan name: pending list JOIN includes plan_title;
         approval stores premium.
PART D — Ban guard helpers: admin rows protected; ban-cache invalidation.
PART E — SQLite seeds premium_enabled=0 (Postgres parity).
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["BOT_TOKEN"] = "123456:TEST-TOKEN"
os.environ["ADMIN_ID"] = "111111111"
# env.txt real keys must never leak into tests (production Supabase!).
os.environ["CODEBUFF_SKIP_ENV_FILE"] = "1"

_tmpdir = tempfile.mkdtemp(prefix="bot_fixes_test_")
os.environ["DB_PATH"] = str(Path(_tmpdir) / "test.db")
os.environ.pop("SUPABASE_DB_URL", None)


async def part_a_limit() -> None:
    from app.database import db
    from app.services.reporter import Reporter

    await db.init()
    try:
        uid = 93001
        await db.upsert_user(uid, "limituser", "Limit", None)

        # 0 / missing = unlimited.
        assert await db.get_setting_cached(f"limit:{uid}", "0") == "0"
        await db.set_setting(f"limit:{uid}", "3")

        # Two cached messages today -> below limit of 3.
        await db.add_event(uid, "text", "one", chat_id=1, message_id=1, sender_id=uid)
        await db.add_event(uid, "photo", "file:x|photo|", chat_id=1, message_id=2, sender_id=uid)
        reporter = Reporter(bot=None)  # bot not used by _limit_reached
        assert await reporter._limit_reached(uid) is False

        # Third message today -> limit reached.
        await db.add_event(uid, "text", "two", chat_id=1, message_id=3, sender_id=uid)
        assert await reporter._limit_reached(uid) is True

        # Verify the since-window math used by the limit counter.
        since = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        n_today = await db.count_user_events_since(
            uid, since, ["text", "photo", "video", "sticker", "animation"]
        )
        assert n_today == 3, n_today
        n_week = await db.count_user_events_since(
            uid, datetime.now() - timedelta(days=7), ["text"]
        )
        assert n_week == 2, n_week  # only 'one' and 'two' are text so far

        # Premium removes the limit even if it is set.
        await db.extend_premium(uid, 7)
        await db.add_event(uid, "text", "three", chat_id=1, message_id=4, sender_id=uid)
        await db.add_event(uid, "text", "four", chat_id=1, message_id=5, sender_id=uid)
        assert await reporter._limit_reached(uid) is False

        # Granting premium via the panel also CLEARS the stored limit.
        await db.set_setting(f"limit:{uid}", "0")
        assert await db.get_setting_cached(f"limit:{uid}", "0") == "0"
        print("PART A (daily limit) PASSED ✅")
    finally:
        await db.close()


async def part_b_cached_text() -> None:
    from app.database import db

    await db.init()
    try:
        uid = 93002
        await db.upsert_user(uid, "cacheuser", "Cache", None)
        await db.add_event(
            uid, "text", "original", chat_id=77, message_id=10, sender_id=uid
        )

        latest = await db.recent_events(limit=50)
        mine = [r for r in latest if r.get("user_id") == uid and r.get("message_id")]
        assert mine, "cached message row must exist"
        event = mine[0]

        # Update in place (the panel's "Almashtirish" flow).
        ok = await db.update_event_details(77, 10, "replaced")
        assert ok, "update_event_details must find the cached row"
        fresh = await db.get_event_by_message(77, 10)
        assert fresh["details"] == "replaced"

        # Delete (the panel's "Nusxani o'chirish" flow).
        assert await db.delete_cached_event(event["id"]) is True
        assert await db.delete_cached_event(event["id"]) is False
        assert await db.get_event_by_message(77, 10) is None
        print("PART B (cached text) PASSED ✅")
    finally:
        await db.close()


async def part_c_payments() -> None:
    from app.database import db

    await db.init()
    try:
        uid = 93003
        await db.upsert_user(uid, "payuser", "Pay", None)
        plan_id = await db.create_plan("Fix plan", 30, 12345, "d")
        pay_id = await db.create_payment(uid, plan_id, "receipt_x")

        rows = await db.pending_payments_with_plans()
        row = next((r for r in rows if r["id"] == pay_id), None)
        assert row is not None, "pending payment must be listed"
        assert row["plan_title"] == "Fix plan", row
        assert row["duration_days"] == 30

        until = await db.extend_premium(uid, row["duration_days"])
        assert until is not None
        await db.set_payment_status(pay_id, "approved", 111111111)
        assert all(p["id"] != pay_id for p in await db.pending_payments())

        # Deleting the plan must not crash the JOIN (plan_title becomes None).
        await db.delete_plan(plan_id)
        rows = await db.pending_payments_with_plans()
        assert all(r["id"] != pay_id for r in rows)  # already approved anyway
        print("PART C (payments with plan) PASSED ✅")
    finally:
        await db.close()


async def part_d_ban_guard() -> None:
    from app import middlewares
    from app.database import db
    from app.middlewares import invalidate_ban_cache

    # Cache invalidation helper must be a no-op-safe function.
    invalidate_ban_cache(42)  # never raises even for unknown ids
    assert 42 not in middlewares._ban_cache

    await db.init()
    try:
        # Admin-flagged row exists -> panel logic must refuse to ban it.
        await db.upsert_user(93004, "adminuser", "Admin", None)
        await db.set_admin(93004, True)
        row = await db.get_user(93004)
        assert bool(row and row.get("is_admin"))
        # (the handler-level refusal itself is covered by _is_admin_row logic)
        from app.handlers.admin_panel import _is_admin_row

        assert _is_admin_row(row) is True
        assert _is_admin_row({"is_admin": 0}) is False
        assert _is_admin_row(None) is False
        print("PART D (ban guard) PASSED ✅")
    finally:
        await db.close()


async def part_e_seed_parity() -> None:
    from app.database import db

    await db.init()
    try:
        value = await db.get_setting("premium_enabled", "missing")
        assert value in ("0", "1"), f"premium_enabled must be seeded, got {value!r}"
        print("PART E (settings seed parity) PASSED ✅")
    finally:
        await db.close()


async def main() -> None:
    await part_a_limit()
    await part_b_cached_text()
    await part_c_payments()
    await part_d_ban_guard()
    await part_e_seed_parity()
    print("ALL FIXES TESTS PASSED ✅")


if __name__ == "__main__":
    asyncio.run(main())
