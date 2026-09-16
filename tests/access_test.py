"""
Offline tests for the access-control feature (ruxsat / rad / ban / unban).

Run from the project root:

    python tests/access_test.py

Covers (no Telegram network):

PART A — Cache: holat DBdan o'qiladi, qaror keshda DARHOL kuchga kiradi,
         qayta ishga tushirish (load) keshni bazadan tiklaydi.
PART B — Middleware: ruxsati yo'q odam handler'larga YETIB BORMAYDI;
         adminga so'rov kartasi BIR MARTA yuboriladi; callback alert matni
         HTMLsiz bo'ladi.
PART C — Ban / unban: kesh + baza bir xil, banlangan odam bloklanadi.
PART D — Hot path: ruxsatli foydalanuvchi uchun access jadvaliga HECH
         QANDAY murojaat yo'q (tezlik talabi) + sinxron tekshiruv.
PART E — Klaviaturalar: so'rov kartasi (✅/❌) va panel (🚫/✅ + sahifa).
PART F — Ochiq rejim (TEST_MODE=0): yozuvi yo'q odam darhol ruxsat oladi.
PART G — Tugma handlerlari: allow / deny / ban / unban haqiqiy
         handler funksiyalari orqali (admin bo'lmagan odam qaror qila
         olmaydi).
PART H — Routerlar: har bir tugma AYNAN bitta handler'ga tushadi.
PART I — To'liq zanjir (dispatcher end-to-end, soxta Telegram sessiyasi):
         /start -> adminga karta -> ✅ Ruxsat -> menyu ochiladi -> 🚫 Ban
         -> menyu yopiladi.
"""

from __future__ import annotations

import asyncio
import inspect
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["BOT_TOKEN"] = "123456:TEST-TOKEN"
os.environ["ADMIN_ID"] = "111111111"
os.environ["TEST_MODE"] = "1"  # yangi foydalanuvchi ruxsat so'raydi
# env.txt haqiqiy kalitlarga ega — testlar uni o'qimasin (production Supabase!).
os.environ["CODEBUFF_SKIP_ENV_FILE"] = "1"

_tmpdir = tempfile.mkdtemp(prefix="bot_access_test_")
os.environ["DB_PATH"] = str(Path(_tmpdir) / "test.db")
os.environ.pop("SUPABASE_DB_URL", None)

from aiogram import Bot  # noqa: E402
from aiogram.client.session.base import BaseSession  # noqa: E402
from aiogram.types import CallbackQuery, Chat, Message  # noqa: E402
from aiogram.types import User as TgUser  # noqa: E402

ADMIN = 111111111

# Tarmoqqa chiqmaymiz: stub'lar javoblarni shu ro'yxatlarga yozib oladi.
_REPLIES: list[str] = []          # message.answer / callback.answer matnlari
_EDITS: list[tuple] = []          # message.edit_text(text, reply_markup)
_CARDS: list[int] = []            # adminga yuborilgan so'rov kartalari
_BOT = Bot(token="123456:TEST-TOKEN")


class _StubMessage(Message):
    """Message: answer / edit_text Telegramga bormaydi."""

    async def answer(self, text=None, **kwargs):  # type: ignore[override]
        _REPLIES.append(text)
        return None

    async def edit_text(self, text=None, **kwargs):  # type: ignore[override]
        _EDITS.append((text, kwargs.get("reply_markup")))
        return None


class _StubCallback(CallbackQuery):
    """CallbackQuery: answer shunchaki yozib olinadi."""

    async def answer(self, text=None, show_alert=False, **kwargs):  # type: ignore[override]
        _REPLIES.append(text)
        return None


async def _close_db() -> None:
    """Fon yozuvlari tugagach bazani yopamiz (aks holda 'closed database')."""
    from app.database import db
    from app.utils.tasks import drain

    await drain(timeout=5.0)
    await db.close()


def _user(user_id: int, first_name: str = "Test", username: str = "tester") -> TgUser:
    return TgUser(id=user_id, is_bot=False, first_name=first_name, username=username)


def _message(user_id: int, text: str = "/start"):
    msg = _StubMessage(
        message_id=1,
        date=datetime.now(),
        chat=Chat(id=user_id, type="private"),
        from_user=_user(user_id),
        text=text,
    )
    msg.as_(_BOT)
    return msg, msg.from_user


def _callback(user_id: int, data: str, text: str = "Asl so'rov matni"):
    cb = _StubCallback(
        id="1",
        from_user=_user(user_id),
        chat_instance="c",
        data=data,
        message=_StubMessage(
            message_id=2,
            date=datetime.now(),
            chat=Chat(id=admin_chat(), type="private"),
            from_user=_user(user_id),
            text=text,
        ),
    )
    cb.as_(_BOT)
    return cb


def admin_chat() -> int:
    return ADMIN


async def part_a_cache() -> None:
    """Kesh + qaror + qayta yuklash (restart simulyatsiyasi)."""
    from app.database import db
    from app.services import access

    assert not inspect.iscoroutinefunction(access.can_use), (
        "can_use SINXRON bo'lishi kerak (hot path)"
    )

    await db.init()
    try:
        assert access.can_use(ADMIN), "admin HAR DOIM ruxsatli"
        # TEST rejimida yozuvi yo'q odam hali kirmaydi.
        assert not access.can_use(90001)
        assert access.status(90001) is None

        # Ruxsat so'rash -> pending yozuv (bazada ham).
        assert await access.request_access(_user(90001, "Aziz", "aziz"))
        assert access.status(90001) == access.PENDING
        rows = {int(r["user_id"]): r for r in await db.access_rows()}
        assert rows[90001]["status"] == access.PENDING
        assert rows[90001]["created_at"] and rows[90001]["decided_at"] is None
        assert rows[90001]["username"] == "aziz"

        # Takroriy so'rov: yangi karta kerak emas.
        assert not await access.request_access(_user(90001))

        # Qayta ishga tushirish: kesh bazadan tiklanadi.
        access._statuses.clear()
        assert not access.can_use(90001)
        await access.load()
        assert access.status(90001) == access.PENDING

        # Ruxsat -> darhol kuchga kiradi va bazada qoladi.
        await access.set_status(90001, access.ALLOWED, decided_by=ADMIN)
        assert access.can_use(90001)
        rows = {int(r["user_id"]): r for r in await db.access_rows()}
        assert rows[90001]["decided_by"] == ADMIN
        assert rows[90001]["decided_at"], "qaror vaqti yozilishi kerak"

        # Rad etish ham saqlanadi.
        await access.set_status(90002, access.DENIED, decided_by=ADMIN)
        assert not access.can_use(90002)
        assert access.badge(90002) == "❌"
        print("PART A (cache) PASSED ✅")
    finally:
        await _close_db()


async def part_b_middleware() -> None:
    """Ruxsatsiz odam handler'ga yetib bormaydi; karta bir marta ketadi."""
    from app.database import db
    from app.middlewares import RegisterUserMiddleware
    from app.services import access
    from app.utils import texts
    from app.utils.formatting import strip_html

    # Adminga karta yuborishni yozib olamiz (tarmoqqa chiqmaymiz).
    real_notify = access.notify_admin_request

    async def _fake_notify(bot, user):  # noqa: ANN001
        _CARDS.append(user.id)
        return True

    access.notify_admin_request = _fake_notify  # type: ignore[assignment]

    await db.init()
    try:
        mw = RegisterUserMiddleware()
        handled: list[int] = []

        async def handler(event, data):
            handled.append(data["event_from_user"].id)
            return "ok"

        uid = 90011
        _CARDS.clear()
        _REPLIES.clear()

        # 1) Birinchi murojaat: bloklanadi + adminga karta (bir marta).
        msg, user = _message(uid)
        assert await mw(handler, msg, {"event_from_user": user}) is None
        assert handled == [], "ruxsatsiz odam handler'ga yetib bormasligi kerak"
        assert _CARDS == [uid], "adminga so'rov kartasi yuborilishi kerak"
        assert _REPLIES[-1] == texts.ACCESS_PENDING

        # 2) Ikkinchi murojaat: karta TAKRORLANMAYDI, faqat eslatma.
        msg2, user2 = _message(uid)
        assert await mw(handler, msg2, {"event_from_user": user2}) is None
        assert _CARDS == [uid], "karta faqat bir marta yuboriladi"
        assert handled == []
        assert _REPLIES[-1] == texts.ACCESS_PENDING

        # 3) Callback ham bloklanadi; alert matni HTMLsiz bo'lishi kerak.
        cb = _callback(uid, "user:stats")
        assert await mw(handler, cb, {"event_from_user": _user(uid)}) is None
        assert handled == []
        assert _REPLIES[-1] == strip_html(texts.ACCESS_PENDING)
        assert "<" not in (_REPLIES[-1] or ""), "alert ichida HTML teg qolmasin"

        # 4) Ruxsat berilgach handler ishlaydi.
        await access.set_status(uid, access.ALLOWED, decided_by=ADMIN)
        msg3, user3 = _message(uid)
        assert await mw(handler, msg3, {"event_from_user": user3}) == "ok"
        assert handled == [uid]

        # 5) dp.update darajasida middleware UPDATE oladi (Message EMAS) —
        #    ichidagi event topilishi kerak.  Bu aynan shu sababdan
        #    ishlamay qolgan edi: nazorat Update'ni Message deb tekshirardi.
        from aiogram.types import Update

        from app.middlewares import RegisterUserMiddleware as MW

        stranger = 90018
        handled.clear()
        update = _update_message(_BOT, 500, stranger, "/start")
        # event ichidagi Message ham stub sessiya bilan bog'langan (tarmoqsiz).
        assert isinstance(update, Update)
        assert update.event_type == "message"
        assert await mw(handler, update, {"event_from_user": _user(stranger)}) is None
        assert handled == [], "Update darajasida ham ruxsat tekshirilishi kerak"

        # Biznes-update'lar ATAYIN o'tkazib yuboriladi (from_user — suhbatdosh).
        business = Update.model_validate(
            {
                "update_id": 501,
                "business_message": {
                    "message_id": 1,
                    "date": 0,
                    "chat": {"id": 5, "type": "private"},
                    "business_connection_id": "bc_x",
                    "from": {"id": 6, "is_bot": False, "first_name": "Partner"},
                    "text": "salom",
                },
            },
            context={"bot": _BOT},
        )
        assert MW._direct_event(business) is None, "biznes-update tekshirilmaydi"
        print("PART B (middleware) PASSED ✅")
    finally:
        access.notify_admin_request = real_notify  # type: ignore[assignment]
        await _close_db()


async def part_c_ban_unban() -> None:
    """Ban / unban: kesh + baza izchil, banlangan odam bloklanadi."""
    from app.database import db
    from app.middlewares import RegisterUserMiddleware
    from app.services import access
    from app.utils import texts

    await db.init()
    try:
        uid = 90013
        await access.set_status(uid, access.BANNED, decided_by=ADMIN)
        assert not access.can_use(uid)
        assert access.badge(uid) == "🚫"

        rows = {int(r["user_id"]): r for r in await db.access_rows()}
        assert rows[uid]["status"] == access.BANNED
        assert rows[uid]["decided_by"] == ADMIN and rows[uid]["decided_at"]

        # Middleware bloklaydi va ban xabarini beradi.
        handled: list[int] = []

        async def handler(event, data):
            handled.append(1)
            return "ok"

        msg, user = _message(uid)
        _REPLIES.clear()
        assert await RegisterUserMiddleware()(handler, msg, {"event_from_user": user}) is None
        assert handled == []
        assert _REPLIES[-1] == texts.ACCESS_BANNED

        # Hisobot yo'li ham to'xtaydi: banlangan ega hisobot OLMASLIGI kerak.
        from app.services.reporter import Reporter, invalidate_connection

        await db.upsert_connection("bc_gate", uid, True, user_chat_id=uid)
        invalidate_connection(None)
        reporter = Reporter(bot=object())  # _activate tarmoqqa chiqmaydi
        assert await reporter._activate("bc_gate") is None, (
            "banlangan ega biznes-hisobot olmasligi kerak"
        )

        # Unban -> ruxsat qaytadi (kesh va baza) + hisobot yo'li tikalnadi.
        await access.set_status(uid, access.ALLOWED, decided_by=ADMIN)
        assert access.can_use(uid)
        rows = {int(r["user_id"]): r for r in await db.access_rows()}
        assert rows[uid]["status"] == access.ALLOWED
        invalidate_connection(None)
        assert await reporter._activate("bc_gate") == uid

        # is_blocked: yozuvi yo'q odam BLOKLANMAYDI, rad etilgan/banlangan esa bloklanadi.
        assert not access.is_blocked(90017), "yozuvi yo'q odam bloklanmaydi"
        assert access.is_blocked(uid) is False
        await access.set_status(90009, access.DENIED, decided_by=ADMIN)
        assert access.is_blocked(90009) is True  # rad etilgan
        assert access.is_blocked(ADMIN) is False  # admin hech qachon bloklanmaydi
        print("PART C (ban/unban) PASSED ✅")
    finally:
        await _close_db()


async def part_d_hot_path() -> None:
    """Ruxsatli foydalanuvchi update'i access jadvaliga murojaat qilmaydi."""
    from app.config import settings
    from app.database import db
    from app.middlewares import RegisterUserMiddleware
    from app.services import access

    assert not hasattr(settings, "is_user_allowed"), (
        "eski is_user_allowed olib tashlanishi kerak (yagona manba: access.py)"
    )

    await db.init()
    try:
        uid = 90014
        await access.set_status(uid, access.ALLOWED, decided_by=ADMIN)

        real_set_access = db.set_access
        real_access_rows = db.access_rows

        async def _no_io(*args, **kwargs):
            raise AssertionError("hot path access jadvaliga murojaat qildi!")

        db.set_access = _no_io  # type: ignore[assignment]
        db.access_rows = _no_io  # type: ignore[assignment]
        try:
            handled: list[int] = []

            async def handler(event, data):
                handled.append(1)
                return "ok"

            msg, user = _message(uid)
            assert await RegisterUserMiddleware()(handler, msg, {"event_from_user": user}) == "ok"
            assert handled == [1]
        finally:
            db.set_access = real_set_access  # type: ignore[assignment]
            db.access_rows = real_access_rows  # type: ignore[assignment]

        # 100 000 tekshiruv — bir soniyadan ancha tez bo'lishi kerak.
        start = time.perf_counter()
        for _ in range(100_000):
            access.can_use(uid)
        elapsed = time.perf_counter() - start
        assert elapsed < 1.0, f"can_use juda sekin: {elapsed:.3f}s / 100k"
        print(f"PART D (hot path) PASSED ✅  (100k tekshiruv: {elapsed * 1000:.0f} ms)")
    finally:
        await _close_db()


def part_e_keyboards() -> None:
    """So'rov kartasi va ban/unban paneli tugmalari."""
    from app.keyboards import access_kb, user_kb
    from app.utils import texts

    # -- so'rov kartasi: ✅ Ruxsat berish / ❌ Rad etish ---------------------
    card = access_kb.request_card(90001)
    labels = [b.text for row in card.inline_keyboard for b in row]
    callbacks = [b.callback_data for row in card.inline_keyboard for b in row]
    assert any("Ruxsat berish" in label for label in labels), labels
    assert any("Rad etish" in label for label in labels), labels
    assert callbacks == ["access:allow:90001", "access:deny:90001"], callbacks

    # -- panel: HOLATGA QARAB ban / ruxsat berish / blokdan chiqarish -------
    panel = access_kb.users_panel(
        [(11, "Aziz", "ban"), (22, "Sobir", "grant"), (33, "Dilnoza", "unban")],
        1,
        3,
    )
    ban_btn = panel.inline_keyboard[0][0]
    grant_btn = panel.inline_keyboard[1][0]
    unban_btn = panel.inline_keyboard[2][0]
    assert ban_btn.callback_data == "access:ban:11:1", ban_btn.callback_data
    assert ban_btn.style == "danger" and "🚫" in ban_btn.text and "Ban" in ban_btn.text
    assert grant_btn.callback_data == "access:unban:22:1", grant_btn.callback_data
    assert "Ruxsat berish" in grant_btn.text and grant_btn.style == "success"
    assert unban_btn.callback_data == "access:unban:33:1", unban_btn.callback_data
    assert "Blokdan chiqarish" in unban_btn.text and unban_btn.style == "success"
    # Tugmada kim ekani ham ko'rinadi (ism + ID).
    assert "Aziz" in ban_btn.text and "11" in ban_btn.text

    # -- sahifalash: 1/3 -> faqat "keyingi" (navbat 4-qatorda) --------------
    assert [b.callback_data for b in panel.inline_keyboard[3]] == ["user:users:p:2"]
    last_page = access_kb.users_panel([(11, "Aziz", "ban")], 3, 3)
    assert [b.callback_data for b in last_page.inline_keyboard[1]] == ["user:users:p:2"]

    # -- oxirgi qatorda menyuga qaytish -------------------------------------
    assert panel.inline_keyboard[-1][0].callback_data == user_kb.CB_BACK_MENU

    # -- callback ma'lumotlari va tugma matni chegarada ---------------------
    for row in panel.inline_keyboard:
        for button in row:
            if button.callback_data:
                assert len(button.callback_data.encode()) <= 64
            assert len(button.text) <= 64, f"tugma matni juda uzun: {button.text}"

    # -- uzun ism qisqartiriladi --------------------------------------------
    assert len(access_kb.short_label("a", "Juda Uzun Ism Egasi", 1)) <= access_kb.LABEL_MAX
    assert access_kb.short_label(None, None, 777) == "777"

    # -- matnlar formatlanadi (xato bermasin) -------------------------------
    texts.USERS_PANEL_TITLE.format(
        total="2", online="1", body="x", legend=texts.USERS_PANEL_LEGEND
    )
    texts.ACCESS_REQUEST_ADMIN.format(who="x", user_id=1, username="@x")
    texts.USERS_PANEL_LINE.format(badge="✅", mention="x", user_id=1)
    print("PART E (keyboards) PASSED ✅")


def part_f_open_mode() -> None:
    """TEST_MODE=0: yozuvi yo'q odam darhol ruxsat oladi (DBga yozuvsiz)."""
    from app.config import settings
    from app.services import access

    assert settings.test_mode is True, "bu fayl TEST_MODE=1 bilan ishlaydi"
    stranger = 90016
    assert not access.can_use(stranger), "TEST rejimida tasdiq kerak"
    object.__setattr__(settings, "test_mode", False)
    try:
        assert access.can_use(stranger), "ochiq rejimda hamma kiradi"
        assert access.badge(stranger) == "✅"
    finally:
        object.__setattr__(settings, "test_mode", True)
    print("PART F (open mode) PASSED ✅")


async def part_g_buttons() -> None:
    """HAQIQIY handler'lar: allow / deny / ban / unban tugmalari."""
    from app.database import db
    from app.handlers import admin as admin_handlers
    from app.keyboards import access_kb, user_kb
    from app.services import access
    from app.utils import texts

    real_notify = access.notify_user
    notified: list[tuple[int, str]] = []

    async def _fake_notify(bot, user_id, text, **kwargs):  # noqa: ANN001
        notified.append((user_id, text))
        return True

    access.notify_user = _fake_notify  # type: ignore[assignment]

    def panel_callbacks() -> list[str]:
        markup = _EDITS[-1][1]
        return [
            b.callback_data
            for row in markup.inline_keyboard
            for b in row
            if b.callback_data
        ]

    await db.init()
    try:
        # ===== ✅ Ruxsat berish ===========================================
        uid = 90021
        await access.request_access(_user(uid, "Aziz", "aziz"))
        _EDITS.clear()
        cb = _callback(
            ADMIN,
            f"{access_kb.CB_ALLOW}:{uid}",
            text=texts.ACCESS_REQUEST_ADMIN.format(who="Aziz", user_id=uid, username="@aziz"),
        )
        await admin_handlers.allow_user(cb, _BOT)
        assert access.can_use(uid) and access.status(uid) == access.ALLOWED
        assert notified[-1] == (uid, texts.USER_APPROVED), notified[-1]
        edited, markup = _EDITS[-1]
        assert edited.startswith(texts.ACCESS_REQUEST_ALLOWED), edited[:60]
        assert "@aziz" in edited, "karta matni saqlanib qolishi kerak"
        assert markup.inline_keyboard == [], "qarordan keyin tugmalar olib tashlanadi"
        rows = {int(r["user_id"]): r for r in await db.access_rows()}
        assert rows[uid]["status"] == access.ALLOWED

        # ===== ❌ Rad etish ===============================================
        uid2 = 90022
        await access.request_access(_user(uid2, "Sobir", "sobir"))
        cb = _callback(ADMIN, f"{access_kb.CB_DENY}:{uid2}")
        await admin_handlers.deny_user(cb, _BOT)
        assert not access.can_use(uid2) and access.status(uid2) == access.DENIED
        assert notified[-1] == (uid2, texts.USER_DENIED)

        # ===== admin bo'lmagan odam qaror qila olmaydi ====================
        cb = _callback(90023, f"{access_kb.CB_ALLOW}:{uid2}")
        await admin_handlers.allow_user(cb, _BOT)
        assert access.status(uid2) == access.DENIED, "begona odam ruxsat bera olmasin"
        assert _REPLIES[-1] == "Bu bo'lim faqat admin uchun"

        # ===== panel: ro'yxat + ban/unban tugmalari ========================
        await db.upsert_user(uid, "aziz", "Aziz", None)
        await db.upsert_user(uid2, "sobir", "Sobir", None)
        _EDITS.clear()
        await admin_handlers.show_users(_callback(ADMIN, user_kb.CB_USERS))
        assert "Foydalanuvchilar boshqaruvi" in _EDITS[-1][0]
        cbs = panel_callbacks()
        assert f"{access_kb.CB_BAN}:{uid}:1" in cbs, cbs      # ruxsatli -> Ban
        assert f"{access_kb.CB_UNBAN}:{uid2}:1" in cbs, cbs   # rad etilgan -> Unban

        # ===== 🚫 Ban =====================================================
        _EDITS.clear()
        await admin_handlers.ban_user(_callback(ADMIN, f"{access_kb.CB_BAN}:{uid}:1"), _BOT)
        assert not access.can_use(uid) and access.status(uid) == access.BANNED
        assert notified[-1] == (uid, texts.USER_BANNED)
        assert _REPLIES[-1] == "🚫 Banlandi"
        assert f"{access_kb.CB_UNBAN}:{uid}:1" in panel_callbacks(), (
            "banlangandan keyin tugma Unban bo'lishi kerak"
        )

        # ===== ✅ Unban ===================================================
        await admin_handlers.unban_user(_callback(ADMIN, f"{access_kb.CB_UNBAN}:{uid}:1"), _BOT)
        assert access.can_use(uid), "unban ruxsatni qaytaradi"
        assert notified[-1] == (uid, texts.USER_UNBANNED)
        assert _REPLIES[-1] == "✅ Ruxsat berildi"

        # ===== sahifalash ================================================
        _EDITS.clear()
        await admin_handlers.page_users(_callback(ADMIN, "user:users:p:1"))
        assert "Foydalanuvchilar boshqaruvi" in _EDITS[-1][0]

        # ===== buzuq callback: yiqilmaydi ================================
        await admin_handlers.ban_user(_callback(ADMIN, f"{access_kb.CB_BAN}:x:y"), _BOT)
        assert _REPLIES[-1] == "Foydalanuvchi IDsi topilmadi"
        print("PART G (allow/deny/ban/unban buttons) PASSED ✅")
    finally:
        access.notify_user = real_notify  # type: ignore[assignment]
        await _close_db()


async def part_h_wiring() -> None:
    """Routerlar: har bir tugma callback'i AYNAN bitta handler'ga tushadi."""
    from app.handlers import admin, user
    from app.keyboards import access_kb, user_kb

    handlers = []
    for router in (admin.router, user.router):
        handlers += [(router.name, h) for h in router.callback_query.handlers]

    expected = {
        f"{access_kb.CB_ALLOW}:5": "allow_user",
        f"{access_kb.CB_DENY}:5": "deny_user",
        f"{access_kb.CB_BAN}:5:1": "ban_user",
        f"{access_kb.CB_UNBAN}:5:1": "unban_user",
        user_kb.CB_USERS: "show_users",
        f"{access_kb.CB_USERS_PAGE}:2": "page_users",
        user_kb.CB_STATS: "show_stats",
        user_kb.CB_BACK_MENU: "back_to_menu",
        user_kb.CB_CONNECT: "show_connect",
    }
    for data, name in expected.items():
        cb = _callback(ADMIN, data)
        hits = []
        for _router_name, handler in handlers:
            if all([await f.call(cb) for f in handler.filters]):
                hits.append(getattr(handler.callback, "__name__", "?"))
        assert hits == [name], f"{data} -> {hits} (kutilgan: {name})"
    print("PART H (router wiring) PASSED ✅")


class _StubSession(BaseSession):
    """Telegram serveri o'rniga: so'rovlarni yozib oladi, soxta javob qaytaradi.

    Shu sababli butun zanjirni (update -> middleware -> handler -> Bot API)
    TARMOQSIZ sinab ko'rish mumkin.
    """

    def __init__(self) -> None:
        super().__init__()
        self.calls: list = []

    async def make_request(self, bot, method, timeout=None):  # type: ignore[override]
        self.calls.append(method)
        return True

    async def stream_content(
        self, url, headers=None, timeout=30, chunk_size=65536, raise_for_status=True
    ):
        yield b""

    async def close(self) -> None:  # type: ignore[override]
        return None

    # -- qulaylik: so'rovlarni tekshirish -------------------------------
    def sent(self, chat_id: int) -> list:
        return [
            c
            for c in self.calls
            if getattr(c, "chat_id", None) == chat_id and c.__class__.__name__ == "SendMessage"
        ]

    def edited(self) -> list:
        return [c for c in self.calls if c.__class__.__name__ == "EditMessageText"]

    @staticmethod
    def markup(call) -> str:
        """Tugma callback ma'lumotlarini bitta satrga yig'adi."""
        markup = getattr(call, "reply_markup", None)
        if markup is None:
            return ""
        return " ".join(
            b.callback_data or ""
            for row in markup.inline_keyboard
            for b in row
        )


# Testlarda tasodifan REAL Telegram so'rovi ketmasin (offline ishlash sharti).
_BOT.session = _StubSession()


def _update_message(bot, update_id: int, user_id: int, text: str):
    """Xom Telegram update'i (xuddi tarmoqdan kelgandek)."""
    from aiogram.types import Update

    return Update.model_validate({
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "date": int(time.time()),
            "chat": {"id": user_id, "type": "private"},
            "from": {
                "id": user_id,
                "is_bot": False,
                "first_name": "Test",
                "username": f"u{user_id}",
            },
            "text": text,
        },
    }, context={"bot": bot})


def _update_callback(bot, update_id: int, user_id: int, data: str, chat_id: int):
    from aiogram.types import Update

    return Update.model_validate({
        "update_id": update_id,
        "callback_query": {
            "id": str(update_id),
            "from": {
                "id": user_id,
                "is_bot": False,
                "first_name": "Test",
                "username": f"u{user_id}",
            },
            "chat_instance": "c",
            "data": data,
            "message": {
                "message_id": 99,
                "date": int(time.time()),
                "chat": {"id": chat_id, "type": "private"},
                "from": {"id": 1, "is_bot": True, "first_name": "bot"},
                "text": "karta",
            },
        },
    }, context={"bot": bot})


async def part_i_dispatcher_end_to_end() -> None:
    """To'liq zanjir: /start -> so'rov -> ✅ Ruxsat -> /start ishlaydi -> 🚫 Ban."""
    from aiogram import Bot, Dispatcher

    from app.database import db
    from app.handlers import admin, business, user
    from app.keyboards import access_kb, user_kb
    from app.middlewares import RegisterUserMiddleware
    from app.services import access

    await db.init()
    try:
        bot = Bot(token="123456:TEST-TOKEN")
        session = _StubSession()
        bot.session = session  # type: ignore[assignment]

        dp = Dispatcher()
        dp.update.outer_middleware(RegisterUserMiddleware())
        for router in (business.router, admin.router, user.router):
            dp.include_router(router)

        uid = 90031
        update_id = 1

        # 1) Yangi odam /start -> MENYU YO'Q, adminga esa TUGMALI karta ketadi.
        await dp.feed_update(bot, _update_message(bot, update_id, uid, "/start"))
        update_id += 1
        stranger_msgs = session.sent(uid)
        assert stranger_msgs, "foydalanuvchi javob olishi kerak"
        assert not getattr(stranger_msgs[-1], "reply_markup", None), (
            "ruxsatsiz odamga menyu berilmasin"
        )
        cards = [c for c in session.sent(ADMIN) if "access:allow:" in _StubSession.markup(c)]
        assert len(cards) == 1, f"adminga aynan bitta karta: {len(cards)}"
        assert f"access:allow:{uid}" in _StubSession.markup(cards[0])
        assert f"access:deny:{uid}" in _StubSession.markup(cards[0])
        assert access.status(uid) == access.PENDING

        # 2) Yana /start -> kartalar soni oshmaydi (spam yo'q).
        await dp.feed_update(bot, _update_message(bot, update_id, uid, "/start"))
        update_id += 1
        cards = [c for c in session.sent(ADMIN) if "access:allow:" in _StubSession.markup(c)]
        assert len(cards) == 1, "karta takrorlanmasligi kerak"

        # 3) Admin «✅ Ruxsat berish» bosadi.
        await dp.feed_update(
            bot, _update_callback(bot, update_id, ADMIN, f"{access_kb.CB_ALLOW}:{uid}", ADMIN)
        )
        update_id += 1
        assert access.can_use(uid), "ruxsat berilgach odam kira olishi kerak"
        assert session.edited(), "karta tahrirlanishi kerak (tugmalar olib tashlanadi)"
        approved = [c for c in session.sent(uid) if "Endi botdan" in (c.text or "")]
        assert approved, "foydalanuvchiga 'ruxsat berildi' xabari ketishi kerak"
        menus_before = [
            c for c in session.sent(uid) if "user:stats" in _StubSession.markup(c)
        ]
        assert menus_before, "ruxsat berilgach menyu ham yuborilishi kerak"

        # 4) Endi /start HAQIQIY menyuni beradi (handler ishga tushadi).
        await dp.feed_update(bot, _update_message(bot, update_id, uid, "/start"))
        update_id += 1
        menus_after = [
            c for c in session.sent(uid) if "user:stats" in _StubSession.markup(c)
        ]
        assert len(menus_after) > len(menus_before), (
            "ruxsatdan keyin /start menyu berishi kerak"
        )

        # 5) Admin panelni ochadi: ban tugmasi shu odam uchun chiqadi.
        await dp.feed_update(
            bot, _update_callback(bot, update_id, ADMIN, user_kb.CB_USERS, ADMIN)
        )
        update_id += 1
        panel = session.edited()[-1]
        assert f"access:ban:{uid}:1" in _StubSession.markup(panel)

        # 6) 🚫 Ban tugmasi -> odam bloklanadi.
        await dp.feed_update(
            bot, _update_callback(bot, update_id, ADMIN, f"{access_kb.CB_BAN}:{uid}:1", ADMIN)
        )
        update_id += 1
        assert access.status(uid) == access.BANNED
        assert any("bloklandingiz" in (c.text or "") for c in session.sent(uid))

        # 7) Banlangandan keyin /start -> MENYU YO'Q, ban xabari.
        await dp.feed_update(bot, _update_message(bot, update_id, uid, "/start"))
        update_id += 1
        last = session.sent(uid)[-1]
        assert "bloklangansiz" in (last.text or ""), last.text
        assert not getattr(last, "reply_markup", None), "banlanganga menyu berilmaydi"
        print("PART I (dispatcher end-to-end) PASSED ✅")
    finally:
        await bot.session.close()
        await _close_db()


async def part_j_one_round_trip() -> None:
    """Tezlik: har bir ekran BITTA so'rovda (round-trip) yig'iladi.

    Supabase uzoq regionda bo'lsa (Sydney ~1.2 s) har bir qo'shimcha so'rov
    foydalanuvchiga ~1.2 s bo'lib qaytadi.  Shu sababli statistika ekrani
    7 so'rovdan 1 so'rovga tushirildi, /start esa 2 dan 1 ga.
    """
    from app.database import db
    from app.storage_sqlite import SqliteDatabase
    from app.utils.timeutils import is_online, now_iso

    await db.init()
    try:
        uid = 90041
        await db.upsert_user(uid, "speed", "Speed", None)
        await db.add_event(uid, "text", "a", chat_id=1, message_id=1, sender_id=uid)
        await db.add_event(uid, "edit", "a->b", chat_id=1, message_id=1, sender_id=uid)
        await db.add_event(uid, "delete", "a", chat_id=1, message_id=2, sender_id=uid)
        await db.add_event(
            uid, "delete_media", "file:x|photo|", chat_id=1, message_id=3, sender_id=uid
        )
        await db.upsert_connection("bc_speed", uid, True, user_chat_id=uid)

        # -- _fetch_* chaqiruvlarini sanaymiz = so'rovlar soni ---------------
        counts = {"n": 0}
        backend = db._backend
        originals: dict[str, object] = {}
        for name in ("_fetch_one", "_fetch_all", "_fetchval"):
            originals[name] = getattr(backend, name)

            def wrapper(*args, _name=name, **kwargs):
                counts["n"] += 1
                return originals[_name](*args, **kwargs)  # type: ignore[operator]

            setattr(backend, name, wrapper)
        try:
            counts["n"] = 0
            stats = await db.user_stats(uid)
            assert counts["n"] == 1, f"statistika {counts['n']} so'rov yubordi (1 kutilgan)"

            counts["n"] = 0
            connected = await db.has_active_connection(uid)
            assert counts["n"] == 1, f"/start {counts['n']} so'rov yubordi (1 kutilgan)"
        finally:
            for name, original in originals.items():
                setattr(backend, name, original)

        # -- raqamlar alohida so'rovlar bilan AYNAN bir xil -----------------
        assert stats["users_total"] == await db.count_users()
        assert stats["events_total"] == await db.count_user_events(uid)
        assert stats["edits"] == await db.count_user_events(uid, "edit")
        assert stats["deletes"] == await db.count_user_events(uid, "delete")
        assert stats["deletes_media"] == await db.count_user_events(uid, "delete_media")
        assert stats["active_connections"] == len(
            [c for c in await db.connections_for_user(uid) if c.get("is_enabled")]
        )
        assert connected is True
        assert stats["events_total"] == 4 and stats["edits"] == 1

        # -- "online" hisobi xotirada (qo'shimcha so'rovsiz) -----------------
        assert is_online(now_iso())
        assert not is_online(None)
        assert not is_online("2020-01-01T00:00:00")
        print("PART J (one round trip per screen) PASSED ✅")
    finally:
        await _close_db()


async def part_k_no_waiting_writes() -> None:
    """Tezlik: ro'yxatga olish yozuvi update'ni KUTDIRMAYDI (fonda ketadi)."""
    import app.utils.tasks as tasks
    from app.database import db
    from app.middlewares import RegisterUserMiddleware, _last_upsert
    from app.services import access

    await db.init()
    try:
        uid = 90042
        await access.set_status(uid, access.ALLOWED, decided_by=ADMIN)
        _last_upsert.pop(uid, None)

        real_upsert = db.upsert_user
        started = asyncio.Event()
        never = asyncio.Event()

        async def slow_upsert(**kwargs):
            started.set()
            await never.wait()  # hech qachon tugamaydi

        db.upsert_user = slow_upsert  # type: ignore[assignment]
        try:
            handled: list[int] = []

            async def handler(event, data):
                handled.append(1)
                return "ok"

            msg, user = _message(uid)
            begin = time.perf_counter()
            assert await RegisterUserMiddleware()(handler, msg, {"event_from_user": user}) == "ok"
            elapsed = time.perf_counter() - begin

            # Yozuv hali TUGAMAGAN bo'lsa ham update allaqachon javob bergan.
            assert handled == [1]
            assert not never.is_set(), "yozuv tugamagan bo'lishi kerak"
            assert elapsed < 0.2, f"update yozuvni kutdi: {elapsed:.3f}s"

            await asyncio.sleep(0.05)  # fon vazifasi navbatga tushsin
            assert started.is_set(), "yozuv fonda boshlanishi kerak"
            assert not never.is_set()
            assert tasks.pending_count() >= 1, "yozuv fon vazifasi sifatida ketishi kerak"
        finally:
            db.upsert_user = real_upsert  # type: ignore[assignment]
            never.set()
            await asyncio.sleep(0.05)  # fon vazifalari tugasin
        print("PART K (writes never block an update) PASSED ✅")
    finally:
        await _close_db()


async def main() -> None:
    await part_a_cache()
    await part_b_middleware()
    await part_c_ban_unban()
    await part_d_hot_path()
    part_e_keyboards()
    part_f_open_mode()
    await part_g_buttons()
    await part_h_wiring()
    await part_i_dispatcher_end_to_end()
    await part_j_one_round_trip()
    await part_k_no_waiting_writes()
    print("ALL ACCESS TESTS PASSED ✅")


if __name__ == "__main__":
    asyncio.run(main())
