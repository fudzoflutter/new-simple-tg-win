"""
Outer middleware (har bir update uchun ishlaydi).

* :class:`RegisterUserMiddleware` – foydalanuvchini DBga yozadi va
  ``last_activity`` ni yangilab boradi ("kim onlayn" hisobi uchun).

Ban / kirish-tasdiqlash tizimi admin panel bilan birga OLIB TASHLANGAN
(yangi talab) — endi bot barcha foydalanuvchilarga ochiq.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable, Optional

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, User as TgUser

from app.config import settings
from app.database import db

logger = logging.getLogger(__name__)

# Oddiy anti-spam: bir foydalanuvchi soniyasiga ko'pi bilan N so'rov.
RATE_LIMIT_EVENTS = 5
RATE_WINDOW = 1.0  # sekund

# Tezlik: har bir update uchun DB YOZUVI juda qimmat (Railway <-> Supabase
# ~200 ms).  Yangi foydalanuvchini ro'yxatga olish + last_activity
# yangilash 60 sekundda BIR marta yetarli.
UPSERT_INTERVAL_SECONDS = 60.0

# Keshlar (protsess ichida) — MAXSUS: faqat event loop ichidan o'zgartiriladi.
_last_upsert: dict[int, float] = {}
_buckets: dict[int, list[float]] = {}
_MAX_BUCKETS = 5_000


class RegisterUserMiddleware(BaseMiddleware):
    """Foydalanuvchini DBga yozish + faollikni yangilash.

    ``business_message`` update'lari ATAYIN o'tkazib yuboriladi: ularda
    ``from_user`` — suhbatdosh, bot foydalanuvchisi emas; ularni ro'yxatga
    olish foydalanuvchilar ro'yxatini ifloslantiradi.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: Optional[TgUser] = data.get("event_from_user")
        is_direct = isinstance(event, CallbackQuery) or (
            isinstance(event, Message) and not event.business_connection_id
        )
        if user is not None and not user.is_bot and is_direct:
            # TEZLIK: upsert har update'da emas — foydalanuvchi uchun 60 s da
            # bir marta (yangi foydalanuvchi esa DARHOL yoziladi).
            now = time.monotonic()
            last = _last_upsert.get(user.id, 0.0)
            if now - last >= UPSERT_INTERVAL_SECONDS:
                # YAZUVNI boshlashdan OLDIN belgilaymiz: xato bo'lsa ham
                # keyingi urinish 60 s dan KECHIN bo'ladi.
                _last_upsert[user.id] = now
                if len(_last_upsert) > _MAX_BUCKETS:
                    oldest = next(iter(_last_upsert))
                    _last_upsert.pop(oldest, None)
                try:
                    await db.upsert_user(
                        user_id=user.id,
                        username=user.username,
                        first_name=user.first_name,
                        last_name=user.last_name,
                    )
                except Exception:  # noqa: BLE001 – DB xatosi update'larni uzmasin
                    logger.exception("Failed to upsert user %s", user.id)

            # Anti-spam: admin uchun emas.
            if user.id != settings.admin_id and self._is_flooding(user.id):
                logger.warning("Rate limit hit for user %s", user.id)
                return None

        return await handler(event, data)

    @staticmethod
    def _is_flooding(user_id: int) -> bool:
        # Xotira cheklovi: juda ko'p noyob id to'plansa (spam/attack)
        # eng qadimgi yozuvlarni tashlab qo'yamiz.
        if len(_buckets) > _MAX_BUCKETS:
            oldest = next(iter(_buckets))
            _buckets.pop(oldest, None)
        now = time.monotonic()
        window: list[float] = _buckets.setdefault(user_id, [])
        window[:] = [t for t in window if now - t < RATE_WINDOW]
        window.append(now)
        return len(window) > RATE_LIMIT_EVENTS
