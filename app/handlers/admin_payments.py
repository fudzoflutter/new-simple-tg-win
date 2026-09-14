"""
Admin handlerlari – to'lovlar (5-band).

Cheklar app/handlers/user.py da qabul qilinadi va Tasdiqlash/Rad etish
tugmalari bilan egaga yuboriladi.  Bu yerda admin qaror qabul qiladi:

* ✅ Tasdiqlash -> premium uzaytiriladi, foydalanuvchiga xabar boradi
* ❌ Rad etish  -> foydalanuvchiga xabar boradi
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.database import db
from app.keyboards import admin_kb
from app.utils import texts
from app.utils.formatting import esc, fmt_date, fmt_datetime

router = Router(name="admin_payments")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Kutilayotgan to'lovlar ro'yxati (cheklar rasmlari egaga allaqachon
# yuborilgan; ro'yxat — umumiy ko'rinish uchun).
# ---------------------------------------------------------------------------
@router.callback_query(F.data == admin_kb.CB_PAYMENTS)
async def show_payments(cb: CallbackQuery) -> None:
    rows = await db.pending_payments()
    if not rows:
        body = texts.ADMIN_PAYMENTS_EMPTY
    else:
        lines = []
        for p in rows:
            user = await db.get_user(p["user_id"])
            name = (
                esc(user.get("first_name") or str(p["user_id"])) if user else str(p["user_id"])
            )
            lines.append(f"💳 #{p['id']} — {name} — {fmt_datetime(p['created_at'])}")
        body = "\n".join(lines)

    await cb.message.edit_text(
        texts.ADMIN_PAYMENTS_TITLE.format(list=body),
        reply_markup=admin_kb.payments_menu(),
    )
    await cb.answer()


# ---------------------------------------------------------------------------
# Tasdiqlash / rad etish
# ---------------------------------------------------------------------------
@router.callback_query(F.data.startswith(admin_kb.CB_PAYMENT_OK))
async def approve_payment(cb: CallbackQuery) -> None:
    await _decide(cb, approved=True)


@router.callback_query(F.data.startswith(admin_kb.CB_PAYMENT_NO))
async def reject_payment(cb: CallbackQuery) -> None:
    await _decide(cb, approved=False)


async def _decide(cb: CallbackQuery, *, approved: bool) -> None:
    prefix = admin_kb.CB_PAYMENT_OK if approved else admin_kb.CB_PAYMENT_NO
    raw = cb.data.removeprefix(prefix)
    if not raw.isdigit():
        await cb.answer(texts.UNKNOWN_ACTION, show_alert=True)
        return

    # JOIN orqali tarif davomiyligini bir so'rovda olamiz.
    payment = await db.payment_with_plan(int(raw))
    if payment is None or payment["status"] != "pending":
        await cb.answer(texts.ADMIN_PAYMENT_GONE, show_alert=True)
        return

    user_id = payment["user_id"]
    days = payment["duration_days"] or 0

    if approved:
        until = await db.extend_premium(user_id, days)
        await db.set_payment_status(payment["id"], "approved", cb.from_user.id)
        try:
            await cb.bot.send_message(
                user_id,
                texts.PREMIUM_APPROVED_USER.format(date=fmt_date(until)),
                parse_mode="HTML",
            )
        except Exception:  # noqa: BLE001
            logger.info("Could not notify user %s about approval", user_id)
        await cb.answer(
            texts.ADMIN_PAYMENT_APPROVED.format(
                payment_id=payment["id"], date=fmt_date(until)
            ),
            show_alert=True,
        )
    else:
        await db.set_payment_status(payment["id"], "rejected", cb.from_user.id)
        try:
            await cb.bot.send_message(
                user_id, texts.PREMIUM_REJECTED_USER, parse_mode="HTML"
            )
        except Exception:  # noqa: BLE001
            logger.info("Could not notify user %s about rejection", user_id)
        await cb.answer(
            texts.ADMIN_PAYMENT_REJECTED.format(payment_id=payment["id"]),
            show_alert=True,
        )

    # Chek xabaridagi tugmalarni o'chirish.
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:  # noqa: BLE001
        pass
