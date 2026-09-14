"""
Admin handlers – premium plans (spec item 5).

The wizard asks for: title -> duration (days) -> price -> description, then
stores the plan.  Plans immediately appear on the user's Premium screen.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from app.database import db
from app.keyboards import admin_kb
from app.states import PlanWizard
from app.utils import texts
from app.utils.formatting import esc, fmt_number

router = Router(name="admin_plans")
logger = logging.getLogger(__name__)

# Tarif tahrirlash maydonlari (callback data orqali keladi).
EDIT_FIELDS = {"title", "duration", "price", "desc"}


# ---------------------------------------------------------------------------
# Plans list
# ---------------------------------------------------------------------------
@router.callback_query(F.data == admin_kb.CB_PLANS)
async def show_plans(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    plans = await db.all_plans()

    if not plans:
        body = texts.ADMIN_PLANS_EMPTY
    else:
        lines = []
        for p in plans:
            mark = (
                texts.ADMIN_PLAN_ACTIVE_MARK
                if p["is_active"]
                else texts.ADMIN_PLAN_HIDDEN_MARK
            )
            lines.append(
                texts.ADMIN_PLAN_LINE.format(
                    title=esc(p["title"]),
                    days=p["duration_days"],
                    price=fmt_number(p["price"]),
                    active=mark,
                )
            )
        body = "".join(lines)

    # Har bir tarif nomi ENDI BOSILADIGAN tugma — bosilganda kartochka
    # (tahrirlash / yashirish / o'chirish) ochiladi.
    plan_rows = [
        [admin_kb.btn(str(p["title"])[:48], f"{admin_kb.CB_PLAN_VIEW}{p['id']}")]
        for p in plans
    ]

    await cb.message.edit_text(
        texts.ADMIN_PLANS_TITLE.format(list=body),
        reply_markup=admin_kb.plans_menu_with(plan_rows),
    )
    await cb.answer()


# ---------------------------------------------------------------------------
# One plan card: view, edit wizard, hide/show, delete
# ---------------------------------------------------------------------------
async def _render_plan_card(plan: dict) -> tuple[str, InlineKeyboardMarkup]:
    """Bitta tarif kartochkasi — tahrirlash/o'chirish SHU YERDAN bo'ladi."""
    text = texts.ADMIN_PLAN_DETAILS.format(
        title=esc(plan["title"]),
        days=plan["duration_days"],
        price=fmt_number(plan["price"]),
        description=esc(plan["description"]) or "—",
        status=texts.ADMIN_PLAN_ACTIVE_MARK
        if plan["is_active"]
        else texts.ADMIN_PLAN_HIDDEN_MARK,
    )
    return text, admin_kb.plan_row(plan["id"])


@router.callback_query(F.data.startswith(admin_kb.CB_PLAN_VIEW))
async def view_plan(cb: CallbackQuery) -> None:
    """Ro'yxatdagi tarif NOMINI bosganda — kartochka ochiladi."""
    raw = cb.data.removeprefix(admin_kb.CB_PLAN_VIEW)
    if not raw.isdigit():
        await cb.answer(texts.UNKNOWN_ACTION, show_alert=True)
        return
    plan = await db.get_plan(int(raw))
    if plan is None:
        await cb.answer(texts.UNKNOWN_ACTION, show_alert=True)
        return
    text, markup = await _render_plan_card(plan)
    await cb.message.edit_text(text, reply_markup=markup)
    await cb.answer()


# ---------------------------------------------------------------------------
# Edit wizard: field-by-field, "-" keeps the current value
# ---------------------------------------------------------------------------
@router.callback_query(F.data.startswith(admin_kb.CB_PLAN_EDIT))
async def start_plan_edit(cb: CallbackQuery, state: FSMContext) -> None:
    """'adm:plan:edit:<id>' yoki 'adm:plan:edit:<id>:<field>'."""
    raw = cb.data.removeprefix(admin_kb.CB_PLAN_EDIT)
    parts = raw.split(":")
    if not parts or not parts[0].isdigit():
        await cb.answer(texts.UNKNOWN_ACTION, show_alert=True)
        return
    plan_id = int(parts[0])
    plan = await db.get_plan(plan_id)
    if plan is None:
        await cb.answer(texts.UNKNOWN_ACTION, show_alert=True)
        return

    field = parts[1] if len(parts) > 1 else ""
    if field not in EDIT_FIELDS:
        # Umumiy tahrirlash menyusi (maydon tanlanmagan bo'lsa).
        await cb.message.edit_text(
            texts.ADMIN_PLAN_DETAILS.format(
                title=esc(plan["title"]),
                days=plan["duration_days"],
                price=fmt_number(plan["price"]),
                description=esc(plan["description"]) or "—",
                status=texts.ADMIN_PLAN_ACTIVE_MARK
                if plan["is_active"]
                else texts.ADMIN_PLAN_HIDDEN_MARK,
            ),
            reply_markup=admin_kb.plan_edit_menu(plan_id),
        )
        await cb.answer()
        return

    await state.set_state(PlanWizard.editing)
    await state.update_data(edit_plan_id=plan_id, edit_field=field)
    ask = {
        "title": texts.ADMIN_PLAN_EDIT_TITLE,
        "duration": texts.ADMIN_PLAN_EDIT_DURATION,
        "price": texts.ADMIN_PLAN_EDIT_PRICE,
        "desc": texts.ADMIN_PLAN_EDIT_DESC,
    }[field]
    prompt = ask.format(
        title=esc(plan["title"]),
        days=plan["duration_days"],
        price=fmt_number(plan["price"]),
        description=esc(plan["description"]) or "—",
    )
    await cb.message.edit_text(prompt, reply_markup=admin_kb.cancel_to_panel())
    await cb.answer()


@router.message(PlanWizard.editing)
async def plan_edit_value(message: Message, state: FSMContext) -> None:
    """Tahrirlash qiymatini qabul qiladi ('-' = o'zgartirmaslik)."""
    data = await state.get_data()
    plan_id: int = data["edit_plan_id"]
    field: str = data["edit_field"]
    plan = await db.get_plan(plan_id)
    if plan is None:
        await state.clear()
        await message.answer(texts.UNKNOWN_ACTION)
        return

    raw = (message.text or "").strip()
    updates: dict = {}
    error: str | None = None

    if raw == "-":
        pass  # hech narsa o'zgarmaydi
    elif field == "title":
        if raw:
            updates["title"] = raw[:64]
    elif field == "duration":
        if not raw.isdigit() or not (1 <= int(raw) <= 3650):
            error = texts.WIZARD_PLAN_DAYS_INVALID
        else:
            updates["duration_days"] = int(raw)
    elif field == "price":
        cleaned = raw.replace(" ", "").replace(",", "")
        if not cleaned.isdigit():
            error = texts.WIZARD_PLAN_PRICE_INVALID
        else:
            updates["price"] = int(cleaned)
    elif field == "desc":
        if raw == "0":
            updates["description"] = ""
        else:
            updates["description"] = raw[:500]

    if error:
        await message.answer(error)
        return

    if updates:
        await db.update_plan(plan_id, **updates)
    await state.clear()

    fresh = await db.get_plan(plan_id)
    await message.answer(texts.ADMIN_PLAN_EDIT_DONE)
    if fresh:
        text, markup = await _render_plan_card(fresh)
        await message.answer(text, reply_markup=markup)


@router.callback_query(F.data == admin_kb.CB_PLAN_ADD)
async def start_plan_wizard(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(PlanWizard.title)
    await cb.message.edit_text(
        texts.WIZARD_PLAN_CREATE_ASK,
        reply_markup=admin_kb.cancel_to_panel(),
    )
    await cb.answer()


@router.message(PlanWizard.title)
async def plan_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=message.text.strip()[:64])
    await state.set_state(PlanWizard.duration)
    await message.answer(
        texts.WIZARD_PLAN_DURATION_ASK,
        reply_markup=admin_kb.cancel_to_panel(),
    )


@router.message(PlanWizard.duration)
async def plan_duration(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if not raw.isdigit() or not (1 <= int(raw) <= 3650):
        await message.answer(texts.WIZARD_PLAN_DAYS_INVALID)
        return
    await state.update_data(duration_days=int(raw))
    await state.set_state(PlanWizard.price)
    await message.answer(
        texts.WIZARD_PLAN_PRICE_ASK,
        reply_markup=admin_kb.cancel_to_panel(),
    )


@router.message(PlanWizard.price)
async def plan_price(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip().replace(" ", "").replace(",", "")
    if not raw.isdigit():
        await message.answer(texts.WIZARD_PLAN_PRICE_INVALID)
        return
    await state.update_data(price=int(raw))
    await state.set_state(PlanWizard.description)
    await message.answer(
        texts.WIZARD_PLAN_DESC_ASK,
        reply_markup=admin_kb.cancel_to_panel(),
    )


@router.message(PlanWizard.description)
async def plan_description(message: Message, state: FSMContext) -> None:
    raw = (message.text or "-").strip()
    description = "" if raw == "-" else raw[:500]

    data = await state.get_data()
    plan_id = await db.create_plan(
        title=data["title"],
        duration_days=data["duration_days"],
        price=data["price"],
        description=description,
    )
    await state.clear()

    await message.answer(
        texts.ADMIN_PLAN_CREATED.format(title=esc(data["title"]))
        + f"\n\n🆔 Plan ID: <code>{plan_id}</code>",
        reply_markup=admin_kb.plans_menu(),
    )


# ---------------------------------------------------------------------------
# Manage one plan: hide/show, delete
# ---------------------------------------------------------------------------
@router.callback_query(F.data.startswith(admin_kb.CB_PLAN_TOGGLE))
async def toggle_plan(cb: CallbackQuery) -> None:
    raw = cb.data.removeprefix(admin_kb.CB_PLAN_TOGGLE)
    if not raw.isdigit():
        await cb.answer(texts.UNKNOWN_ACTION, show_alert=True)
        return
    plan = await db.get_plan(int(raw))
    if plan is None:
        await cb.answer(texts.UNKNOWN_ACTION, show_alert=True)
        return
    await db.set_plan_active(plan["id"], not plan["is_active"])
    await cb.answer(texts.ADMIN_VISIBILITY_CHANGED)
    await show_plans_refresh(cb)


@router.callback_query(F.data.startswith(admin_kb.CB_PLAN_DELETE))
async def delete_plan(cb: CallbackQuery) -> None:
    raw = cb.data.removeprefix(admin_kb.CB_PLAN_DELETE)
    # Format: '<id>' (so'rash) yoki '<id>:confirm' (bajarish).
    if not raw:
        await cb.answer(texts.UNKNOWN_ACTION, show_alert=True)
        return
    if raw.endswith(":confirm"):
        plan_id = int(raw.removesuffix(":confirm"))
        await db.delete_plan(plan_id)
        await cb.answer(texts.ADMIN_PLAN_DELETED)
        await show_plans_refresh(cb)
    else:
        plan = await db.get_plan(int(raw))
        if plan is None:
            await cb.answer(texts.UNKNOWN_ACTION, show_alert=True)
            return
        title = esc(plan["title"])
        await cb.message.edit_text(
            texts.ADMIN_PLAN_CONFIRM_DELETE.format(title=title),
            reply_markup=admin_kb.plan_delete_confirm(plan["id"]),
        )
        await cb.answer()


async def show_plans_refresh(cb: CallbackQuery) -> None:
    """Re-render the plans list after a change."""
    plans = await db.all_plans()
    if not plans:
        body = texts.ADMIN_PLANS_EMPTY
    else:
        lines = []
        for p in plans:
            mark = (
                texts.ADMIN_PLAN_ACTIVE_MARK
                if p["is_active"]
                else texts.ADMIN_PLAN_HIDDEN_MARK
            )
            lines.append(
                texts.ADMIN_PLAN_LINE.format(
                    title=esc(p["title"]),
                    days=p["duration_days"],
                    price=fmt_number(p["price"]),
                    active=mark,
                )
            )
        body = "".join(lines)
    try:
        await cb.message.edit_text(
            texts.ADMIN_PLANS_TITLE.format(list=body),
            reply_markup=admin_kb.plans_menu_with(
                [
                    [admin_kb.btn(str(p["title"])[:48], f"{admin_kb.CB_PLAN_VIEW}{p['id']}")]
                    for p in plans
                ]
            ),
        )
    except Exception:  # noqa: BLE001 – message may be identical
        pass
