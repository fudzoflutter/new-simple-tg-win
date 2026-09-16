"""
Outer middleware (har bir update uchun ishlaydi).

:class:`RegisterUserMiddleware` ikki ish qiladi:

1. **Kirish nazorati** — foydalanuvchi botdan foydalana oladimi
   (allow / deny / ban; :mod:`app.services.access`).  Ruxsati yo'q odam
   handler'larga YETIB BORMAYDI: u birinchi marta murojaat qilsa adminga
   «Ruxsat berish / Rad etish» kartasi yuboriladi.
2. **Ro'yxatga olish** — foydalanuvchini DBga yozish va ``last_activity``
   ni yangilash ("kim onlayn" hisobi uchun).

TEZLIK (muhim talab)
--------------------
Ruxsat tekshiruvi SOF SINXRON: keshdagi lug'atdan bitta o'qish — hech
qanday ``await``, DB so'rovi yoki tarmoq yo'q.  DBga yozish faqat:

* yangi foydalanuvchi birinchi marta ruxsat so'raganda (bir marta), va
* ro'yxatga olish 60 sekundda bir marta (quyida ``UPSERT_INTERVAL_SECONDS``).

Shu sababli nazorat bot tezligiga ta'sir qilmaydi.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable, Optional

from aiogram import BaseMiddleware
from aiogram.types import (
    CallbackQuery,
    Message,
    TelegramObject,
    Update,
    User as TgUser,
)

from app.config import settings
from app.database import db
from app.services import access
from app.utils.formatting import strip_html
from app.utils.tasks import spawn

logger = logging.getLogger(__name__)

# Oddiy anti-spam: bir foydalanuvchi soniyasiga ko'pi bilan N so'rov.
RATE_LIMIT_EVENTS = 5          # matn xabarlari
# Tugmalar (callback) — bu foydalanuvchi interfeysi: ularni JIMGINA tashlab
# bo'lmaydi (tugma "ishlamayapti"dek ko'rinadi, spinner esa aylanib qoladi).
# Shu sababli chegara ancha yumshoq.
RATE_LIMIT_CALLBACKS = 15
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
    """Ruxsatni tekshirish + foydalanuvchini DBga yozish.

    MUHIM: middleware ``dp.update`` darajasida o'rnatiladi
    (:mod:`app.main`), ya'ni bu yerga keladigan ``event`` — **Update**, 
    Message/CallbackQuery emas.  Shu sababli avval uning ICHIDAGI
    foydalanuvchi event'i ajratib olinadi (:meth:`_direct_event`):

    * ``message`` / ``edited_message`` / ``callback_query`` — egasi
      foydalanuvchi, tekshiriladi va ro'yxatga olinadi;
    * ``business_*`` update'lari ATAYIN o'tkazib yuboriladi — ularda
      ``from_user`` — suhbatdosh, bot foydalanuvchisi emas (ro'yxatni
      ifloslantiradi).
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: Optional[TgUser] = data.get("event_from_user")
        direct = self._direct_event(event)

        if user is not None and not user.is_bot and direct is not None:
            # ---- KIRISH NAZORATI (kesh) --------------------------------------
            # SINXRON tekshiruv: ruxsatli foydalanuvchi uchun qo'shimcha
            # xarajat — bitta lug'atdan o'qish (mikrosekundlar).
            if not access.can_use(user.id):
                await self._deny(direct, user)
                return None

            # ---- RO'YXATGA OLISH ---------------------------------------------
            # TEZLIK: ikki qavat himoya.
            #  1) upsert har update'da emas — foydalanuvchi uchun 60 s da bir
            #     marta (yangi foydalanuvchi esa DARHOL yoziladi);
            #  2) yozuv FONDA ketadi: Supabase uzoqda bo'lsa bu ~1.2 s, lekin
            #     foydalanuvchi uni KUTMAYDI.
            now = time.monotonic()
            last = _last_upsert.get(user.id, 0.0)
            if now - last >= UPSERT_INTERVAL_SECONDS:
                # YAZUVNI boshlashdan OLDIN belgilaymiz: xato bo'lsa ham
                # keyingi urinish 60 s dan KECHIN bo'ladi.
                _last_upsert[user.id] = now
                if len(_last_upsert) > _MAX_BUCKETS:
                    oldest = next(iter(_last_upsert))
                    _last_upsert.pop(oldest, None)
                spawn(
                    db.upsert_user(
                        user_id=user.id,
                        username=user.username,
                        first_name=user.first_name,
                        last_name=user.last_name,
                    ),
                    name=f"upsert:{user.id}",
                )

            # Anti-spam: admin uchun emas.  Tugmalar uchun chegara yumshoqroq
            # (ular jimgina tashlab yuborilmasligi kerak).
            limit = (
                RATE_LIMIT_EVENTS
                if isinstance(direct, Message)
                else RATE_LIMIT_CALLBACKS
            )
            if user.id != settings.admin_id and self._is_flooding(user.id, limit):
                logger.warning("Rate limit hit for user %s", user.id)
                return None

        return await handler(event, data)

    @staticmethod
    def _direct_event(event: TelegramObject) -> Optional[TelegramObject]:
        """Update ichidan foydalanuvchi bilan BEVOSITA bog'liq event'ni oladi.

        ``None`` — bu update bo'yicha kirish nazorati va ro'yxatga olish
        kerak emas (biznes-hodisalar hamda xabar/callback bo'lmagan
        update turlari).
        """
        inner: Optional[TelegramObject] = event
        if isinstance(event, Update):
            kind = event.event_type or ""
            if kind.startswith("business_"):
                return None
            inner = getattr(event, kind, None)

        if isinstance(inner, CallbackQuery):
            return inner
        if isinstance(inner, Message) and not inner.business_connection_id:
            return inner
        return None

    @staticmethod
    async def _deny(event: TelegramObject, user: TgUser) -> None:
        """Ruxsati yo'q foydalanuvchini to'xtatadi.

        Uch holat: (1) bazada yozuvi yo'q — birinchi murojaat, adminga
        tugmali so'rov kartasi yuboriladi; (2) so'rov yuborilgan — kutish
        eslatmasi; (3) rad etilgan yoki banlangan — aniq xabar.

        Adminga xabar va DB yozuvi FAQAT birinchi murojaatda bo'ladi
        (:func:`app.services.access.request_access` takrorlanishni
        to'xtatadi), shuning uchun bu yo'l ham "arzon".
        """
        # Holat `None` (birinchi murojaat) yoki `pending` (javob hali yo'q):
        # adminga karta yuboramiz.  ``request_access`` takrorlanishni o'zi
        # to'xtatadi — karta bir marta ketadi (jarayon qayta ishga tushsa,
        # eslatma sifatida yana bir marta).
        if access.status(user.id) in (None, access.PENDING):
            if await access.request_access(user):
                await access.notify_admin_request(event.bot, user)
        text = access.blocked_notice(user.id)

        try:
            if isinstance(event, CallbackQuery):
                # Alert matni HTML sifatida o'qilmaydi — teglarni olib tashlaymiz.
                await event.answer(strip_html(text), show_alert=True)
            else:
                await event.answer(text)
        except Exception:  # noqa: BLE001 – javob berolmasak ham update yiqilmasin
            logger.exception("Ruxsatsiz javob yuborilmadi (user=%s)", user.id)

    @staticmethod
    def _is_flooding(user_id: int, limit: int = RATE_LIMIT_EVENTS) -> bool:
        # Xotira cheklovi: juda ko'p noyob id to'plansa (spam/attack)
        # eng qadimgi yozuvlarni tashlab qo'yamiz.
        if len(_buckets) > _MAX_BUCKETS:
            oldest = next(iter(_buckets))
            _buckets.pop(oldest, None)
        now = time.monotonic()
        window: list[float] = _buckets.setdefault(user_id, [])
        window[:] = [t for t in window if now - t < RATE_WINDOW]
        window.append(now)
        return len(window) > limit
