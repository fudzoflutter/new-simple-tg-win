"""
Outer middlewares (har bir update uchun ishlaydi).

* :class:`RegisterUserMiddleware` – foydalanuvchini DBga yozadi va
  ``last_activity`` ni yangilab boradi ("kim onlayn" ekrani uchun).
  YANGI foydalanuvchi avtomatik ``access_status='pending'`` bo'ladi —
  admin tasdiqlamaguncha bot ishlamaydi (yangi talab).
* :class:`AccessGuardMiddleware` – banlangan va tasdiqlanmagan
  foydalanuvchilarning so'rovlarini to'sadi.

Ega (``settings.admin_id``) hech qachon bloklanmaydi.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable, Optional

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, User as TgUser

from app.config import settings
from app.database import db
from app.utils import texts

logger = logging.getLogger(__name__)

# Oddiy anti-spam: bir foydalanuvchi soniyasiga ko'pi bilan N so'rov.
RATE_LIMIT_EVENTS = 5
RATE_WINDOW = 1.0  # sekund


class RegisterUserMiddleware(BaseMiddleware):
    """Foydalanuvchini DBga yozish + faollikni yangilash.

    ``business_message`` update'lari ATAYIN o'tkazib yuboriladi: ularda
    ``from_user`` — suhbatdosh, bot foydalanuvchisi emas; ularni ro'yxatga
    olish foydalanuvchilar ro'yxatini (va ommaviy xabar oluvchilarni)
    ifloslantiradi.
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
        if len(RegisterUserMiddleware._buckets) > MAX_BUCKETS:
            oldest = next(iter(RegisterUserMiddleware._buckets))
            RegisterUserMiddleware._buckets.pop(oldest, None)
        now = time.monotonic()
        window: list[float] = RegisterUserMiddleware._buckets.setdefault(user_id, [])
        window[:] = [t for t in window if now - t < RATE_WINDOW]
        window.append(now)
        return len(window) > RATE_LIMIT_EVENTS

    _buckets: dict[int, list[float]] = {}

MAX_BUCKETS = 5_000


class AccessGuardMiddleware(BaseMiddleware):
    """Ban + kirish tasdiqlash tekshiruvi.

    - ``is_banned``        -> bot umuman ishlamaydi
    - ``access_status = 'pending'``  -> "so'rovingiz ko'rib chiqilmoqda"
    - ``access_status = 'rejected'`` -> "rad etilgan"
    Ega doim o'tadi.  business_* update'lariga tegmaydi (ularning
    from_user — suhbatdosh, tekshiruv uchun mos emas; ularni business.py
    ning o'zida connection egasi bo'yicha tekshiramiz).

    MUHIM (bug fix): ``/start`` bu to'siqdan O'TADI hatto pending/rejected
    bo'lganda ham — aks holda kirish SO'ROVI panelda umuman paydo
    bo'lmaydi (handler egani xabar qiladi, to'siq esa hamma narsani
    yutib yuborardi).  Handler o'zi statusga qarab to'g'ri ekranni
    ko'rsatadi.
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

        # /start har doim handlerga yetib borishi kerak (so'rov ro'yxati
        # shu yerda to'ldiriladi).  Banlangan foydalanuvchi uchun ham
        # handler o'zi BANNED ekranni ko'rsatadi.
        is_start = (
            isinstance(event, Message)
            and (event.text or "").strip().lower().startswith("/start")
        )

        if (
            user is not None
            and user.id != settings.admin_id
            and is_direct
            and not is_start
        ):
            row = await db.get_user(user.id)

            if row and row.get("is_banned"):
                logger.info("Blocked banned user %s", user.id)
                await self._reject(event, texts.BANNED, texts.BAN_CALLBACK)
                return None

            status = (row or {}).get("access_status") or "pending"
            if status == "pending":
                await self._reject(event, texts.ACCESS_PENDING, texts.ACCESS_PENDING_CALLBACK)
                return None
            if status == "rejected":
                await self._reject(event, texts.ACCESS_REJECTED, texts.ACCESS_REJECTED_CALLBACK)
                return None

        return await handler(event, data)

    @staticmethod
    async def _reject(event: TelegramObject, html_text: str, plain_text: str) -> None:
        """Javob qaytarish: callback -> alert, oddiy xabar -> matn."""
        if isinstance(event, CallbackQuery):
            await event.answer(plain_text, show_alert=True)
        elif isinstance(event, Message):
            await event.answer(html_text)
