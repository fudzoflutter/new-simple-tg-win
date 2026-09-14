"""
Admin handlerlari – panel, statistika, kirish so'rovlari, foydalanuvchilar.

Ushbu handlerlarga faqat egasi (ADMIN_ID) yoki DBda admin deb belgilanganlar
kiradi: filtr main.py da routerga ulanadi (:class:`app.filters.IsAdmin`).
"""

from __future__ import annotations

from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from app.config import settings
from app.database import db, parse_dt
from app.keyboards import admin_kb, user_kb
from app.states import AdminGrant
from app.utils import texts
from app.utils.formatting import esc, fmt_date, fmt_datetime

router = Router(name="admin_panel")

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
    await cb.message.edit_text(await _dashboard_text(), reply_markup=await _panel_kb())
    await cb.answer()


async def _panel_kb() -> InlineKeyboardMarkup:
    """Panel klaviaturasi — so'rov/to'lov sonlari + Premium holati bilan."""
    return admin_kb.panel(
        pending_access=await db.count_pending_access(),
        pending_payments=len(await db.pending_payments()),
        premium_enabled=await premium_enabled(),
    )


async def premium_enabled() -> bool:
    """Premium bo'limi hozir yoqilganmi? (DBda saqlanadi, default — o'chiq)"""
    return (await db.get_setting("premium_enabled", "0")) == "1"


async def _dashboard_text() -> str:
    """Panel sarlavhasidagi jonli raqamlar."""
    total = await db.count_users()
    banned = total - await db.count_users(only_active=True)
    return texts.ADMIN_TITLE.format(
        users=total,
        online=await db.count_online(ONLINE_WINDOW_SECONDS),
        premium=len(await db.premium_users()),
        premium_state=texts.PREMIUM_STATE_ON
        if await premium_enabled()
        else texts.PREMIUM_STATE_OFF,
        connected=len(await db.connected_user_ids()),
        banned=banned,
    )


# ---------------------------------------------------------------------------
# Premium bo'limini yoqish/o'chirish (yangi talab: Premium yashirin boshlanadi)
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
    # Panelni yangilash — tugma va holat darhol almashadi.
    await cb.message.edit_text(await _dashboard_text(), reply_markup=await _panel_kb())


# ---------------------------------------------------------------------------
# Kirish so'rovlari navbati (yangi talab)
# ---------------------------------------------------------------------------
def _user_line(row: dict) -> str:
    """Ro'yxatdagi bitta qator: 🟢/⚪️ Ism (@username) — id."""
    name = row.get("first_name") or row.get("username") or str(row["user_id"])
    username = f"@{row['username']}" if row.get("username") else "—"
    dot = "🟢" if _is_online(row) else "⚪️"
    ban_mark = " ⛔️" if row.get("is_banned") else ""
    return f"{dot} {esc(name)} ({username}) — <code>{row['user_id']}</code>{ban_mark}"


def _is_online(row: dict) -> bool:
    last = parse_dt(row.get("last_activity"))
    if not last:
        return False
    return (datetime.now() - last).total_seconds() < ONLINE_WINDOW_SECONDS


@router.callback_query(F.data.regexp(r"^adm:access(\d+|)$"))
async def show_access_requests(cb: CallbackQuery) -> None:
    """'adm:access' yoki 'adm:access:<page>' — kutilayotgan so'rovlar.

    MUHIM (bug fix): avvalgi `startswith(CB_ACCESS)` filtri shu handlerga
    'adm:access:ok:<id>' / 'adm:access:no:<id>' (Tasdiqlash/Rad etish)
    callbacklarini HAM tutib qo'yardi — shu sababli ✅ bosilganda
    so'rov TASDIQLANMASDI, ro'yxat qayta ochilardi.  Regexp aniq
    'adm:access' yoki 'adm:access:<page>' formatlariga mos keladi.
    """
    suffix = cb.data.removeprefix(admin_kb.CB_ACCESS)
    page = int(suffix) if suffix.isdigit() and int(suffix) > 0 else 1

    rows = await db.pending_access_users()
    if not rows:
        await cb.message.edit_text(
            texts.ADMIN_ACCESS_EMPTY, reply_markup=admin_kb.online_list()
        )
        await cb.answer()
        return

    pages = max(1, (len(rows) + admin_kb.PAGE_SIZE - 1) // admin_kb.PAGE_SIZE)
    page = min(page, pages)
    chunk = rows[(page - 1) * admin_kb.PAGE_SIZE : page * admin_kb.PAGE_SIZE]

    text = texts.ADMIN_ACCESS_TITLE.format(page=page, pages=pages) + "\n\n" + "\n".join(
        _user_line(r) for r in chunk
    )
    buttons = admin_kb.access_buttons(
        [(r.get("first_name") or r.get("username") or str(r["user_id"]), r["user_id"]) for r in chunk]
    )
    await cb.message.edit_text(
        text, reply_markup=admin_kb.access_pager(page, pages, buttons)
    )
    await cb.answer()


async def _render_access_card(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """So'rov kartochkasi: foydalanuvchi ma'lumoti + Tasdiqlash/Rad etish."""
    row = await db.get_user(user_id)
    if row is None:
        return texts.ADMIN_USER_NOT_FOUND, admin_kb.online_list()

    created = fmt_datetime(parse_dt(row.get("created_at")))
    text = (
        f"{texts.E_USER} <b>{esc(row.get('first_name') or str(user_id))}</b>\n\n"
        f"{texts.E_ID} ID: <code>{user_id}</code>\n"
        f"🔗 Username: {'@' + row['username'] if row.get('username') else '—'}\n"
        f"📅 So'rov vaqti: {created}\n\n"
        "Bu foydalanuvchiga botdan foydalanishga ruxsat berasizmi?"
    )
    return text, admin_kb.access_decision(user_id)


@router.callback_query(F.data.startswith(admin_kb.CB_ACCESS_OK))
async def approve_access(cb: CallbackQuery) -> None:
    await _decide_access(cb, approved=True)


@router.callback_query(F.data.startswith(admin_kb.CB_ACCESS_NO))
async def reject_access(cb: CallbackQuery) -> None:
    await _decide_access(cb, approved=False)


async def _decide_access(cb: CallbackQuery, *, approved: bool) -> None:
    prefix = admin_kb.CB_ACCESS_OK if approved else admin_kb.CB_ACCESS_NO
    raw = cb.data.removeprefix(prefix)
    if not raw.isdigit():
        await cb.answer(texts.UNKNOWN_ACTION, show_alert=True)
        return
    user_id = int(raw)
    row = await db.get_user(user_id)
    if row is None:
        await cb.answer(texts.ADMIN_USER_NOT_FOUND, show_alert=True)
        return

    await db.set_access(
        user_id, "approved" if approved else "rejected", cb.from_user.id
    )

    # Foydalanuvchiga qaror haqida xabar berish.
    try:
        if approved:
            # 1) Tasdiq matni...
            await cb.bot.send_message(
                user_id,
                texts.ACCESS_APPROVED_USER,
                parse_mode="HTML",
            )
            # 2) ...va DARHOL ishlaydigan asosiy menyu (eng muhim talab):
            #    foydalanuvchi /start ni qaytadan bosishi shart emas.
            await cb.bot.send_message(
                user_id,
                f"{texts.WELCOME}\n\n{texts.MENU_HINT}",
                reply_markup=user_kb.main_menu(
                    connected=False,
                    premium_enabled=await premium_enabled(),
                ),
                disable_web_page_preview=True,
            )
        else:
            await cb.bot.send_message(
                user_id,
                texts.ACCESS_REJECTED_NOTIFY,
                parse_mode="HTML",
            )
    except Exception:  # noqa: BLE001
        pass

    name = esc(row.get("first_name") or str(user_id))
    done = (
        texts.ADMIN_ACCESS_APPROVED_DONE if approved else texts.ADMIN_ACCESS_REJECTED_DONE
    )
    await cb.answer(done.format(name=name), show_alert=True)

    # Kartochkani yangilash — tugmalar yo'qoladi.
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# Foydalanuvchilar ro'yxati (5-band)
# ---------------------------------------------------------------------------
@router.callback_query(F.data.startswith(admin_kb.CB_USERS))
async def show_users(cb: CallbackQuery, state: FSMContext) -> None:
    """'adm:users' yoki 'adm:users:<page>' — sahifalangan ro'yxat."""
    await state.clear()
    raw = cb.data.removeprefix(admin_kb.CB_USERS)
    page = int(raw) if raw.isdigit() and int(raw) > 0 else 1

    users = await db.all_users()
    if not users:
        await cb.message.edit_text(
            texts.ADMIN_USER_EMPTY, reply_markup=admin_kb.online_list()
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
    await cb.message.edit_text(text, reply_markup=admin_kb.users_pager(page, pages, buttons))
    await cb.answer()


# ---------------------------------------------------------------------------
# Bitta foydalanuvchi kartochkasi: profil + cheklash (5-band)
# ---------------------------------------------------------------------------
async def _render_user_card(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Kartochka matni + klaviatura (ko'rish va yangilashda umumiy)."""
    row = await db.get_user(user_id)
    if row is None:
        return texts.ADMIN_USER_NOT_FOUND, admin_kb.online_list()

    events_count = await db.count_user_events(user_id)
    conns = await db.connections_for_user(user_id)
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
async def show_user_card(cb: CallbackQuery) -> None:
    raw = cb.data.removeprefix(admin_kb.CB_USER)
    if not raw.isdigit():
        await cb.answer(texts.UNKNOWN_ACTION, show_alert=True)
        return
    text, markup = await _render_user_card(int(raw))
    await cb.message.edit_text(text, reply_markup=markup)
    await cb.answer()


# ---------------------------------------------------------------------------
# Cheklash / bandan chiqarish (5-band)
# ---------------------------------------------------------------------------
@router.callback_query(F.data.startswith(admin_kb.CB_USER_BAN))
async def ban_user(cb: CallbackQuery) -> None:
    await _set_ban(cb, banned=True)


@router.callback_query(F.data.startswith(admin_kb.CB_USER_UNBAN))
async def unban_user(cb: CallbackQuery) -> None:
    await _set_ban(cb, banned=False)


async def _set_ban(cb: CallbackQuery, *, banned: bool) -> None:
    prefix = admin_kb.CB_USER_BAN if banned else admin_kb.CB_USER_UNBAN
    raw = cb.data.removeprefix(prefix)
    if not raw.isdigit():
        await cb.answer(texts.UNKNOWN_ACTION, show_alert=True)
        return
    user_id = int(raw)

    if user_id == settings.admin_id:
        await cb.answer(texts.ADMIN_CANNOT_BAN_OWNER, show_alert=True)
        return

    await db.set_banned(user_id, banned)
    row = await db.get_user(user_id)
    name = esc(row.get("first_name") or str(user_id)) if row else str(user_id)
    done = texts.ADMIN_USER_BANNED_DONE if banned else texts.ADMIN_USER_UNBANNED_DONE

    # Kartochkani yangilash — holat va tugma darhol almashadi.
    text, markup = await _render_user_card(user_id)
    await cb.message.edit_text(text, reply_markup=markup)
    await cb.answer(done.format(name=name), show_alert=True)


# ---------------------------------------------------------------------------
# Obuna BERISH / OLISH (yangi talab: DBdagi aynan foydalanuvchiga)
# ---------------------------------------------------------------------------
@router.callback_query(F.data.startswith(admin_kb.CB_USER_GRANT))
async def grant_premium(cb: CallbackQuery, state: FSMContext) -> None:
    """«🎁 Obuna berish» — kun sonini so'raymiz."""
    raw = cb.data.removeprefix(admin_kb.CB_USER_GRANT)
    if not raw.isdigit():
        await cb.answer(texts.UNKNOWN_ACTION, show_alert=True)
        return
    user_id = int(raw)
    row = await db.get_user(user_id)
    if row is None:
        await cb.answer(texts.ADMIN_USER_NOT_FOUND, show_alert=True)
        return
    await state.set_state(AdminGrant.days)
    await state.update_data(grant_user_id=user_id)
    await cb.message.edit_text(
        texts.ADMIN_GRANT_ASK.format(
            user=esc(row.get("first_name") or str(user_id))
        ),
        reply_markup=admin_kb.cancel_to_panel(),
    )
    await cb.answer()


@router.message(AdminGrant.days)
async def grant_premium_days(message: Message, state: FSMContext) -> None:
    """Kun sonini qabul qilib, obunani faollashtirish."""
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
    # muddat boshlanadi.
    until = await db.extend_premium(user_id, int(raw))
    row = await db.get_user(user_id)
    name = esc(row.get("first_name") or str(user_id)) if row else str(user_id)

    # 1) Foydalanuvchiga DARHOL xabar (yangi talab).
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
        pass

    # 2) Egaga tasdiq + yangilangan kartochka.
    await message.answer(
        texts.ADMIN_GRANT_DONE.format(name=name, date=fmt_date(until))
    )
    text, markup = await _render_user_card(user_id)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith(admin_kb.CB_USER_PREM_OFF))
async def remove_premium(cb: CallbackQuery) -> None:
    """«🗑 Obunani olib qo'yish» — premium_until = NULL."""
    raw = cb.data.removeprefix(admin_kb.CB_USER_PREM_OFF)
    if not raw.isdigit():
        await cb.answer(texts.UNKNOWN_ACTION, show_alert=True)
        return
    user_id = int(raw)
    await db.set_premium(user_id, None)
    row = await db.get_user(user_id)
    name = esc(row.get("first_name") or str(user_id)) if row else str(user_id)

    try:
        await cb.bot.send_message(
            user_id, texts.PREMIUM_REMOVED_USER, parse_mode="HTML"
        )
    except Exception:  # noqa: BLE001
        pass

    text, markup = await _render_user_card(user_id)
    await cb.message.edit_text(text, reply_markup=markup)
    await cb.answer(
        texts.ADMIN_PREMIUM_REMOVED_DONE.format(name=name), show_alert=True
    )


# ---------------------------------------------------------------------------
# Onlayn foydalanuvchilar (5-band — kim hozir botdan foydalanmoqda)
# ---------------------------------------------------------------------------
@router.callback_query(F.data == admin_kb.CB_ONLINE)
async def show_online(cb: CallbackQuery) -> None:
    rows = await db.online_users(ONLINE_WINDOW_SECONDS)
    if not rows:
        body = texts.ADMIN_ONLINE_EMPTY
    else:
        body = "\n".join(_user_line(row) for row in rows)

    await cb.message.edit_text(
        texts.ADMIN_ONLINE_TITLE.format(list=body),
        reply_markup=admin_kb.online_list(),
    )
    await cb.answer()
