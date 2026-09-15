"""
Admin handlerlari – panel, statistika va foydalanuvchilarni boshqarish.

Ushbu handlerlarga faqat egasi (ADMIN_ID) yoki DBda admin deb belgilanganlar
kiradi: filtr main.py da routerga ulanadi (:class:`app.filters.IsAdmin`).

Yangi talablar (2026-09-14):
* To'lovlar ekrani endi tarif NOMI bilan (JOIN orqali) — admin chekni
  tekshirganda qaysi tarif uchun pul to'langanini ko'radi.
* Obuna berish FSM matn bo'lmagan xabarlarda yiqilmaydi.
* Banlash: admin/ega huquqli foydalanuvchini banlash MUMKIN EMAS, va
  banlangan foydalanuvchining cheki 30 s keshini BEKOR qiladi.
* "🎁 Obuna berish" to'liq ishlaydi: kun soni -> extend_premium -> foydalanuvchi
  xabari -> yangilangan kartochka.
* "⏳ Kunlik limit" — premiumning teskari tomoni: premium YO'Q foydalanuvchiga
  kunlik nusxalash chegara qo'yish (premium = cheksiz).
* "📝 Nusxa" boshqaruvi: keshlangan so'nggi xabarni ko'rish/almashtirish/o'chirish.
"""

from __future__ import annotations

import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from app.config import settings
from app.database import db, parse_dt
from app.keyboards import admin_kb
from app.middlewares import invalidate_ban_cache
from app.states import AdminGrant, AdminLimitSet, AdminTextSet
from app.utils import texts
from app.utils.formatting import esc, fmt_date, fmt_datetime, fmt_number
from app.utils.ui import edit_or_send

router = Router(name="admin_panel")
logger = logging.getLogger(__name__)

# Foydalanuvchi shu vaqt ichida faol bo'lsa — "onlayn" hisoblanadi.
ONLINE_WINDOW_SECONDS = 120


# ---------------------------------------------------------------------------
# /admin komandasi + panel tugmasi — jonli ko'rsatkichlar
# ---------------------------------------------------------------------------
@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(await _dashboard_text(), reply_markup=await _panel_kb())


@router.callback_query(F.data == admin_kb.CB_PANEL)
async def show_panel(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await edit_or_send(
        cb.message, await _dashboard_text(), reply_markup=await _panel_kb()
    )
    await cb.answer()


async def _panel_kb() -> InlineKeyboardMarkup:
    """Panel klaviaturasi — to'lovlar soni + Premium holati bilan.

    Tezlik: 2 so'rov PARALLEL (ketma-ket emas).
    """
    payments, prem = await db.gather(
        db.pending_payments(),
        premium_enabled(),
    )
    return admin_kb.panel(
        pending_payments=len(payments),
        premium_enabled=prem,
    )


async def premium_enabled() -> bool:
    """Premium bo'limi ochiqmi? (KESHLANGAN o'qish — 5 sek TTL)"""
    return (await db.get_setting_cached("premium_enabled", "0")) == "1"


async def _dashboard_text() -> str:
    """Panel sarlavhasidagi jonli raqamlar (6 so'rov PARALLEL)."""
    (
        total,
        active,
        online,
        premium,
        connected,
        prem,
    ) = await db.gather(
        db.count_users(),
        db.count_users(only_active=True),
        db.count_online(ONLINE_WINDOW_SECONDS),
        db.premium_users(),
        db.connected_user_ids(),
        premium_enabled(),
    )
    return texts.ADMIN_TITLE.format(
        users=total,
        online=online,
        premium=len(premium),
        premium_state=texts.PREMIUM_STATE_ON if prem else texts.PREMIUM_STATE_OFF,
        connected=len(connected),
        banned=total - active,
    )


# ---------------------------------------------------------------------------
# Premium bo'limini yoqish/o'chirish
# ---------------------------------------------------------------------------
@router.callback_query(F.data == admin_kb.CB_PREMIUM_TOGGLE)
async def toggle_premium(cb: CallbackQuery) -> None:
    """Bir bosishda Premium bo'limini hammaga yoqish yoki yashirish."""
    new_state = not await premium_enabled()
    await db.set_setting("premium_enabled", "1" if new_state else "0")
    await cb.answer(
        texts.ADMIN_PREMIUM_ON if new_state else texts.ADMIN_PREMIUM_OFF,
        show_alert=True,
    )
    # Panelni yangilash — tugma va holat darhol almashadi (PARALLEL).
    text, markup = await db.gather(_dashboard_text(), _panel_kb())
    await edit_or_send(cb.message, text, reply_markup=markup)


# ---------------------------------------------------------------------------
# Foydalanuvchilar ro'yxati uchun umumiy yordamchilar
# ---------------------------------------------------------------------------
def _user_line(row: dict) -> str:
    """Ro'yxatdagi bitta qator: 🟢/⚪️ Ism (@username) — id."""
    name = row.get("first_name") or row.get("username") or str(row["user_id"])
    username = f"@{row['username']}" if row.get("username") else "—"
    dot = "🟢" if _is_online(row) else "⚪️"
    ban_mark = texts.USER_LINE_BAN_MARK if row.get("is_banned") else ""
    return f"{dot} {esc(name)} ({username}) — <code>{row['user_id']}</code>{ban_mark}"


def _is_online(row: dict) -> bool:
    last = parse_dt(row.get("last_activity"))
    if not last:
        return False
    return (datetime.now() - last).total_seconds() < ONLINE_WINDOW_SECONDS


def _page_of(raw: str) -> int:
    """Callback oxiridagi sahifa raqamini xavfsiz o'qiydi (1 = standart)."""
    try:
        page = int(raw)
    except ValueError:
        return 1
    return page if page > 0 else 1


# ---------------------------------------------------------------------------
# Foydalanuvchilar ro'yxati (sahifalangan)
# ---------------------------------------------------------------------------
@router.callback_query(F.data.startswith(admin_kb.CB_USERS))
async def show_users(cb: CallbackQuery, state: FSMContext) -> None:
    """'adm:users' yoki 'adm:users:<page>' — sahifalangan ro'yxat."""
    await state.clear()
    page = _page_of(cb.data.removeprefix(admin_kb.CB_USERS))

    users = await db.all_users()
    if not users:
        await edit_or_send(
            cb.message, texts.ADMIN_USER_EMPTY, reply_markup=admin_kb.online_list()
        )
        await cb.answer()
        return

    pages = max(1, (len(users) + admin_kb.PAGE_SIZE - 1) // admin_kb.PAGE_SIZE)
    page = min(page, pages)
    chunk = users[(page - 1) * admin_kb.PAGE_SIZE : page * admin_kb.PAGE_SIZE]

    text = texts.ADMIN_USERS_TITLE.format(page=page, pages=pages) + "\n\n" + "\n".join(
        _user_line(row) for row in chunk
    )
    # Har bir foydalanuvchi tugma — bosilganda kartochkasi ochiladi.
    buttons = admin_kb.user_buttons(
        [
            (row.get("first_name") or row.get("username") or str(row["user_id"]), row["user_id"])
            for row in chunk
        ]
    )
    await edit_or_send(
        cb.message, text, reply_markup=admin_kb.users_pager(page, pages, buttons)
    )
    await cb.answer()


# ---------------------------------------------------------------------------
# Bitta foydalanuvchi kartochkasi: profil + boshqaruv
# ---------------------------------------------------------------------------
async def _render_user_card(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Kartochka matni + klaviatura (ko'rish va yangilashda umumiy).

    Tezlik: 3 so'rov PARALLEL (~1 so'rov vaqti).
    """
    row = await db.get_user(user_id)
    if row is None:
        return texts.ADMIN_USER_NOT_FOUND, admin_kb.online_list()

    events_count, conns = await db.gather(
        db.count_user_events(user_id),
        db.connections_for_user(user_id),
    )
    premium = parse_dt(row.get("premium_until"))
    is_premium = premium is not None and premium > datetime.now()

    text = texts.ADMIN_USER_CARD.format(
        E_USER=texts.E_USER,
        E_ID=texts.E_ID,
        name=esc(row.get("first_name") or str(user_id)),
        user_id=user_id,
        username=f"@{row['username']}" if row.get("username") else "—",
        premium=texts.PREMIUM_ACTIVE.format(date=fmt_date(premium))
        if is_premium
        else texts.PREMIUM_INACTIVE,
        last_seen=fmt_datetime(parse_dt(row.get("last_activity"))),
        registered=fmt_datetime(parse_dt(row.get("created_at"))),
        events=events_count,
        connections=len(conns),
        status=texts.STATUS_BANNED if row.get("is_banned") else texts.STATUS_ACTIVE,
    )
    return text, admin_kb.user_card(user_id, bool(row.get("is_banned")), is_premium)


@router.callback_query(F.data.startswith(admin_kb.CB_USER))
async def show_user_card(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    try:
        user_id = int(cb.data.removeprefix(admin_kb.CB_USER))
    except ValueError:
        await cb.answer(texts.UNKNOWN_ACTION, show_alert=True)
        return
    text, markup = await _render_user_card(user_id)
    await edit_or_send(cb.message, text, reply_markup=markup)
    await cb.answer()


# ---------------------------------------------------------------------------
# Cheklash / bandan chiqarish
# ---------------------------------------------------------------------------
def _is_admin_row(row: dict | None) -> bool:
    """DB yozuvi adminlikni bildiradimi (ega settings.admin_id emas!)."""
    return bool(row and row.get("is_admin"))


async def _set_ban(cb: CallbackQuery, *, banned: bool) -> None:
    prefix = admin_kb.CB_USER_BAN if banned else admin_kb.CB_USER_UNBAN
    try:
        user_id = int(cb.data.removeprefix(prefix))
    except ValueError:
        await cb.answer(texts.UNKNOWN_ACTION, show_alert=True)
        return

    # XAVFSIZLIK: ega HECH QACHON banlanmaydi.
    if user_id == settings.admin_id:
        await cb.answer(texts.ADMIN_CANNOT_BAN_OWNER, show_alert=True)
        return

    row = await db.get_user(user_id)
    if row is None:
        await cb.answer(texts.ADMIN_USER_NOT_FOUND, show_alert=True)
        return
    # XAVFSIZLIK: DBda admin deb belgilangan foydalanuvchini ham banlab
    # bo'lmaydi (aks holda qolgan adminlar panelga kira olmay qoladi).
    if banned and _is_admin_row(row):
        await cb.answer(texts.ADMIN_USER_IS_ADMIN, show_alert=True)
        return

    await db.set_banned(user_id, banned)
    # KESH: banlangan foydalanuvchi 30 sekund KUTMASIN — darhol bloklansin;
    # bandan chiqqan esa dARHOL ishlashi kerak.
    invalidate_ban_cache(user_id)

    name = esc(row.get("first_name") or str(user_id))
    done = texts.ADMIN_USER_BANNED_DONE if banned else texts.ADMIN_USER_UNBANNED_DONE

    # Kartochkani yangilash — holat va tugma darhol almashadi.
    text, markup = await _render_user_card(user_id)
    await edit_or_send(cb.message, text, reply_markup=markup)
    await cb.answer(done.format(name=name), show_alert=True)


@router.callback_query(F.data.startswith(admin_kb.CB_USER_BAN))
async def ban_user(cb: CallbackQuery) -> None:
    await _set_ban(cb, banned=True)


@router.callback_query(F.data.startswith(admin_kb.CB_USER_UNBAN))
async def unban_user(cb: CallbackQuery) -> None:
    await _set_ban(cb, banned=False)


# ---------------------------------------------------------------------------
# Obuna BERISH / OLISH (gift + limit)
# ---------------------------------------------------------------------------
@router.callback_query(F.data.startswith(admin_kb.CB_USER_GRANT))
async def grant_premium(cb: CallbackQuery, state: FSMContext) -> None:
    """«🎁 Obuna berish» — kun sonini so'raymiz."""
    try:
        user_id = int(cb.data.removeprefix(admin_kb.CB_USER_GRANT))
    except ValueError:
        await cb.answer(texts.UNKNOWN_ACTION, show_alert=True)
        return
    row = await db.get_user(user_id)
    if row is None:
        await cb.answer(texts.ADMIN_USER_NOT_FOUND, show_alert=True)
        return
    await state.set_state(AdminGrant.days)
    await state.update_data(grant_user_id=user_id)
    await edit_or_send(
        cb.message,
        texts.ADMIN_GRANT_ASK.format(
            user=esc(row.get("first_name") or str(user_id))
        ),
        reply_markup=admin_kb.cancel_to_user_card(user_id),
    )
    await cb.answer()


@router.message(AdminGrant.days)
async def grant_premium_days(message: Message, state: FSMContext) -> None:
    """Kun sonini qabul qilib, obunani faollashtirish.

    MATN BO'LMAGAN xabar (stiker/rasm/...) — yiqilmasdan qayta so'raydi.
    """
    raw = (message.text or "").strip()
    if not raw.isdigit() or not (1 <= int(raw) <= 3650):
        await message.answer(texts.ADMIN_GRANT_DAYS_INVALID)
        return
    data = await state.get_data()
    user_id: int = data.get("grant_user_id", 0)
    await state.clear()

    if not user_id:
        await message.answer(texts.UNKNOWN_ACTION)
        return

    # 'Uzaytirildi' vs 'berildi' xabari uchun AVVALGI holatni o'qiymiz.
    prev_row = await db.get_user(user_id)
    prev_until = parse_dt(prev_row.get("premium_until")) if prev_row else None
    had_premium = prev_until is not None and prev_until > datetime.now()

    # Obuna mavjud vaqtni UZAYTIRADI (extend_premium), yo'q bo'lsa yangi
    # muddat boshlanadi.  Gift berilganda kunlik limit ham BEKOR qilinadi:
    # premium = cheksiz ishlash.
    until = await db.extend_premium(user_id, int(raw))
    await db.set_setting(_user_limit_key(user_id), "0")
    row = await db.get_user(user_id)
    name = esc(row.get("first_name") or str(user_id)) if row else str(user_id)

    # 1) Foydalanuvchiga DARHOL xabar (gift yetkazilishi — yangi talab).
    try:
        await message.bot.send_message(
            user_id,
            (
                texts.PREMIUM_EXTENDED_USER
                if had_premium
                else texts.PREMIUM_GRANTED_USER
            ).format(date=fmt_date(until)),
            parse_mode="HTML",
        )
    except Exception:  # noqa: BLE001 – foydalanuvchi botni bloklagan bo'lishi mumkin
        logger.info("Could not notify user %s about granted premium", user_id)

    # 2) Egaga tasdiq + yangilangan kartochka.
    await message.answer(
        texts.ADMIN_GRANT_DONE.format(name=name, date=fmt_date(until))
    )
    text, markup = await _render_user_card(user_id)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith(admin_kb.CB_USER_PREM_OFF))
async def remove_premium(cb: CallbackQuery) -> None:
    """«🗑 Obunani olib qo'yish» — premium_until = NULL."""
    try:
        user_id = int(cb.data.removeprefix(admin_kb.CB_USER_PREM_OFF))
    except ValueError:
        await cb.answer(texts.UNKNOWN_ACTION, show_alert=True)
        return
    await db.set_premium(user_id, None)
    row = await db.get_user(user_id)
    name = esc(row.get("first_name") or str(user_id)) if row else str(user_id)

    try:
        await cb.bot.send_message(
            user_id, texts.PREMIUM_REMOVED_USER, parse_mode="HTML"
        )
    except Exception:  # noqa: BLE001
        logger.info("Could not notify user %s about premium removal", user_id)

    text, markup = await _render_user_card(user_id)
    await edit_or_send(cb.message, text, reply_markup=markup)
    await cb.answer(
        texts.ADMIN_PREMIUM_REMOVED_DONE.format(name=name), show_alert=True
    )


# ---------------------------------------------------------------------------
# Kunlik limit (premiumning teskari tomoni — "premium beraman, lekin
# cheklab turaman" so'rovi uchun).  Premium faol bo'lsa limit O'TMAYDI.
# ---------------------------------------------------------------------------
def _user_limit_key(user_id: int) -> str:
    return f"limit:{user_id}"


@router.callback_query(F.data.startswith(admin_kb.CB_USER_LIMIT))
async def ask_daily_limit(cb: CallbackQuery, state: FSMContext) -> None:
    """«⏳ Kunlik limit o'rnatish» — kuniga nechta xabar nusxalansin?"""
    try:
        user_id = int(cb.data.removeprefix(admin_kb.CB_USER_LIMIT))
    except ValueError:
        await cb.answer(texts.UNKNOWN_ACTION, show_alert=True)
        return
    row = await db.get_user(user_id)
    if row is None:
        await cb.answer(texts.ADMIN_USER_NOT_FOUND, show_alert=True)
        return
    premium = parse_dt(row.get("premium_until"))
    if premium and premium > datetime.now():
        # Premium foydalanuvchini limitlash MAQNOSIZ — avval obunani oling.
        await cb.answer(texts.ADMIN_PREMIUM_LIMIT_DENIED, show_alert=True)
        return

    await state.set_state(AdminLimitSet.limit)
    await state.update_data(limit_user_id=user_id)
    await edit_or_send(
        cb.message,
        texts.ADMIN_LIMIT_ASK.format(
            user=esc(row.get("first_name") or str(user_id))
        ),
        reply_markup=admin_kb.cancel_to_user_card(user_id),
    )
    await cb.answer()


@router.message(AdminLimitSet.limit)
async def set_daily_limit(message: Message, state: FSMContext) -> None:
    """Kunlik limitni saqlaydi (0 = cheksiz; premium esa doim cheksiz)."""
    raw = (message.text or "").strip().replace(" ", "")
    if not raw.isdigit() or int(raw) > 100000:
        await message.answer(texts.ADMIN_LIMIT_INVALID)
        return
    data = await state.get_data()
    user_id: int = data.get("limit_user_id", 0)
    await state.clear()
    if not user_id:
        await message.answer(texts.UNKNOWN_ACTION)
        return

    try:
        await db.set_setting(_user_limit_key(user_id), str(int(raw)))
    except Exception:  # noqa: BLE001 – DB xatosi paneldagi xabarni buzmasin
        logger.exception("Failed to store daily limit for %s", user_id)
        await message.answer(texts.ADMIN_LIMIT_PARSING_FAILED)
        return

    row = await db.get_user(user_id)
    name = esc(row.get("first_name") or str(user_id)) if row else str(user_id)
    await message.answer(
        texts.ADMIN_LIMIT_OFF.format(name=name)
        if int(raw) == 0
        else texts.ADMIN_LIMIT_SET.format(name=name, n=fmt_number(int(raw)))
    )
    try:
        await message.bot.send_message(
            user_id,
            texts.LIMIT_REMOVED_USER
            if int(raw) == 0
            else texts.LIMIT_SET_USER.format(limit=fmt_number(int(raw))),
            parse_mode="HTML",
        )
    except Exception:  # noqa: BLE001
        logger.info("Could not notify user %s about daily limit", user_id)

    text, markup = await _render_user_card(user_id)
    await message.answer(text, reply_markup=markup)


# ---------------------------------------------------------------------------
# Saqlangan (nusxalangan) so'nggi xabar: ko'rish / almashtirish / o'chirish
# ---------------------------------------------------------------------------
async def _latest_cached_event(user_id: int) -> dict | None:
    """Foydalanuvchi nomidan keshlangan ENG OXIRGI xabar yozuvi."""
    rows = await db.recent_events(limit=200)
    for r in rows:
        if r.get("user_id") == user_id and r.get("message_id"):
            return r
    return None


@router.callback_query(F.data.startswith(admin_kb.CB_USER_TEXT_VIEW))
async def view_cached_text(cb: CallbackQuery, state: FSMContext) -> None:
    """Keshlangan so'nggi xabarni ko'rish."""
    await state.clear()
    try:
        user_id = int(cb.data.removeprefix(admin_kb.CB_USER_TEXT_VIEW))
    except ValueError:
        await cb.answer(texts.UNKNOWN_ACTION, show_alert=True)
        return

    event = await _latest_cached_event(user_id)
    if event is None:
        await cb.answer(texts.ADMIN_TEXT_MISSING, show_alert=True)
        return

    details = (event.get("details") or "")[:3000]
    text = texts.ADMIN_LAST_TEXT.format(text=esc(details or texts.NO_TEXT))
    await edit_or_send(
        cb.message, text, reply_markup=admin_kb.user_text_view(user_id, True)
    )
    await cb.answer()


@router.callback_query(F.data.startswith(admin_kb.CB_USER_TEXT_SET))
async def ask_replace_text(cb: CallbackQuery, state: FSMContext) -> None:
    """Keshlangan xabarni ALMASHTIRISH — yangi matn so'raladi."""
    try:
        user_id = int(cb.data.removeprefix(admin_kb.CB_USER_TEXT_SET))
    except ValueError:
        await cb.answer(texts.UNKNOWN_ACTION, show_alert=True)
        return
    row = await db.get_user(user_id)
    if row is None:
        await cb.answer(texts.ADMIN_USER_NOT_FOUND, show_alert=True)
        return
    await state.set_state(AdminTextSet.text)
    await state.update_data(text_user_id=user_id)
    await edit_or_send(
        cb.message,
        texts.ADMIN_AWAITING_TEXT,
        reply_markup=admin_kb.cancel_to_user_card(user_id),
    )
    await cb.answer()


@router.message(AdminTextSet.text)
async def replace_cached_text(message: Message, state: FSMContext) -> None:
    """Yangi matnni saqlaydi (eski yozuv JOYIDA yangilanadi)."""
    raw = (message.text or "").strip()
    if not raw:
        await message.answer(texts.ADMIN_TEXT_ONLY)
        return
    data = await state.get_data()
    user_id: int = data.get("text_user_id", 0)
    await state.clear()
    if not user_id:
        await message.answer(texts.UNKNOWN_ACTION)
        return

    event = await _latest_cached_event(user_id)
    if event is None or not event.get("chat_id") or not event.get("message_id"):
        await message.answer(texts.ADMIN_TEXT_MISSING)
        return

    updated = await db.update_event_details(
        int(event["chat_id"]), int(event["message_id"]), raw
    )
    if not updated:
        await message.answer(texts.ADMIN_TEXT_MISSING)
        return

    await message.answer(texts.ADMIN_TEXT_UPDATED)
    text, markup = await _render_user_card(user_id)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith(admin_kb.CB_USER_TEXT_DEL))
async def delete_cached_text(cb: CallbackQuery) -> None:
    """Keshlangan so'nggi xabar yozuvini o'chiradi (statistika qoladi)."""
    try:
        user_id = int(cb.data.removeprefix(admin_kb.CB_USER_TEXT_DEL))
    except ValueError:
        await cb.answer(texts.UNKNOWN_ACTION, show_alert=True)
        return

    event = await _latest_cached_event(user_id)
    if event is None:
        await cb.answer(texts.ADMIN_TEXT_MISSING, show_alert=True)
        return

    await db.delete_cached_event(int(event["id"]))
    await cb.answer(texts.ADMIN_TEXT_REMOVED, show_alert=True)

    text, markup = await _render_user_card(user_id)
    await edit_or_send(cb.message, text, reply_markup=markup)


# ---------------------------------------------------------------------------
# Onlayn foydalanuvchilar
# ---------------------------------------------------------------------------
@router.callback_query(F.data == admin_kb.CB_ONLINE)
async def show_online(cb: CallbackQuery) -> None:
    rows = await db.online_users(ONLINE_WINDOW_SECONDS)
    if not rows:
        body = texts.ADMIN_ONLINE_EMPTY
    else:
        body = "\n".join(_user_line(row) for row in rows)

    await edit_or_send(
        cb.message,
        texts.ADMIN_ONLINE_TITLE.format(list=body),
        reply_markup=admin_kb.online_list(),
    )
    await cb.answer()
