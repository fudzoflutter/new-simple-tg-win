"""
Foydalanuvchi tomonidagi handlerlar (1–3-bandlar va 5-bandning foydalanuvchi
qismi) + YANGI kirish tasdiqlash oqimi.

* /start              – tasdiqlangan bo'lsa menyu, aks holda "kutilmoqda"
* Statistika          – shaxsiy statistika + "qanday ishlaydi" izohi
* Ulanish             – tg://settings/edit orqali sozlamalarga yo'naltirish
* Premium             – tariflar, nusxalanadigan karta, chek yuklash
"""

from __future__ import annotations

import time
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.config import settings
from app.database import db, parse_dt
from app.keyboards import admin_kb, user_kb
from app.utils import texts
from app.utils.formatting import (
    esc,
    fmt_date,
    fmt_datetime,
    fmt_number,
    mention_by_id,
)
from app.utils.texts import (
    MY_SUB_ACTIVE,
    MY_SUB_INACTIVE,
    MY_SUB_TITLE,
    PREMIUM_CHECKOUT,
    STATS_BODY,
    plan_checkout_title,
)

router = Router(name="user")

# /start dan keyin foydalanuvchi "yangi" hisoblanadigan vaqt (sek).
NEW_REQUEST_WINDOW_SECONDS = 5

# Egaga eslatma yuborish orasidagi eng kam vaqt (bir foydalanuvchi uchun).
ADMIN_REMINDER_COOLDOWN = 60.0
_last_admin_reminder: dict[int, float] = {}


async def _premium_enabled() -> bool:
    """Premium bo'limi hozir hammaga ochiqmi? (admin panelda yoqiladi)"""
    return (await db.get_setting("premium_enabled", "0")) == "1"


# ---------------------------------------------------------------------------
# /start – kirish tasdiqlash + asosiy menyu
# ---------------------------------------------------------------------------
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    """Kirish nuqtasi: tasdiqlangan — menyu; pending/rejected — ogohlantirish."""
    await state.clear()

    # Ega (admin) uchun har doim to'g'ridan-to'g'ri menyu: u hech qachon
    # o'z so'rovini tasdiqlashi kerak bo'lmaydi (bug fix).
    if settings.admin_id == message.from_user.id:
        await db.set_access(message.from_user.id, "approved", message.from_user.id)
        await message.answer(
            f"{texts.WELCOME}\n\n{texts.MENU_HINT}",
            reply_markup=user_kb.main_menu(
                connected=False,
                premium_enabled=await _premium_enabled(),
            ),
            disable_web_page_preview=True,
        )
        return

    row = await db.get_user(message.from_user.id)

    status = (row or {}).get("access_status") or "pending"
    if (row or {}).get("is_banned"):
        await message.answer(texts.BANNED)
        return
    if status == "rejected":
        await message.answer(texts.ACCESS_REJECTED)
        return
    if status == "pending":
        # Menyu ham ILova qilinadi (faqat matn emas): admin tasdiqlagach
        # foydalanuvchi /start ni YANA bir marta bosadi va DARHOL
        # ishlaydigan menyuni ko'radi — qaytadan so'rov yubormaydi.
        await message.answer(
            texts.ACCESS_PENDING,
            reply_markup=user_kb.main_menu(
                connected=False,
                premium_enabled=await _premium_enabled(),
            ),
        )
        await _notify_admin_about_request(message)
        return

    conns = await db.connections_for_user(message.from_user.id)
    is_connected = any(c.get("is_enabled") for c in conns)
    if is_connected:
        # 2-band (yangi talab): "Ulanish" so'rovi o'rniga ALLAQACHON
        # ULANGANLIK tasdigi.
        await message.answer(
            texts.ALREADY_CONNECTED,
            reply_markup=user_kb.main_menu(
                connected=True,
                premium_enabled=await _premium_enabled(),
            ),
            disable_web_page_preview=True,
        )
        return

    # Tasdiqlangan, hali ulanmagan foydalanuvchi — menyuni ochamiz.
    await message.answer(
        f"{texts.WELCOME}\n\n{texts.MENU_HINT}",
        reply_markup=user_kb.main_menu(
            connected=False,
            premium_enabled=await _premium_enabled(),
        ),
        disable_web_page_preview=True,
    )


async def _notify_admin_about_request(message: Message) -> None:
    """Egaga yangi kirish so'rovi haqida xabar.

    Har bir PENDING foydalanuvchining /start i egaga eslatma yuboradi
    (yangi talab: so'rovlar panelda paydo bo'lishi KAFOLATLANGAN).
    Bir daqiqada ko'p marta /start bosilsa, spam bo'lmasligi uchun oxirgi
    eslatmadan keyin kamida 60 sekund o'tishi kerak.
    """
    # Ega o'ziga o'zi xabar yubormasin (ikki marta himoya).
    if message.from_user.id == settings.admin_id:
        return

    now = time.monotonic()
    last = _last_admin_reminder.get(message.from_user.id, 0.0)
    if now - last < ADMIN_REMINDER_COOLDOWN:
        return
    _last_admin_reminder[message.from_user.id] = now

    await db.touch_user(message.from_user.id)
    try:
        await message.bot.send_message(
            settings.admin_id,
            texts.ADMIN_NEW_ACCESS_REQUEST.format(
                E_USER=texts.E_USER,
                E_ID=texts.E_ID,
                user=mention_by_id(
                    message.from_user.id,
                    message.from_user.first_name or "User",
                    message.from_user.username,
                ),
                user_id=message.from_user.id,
                username=f"@{message.from_user.username}" if message.from_user.username else "—",
            ),
            parse_mode="HTML",
            reply_markup=admin_kb.access_decision(message.from_user.id),
        )
    except Exception:  # noqa: BLE001
        pass
    # Necha kutilayotgan so'rov borligini ham egaga eslatamiz.
    pending = await db.count_pending_access()
    try:
        await message.bot.send_message(
            settings.admin_id,
            f"✅ Kutilayotgan kirish so'rovlari: <b>{pending}</b>. "
            "Panelda «✅ Kirish so'rovlari» bo'limida ko'rinadi (/admin).",
            parse_mode="HTML",
        )
    except Exception:  # noqa: BLE001
        pass


@router.callback_query(F.data == user_kb.CB_BACK_MENU)
async def back_to_menu(cb: CallbackQuery, state: FSMContext) -> None:
    """Har qanday ekrandan menyuga qaytish (ulanish holati bilan)."""
    await state.clear()
    conns = await db.connections_for_user(cb.from_user.id)
    connected = any(c.get("is_enabled") for c in conns)
    await cb.message.edit_text(
        f"{texts.WELCOME}\n\n{texts.MENU_HINT}",
        reply_markup=user_kb.main_menu(
            connected=connected,
            premium_enabled=await _premium_enabled(),
        ),
    )
    await cb.answer()


# ---------------------------------------------------------------------------
# Statistika + qanday ishlaydi (2-band) — premium emoji bilan
# ---------------------------------------------------------------------------
def _premium_line(user: dict) -> str:
    until = parse_dt(user.get("premium_until"))
    if until and until > datetime.now():
        return texts.PREMIUM_ACTIVE.format(date=fmt_date(until))
    return texts.PREMIUM_INACTIVE


def _human_left(until: datetime) -> str:
    """Qolgan vaqtni o'zbekcha: '3 kun 4 soat 12 daqiqa'."""
    total_minutes = max(0, int((until - datetime.now()).total_seconds() // 60))
    days, rem = divmod(total_minutes, 1440)
    hours, minutes = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days} kun")
    if hours:
        parts.append(f"{hours} soat")
    parts.append(f"{minutes} daqiqa")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Mening obunam (4-band, yangi talab) — qolgan vaqtni tekshirish
# ---------------------------------------------------------------------------
@router.callback_query(F.data == user_kb.CB_MY_SUB)
async def show_my_sub(cb: CallbackQuery) -> None:
    """Obuna holati: faol/emas, tugash sanasi va QOLGAN VAQT."""
    user = await db.get_user(cb.from_user.id) or {}
    until = parse_dt(user.get("premium_until"))
    if until and until > datetime.now():
        body = MY_SUB_ACTIVE.format(date=fmt_datetime(until), left=_human_left(until))
    else:
        body = MY_SUB_INACTIVE
    await cb.message.edit_text(
        MY_SUB_TITLE.format(body=body),
        reply_markup=user_kb.my_sub_menu(),
    )
    await cb.answer()


@router.callback_query(F.data == user_kb.CB_STATS)
async def show_stats(cb: CallbackQuery) -> None:
    """Shaxsiy statistika ekrani (premium emoji IDlari bilan bezatilgan)."""
    user = await db.get_user(cb.from_user.id) or {}
    conns = await db.connections_for_user(cb.from_user.id)
    connected = any(c.get("is_enabled") for c in conns)

    # Faqat SHU foydalanuvchining raqamlari.
    total = await db.count_user_events(cb.from_user.id)
    edits = await db.count_user_events(cb.from_user.id, "edit")
    deletes = await db.count_user_events(cb.from_user.id, "delete") + await db.count_user_events(
        cb.from_user.id, "delete_media"
    )

    body = STATS_BODY.format(
        mention=mention_by_id(
            cb.from_user.id, cb.from_user.first_name or "User", cb.from_user.username
        ),
        user_id=cb.from_user.id,
        connection_line=texts.CONNECTED_LINE if connected else texts.NOT_CONNECTED_LINE,
        premium_line=_premium_line(user),
        total=fmt_number(total),
        edits=fmt_number(edits),
        deletes=fmt_number(deletes),
    )
    await cb.message.edit_text(
        texts.STATS_TITLE.format(body=body) + "\n\n" + texts.HOW_IT_WORKS,
        reply_markup=user_kb.back_to_menu(),
    )
    await cb.answer()


# ---------------------------------------------------------------------------
# Ulanish yo'riqnomasi (1-band) — tg://settings/edit havolasi bilan
# ---------------------------------------------------------------------------
@router.callback_query(F.data == user_kb.CB_CONNECT)
async def show_connect(cb: CallbackQuery) -> None:
    """Sozlamalar → Telegram Business → Chatbotlar yo'riqnomasi."""
    me = await cb.bot.me()
    bot_username = me.username or ""
    await cb.message.edit_text(
        texts.CONNECT_TITLE.format(bot_username=bot_username),
        reply_markup=user_kb.connect_menu(),
        disable_web_page_preview=True,
    )
    await cb.answer()


# ---------------------------------------------------------------------------
# Premium (5-band — foydalanuvchi tomoni)
# ---------------------------------------------------------------------------
@router.callback_query(F.data == user_kb.CB_PREMIUM)
async def show_premium(cb: CallbackQuery, state: FSMContext) -> None:
    """Tarif tanlash: '30 kun - 10 000' tugmalari."""
    # Ikkinchi himoya qatlami: bo'lim o'chiq bo'lsa hech kim kira olmaydi,
    # hatto eski xabardagi tugma orqali ham.
    if not await _premium_enabled():
        await cb.answer(texts.PREMIUM_HIDDEN_USER, show_alert=True)
        return

    await state.clear()
    plans = await db.active_plans()
    if not plans:
        await cb.message.edit_text(
            texts.PREMIUM_NO_PLANS, reply_markup=user_kb.back_to_menu()
        )
        await cb.answer()
        return

    user = await db.get_user(cb.from_user.id) or {}
    until = parse_dt(user.get("premium_until"))
    note = ""
    if until and until > datetime.now():
        note = "\n\n" + texts.PREMIUM_ALREADY.format(date=fmt_date(until))

    await cb.message.edit_text(
        texts.PREMIUM_TITLE + note,
        reply_markup=await user_kb.premium_plans(db),
    )
    await cb.answer()


@router.callback_query(F.data.startswith(user_kb.CB_PLAN))
async def show_checkout(cb: CallbackQuery, state: FSMContext) -> None:
    """To'lov oynasi: narx + nusxalanadigan karta + chek yo'riqnomasi."""
    await state.clear()
    raw = cb.data.removeprefix(user_kb.CB_PLAN)
    if not raw.isdigit():
        await cb.answer(texts.UNKNOWN_ACTION, show_alert=True)
        return
    plan = await db.get_plan(int(raw))
    if plan is None or not plan["is_active"]:
        await cb.answer(texts.UNKNOWN_ACTION, show_alert=True)
        return

    await cb.message.edit_text(
        PREMIUM_CHECKOUT.format(
            title=plan_checkout_title(plan["title"], plan["duration_days"]),
            price=fmt_number(plan["price"]),
            card=settings.payment_card_number,
            holder=settings.payment_card_holder,
            description=esc(plan["description"]),
        ),
        reply_markup=user_kb.premium_checkout(plan["id"]),
    )
    await cb.answer()


# ---------------------------------------------------------------------------
# Chek yuklash — to'lovdan keyin yuborilgan foto
# ---------------------------------------------------------------------------
@router.message(F.photo)
async def receive_receipt(message: Message, state: FSMContext) -> None:
    """Shaxsiy chatga yuborilgan har qanday foto = to'lov cheki.

    Chek Tasdiqlash/Rad etish tugmalari bilan egaga yuboriladi
    (admin qismi — app/handlers/admin_payments.py).
    """
    if await state.get_state() is not None:
        return  # boshqa usta (masalan, ommaviy xabar) suhbatni egallagan
    if message.from_user and message.from_user.id == settings.admin_id:
        return  # eganing o'z fotosi chek emas

    plans = await db.active_plans()
    if not plans:
        await message.answer(texts.UNKNOWN_ACTION)
        return
    plan = plans[0]  # sodda: birinchi faol tarif

    file_id = message.photo[-1].file_id
    payment_id = await db.create_payment(message.from_user.id, plan["id"], file_id)

    caption = texts.ADMIN_PAYMENT_CARD.format(
        payment_id=payment_id,
        user=mention_by_id(
            message.from_user.id,
            message.from_user.first_name or "User",
            message.from_user.username,
        ),
        plan=f"{esc(plan['title'])} ({plan['duration_days']} kun / {fmt_number(plan['price'])})",
        created=fmt_datetime(datetime.now()),
    )
    await message.bot.send_photo(
        settings.admin_id,
        photo=file_id,
        caption=caption,
        parse_mode="HTML",
        reply_markup=admin_kb.payment_decision(payment_id),
    )
    await message.answer(texts.RECEIPT_RECEIVED)
