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
os.environ.setdefault("TEST_MODE", "0")  # Test mode off for tests
# env.txt haqiqiy kalitlarni o'z ichiga oladi — testlar uni o'qimasin.
os.environ.setdefault("CODEBUFF_SKIP_ENV_FILE", "1")

from app.keyboards import user_kb  # noqa: E402
from app.utils import texts  # noqa: E402


def part1_offline() -> None:
    """Klaviatura va matn tekshiruvlari (DB kerak emas)."""
    menu = user_kb.main_menu(connected=True)
    assert menu.inline_keyboard[0][0].style == "primary"
    assert menu.inline_keyboard[1][0].style == "success"
    labels = [b.text for row in menu.inline_keyboard for b in row]
    assert any("Statistika" in label for label in labels)
    assert any("Foydalanuvchilar" in label for label in labels)
    # Premium removed: no premium button anywhere in the menu.
    assert not any("Premium" in label for label in labels)

    assert user_kb.back_to_menu() is not None

    connect_kb = user_kb.connect_menu("privatezeninbot")
    assert connect_kb.inline_keyboard[0][0].text == "⚙️ Sozlamalarni ochish"

    # Matnlar o'zbekcha va formatlash xatosiz yig'iladi.
    texts.STATS_TITLE.format(body=texts.STATS_BODY.format(
        mention="x", user_id=1,
        connection_line=texts.CONNECTED_LINE,
        users="0", total="0", edits="0", deletes="0",
    ))
    texts.USERS_COUNT.format(total="1", online="1")

    # Havola tozalovchi xizmat ishlaydi (kuzatuv parametri olib tashlanadi).
    from app.services.linkcleaner import clean_url

    assert clean_url("https://x.com/p?utm_source=a&id=1") == "https://x.com/p?id=1"
    print("PART 1 (offline) PASSED ✅")


async def part2_supabase() -> None:
    """DB tekshiruvlari — faqat haqiqiy SUPABASE_DB_URL bilan."""
    from app.database import db

    await db.init()
    try:
        # -- kirish ochiq (tasdiqlash/ban tizimi olib tashlandi) --------------
        await db.upsert_user(9001, "testuser", "Test", None)
        row = await db.get_user(9001)
        assert row["username"] == "testuser"
        assert await db.count_users() >= 1

        # -- events + connections -------------------------------------------------
        await db.add_event(9001, "edit", "a -> b", chat_id=55, message_id=10,
                           sender_id=9001)
        found = await db.get_event_by_message(55, 10)
        assert found and found["event_type"] == "edit"
        assert await db.count_user_events(9001, "edit") == 1

        await db.upsert_connection("bc_test", 9001, True, user_chat_id=9001)
        await db.upsert_connection("bc_test", 9001, False, user_chat_id=9001)
        conn = await db.get_connection("bc_test")
        assert not conn["is_enabled"] and conn["disconnected_at"]
        print("PART 2 (Supabase) PASSED ✅")
    finally:
        await db.close()


if __name__ == "__main__":
    part1_offline()
    if os.getenv("SUPABASE_DB_URL"):
        asyncio.run(part2_supabase())
    else:
        print("PART 2 SKIPPED (SUPABASE_DB_URL not set - Supabase tests skipped)")
