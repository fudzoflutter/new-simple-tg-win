"""
Broadcast service (spec item 5 – advertisements).

Takes any message the admin sent (text with links, photo, video, sticker —
premium emoji included) and delivers it to every active user.  Uses
``copy_message`` so the post keeps its formatting; falls back to a plain
``send_message`` if a specific user rejects the copy.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter

from app.database import db

logger = logging.getLogger(__name__)

# Delay between users – keeps us well under Telegram's rate limits.
THROTTLE_SECONDS = 0.05


@dataclass
class BroadcastResult:
    """Simple counters returned to the admin after the run."""

    sent: int = 0
    failed: int = 0
    skipped: int = 0


class Broadcaster:
    """Delivers an admin post to all users currently using the bot."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def broadcast(self, from_chat_id: int, message_id: int) -> BroadcastResult:
        """Copy the source message to every active user.

        429 (flood-wait) bo'lsa Telegramning o'z aytgan vaqticha kutamiz —
        xabar YO'QOTILMAYDI, keyin qayta uriniladi.  Block qilingan /
        botni o'chirgan foydalanuvchi 'skipped' hisoblanadi.
        """
        result = BroadcastResult()
        users = await db.all_users(only_active=True)

        for user in users:
            user_id = user["user_id"]
            try:
                await self.bot.copy_message(
                    chat_id=user_id,
                    from_chat_id=from_chat_id,
                    message_id=message_id,
                )
                result.sent += 1
            except TelegramRetryAfter as exc:
                # Telegram aytgan chaqiruvni kutib, BIR MARTA qayta urinamiz.
                logger.warning(
                    "Flood control: waiting %ss before user %s", exc.retry_after, user_id
                )
                await asyncio.sleep(exc.retry_after + 1)
                try:
                    await self.bot.copy_message(
                        chat_id=user_id,
                        from_chat_id=from_chat_id,
                        message_id=message_id,
                    )
                    result.sent += 1
                except Exception:  # noqa: BLE001 – qayta urinish ham yiqildi
                    result.skipped += 1
            except Exception:  # noqa: BLE001 – count, do not crash
                logger.debug("copy_message failed for %s: %s", user_id, exc)
                if await self._fallback_send(from_chat_id, message_id, user_id):
                    result.sent += 1
                else:
                    result.skipped += 1
            await asyncio.sleep(THROTTLE_SECONDS)

        return result

    async def _fallback_send(
        self, from_chat_id: int, message_id: int, user_id: int
    ) -> bool:
        """Last resort: forward the original – better than nothing.

        429 bo'lsa bir marta kutib ko'ramiz, keyin taslim bo'lamiz.
        """
        for attempt in (1, 2):
            try:
                source = await self.bot.forward_message(
                    chat_id=user_id, from_chat_id=from_chat_id, message_id=message_id
                )
                return source is not None
            except TelegramRetryAfter as exc:
                if attempt == 2:
                    return False
                await asyncio.sleep(exc.retry_after + 1)
            except Exception:  # noqa: BLE001
                return False
        return False
