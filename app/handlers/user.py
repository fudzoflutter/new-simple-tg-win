"""
Foydalanuvchi tomonidagi handlerlar.

* /start              – asosiy menyu
* Statistika          – shaxsiy statistika + "qanday ishlaydi" izohi
* Ulanish             – tg://settings/edit orqali sozlamalarga yo'naltirish

«👥 Foydalanuvchilar» (ban/unban bilan) :mod:`app.handlers.admin` da —
u faqat admin uchun.

Premium / obuna / to'lov bo'limlari OLIB TASHLANGAN (yangi talab).
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.database import db
from app.keyboards import user_kb
from app.utils import texts
from app.utils.formatting import fmt_number, mention_by_id
from app.utils.texts import STATS_BODY, STATS_TITLE

router = Router(name="user")
logger = logging.getLogger(__name__)

# ESLATMA (tezlik): har bir callback handler AVVAL ``cb.answer()`` qiladi.
# Aks holda tugma ustidagi "spinner" DB so'rovi tugagunicha aylanib turadi
# (Supabase uzoqda — foydalanuvchiga "tugma ishlamayapti"dek tuyuladi).


# Bot username hech qachon o'zgarmaydi — bir marta so'raymiz, keyin kesh.
_bot_username: str = ""


# ---------------------------------------------------------------------------
# /start – asosiy menyu
# ---------------------------------------------------------------------------
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    """Kirish nuqtasi: to'g'ridan-to'g'ri menyu."""
    await state.clear()

    try:
        # TEZLIK: BITTA so'rov (avval 2 tasi edi — uzoq bazada har biri
        # ~1.2 s; bu yerda faqat "ulanganmi" degan javob kerak).
        is_connected = await db.has_active_connection(message.from_user.id)

        if is_connected:
            await message.answer(
                texts.ALREADY_CONNECTED,
                reply_markup=user_kb.main_menu(connected=True),
                disable_web_page_preview=True,
            )
            return

        await message.answer(
            f"{texts.WELCOME}\n\n{texts.MENU_HINT}",
            reply_markup=user_kb.main_menu(connected=False),
            disable_web_page_preview=True,
        )
    except Exception as e:  # noqa: BLE001 – DB xatosi /start ni to'xtatmasin
        logger.warning("cmd_start DB xatosi: %s - foydalanuvchiga javob berilmaydi", e)
        await message.answer(
            texts.WELCOME + "\n\n" + texts.MENU_HINT,
            reply_markup=user_kb.main_menu(connected=False),
            disable_web_page_preview=True,
        )


@router.callback_query(F.data == user_kb.CB_BACK_MENU)
async def back_to_menu(cb: CallbackQuery, state: FSMContext) -> None:
    """Har qanday ekrandan menyuga qaytish (ulanish holati bilan)."""
    await cb.answer()  # TEZLIK: spinner darhol to'xtaydi
    await state.clear()
    connected = await db.has_active_connection(cb.from_user.id)
    await cb.message.edit_text(
        f"{texts.WELCOME}\n\n{texts.MENU_HINT}",
        reply_markup=user_kb.main_menu(connected=connected),
    )


# ---------------------------------------------------------------------------
# Statistika + qanday ishlaydi
# ---------------------------------------------------------------------------
@router.callback_query(F.data == user_kb.CB_STATS)
async def show_stats(cb: CallbackQuery) -> None:
    """Shaxsiy statistika ekrani.

    TEZLIK: tugma DARHOL javob beradi (spinner to'xtaydi), ekran esa
    BITTA so'rovdan keyin yangilanadi — avval 7 ta alohida so'rov ketardi
    (uzoq Supabaseda ~4 sekund, shu sababli tugma "ishlamayotgandek"
    ko'rinardi).
    """
    await cb.answer()

    try:
        stats = await db.user_stats(cb.from_user.id)
    except Exception:  # noqa: BLE001 – DB xatosi botni to'xtatmasin
        logger.exception("Statistika so'rovi bajarilmadi (user=%s)", cb.from_user.id)
        await cb.message.edit_text(
            texts.ERROR_USER, reply_markup=user_kb.back_to_menu()
        )
        return

    body = STATS_BODY.format(
        mention=mention_by_id(
            cb.from_user.id, cb.from_user.first_name or "User", cb.from_user.username
        ),
        user_id=cb.from_user.id,
        connection_line=(
            texts.CONNECTED_LINE
            if stats["active_connections"]
            else texts.NOT_CONNECTED_LINE
        ),
        users=fmt_number(stats["users_total"]),
        total=fmt_number(stats["events_total"]),
        edits=fmt_number(stats["edits"]),
        deletes=fmt_number(stats["deletes"] + stats["deletes_media"]),
    )
    await cb.message.edit_text(
        STATS_TITLE.format(body=body) + "\n\n" + texts.HOW_IT_WORKS,
        reply_markup=user_kb.back_to_menu(),
    )


# ---------------------------------------------------------------------------
# Ulanish yo'riqnomasi — tg://settings/edit havolasi bilan
# ---------------------------------------------------------------------------
@router.callback_query(F.data == user_kb.CB_CONNECT)
async def show_connect(cb: CallbackQuery) -> None:
    """Sozlamalar → Telegram Business → Chatbotlar yo'riqnomasi."""
    await cb.answer()  # TEZLIK: spinner darhol to'xtaydi
    global _bot_username
    if not _bot_username:  # getMe API so'rovi FAQAT birinchi marta
        me = await cb.bot.me()
        _bot_username = me.username or ""
    await cb.message.edit_text(
        texts.CONNECT_TITLE.format(bot_username=_bot_username),
        reply_markup=user_kb.connect_menu(),
        disable_web_page_preview=True,
    )


# ---------------------------------------------------------------------------
# Havola tozalash (yangi talab — hamma uchun, admin panellsiz)
# ---------------------------------------------------------------------------
