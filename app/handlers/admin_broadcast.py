"""
Admin handlers – broadcast / advertisements (spec item 5).

Supports text with links and formatting, photos, videos, stickers – whatever
the admin sends is copied to every active user.  Premium emoji inside the
post are preserved because we use ``copy_message``.
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.database import db
from app.keyboards import admin_kb
from app.services.broadcaster import Broadcaster
from app.states import BroadcastWizard
from app.utils import texts

router = Router(name="admin_broadcast")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enter the wizard
# ---------------------------------------------------------------------------
@router.callback_query(F.data == admin_kb.CB_BROADCAST)
async def start_broadcast(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(BroadcastWizard.waiting_content)
    await cb.message.edit_text(
        texts.ADMIN_BROADCAST_ASK,
        reply_markup=admin_kb.cancel_to_panel(),
    )
    await cb.answer()


@router.callback_query(F.data == admin_kb.CB_CANCEL)
async def cancel_wizard(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await cb.message.edit_text(
        texts.BROADCAST_CANCELLED,
        reply_markup=admin_kb.panel(
            pending_payments=len(await db.pending_payments()),
            premium_enabled=(await db.get_setting_cached("premium_enabled", "0")) == "1",
        ),
    )
    await cb.answer()


# ---------------------------------------------------------------------------
# Admin sends the post -> confirmation with the recipient count
# ---------------------------------------------------------------------------
@router.message(BroadcastWizard.waiting_content)
async def preview_broadcast(message: Message, state: FSMContext) -> None:
    """Har qanday kontent turini ommaviy post sifatida qabul qiladi."""
    count = await db.count_users(only_active=True)
    if count == 0:
        await state.clear()
        await message.answer(texts.BROADCAST_NO_RECIPIENTS, reply_markup=admin_kb.panel())
        return

    await state.update_data(
        broadcast_chat_id=message.chat.id,
        broadcast_message_id=message.message_id,
    )
    await message.answer(
        texts.ADMIN_BROADCAST_CONFIRM.format(count=count),
        reply_markup=admin_kb.broadcast_confirm(),
    )


# ---------------------------------------------------------------------------
# Launch
# ---------------------------------------------------------------------------
@router.callback_query(F.data == admin_kb.CB_BROADCAST_SEND)
async def launch_broadcast(cb: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    chat_id = data.get("broadcast_chat_id")
    message_id = data.get("broadcast_message_id")
    if not chat_id or not message_id:
        await cb.answer(texts.ADMIN_BROADCAST_EMPTY, show_alert=True)
        return

    await state.clear()
    await cb.answer(texts.ADMIN_BROADCAST_STARTED)

    # Deliver in the background so the admin can keep using the bot.
    broadcaster = Broadcaster(cb.bot)
    asyncio.create_task(
        _run_broadcast(broadcaster, int(chat_id), int(message_id), cb.from_user.id)
    )


async def _run_broadcast(
    broadcaster: Broadcaster, chat_id: int, message_id: int, admin_id: int
) -> None:
    """Background worker: copies the source post to all active users."""
    try:
        result = await broadcaster.broadcast(chat_id, message_id)
    except Exception:  # noqa: BLE001
        logger.exception("Broadcast crashed")
        return
    try:
        await broadcaster.bot.send_message(
            admin_id,
            texts.ADMIN_BROADCAST_DONE.format(
                sent=result.sent, skipped=result.skipped
            ),
            parse_mode="HTML",
        )
    except Exception:  # noqa: BLE001
        logger.exception("Could not deliver broadcast summary")
