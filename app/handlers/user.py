"""
Foydalanuvchi tomonidagi handlerlar.

* /start              – asosiy menyu (kirish ochiq)
* Statistika          – shaxsiy statistika + "qanday ishlaydi" izohi
* Foydalanuvchilar    – botdan nechta odam foydalanayotgani (hamma uchun)
* Ulanish             – tg://settings/edit orqali sozlamalarga yo'naltirish
* Havola tozalash     – yuborilgan havoladan kuzatuv parametrlarini olib
                        tashlash (hamma uchun, admin panellsiz)

Premium / obuna / to'lov bo'limlari OLIB TASHLANGAN (yangi talab).
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.database import db
from app.keyboards import user_kb
from app.services.linkcleaner import clean_text
from app.utils import texts
from app.utils.formatting import esc, fmt_number, mention_by_id
from app.utils.texts import STATS_BODY, STATS_TITLE

router = Router(name="user")


# Bot username hech qachon o'zgarmaydi — bir marta so'raymiz, keyin kesh.
_bot_username: str = ""


# ---------------------------------------------------------------------------
# /start – asosiy menyu
# ---------------------------------------------------------------------------
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    """Kirish nuqtasi: to'g'ridan-to'g'ri menyu."""
    await state.clear()

    # ParALLEL: foydalanuvchi + ulanishlar (2 so'rov ~1 so'rov vaqtida).
    _, conns = await db.gather(
        db.get_user(message.from_user.id),
        db.connections_for_user(message.from_user.id),
    )
    is_connected = any(c.get("is_enabled") for c in conns)

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


@router.callback_query(F.data == user_kb.CB_BACK_MENU)
async def back_to_menu(cb: CallbackQuery, state: FSMContext) -> None:
    """Har qanday ekrandan menyuga qaytish (ulanish holati bilan)."""
    await state.clear()
    conns = await db.connections_for_user(cb.from_user.id)
    connected = any(c.get("is_enabled") for c in conns)
    await cb.message.edit_text(
        f"{texts.WELCOME}\n\n{texts.MENU_HINT}",
        reply_markup=user_kb.main_menu(connected=connected),
    )
    await cb.answer()


# ---------------------------------------------------------------------------
# Statistika + qanday ishlaydi
# ---------------------------------------------------------------------------
@router.callback_query(F.data == user_kb.CB_STATS)
async def show_stats(cb: CallbackQuery) -> None:
    """Shaxsiy statistika ekrani (premium emoji IDlari bilan bezatilgan)."""
    # ParALLEL: barcha so'rovlar bir vaqtda (Supabase uzoqda — tezlik uchun).
    _, conns, total, edits, d1, d2, users_total = await db.gather(
        db.get_user(cb.from_user.id),
        db.connections_for_user(cb.from_user.id),
        db.count_user_events(cb.from_user.id),
        db.count_user_events(cb.from_user.id, "edit"),
        db.count_user_events(cb.from_user.id, "delete"),
        db.count_user_events(cb.from_user.id, "delete_media"),
        db.count_users(),
    )
    connected = any(c.get("is_enabled") for c in conns)
    deletes = d1 + d2

    body = STATS_BODY.format(
        mention=mention_by_id(
            cb.from_user.id, cb.from_user.first_name or "User", cb.from_user.username
        ),
        user_id=cb.from_user.id,
        connection_line=texts.CONNECTED_LINE if connected else texts.NOT_CONNECTED_LINE,
        users=fmt_number(users_total),
        total=fmt_number(total),
        edits=fmt_number(edits),
        deletes=fmt_number(deletes),
    )
    await cb.message.edit_text(
        STATS_TITLE.format(body=body) + "\n\n" + texts.HOW_IT_WORKS,
        reply_markup=user_kb.back_to_menu(),
    )
    await cb.answer()


# ---------------------------------------------------------------------------
# Foydalanuvchilar soni — HAMMA uchun (admin panel shart emas)
# ---------------------------------------------------------------------------
@router.callback_query(F.data == user_kb.CB_USERS)
async def show_users(cb: CallbackQuery) -> None:
    """Botdan qancha odam foydalanayotganini ko'rsatadi."""
    total, online = await db.gather(db.count_users(), db.count_online())
    await cb.message.edit_text(
        texts.USERS_COUNT.format(total=fmt_number(total), online=fmt_number(online)),
        reply_markup=user_kb.back_to_menu(),
    )
    await cb.answer()


# ---------------------------------------------------------------------------
# Ulanish yo'riqnomasi — tg://settings/edit havolasi bilan
# ---------------------------------------------------------------------------
@router.callback_query(F.data == user_kb.CB_CONNECT)
async def show_connect(cb: CallbackQuery) -> None:
    """Sozlamalar → Telegram Business → Chatbotlar yo'riqnomasi."""
    global _bot_username
    if not _bot_username:  # getMe API so'rovi FAQAT birinchi marta
        me = await cb.bot.me()
        _bot_username = me.username or ""
    await cb.message.edit_text(
        texts.CONNECT_TITLE.format(bot_username=_bot_username),
        reply_markup=user_kb.connect_menu(),
        disable_web_page_preview=True,
    )
    await cb.answer()


# ---------------------------------------------------------------------------
# Havola tozalash (yangi talab — hamma uchun, admin panellsiz)
# ---------------------------------------------------------------------------
@router.callback_query(F.data == user_kb.CB_CLEAN)
async def show_clean(cb: CallbackQuery) -> None:
    """«Havola tozalash» yo'riqnomasi."""
    await cb.message.edit_text(
        texts.LINK_TITLE,
        reply_markup=user_kb.back_to_menu(),
        disable_web_page_preview=True,
    )
    await cb.answer()


@router.message(F.text)
async def clean_link_message(message: Message) -> None:
    """Matndagi havolalardan kuzatuv parametrlarini olib tashlaydi.

    Faqat HAQIQATAN o'zgargan havolalar uchun javob beradi (shovqinsiz).
    Oddiy matn (havolasiz) e'tiborsiz qoldiriladi.
    """
    if message.text.startswith("/"):
        return  # buyruqlar — bu yerga tegmasin
    changed = clean_text(message.text)
    if not changed:
        return

    if len(changed) == 1:
        html = texts.LINK_CLEANED.format(url=esc(changed[0][1]))
    else:
        rows = "\n".join(
            f"{index}. <code>{esc(cleaned)}</code>"
            for index, (_, cleaned) in enumerate(changed, start=1)
        )
        html = f"{texts.LINK_MULTI_HEADER}\n\n{rows}"
    await message.answer(
        html, parse_mode="HTML", disable_web_page_preview=True
    )
