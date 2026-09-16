"""
Hisobot xizmati (4-band — yangilangan talab).

Telegram business-update'larini ulanish egasining O'Z botiga yuboriladigan
xabarga aylantiradi.  Qoidalar QAT'IY:

* yuborilgan xabarlar FORVARD QILINMAYDI — tarkib jim KESHlanadi (DBda);
* matn xabari           -> faqat TAHRIRLANGANDA yoki O'CHIRILGANDA xabar;
* media (rasm/video/GIF/stiker/ovozli xabar/dumaloq video) -> faqat
  O'CHIRILGANDA xabar (keshlangan fayl qayta yuboriladi);
* hisobot faqat SUHBATDOSH hodisalari uchun: eganing o'z yuborgan/
  tahrirlagan/o'chirgan xabarlari hech qachon hisobot qilib berilmaydi.

Tahrirlash hisoboti namunadagi ko'rinishda:

    ✏️ Message edited

    👤 Who: @username
    📱 Default: eski matn
    📲 Edited: yangi matn
    💬 Chat: Alijon
    🕒 Time: 23:08:54

Har bir xabar DBda BITTA yozuv bilan saqlanadi: tahrirlashda yozuv JOYIDA
yangilanadi (update_event_details) — shu sababli keyingi o'chirish hisoboti
doim ENG OXIRGI tarkibni beradi.

Shaxsiylik: hisobotlar faqat ulanish EGASIGA boradi (admin emas!).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import (
    BusinessMessagesDeleted,
    Chat,
    Message,
    User as TgUser,
)

from app.config import settings
from app.database import db
from app.services import access


# Hisobotlardagi vaqtlar: Toshkent (UTC+5) vaqtida, server soatiga
# bog'liq bo'lmagan holda (app/utils/timeutils.py — bitta joyda sozlanadi).
from app.utils.formatting import esc, mention_by_id
from app.utils.texts import (
    NO_TEXT,
    REPORT_DELETED_MEDIA,
    REPORT_DELETED_MEDIA_CAPTION,
    REPORT_DELETED_TEXT,
    REPORT_EDIT,
    REPORT_FOOTER,
    REPORT_FOOTER_DELETED,
    REPORT_UNCACHED,
    TRUNCATED,
    UNKNOWN_CHAT,
    WHO_UNKNOWN,
)
from app.utils.timeutils import hms, now_report

logger = logging.getLogger(__name__)

# Hisobot xabarida ko'rsatiladigan matn chegarasi (DBda TO'LIQ saqlanadi).
MAX_TEXT = 350
MAX_TITLE = 64
MAX_BULK_DELETES = 10  # bir vaqtda o'chirilgan xabarlar ustidagi cheklov

# Keshda topilmagan o'chirishlar haqida ogohlantirish oralig'i (sekund).
# Bunday holat jimgina o'tkazib yuborilardi — foydalanuvchi "ovoz/dumaloq video
# kelmadi" deb ko'rardi, sababi esa ko'rinmasdi.  Endi 15 daqiqada ko'pi bilan
# bir marta xabar beriladi (shovqin qilmasligi uchun).
UNCACHED_WARNING_INTERVAL = 900
_last_uncached_warning = 0.0

# ---------------------------------------------------------------------------
# Hodisa turlari (DB qiymatlari)
# ---------------------------------------------------------------------------
EVENT_EDIT = "edit"
EVENT_DELETE = "delete"
EVENT_DELETE_MEDIA = "delete_media"
EVENT_STICKER = "sticker"
EVENT_PHOTO = "photo"
EVENT_VIDEO = "video"
EVENT_ANIMATION = "animation"  # GIF
EVENT_VOICE = "voice"          # ovozli xabar
EVENT_VIDEO_NOTE = "video_note"  # dumaloq (circular) video
EVENT_TEXT = "text"

KIND_LABELS = {
    EVENT_STICKER: "Sticker",
    EVENT_PHOTO: "Photo",
    EVENT_VIDEO: "Video",
    EVENT_ANIMATION: "GIF",
    EVENT_VOICE: "Voice",
    EVENT_VIDEO_NOTE: "Video note",
    EVENT_TEXT: "Message",
}

MEDIA_EVENTS = frozenset(
    {
        EVENT_STICKER,
        EVENT_PHOTO,
        EVENT_VIDEO,
        EVENT_ANIMATION,
        EVENT_VOICE,
        EVENT_VIDEO_NOTE,
    }
)


# ---------------------------------------------------------------------------
# Ulanish keshi (protsess ichida) — TEZLIK uchun.
#
# Har bir business-update'da `db.get_connection` chaqirish Supabase ustida
# ~200 ms turadi, holbuki ulanish FAQAT `business_connection` hodisasida
# o'zgaradi.  Shuning uchun faol ulanishning (owner_id, owner_chat) juftini
# eslab qolamiz va o'sha hodisada tozalaymiz:
#   app.handlers.business.on_connection -> invalidate_connection(...)
#
# TTL — ehtiyot chorasi: hodisa o'tkazib yuborilsa ham eski holat abadiy
# qolmaydi.  Uzilgan/yo'q ulanish KESHLANMAYDI: u keyingi update'da baribir
# qayta o'qiladi.
# ---------------------------------------------------------------------------
_CONNECTION_TTL_SECONDS = 300.0

# business_connection_id -> (monotonic vaqt, owner_id, owner_chat)
_connection_cache: dict[str, tuple[float, int, Optional[int]]] = {}


def invalidate_connection(connection_id: Optional[str] = None) -> None:
    """Ulanish keshini tozalash.

    * ``connection_id`` berilgan bo'lsa — faqat shu yozuv o'chiriladi
      (ulan / uz / ruxsat o'zgardi hodisasida chaqiriladi).
    * ``None`` bo'lsa — butun kesh tozalanadi (restart / testlar uchun).

    Shundan keyingi birinchi update DBdan YANGI holatni o'qiydi.
    """
    if connection_id is None:
        _connection_cache.clear()
    else:
        _connection_cache.pop(connection_id, None)


# ---------------------------------------------------------------------------
# TEZKOR KESH (xotira) — "darhol o'chirish" muammosining yechimi.
#
# aiogram update'larni PARALLEL bajaradi (handle_as_tasks=True): har bir
# update uchun alohida task ochiladi.  Supabase ~1.2 s uzoqda bo'lgani uchun
# xabarni keshlash (INSERT) tugagunicha bir necha sekund o'tadi.  Agar
# suhbatdosh xabarni YUBORIB DARHOL o'chirsa, o'chirish yangilamasi kesh
# yozuvidan OLDIN tekshiriladi va xabar "keshda yo'q" bo'lib tuyuladi —
# hisobot JIM o'tib ketadi (ovozli xabar / dumaloq video / rasm...).
#
# Shu sababli mazmun HECH QANDAY await'siz, xabarni qabul qilishning ENG
# BIRINCHI qadamida xotiradagi lug'atga yoziladi.  O'chirish hisoboti
# shu yozuvdan foydalanadi — DB yozuvi esa odatdagidek (statistika va
# qayta ishga tushishdan keyin ham ishlashi uchun) fonda davom etadi.
#
# Xotira chegaralangan: eng eski yozuvlar chiqib ketadi (DB — asosiy kesh).
# ---------------------------------------------------------------------------
INSTANT_CACHE_MAX = 5_000

# (chat_id, message_id) -> {event_type, details, sender_id, chat_title}
_instant_cache: dict[tuple[int, int], dict] = {}


def remember(
    chat_id: Optional[int],
    message_id: Optional[int],
    event_type: str,
    details: str,
    *,
    sender_id: Optional[int] = None,
    chat_title: str = UNKNOWN_CHAT,
) -> None:
    """Xabar mazmunini XOTIRAGA DARHOL yozadi (await YO'Q, I/O YO'Q).

    Bu funksiya ataylab sinxron: chaqiruvchi handler'ning birinchi qadamida
    ishlaydi, shuning uchun tez o'chirilgan xabar ham hisobotdan qolmaydi.
    """
    if not chat_id or not message_id:
        return
    key = (int(chat_id), int(message_id))
    # Qayta yozilsa — eng oxiriga o'tadi (FIFO chegarasi to'g'ri ishlashi uchun).
    _instant_cache.pop(key, None)
    _instant_cache[key] = {
        "event_type": event_type,
        "details": details,
        "sender_id": sender_id,
        "chat_title": chat_title,
    }
    while len(_instant_cache) > INSTANT_CACHE_MAX:
        oldest = next(iter(_instant_cache))
        _instant_cache.pop(oldest, None)


def recall(chat_id: Optional[int], message_id: Optional[int]) -> Optional[dict]:
    """Xotiradagi keshlan mazmun (topilmasa ``None``)."""
    if not chat_id or not message_id:
        return None
    return _instant_cache.get((int(chat_id), int(message_id)))


def clear_instant_cache() -> None:
    """Tezkor keshni tozalash (testlar / qayta yuklash uchun)."""
    _instant_cache.clear()


class Reporter:
    """Faoliyat hisobotlarini ULANISH EGASIGA yetkazadi (qoidalar yuqorida)."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self._owner_id: Optional[int] = None
        self._owner_chat: Optional[int] = None

    # ------------------------------------------------------------------ API

    async def report_incoming(self, message: Message) -> None:
        """business_message — hisobot YO'Q, tarkib faqat KESHlanadi.

        Talab: har bir yuborilgan xabar (matn, stiker, rasm, video, GIF,
        ovozli xabar, dumaloq video) jim saqlanadi — keyin o'chirilsa,
        aynan nima o'chirilgani ko'rsatilishi uchun.
        """
        # 1) ENG BIRINCHI QADAM, AWAIT'SIZ: mazmunni xotiraga yozamiz.
        #    Sabab: aiogram update'larni parallel bajaradi — suhbatdosh
        #    xabarni yuborib DARHOL o'chirsa, o'chirish yangilamasi shu
        #    funksiyaning DB yozuvidan (~1.2 s) OLDIN ishlanadi.  Xotiradagi
        #    yozuv tufayli hisobot baribir to'g'ri chiqadi.
        event_type, details = self._content_of(message)
        remember(
            message.chat.id if message.chat else None,
            message.message_id,
            event_type,
            details,
            sender_id=message.from_user.id if message.from_user else None,
            chat_title=self._chat_name(message),
        )

        # 2) DBga (asosiy kesh) yozish — statistika va restart uchun.
        owner_id = await self._activate(message.business_connection_id)
        if owner_id is None:
            return
        await self._store(message, event_type, details)

    async def report_edited(self, message: Message) -> None:
        """edited_business_message — faqat suhbatdosh MATN tahriri haqida.

        * Egasining o'z tahriri           -> jim (kesh yangilanadi).
        * Media tahriri (izoh o'zgarishi) -> jim (kesh yangilanadi) — media
          haqida faqat O'CHIRILGANDA xabar beriladi.
        * Suhbatdosh matn tahriri         -> ✏️ hisobot (📱 Default → 📲 Edited).
        """
        owner_id = await self._activate(message.business_connection_id)
        if owner_id is None:
            return

        chat_id = message.chat.id if message.chat else 0
        stored = await db.get_event_by_message(chat_id, message.message_id)
        # Xotiradagi tezkor kesh ham manba bo'la oladi (yozuv hali bazaga
        # tushmagan bo'lsa — "darhol tahrirlash" holati).
        record = stored or recall(chat_id, message.message_id)
        # ESKI mazmun SHU YERDA o'qib olinadi: quyida kesh yangilanadi.
        old_text = (
            self._plain_content(record.get("details") or "") if record else NO_TEXT
        )
        is_media = self._has_media(message)

        # 1) Keshni har doim yangilaymiz — keyingi o'chirish hisoboti shunga
        #    tayanadi (media izohining o'zgarishi ham shu yerda qamrab olinadi).
        if is_media:
            event_type, file_id, caption = self._current_media(message)
            if event_type and file_id:
                details = self._media_details(file_id, event_type, caption)
                if stored:
                    await db.update_event_details(
                        chat_id, message.message_id, details
                    )
                else:
                    await self._store(message, event_type, details)
        else:
            fresh = message.text or message.caption or NO_TEXT
            if stored:
                await db.update_event_details(chat_id, message.message_id, fresh)
            else:
                await self._store(message, EVENT_TEXT, fresh)

        # Statistika yozuvi (DB uchun — hisobot EMAS).
        await self._store_stat(
            message, EVENT_EDIT,
            f"edited: {(message.text or message.caption or 'media')[:120]}",
        )

        # 2) Hisobot — faqat suhbatdoshning MATN tahriri.
        sender = message.from_user
        if is_media or sender is None or sender.id == owner_id:
            return
        new_text = message.text or message.caption or NO_TEXT
        body = REPORT_EDIT.format(
            who=self._who_from_user(sender),
            old=self._clip(old_text),
            new=self._clip(new_text),
        )
        await self._send(
            self._owner_chat, body + self._footer(self._chat_name(message))
        )

    async def _warn_uncached(
        self, chat_title: str, missed: list[int], deleted_hms: str
    ) -> None:
        """Keshda topilmagan o'chirishlar haqida ogohlantiradi (15 daqiqada 1).

        Bu holatda hisobot UMUMAN chiqmaydi — jim qolsa, foydalanuvchi
        "ovoz/dumaloq video qaytmadi" deb ko'radi, sababi esa ko'rinmaydi.
        Shuning uchun sabab aytiladi: xabarni boshqa nusxa (eski build) qabul
        qilgan yoki xabar bot ishga tushishidan oldin yuborilgan.
        """
        global _last_uncached_warning
        if not missed or not self._owner_chat:
            return
        now = time.monotonic()
        if _last_uncached_warning and now - _last_uncached_warning < UNCACHED_WARNING_INTERVAL:
            return  # shovqin qilmaymiz
        _last_uncached_warning = now
        await self._send(
            self._owner_chat,
            REPORT_UNCACHED.format(
                chat=esc(chat_title),
                ids=", ".join(str(m) for m in missed[:MAX_BULK_DELETES]),
                count=len(missed),
                time=deleted_hms,
            ),
        )

    async def report_deleted(self, deleted: BusinessMessagesDeleted) -> None:
        """deleted_business_messages — suhbatdosh NIMA o'chirganini ko'rsatish.

        Har bir o'chirilgan xabar uchun:
        * matn bo'lsa   -> to'liq ASL MATN chiqariladi;
        * media bo'lsa  -> keshlangan fayl QAYTA YUBORILADI;
        * eganing o'z xabari yoki keshda yo'q id — JIM o'tkazib yuboriladi.
        """
        # O'CHIRILISH VAQTI — BITTA MARTA, update kelgan ZAHOTI olinadi.
        #
        # Telegram "deleted_business_messages" yangilamasini darhol yuboradi
        # va unda vaqt maydoni YO'Q (business_connection_id, chat, message_ids
        # — tamom).  Shuning uchun eng aniq manba — shu update qabul qilingan
        # payt.  Uni quyidagi DB so'rovlaridan OLDIN o'lchaymiz (ular Supabase
        # bilan ~1-3 sekund olishi mumkin) va butun hisobot uchun ishlatamiz:
        # sarlavha, media izohi va "Chat/Vaqt" qatori — hammasi AYNAN bir
        # vaqtni ko'rsatadi (sekin fayl yuklash ham uni surib ketmaydi).
        deleted_hms = hms(now_report())

        owner_id = await self._activate(deleted.business_connection_id)
        if owner_id is None:
            return

        chat = deleted.chat
        chat_id = chat.id if chat else 0
        chat_title = self._chat_title_of(chat)

        missed: list[int] = []
        for mid in deleted.message_ids[:MAX_BULK_DELETES]:
            stored = await db.get_event_by_message(chat_id, mid)
            # Baza yozuvi hali tugamagan bo'lsa (tez o'chirish) — xotiradagi
            # tezkor keshlga tayanamiz; aks holda xabar "keshda yo'q" bo'lib
            # ko'rinib, hisobot umuman kelmasdi.
            record = stored or recall(chat_id, mid)

            if not record:
                # Keshda yo'q: BOSHQA nusxa qabul qilgan yoki xabar bot ishga
                # tushishidan oldin yuborilgan.  Bu JIM o'tkazib yuborilmaydi:
                # aks holda "ovoz/dumaloq video kelmadi" ning sababi ko'rinmaydi.
                logger.warning(
                    "Delete skipped: message %s is not cached (chat=%s)",
                    mid,
                    chat_id,
                )
                missed.append(mid)
                continue
            sender_id = record.get("sender_id")
            # Eganing o'z xabari yoki admin o'chirgan istalgan xabar — hisobot YO'Q
            if sender_id and (int(sender_id) == owner_id or int(sender_id) == settings.admin_id):
                continue  # hisobot YO'Q (talab)

            event_type = record.get("event_type") or EVENT_TEXT
            details = record.get("details") or ""
            label = KIND_LABELS.get(event_type, KIND_LABELS[EVENT_TEXT])
            who = await self._who_for_delete(chat, record)

            if event_type == EVENT_TEXT:
                # 1) MATN: to'liq asl matn ko'rsatiladi.
                body = REPORT_DELETED_TEXT.format(
                    who=who, original=self._clip(self._plain_content(details))
                )
                await self._send(
                    self._owner_chat,
                    body + self._footer(chat_title, deleted_at=deleted_hms),
                )
            elif event_type in MEDIA_EVENTS:
                # 2) MEDIA: keshlangan faylni QAYTA YUBORAMIZ.
                sent_ok = False
                file_id = self._extract_file_id(details)
                if file_id:
                    sent_ok = await self._resend_media(
                        self._owner_chat, event_type, file_id,
                        header=REPORT_DELETED_MEDIA_CAPTION.format(
                            kind=label, who=who
                        ),
                        chat_title=chat_title,
                        caption=self._media_caption(details),
                        deleted_at=deleted_hms,
                    )
                if not sent_ok:
                    body = REPORT_DELETED_MEDIA.format(kind=label, who=who, mid=mid)
                    await self._send(
                        self._owner_chat,
                        body + self._footer(chat_title, deleted_at=deleted_hms),
                    )
            else:
                continue

            # Statistika yozuvi (DB uchun — hisobot EMAS).
            await db.add_event(
                user_id=owner_id,
                event_type=(
                    EVENT_DELETE_MEDIA if event_type in MEDIA_EVENTS else EVENT_DELETE
                ),
                details=f"deleted {label.lower()}: {details[:100]}",
                chat_id=chat.id if chat else None,
                chat_title=chat_title,
                message_id=None,  # asl yozuvni "soyabon" qilmasin
            )

        # Keshda topilmagan id bo'lsa — bir marta ogohlantiramiz.
        await self._warn_uncached(chat_title, missed, deleted_hms)

    # ------------------------------------------------------------ internals

    async def _activate(self, connection_id: Optional[str]) -> Optional[int]:
        """Ulanishni tekshiradi va egasini keshlaydi.

        Ulanish faol bo'lsa — eganing user_id qaytariladi (hisobot manzili
        ham keshlanadi).  Aks holda None: na kesh, na hisobot.  Har bir
        'yo'q' sababi LOG qilinadi.

        Natija PROTSESS bo'ylab (_connection_cache) eslab qolinadi — bir xil
        ulanish uchun DBga qayta murojaat qilinmaydi.  Kesh faqat
        ``invalidate_connection`` (business_connection hodisasi) yoki TTL
        orqali yangilanadi.
        """
        if not connection_id:
            logger.warning("Reporter: business_connection_id bo'sh — update o'tdi")
            return None

        # 1) Kesh: shu ulanish yaqinda o'qilgan bo'lsa DBga bormaymiz.
        now = time.monotonic()
        cached = _connection_cache.get(connection_id)
        if cached is not None and now - cached[0] < _CONNECTION_TTL_SECONDS:
            self._owner_id = cached[1]
            self._owner_chat = cached[2]
            return self._owner_id if self._owner_allowed(self._owner_id) else None

        # 2) Keshda yo'q (yoki TTL o'tdi) — DBdan o'qiymiz.
        conn = await db.get_connection(connection_id)
        if not conn:
            logger.warning("Reporter: ulanish DBda topilmadi (%s)", connection_id)
            return None
        if not conn.get("is_enabled"):
            logger.info("Reporter: ulanish o'chirilgan (%s)", connection_id)
            return None
        self._owner_id = int(conn["user_id"])
        chat_id = conn.get("user_chat_id") or conn.get("user_id")
        self._owner_chat = int(chat_id) if chat_id else None
        if not self._owner_allowed(self._owner_id):
            return None
        # Faqat FAOL ulanish keshlanadi — uzilgani qayta o'qiladi.
        _connection_cache[connection_id] = (now, self._owner_id, self._owner_chat)
        return self._owner_id

    @staticmethod
    def _owner_allowed(owner_id: Optional[int]) -> bool:
        """Ega bloklangan bo'lsa hisobot yo'q (ruxsat / ban — access keshida).

        Tekshiruv SOF SINXRON (xotiradagi lug'at), shuning uchun
        business-update'ga qo'shimcha DB so'rovi qo'shilmaydi.  Bloklangan
        ulanish KESHLANMAYDI — ban olib tashlanishi bilan darhol tiklanadi.
        """
        if owner_id is None or not access.is_blocked(owner_id):
            return True
        logger.info("Reporter: ega %s ruxsatsiz — hisobot o'tkazib yuborildi", owner_id)
        return False

    # -- tarkib kesh formati -----------------------------------------------
    # matn :  to'liq matn (escape QILINMAGAN xom holda)
    # media:  "file:<file_id>|<event_type>|<caption>"

    @staticmethod
    def _media_details(
        file_id: str, event_type: str, caption: Optional[str] = None
    ) -> str:
        return f"file:{file_id}|{event_type}|{caption or ''}"

    @staticmethod
    def _extract_file_id(details: str) -> Optional[str]:
        """'file:<id>|...' dan file_id ni oladi."""
        if details.startswith("file:"):
            payload = details[5:]
            return payload.split("|", 1)[0] or None
        return None

    @staticmethod
    def _media_caption(details: str) -> Optional[str]:
        """Keshlangan media izohi (caption) — 3-qism bo'lsa."""
        parts = details.split("|", 2)
        if len(parts) == 3 and parts[2]:
            return parts[2]
        return None

    @staticmethod
    def _plain_content(details: str) -> str:
        """Matn yozuvidan xom matnni oladi (escape holda emas)."""
        return details

    def _content_of(self, message: Message) -> tuple[str, str]:
        """Xabar TURI va keshlanadigan mazmuni (SOF SINXRON — await yo'q).

        * media -> ``("photo", "file:<file_id>|photo|<izoh>")`` va h.k.
        * matn  -> ``("text", "<asl matn>")``

        Tartib ``report_incoming`` bilan bir xil: stiker, GIF, rasm, video,
        ovozli xabar, dumaloq video, keyin matn.
        """
        if message.sticker:
            return EVENT_STICKER, self._media_details(
                message.sticker.file_id, EVENT_STICKER
            )
        if message.animation:  # GIF
            return EVENT_ANIMATION, self._media_details(
                message.animation.file_id, EVENT_ANIMATION, message.caption
            )
        if message.photo:
            return EVENT_PHOTO, self._media_details(
                message.photo[-1].file_id, EVENT_PHOTO, message.caption
            )
        if message.video:
            return EVENT_VIDEO, self._media_details(
                message.video.file_id, EVENT_VIDEO, message.caption
            )
        if message.voice:
            return EVENT_VOICE, self._media_details(
                message.voice.file_id, EVENT_VOICE, message.caption
            )
        if message.video_note:  # dumaloq (circular) video
            return EVENT_VIDEO_NOTE, self._media_details(
                message.video_note.file_id, EVENT_VIDEO_NOTE
            )
        return EVENT_TEXT, (message.text or message.caption or NO_TEXT)

    @staticmethod
    def _has_media(message: Message) -> bool:
        return bool(
            message.sticker
            or message.animation
            or message.photo
            or message.video
            or message.voice
            or message.video_note
        )

    def _current_media(
        self, message: Message
    ) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """Tahrirlangan xabardagi joriy media -> (tur, file_id, izoh)."""
        if message.sticker:
            return EVENT_STICKER, message.sticker.file_id, None
        if message.animation:
            return (
                EVENT_ANIMATION,
                message.animation.file_id,
                message.caption,
            )
        if message.photo:
            return EVENT_PHOTO, message.photo[-1].file_id, message.caption
        if message.video:
            return EVENT_VIDEO, message.video.file_id, message.caption
        if message.voice:
            return EVENT_VOICE, message.voice.file_id, message.caption
        if message.video_note:
            return EVENT_VIDEO_NOTE, message.video_note.file_id, None
        return None, None, None

    # -- "Kim" va chat nomlari ------------------------------------------------

    def _who_from_user(self, user: TgUser) -> str:
        """Hisobotdagi 'Who' — USERNAME ustun: @username, bo'lmasa ism."""
        if user is None:
            return WHO_UNKNOWN
        if user.username:
            return f"@{user.username}"
        name = user.first_name or str(user.id)
        return mention_by_id(user.id, name)

    async def _who_for_delete(self, chat: Optional[Chat], stored: dict) -> str:
        """O'chirilgan xabar KIMniki — username afzal ko'riladi.

        Suhbatdoshlar bot bilan /start qilmaydi, shuning uchun ular users
        jadvalida bo'lmasligi mumkin — unda chat ma'lumotidan foydalanamiz.
        """
        sender_id = stored.get("sender_id")
        if sender_id:
            user = await db.get_user(int(sender_id))
            if user:
                username = user.get("username")
                if username:
                    return f"@{username}"
                name = user.get("first_name") or str(sender_id)
                return mention_by_id(int(sender_id), name, username)
        if chat is not None and chat.type == "private" and chat.username:
            return f"@{chat.username}"
        if chat is not None:
            raw = chat.first_name or chat.title
            if raw:
                return esc(raw[:MAX_TITLE])
        title = stored.get("chat_title")
        if title:
            return esc(title[:MAX_TITLE])
        return WHO_UNKNOWN

    @staticmethod
    def _chat_title_of(chat: Optional[Chat]) -> str:
        if chat is None:
            return UNKNOWN_CHAT
        raw = chat.title or chat.first_name or chat.username
        return esc(raw[:MAX_TITLE]) if raw else UNKNOWN_CHAT

    @staticmethod
    def _chat_name(message: Message) -> str:
        if message.chat is None:
            return UNKNOWN_CHAT
        title = message.chat.title or message.chat.first_name or message.chat.username
        return esc(title[:MAX_TITLE]) if title else UNKNOWN_CHAT

    # -- yuborish ------------------------------------------------------------

    def _footer(self, chat_title: str, *, deleted_at: Optional[str] = None) -> str:
        """Hisobot oxiridagi "Chat + Vaqt" qatori.

        ``deleted_at`` berilgan bo'lsa — qator O'CHIRILGAN vaqtni ko'rsatadi
        (o'chirish hisoboti uchun).  Aks holda hozirgi vaqt (tahrirlash
        hisoboti).  Ikkalasi ham Toshkent (UTC+5) vaqtida.
        """
        if deleted_at is not None:
            return REPORT_FOOTER_DELETED.format(chat=chat_title, time=deleted_at)
        return REPORT_FOOTER.format(chat=chat_title, time=hms(now_report()))

    async def _resend_media(
        self,
        chat_id: Optional[int],
        event_type: str,
        file_id: str,
        *,
        header: str,
        chat_title: str,
        caption: Optional[str] = None,
        deleted_at: Optional[str] = None,
    ) -> bool:
        """Saqlangan media faylni qayta yuborish (o'chirilganda).

        header — sarlavha ("🗑 Photo deleted" + Kim).  ``deleted_at`` —
        o'chirilish vaqti (``HH:MM:SS``, Toshkent); u izoh oxiridagi
        "Chat/Vaqt" qatoriga qo'yiladi.  Muvaffaqiyatsiz bo'lsa False
        qaytaradi — chaqiruvchi matnli zaxira variant yuboradi.
        """
        if chat_id is None:
            return False
        cap = self._apply_gap(header)
        if caption:
            cap += f"\n💬 Caption: {self._clip(caption)}"
        cap += self._footer(chat_title, deleted_at=deleted_at)

        try:
            if event_type == EVENT_STICKER:
                await self.bot.send_sticker(chat_id, sticker=file_id)
                # Stikerlarga caption yozib bo'lmaydi — izoh alohida ketadi.
                await self._send(chat_id, cap)
            elif event_type == EVENT_PHOTO:
                await self.bot.send_photo(
                    chat_id, photo=file_id, caption=cap, parse_mode="HTML"
                )
            elif event_type == EVENT_VIDEO:
                await self.bot.send_video(
                    chat_id, video=file_id, caption=cap, parse_mode="HTML"
                )
            elif event_type == EVENT_ANIMATION:
                await self.bot.send_animation(
                    chat_id, animation=file_id, caption=cap, parse_mode="HTML"
                )
            elif event_type == EVENT_VOICE:
                await self.bot.send_voice(
                    chat_id, voice=file_id, caption=cap, parse_mode="HTML"
                )
            elif event_type == EVENT_VIDEO_NOTE:
                # Dumaloq videoga caption yozib bo'lmaydi — izoh alohida ketadi.
                await self.bot.send_video_note(chat_id, video_note=file_id)
                await self._send(chat_id, cap)
            else:
                return False
            return True
        except Exception:  # noqa: BLE001 – fayl muddati tugagan bo'lishi mumkin
            logger.info("Resend of cached media failed (type=%s)", event_type)
            return False

    @staticmethod
    def _apply_gap(html: str) -> str:
        """Sarlavha bilan asosiy qatorlar ORASIDAGI masofani sozlaydi.

        Har bir hisobot shabloni sarlavhadan keyin aynan bitta "\n\n"
        (bitta bo'sh qator) bilan boshlanadi — birinchi uchraganni
        ``settings.report_line_gap`` ta bo'sh qatorga almashtiramiz:
            1 -> hozirgi ko'rinish, 0 -> yopiq, 2 -> kengroq.
        """
        gap_count = max(0, int(settings.report_line_gap))
        return html.replace("\n\n", "\n" * (gap_count + 1), 1)

    async def _send(self, chat_id: Optional[int], html: str) -> None:
        if chat_id is None:
            logger.warning("Reporter: hisobot manzili yo'q — yuborilmadi")
            return
        html = self._apply_gap(html)
        for attempt in (1, 2):
            try:
                await self.bot.send_message(
                    chat_id, html, parse_mode="HTML", disable_web_page_preview=True
                )
                return
            except TelegramRetryAfter as exc:
                # 429: Telegram aytgan vaqticha kutib BIR martta qayta urinamiz.
                if attempt == 2:
                    break
                await asyncio.sleep(exc.retry_after + 1)
            except Exception:  # noqa: BLE001
                logger.info("Could not deliver report to chat %s", chat_id)
                return
        logger.info("Could not deliver report to chat %s (flood)", chat_id)

    # -- DB yozuvlari ----------------------------------------------------------

    async def _store(
        self, message: Message, event_type: str, details: str
    ) -> None:
        """Xabar yozuvini KESHlash (chat_id + message_id + sender_id bilan).

        sender_id — aynan kim yubordi (ega yoki suhbatdosh): o'chirilganda
        egasining o'z xabarini JIM o'tkazib yuborish uchun kerak.
        """
        await db.add_event(
            user_id=self._owner_id or 0,
            event_type=event_type,
            details=details,
            chat_id=message.chat.id if message.chat else None,
            chat_title=self._chat_name(message),
            message_id=message.message_id,
            sender_id=message.from_user.id if message.from_user else None,
        )
        # Tezkor keshni ham bir xil holatga keltiramiz (manba bitta bo'lsin).
        remember(
            message.chat.id if message.chat else None,
            message.message_id,
            event_type,
            details,
            sender_id=message.from_user.id if message.from_user else None,
            chat_title=self._chat_name(message),
        )

    async def _store_stat(
        self, message: Message, event_type: str, details: str
    ) -> None:
        """Faqat statistika yozuvi (message_id YO'Q — keshni soyabon qilmasin)."""
        await db.add_event(
            user_id=self._owner_id or 0,
            event_type=event_type,
            details=details,
            chat_id=message.chat.id if message.chat else None,
            chat_title=self._chat_name(message),
            message_id=None,
            sender_id=message.from_user.id if message.from_user else None,
        )

    # ---------------------------------------------------------- kichik util

    @staticmethod
    def _clip(text: str) -> str:
        text = esc(text)
        if len(text) <= MAX_TEXT:
            return text
        return text[:MAX_TEXT] + TRUNCATED
