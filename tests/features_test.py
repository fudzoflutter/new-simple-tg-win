"""
Offline feature tests for the 2026-09-14 request batch.

Run from the project root:

    python tests/features_test.py

Covers (no Telegram network):

PART A — Premium plans: create -> EDIT every field -> hide/show -> delete
PART B — Subscriptions: grant (extend) -> user-visible deadline -> remove;
         access requests: pending -> panel list -> approve;
         connection state: connect -> disconnect -> reconnect timestamps
PART C — AccessGuardMiddleware: /start now REACHES handlers for pending
         users (the access-request bug fix); other commands stay blocked.
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

        # -- access requests: pending -> panel list -> approve ----------------
        row = await db.get_user(9001)
        assert row["access_status"] == "pending"
        pending = await db.pending_access_users()
        assert any(u["user_id"] == 9001 for u in pending), pending
        await db.set_access(9001, "approved", 111111111)
        assert not any(
            u["user_id"] == 9001 for u in await db.pending_access_users()
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
    """AccessGuardMiddleware: /start passes through, other commands don't."""
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
                "access_status": "pending",
                "is_banned": False,
            }

    original = middlewares.db
    middlewares.db = StubDB()
    # Stub the outward reply so no Telegram API is touched in the test.
    rejects: list[str] = []

    async def fake_reject(event, html_text, plain_text):
        rejects.append(html_text)

    mw._reject = fake_reject  # type: ignore[method-assign]
    try:
        # /start from a PENDING user must reach the handler now (bug fix).
        called = []

        async def handler(event, data):
            called.append(event)

        start = make_message(9001, "/start")
        await mw(handler, start, {"event_from_user": start.from_user})
        assert called, "/start must pass through the guard for pending users"

        # Any other command must stay blocked for a pending user.
        blocked_called = []

        async def blocked_handler(event, data):
            blocked_called.append(event)

        other = make_message(9001, "/settings")
        await mw(
            blocked_handler, other, {"event_from_user": other.from_user}
        )
        assert not blocked_called, "non-start command must stay blocked"
        assert rejects, "blocked user must still get the 'pending' notice"
        print("PART C (guard passthrough) PASSED ✅")
    finally:
        middlewares.db = original


async def part_d_callback_routing() -> None:
    """The access-requests list filter must NOT swallow ✅/❌ callbacks.

    Bug: F.data.startswith('adm:access') matched 'adm:access:ok:<id>' and
    'adm:access:no:<id>' too, so pressing Approve/Reject re-opened the
    list and the request was never approved.
    """
    import re

    from app.keyboards import admin_kb

    # The pattern used by show_access_requests (keep in sync!).
    pattern = r"^adm:access(\d+|)$"

    must_match = ["adm:access", "adm:access1", "adm:access12"]
    must_not_match = [
        admin_kb.CB_ACCESS_OK + "9001",   # ✅ Tasdiqlash
        admin_kb.CB_ACCESS_NO + "9001",   # ❌ Rad etish
        "adm:accessX",
        "adm:access:ok:9001",
    ]
    for data in must_match:
        assert re.match(pattern, data), f"{data} must open the requests list"
    for data in must_not_match:
        assert not re.match(pattern, data), (
            f"{data} must NOT be caught by the list filter (approve/reject "
            "callbacks would be swallowed)"
        )

    # Registration-order sanity: in admin_panel.py the ✅/❌ handlers must
    # appear AFTER the list handler but with their own startswith filters.
    import inspect

    from app.handlers import admin_panel

    src = inspect.getsource(admin_panel)
    list_pos = src.index("regexp")
    ok_pos = src.index("CB_ACCESS_OK")
    no_pos = src.index("CB_ACCESS_NO")
    assert list_pos < ok_pos < no_pos or list_pos < no_pos < ok_pos, (
        "list handler must come before decision handlers"
    )
    print("PART D (callback routing) PASSED ✅")


async def main() -> None:
    await part_a_plans()
    await part_b_users()
    await part_c_middleware()
    await part_d_callback_routing()
    print("ALL FEATURE TESTS PASSED ✅")


if __name__ == "__main__":
    asyncio.run(main())
