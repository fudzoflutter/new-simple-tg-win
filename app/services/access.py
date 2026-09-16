"""
Kirish nazorati: ruxsat berish / rad etish / ban (yangi talab).

QANDAY ISHLAYDI
---------------
* Har bir foydalanuvchining holati protsess XOTIRASIDA (``_statuses``
  lug'ati) turadi va bot ishga tushishida DBdan BIR MARTA (``load()``)
  o'qiladi.
* :func:`can_use` — SOF SINXRON dict lookup: hech qanday ``await``, DB
  so'rovi yoki tarmoq yo'q.  Shu sababli nazorat bot TEZLIGIGA ta'sir
  qilmaydi (update'ga qo'shimcha ~1 mikrosekund).
* DBga yozish faqat 2 holatda bo'ladi: (1) admin tugma bosganda,
  (2) yangi foydalanuvchi birinchi marta ruxsat so'raganda.

HOLATLAR
--------
======= ====================================================
pending admin javobini kutmoqda (so'rov yuborilgan)
allowed botdan foydalanishga ruxsat berilgan
denied  so'rov rad etilgan
banned  banlangan
======= ====================================================

Ochiq rejimda (``TEST_MODE=0``) yozuvi yo'q foydalanuvchi DARHOL ruxsat
oladi — buning uchun bazaga hech narsa yozilmaydi.  ``TEST_MODE=1`` da esa
u avval admin tasdiqidan o'tadi: eski "faqat admin" eshigi endi yumshoq —
yangi odam bloklanmaydi, balki ruxsat SO'RAYDI.
"""

from __future__ import annotations

import logging
from typing import Optional

from aiogram import Bot
from aiogram.types import User as TgUser

from app.config import settings
from app.database import db
from app.emoji_config import EMOJI

logger = logging.getLogger(__name__)

# -- holatlar ---------------------------------------------------------------
PENDING = "pending"
ALLOWED = "allowed"
DENIED = "denied"
BANNED = "banned"

# -- protsess ichidagi kesh -------------------------------------------------
# MUHIM: faqat event loop ichidan o'zgartiriladi (sinxron, await yo'q).
_statuses: dict[int, str] = {}
# Adminga so'rov kartasi yuborilgan foydalanuvchilar (takror yubormaslik uchun).
_notified: set[int] = set()
# Xotira himoyasi: juda ko'p yozuv to'planib qolmasin.
_MAX_CACHE = 100_000


# ---------------------------------------------------------------------------
# SINXRON TEKSHIRUV — hot path (I/O YO'Q)
# ---------------------------------------------------------------------------
def is_admin(user_id: int) -> bool:
    """Ega (admin) HAR DOIM ruxsatli."""
    return user_id == settings.admin_id


def status(user_id: int) -> Optional[str]:
    """Keshdagi holat (yozuv bo'lmasa ``None``)."""
    return _statuses.get(user_id)


def can_use(user_id: int) -> bool:
    """Foydalanuvchi botdan foydalana oladimi?  (SINXRON — I/O yo'q.)

    * admin                      -> True
    * yozuvi bor                 -> faqat ``allowed``
    * yozuvi yo'q + ochiq rejim  -> True  (bot hamma uchun ochiq)
    * yozuvi yo'q + TEST rejim   -> False (avval ruxsat so'raydi)
    """
    if is_admin(user_id):
        return True
    current = _statuses.get(user_id)
    if current is None:
        return not settings.test_mode
    return current == ALLOWED


def is_blocked(user_id: int) -> bool:
    """Aniq bloklangan odam (tasdiq kutilmoqda / rad etilgan / banlangan).

    HISOBOT YO'LI (business-update) uchun: yozuvi YO'Q foydalanuvchi
    bloklanmaydi — ochiq rejimda bu oddiy holat.  To'g'ridan-to'g'ri
    xabarlar esa :func:`can_use` bilan tekshiriladi (TEST rejimida
    tasdiq talab qiladi).
    """
    if is_admin(user_id):
        return False
    current = _statuses.get(user_id)
    return current is not None and current != ALLOWED


def blocked_notice(user_id: int) -> str:
    """Ruxsati yo'q odamga ko'rsatiladigan matn (HTML, holatga qarab)."""
    from app.utils import texts

    current = _statuses.get(user_id)
    if current == BANNED:
        return texts.ACCESS_BANNED
    if current == DENIED:
        return texts.ACCESS_DENIED
    return texts.ACCESS_PENDING


def badge(user_id: int) -> str:
    """Ro'yxat uchun qisqa holat belgisi (emoji registrydan)."""
    if is_admin(user_id):
        return EMOJI.access_admin.tag
    current = _statuses.get(user_id)
    if current is None:
        return (
            EMOJI.access_pending.tag if settings.test_mode else EMOJI.access_allowed.tag
        )
    return {
        PENDING: EMOJI.access_pending.tag,
        ALLOWED: EMOJI.access_allowed.tag,
        DENIED: EMOJI.access_rejected.tag,
        BANNED: EMOJI.access_banned.tag,
    }.get(current, EMOJI.access_pending.tag)




# ---------------------------------------------------------------------------
# Kesh bilan ishlash
# ---------------------------------------------------------------------------
def _remember(user_id: int, value: str) -> None:
    if user_id not in _statuses and len(_statuses) >= _MAX_CACHE:
        _statuses.pop(next(iter(_statuses)), None)
    _statuses[user_id] = value


async def load() -> int:
    """DBdagi barcha yozuvlarni keshga o'qiydi (startup'da bir marta).

    Shu bittalab so'rovdan keyin update'lar keshdan o'qiydi.
    """
    rows = await db.access_rows()
    _statuses.clear()
    for row in rows:
        value = str(row.get("status") or "")
        if value:
            _remember(int(row["user_id"]), value)
    logger.info("Kirish keshi yuklandi: %d ta yozuv", len(_statuses))
    return len(_statuses)


async def set_status(
    user_id: int,
    new_status: str,
    *,
    decided_by: Optional[int] = None,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
) -> None:
    """Keshni DARHOL yangilaydi, so'ng DBga yozadi.

    Kesh birinchi yangilanadi: admin bosgan tugma shu zahoti ishlaydi va
    baza sekin (Supabase uzoqda) bo'lsa ham tezlik tushmaydi.  Yozib
    bo'lmasa — holat qayta ishga tushgunga qadar keshda qoladi (log yoziladi).
    """
    _remember(user_id, new_status)
    if decided_by is not None:
        # Qaror qabul qilindi — keyingi so'rov yangi karta bo'lishi mumkin.
        _notified.discard(user_id)
    try:
        await db.set_access(
            user_id,
            new_status,
            username=username,
            first_name=first_name,
            decided_by=decided_by,
        )
    except Exception:  # noqa: BLE001 – baza xatosi botni to'xtatmasin
        logger.exception("Kirish holati saqlanmadi: user=%s status=%s", user_id, new_status)


async def request_access(user: TgUser) -> bool:
    """Yangi foydalanuvchi uchun ``pending`` yozuv yaratadi.

    Qaytaradi: ``True`` — bu BIRINCHI so'rov (adminga karta yuborilishi
    kerak), ``False`` — so'rov allaqachon yuborilgan (takrorlamaymiz).
    """
    if user.id in _notified:
        return False
    _notified.add(user.id)  # await'gacha belgilaymiz: parallel update'lar takrorlanmasin
    if _statuses.get(user.id) != PENDING:
        await set_status(user.id, PENDING, username=user.username, first_name=user.first_name)
    return True


# ---------------------------------------------------------------------------
# Xabarnomalar
# ---------------------------------------------------------------------------
async def notify_admin_request(bot: Bot, user: TgUser) -> bool:
    """Adminga «Ruxsat berish / Rad etish» tugmalari bilan karta yuboradi."""
    from app.keyboards import access_kb
    from app.utils import texts
    from app.utils.formatting import mention_by_id

    try:
        await bot.send_message(
            settings.admin_id,
            texts.ACCESS_REQUEST_ADMIN.format(
                who=mention_by_id(user.id, user.first_name or "User", user.username),
                user_id=user.id,
                username=f"@{user.username}" if user.username else "—",
            ),
            reply_markup=access_kb.request_card(user.id),
        )
        return True
    except Exception:  # noqa: BLE001 – admin botni bloklagan bo'lishi mumkin
        logger.exception("Admin uchun so'rov kartasi yuborilmadi")
        # Karta yetib bormadi — keyingi murojaatda yana urinib ko'ramiz.
        _notified.discard(user.id)
        return False


async def notify_user(bot: Bot, user_id: int, text: str, *, with_menu: bool = False) -> bool:
    """Foydalanuvchiga qaror haqida xabar beradi.

    Foydalanuvchi botni bloklagan bo'lsa jim o'tadi (xato ko'tarmaydi).
    """
    from app.keyboards import user_kb
    from app.utils import texts

    try:
        await bot.send_message(user_id, text, parse_mode="HTML")
        if with_menu:
            await bot.send_message(
                user_id,
                f"{texts.WELCOME}\n\n{texts.MENU_HINT}",
                reply_markup=user_kb.main_menu(),
                parse_mode="HTML",
            )
        return True
    except Exception:  # noqa: BLE001
        logger.info("Foydalanuvchiga xabar yuborilmadi (user=%s)", user_id)
        return False
