"""
Offline feature tests for the 2026-09-14 request batch.

Run from the project root:

    python tests/features_test.py

Covers (no Telegram network):

PART A — Premium plans: create -> EDIT every field -> hide/show -> delete
PART B — Subscriptions: grant (extend) -> user-visible deadline -> remove;
         access is OPEN for everyone (approval feature removed):
         a fresh user is 'approved' right away;
         connection state: connect -> disconnect -> reconnect timestamps
PART C — AccessGuardMiddleware: only banned users are blocked now;
         everyone else (and /start) passes through.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["BOT_TOKEN"] = "123456:TEST-TOKEN"
os.environ["ADMIN_ID"] = "111111111"

# Part A/B use the REAL sqlite backend in a temp file.
_tmpdir = tempfile.mkdtemp(prefix="bot_features_test_")
os.environ["DB_PATH"] = str(Path(_tmpdir) / "test.db")
os.environ.pop("SUPABASE_DB_URL", None)


async def part_a_plans() -> None:
    from app.database import db

    await db.init()
    try:
        plan_id = await db.create_plan("Old title", 30, 10000, "old desc")
        await db.update_plan(plan_id, title="New title")
        await db.update_plan(plan_id, duration_days=7, price=5000)
        await db.update_plan(plan_id, description="")
        plan = await db.get_plan(plan_id)
        assert plan["title"] == "New title", plan
        assert plan["duration_days"] == 7 and plan["price"] == 5000
        assert plan["description"] == ""
        # empty update must not corrupt anything
        await db.update_plan(plan_id)
        assert (await db.get_plan(plan_id))["title"] == "New title"

        await db.set_plan_active(plan_id, False)
        assert (await db.get_plan(plan_id))["is_active"] in (0, False)
        await db.delete_plan(plan_id)
        assert await db.get_plan(plan_id) is None
        print("PART A (plan edit/delete) PASSED ✅")
    finally:
        await db.close()


async def part_b_users() -> None:
    from app.database import db

    await db.init()
    try:
        # -- subscriptions: grant -> extend -> remove ------------------------
        await db.upsert_user(9001, "testuser", "Test", None)
        until1 = await db.extend_premium(9001, 30)
        until2 = await db.extend_premium(9001, 10)  # extending adds on top
        # DB stores second precision, so allow a tiny tolerance.
        delta = (until2 - until1).total_seconds()
        assert abs(delta - 10 * 86400) < 5, (until1, until2)
        await db.set_premium(9001, None)
        assert (await db.get_user(9001))["premium_until"] is None

        # -- kirish ochiq (tasdiqlash tizimi olib tashlandi) -----------------
        row = await db.get_user(9001)
        assert row["access_status"] == "approved", (
            "yangi foydalanuvchi darhol approved bo'lishi kerak"
        )

        # -- connection lifecycle ---------------------------------------------
        await db.upsert_connection("bc_feat", 9001, True, user_chat_id=9001)
        conn = await db.get_connection("bc_feat")
        assert conn["is_enabled"] and conn["connected_at"]
        await db.upsert_connection("bc_feat", 9001, False)
        conn = await db.get_connection("bc_feat")
        assert not conn["is_enabled"] and conn["disconnected_at"]
        await db.upsert_connection("bc_feat", 9001, True)
        conn = await db.get_connection("bc_feat")
        assert conn["is_enabled"] and conn["disconnected_at"] is None
        print("PART B (subs / requests / connections) PASSED ✅")
    finally:
        await db.close()


async def part_c_middleware() -> None:
    """AccessGuardMiddleware: faqat BANLANGAN foydalanuvchi to'siladi."""
    from datetime import datetime

    from aiogram.types import Chat, Message, User

    from app import middlewares
    from app.middlewares import AccessGuardMiddleware

    mw = AccessGuardMiddleware()

    def make_message(uid: int, text: str) -> Message:
        return Message(
            message_id=1,
            date=datetime.now(),
            chat=Chat(id=1, type="private"),
            from_user=User(id=uid, is_bot=False, first_name="Tester"),
            text=text,
        )

    class StubDB:
        async def get_user(self, user_id: int) -> dict:
            return {
                "user_id": user_id,
                "access_status": "approved",  # endi hamma approved
                "is_banned": user_id == 9002,  # faqat 9002 banlangan
            }

    original = middlewares.db
    middlewares.db = StubDB()
    # Stub the outward reply so no Telegram API is touched in the test.
    rejects: list[str] = []

    async def fake_reject(event, html_text, plain_text):
        rejects.append(html_text)

    mw._reject = fake_reject  # type: ignore[method-assign]
    try:
        # Oddiy (banlanmagan) foydalanuvchi — har qanday so'rov o'tadi.
        called = []

        async def handler(event, data):
            called.append(event)

        normal = make_message(9001, "/settings")
        await mw(handler, normal, {"event_from_user": normal.from_user})
        assert called, "unbanned user must pass through the guard"
        assert not rejects

        # Banlangan foydalanuvchi — to'siladi.
        blocked_called = []

        async def blocked_handler(event, data):
            blocked_called.append(event)

        banned = make_message(9002, "/start")
        await mw(
            blocked_handler, banned, {"event_from_user": banned.from_user}
        )
        assert not blocked_called, "banned user must be blocked"
        assert rejects, "banned user must get the ban notice"
        print("PART C (guard ban-only) PASSED ✅")
    finally:
        middlewares.db = original


async def main() -> None:
    await part_a_plans()
    await part_b_users()
    await part_c_middleware()
    print("ALL FEATURE TESTS PASSED ✅")


if __name__ == "__main__":
    asyncio.run(main())
