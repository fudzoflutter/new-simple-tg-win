"""
Offline smoke test – Telegram tarmog'iga ulanmaydi.

Ishga tushirish (loyiha ildizidan):

    python tests/smoke_test.py

1-qism (klaviaturalar, matnlar, sozlamalar) — har doim ishlaydi.
2-qism (Supabase DB) — faqat SUPABASE_DB_URL berilganda:

    SUPABASE_DB_URL="postgresql://..." python tests/smoke_test.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("BOT_TOKEN", "123456:TEST-TOKEN")
os.environ.setdefault("ADMIN_ID", "111111111")

from app.keyboards import admin_kb, user_kb  # noqa: E402
from app.utils import texts  # noqa: E402


def part1_offline() -> None:
    """Klaviatura va matn tekshiruvlari (DB kerak emas)."""
    menu = user_kb.main_menu(connected=True)
    assert menu.inline_keyboard[0][0].style == "primary"
    assert menu.inline_keyboard[1][0].style == "success"

    admin_kb.panel(pending_access=2, pending_payments=1)
    admin_kb.access_buttons([("Ali", 5)])
    admin_kb.access_pager(1, 3, admin_kb.access_buttons([("Ali", 5)]))
    admin_kb.access_decision(5)
    admin_kb.users_pager(2, 5, admin_kb.user_buttons([("Bob", 6)]))
    admin_kb.user_card(6, banned=False)
    admin_kb.plans_menu()
    admin_kb.plan_row(1)
    admin_kb.plan_delete_confirm(1)
    admin_kb.payment_decision(3)
    admin_kb.broadcast_confirm()
    admin_kb.cancel_to_panel()
    assert user_kb.premium_checkout(1) is not None

    connect_kb = user_kb.connect_menu("privatezeninbot")
    assert connect_kb.inline_keyboard[0][0].text == "⚙️ Sozlamalarni ochish"

    # Matnlar uzbekcha va formatlash xatosiz yig'iladi.
    assert "Admin panel" in texts.ADMIN_TITLE.format(
        users=1, online=0, premium=0, premium_state=texts.PREMIUM_STATE_OFF,
        connected=0, banned=0,
    )
    texts.STATS_TITLE.format(body=texts.STATS_BODY.format(
        mention="x", user_id=1,
        connection_line=texts.CONNECTED_LINE,
        premium_line=texts.PREMIUM_INACTIVE,
        total="0", edits="0", deletes="0",
    ))
    texts.ADMIN_NEW_ACCESS_REQUEST.format(E_USER="u", E_ID="i", user="x", user_id=1, username="@a")
    print("PART 1 (offline) PASSED ✅")


async def part2_supabase() -> None:
    """DB tekshiruvlari — faqat haqiqiy SUPABASE_DB_URL bilan."""
    from app.database import db

    await db.init()
    try:
        # -- access approval oqimi --------------------------------------------
        await db.upsert_user(9001, "testuser", "Test", None)
        row = await db.get_user(9001)
        assert row["access_status"] == "pending", "yangi foydalanuvchi pending bo'lishi kerak"
        assert await db.count_pending_access() >= 1

        await db.set_access(9001, "approved", 111111111)
        assert (await db.get_user(9001))["access_status"] == "approved"

        # -- premium -----------------------------------------------------------
        until = await db.extend_premium(9001, 30)
        assert until is not None

        # -- plans + payments ---------------------------------------------------
        plan_id = await db.create_plan("Premium", 30, 10000, "Test")
        assert (await db.get_plan(plan_id))["price"] == 10000
        pay_id = await db.create_payment(9001, plan_id, "file_x")
        joined = await db.payment_with_plan(pay_id)
        assert joined["duration_days"] == 30
        await db.set_payment_status(pay_id, "approved", 111111111)
        assert all(p["id"] != pay_id for p in await db.pending_payments())

        # -- events + connections -------------------------------------------------
        await db.add_event(9001, "edit", "a -> b", chat_id=55, message_id=10)
        found = await db.get_event_by_message(55, 10)
        assert found and found["event_type"] == "edit"
        assert await db.count_user_events(9001, "edit") == 1

        await db.upsert_connection("bc_test", 9001, True, user_chat_id=9001)
        await db.upsert_connection("bc_test", 9001, False, user_chat_id=9001)
        conn = await db.get_connection("bc_test")
        assert not conn["is_enabled"] and conn["disconnected_at"]

        # -- tozalash --------------------------------------------------------------
        await db.delete_plan(plan_id)
        await db.set_banned(9001, True)
        print("PART 2 (Supabase) PASSED ✅")
    finally:
        await db.close()


if __name__ == "__main__":
    part1_offline()
    if os.getenv("SUPABASE_DB_URL"):
        asyncio.run(part2_supabase())
    else:
        print("PART 2 SKIPPED (SUPABASE_DB_URL not set - Supabase tests skipped)")
