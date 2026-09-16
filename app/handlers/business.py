"""
Business-ulanish handlerlari (3–4-bandlar).

Bot biror foydalanuvchining "Telegram Business → Chatbotlar"iga qo'shilganda:

* ``business_connection``          – ulanish o'rnatildi / uzildi
* ``business_message``             – chatlarida xabar yuborildi
* ``edited_business_message``      – xabar tahrirlandi
* ``deleted_business_messages``    – xabar(lar) o'chirildi

Hisobot QOIDALARI (4-band, yangi talab):

* yuborilgan xabarlar FORVARD qilinmaydi — tarkib jim KESHlanadi;
* matn xabari           -> faqat TAHRIRLANGANDA yoki O'CHIRILGANDA xabar;
* media (rasm/video/GIF/stiker/ovozli xabar/dumaloq video) -> faqat
  O'CHIRILGANDA xabar (fayl qayta yuboriladi);
* hisobot faqat SUHBATDOSH hodisalari uchun — eganing o'z yuborgan/
  tahrirlagan/o'chirgan xabarlari hech qachon hisobot qilib berilmaydi.

Har bir hodisa baribir DBGA eganing nomiga saqlanadi (statistika uchun).
"""

from __future__ import annotations

import logging

from aiogram import Bot, Router
from aiogram.types import (
    BusinessConnection,
    BusinessMessagesDeleted,
    Message,
    User as TgUser,
)

from app.config import settings
from app.database import db
from app.keyboards import user_kb
from app.services import access
from app.services.reporter import Reporter, invalidate_connection
from app.utils import texts

router = Router(name="business")
logger = logging.getLogger(__name__)


def _mention(user: TgUser) -> str:
    """Kichik mahalliy eslatma yordamchisi."""
    from app.utils.formatting import mention_by_id

    name = user.first_name or user.username or str(user.id)
    return mention_by_id(user.id, name, user.username)


# ---------------------------------------------------------------------------
# Ulanish o'rnatildi / uzildi (3-band)
# ---------------------------------------------------------------------------
@router.business_connection()
async def on_connection(connection: BusinessConnection, bot: Bot) -> None:
    """Ulanish, uzilish yoki huquqlar o'zgarganda ishga tushadi."""
    is_enabled = bool(connection.is_enabled)
    user = connection.user

    # Foydalanuvchini ro'yxatga olish (/start bosmagan bo'lishi mumkin).
    await db.upsert_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )
    existed = await db.get_connection(connection.id) is not None
    await db.upsert_connection(
        business_connection_id=connection.id,
        user_id=user.id,
        is_enabled=is_enabled,
        user_chat_id=connection.user_chat_id,
    )
    # Ulanish holati o'zgardi — in-memory keshni yangilaymiz, shunda keyingi
    # business-update'lar DBga qayta murojaat qilmasdan TO'G'RI egasini oladi
    # (app/services/reporter.py dagi _connection_cache).
    invalidate_connection(connection.id)

    # 0) KIRISH NAZORATI: ruxsati yo'q foydalanuvchi biznes-ulanish orqali
    #    ham botdan foydalana olmaydi (hisobot kelmaydi — app/services/access
    #    + reporter._owner_allowed).  Ulanish BAZADA qoladi: admin ruxsat
    #    berishi bilan hisobotlar o'sha zahoti boshlanadi.
    if not access.can_use(user.id):
        if is_enabled:
            # Birinchi murojaatda adminga tugmali karta yuboriladi.
            if await access.request_access(user):
                await access.notify_admin_request(bot, user)
            try:
                await bot.send_message(
                    connection.user_chat_id or user.id,
                    access.blocked_notice(user.id),
                    parse_mode="HTML",
                )
            except Exception:  # noqa: BLE001 – bloklagan bo'lishi mumkin
                logger.info("Ruxsatsiz foydalanuvchiga xabar yuborilmadi: %s", user.id)
        logger.info(
            "Business connection %s: owner=%s ruxsatsiz — hisobot o'chirilgan",
            connection.id,
            user.id,
        )
        return

    # 1) Foydalanuvchining o'ziga xabar (3-band).
    #    ULANGANLIK darhol tasdiqlanadi: birinchi ulanish — "amalga oshdi",
    #    qayta yoqilganlik — "tiklandi", o'chirilganlik — "to'xtatildi".
    #    user_chat_id bo'lmasa (ba'zi Telegram versiyalari yubormaydi) —
    #    foydalanuvchining o'z IDsi ishlatiladi (shaxsiy chat = user_id).
    notify_chat = connection.user_chat_id or user.id
    try:
        if is_enabled:
            text = (
                texts.BUSINESS_ENABLED_AGAIN if existed
                else texts.BUSINESS_CONNECTED
            )
        else:
            text = texts.BUSINESS_DISABLED
        await bot.send_message(notify_chat, text, parse_mode="HTML")
        await bot.send_message(
            notify_chat,
            f"{texts.WELCOME}\n\n{texts.MENU_HINT}",
            reply_markup=user_kb.main_menu(connected=is_enabled),
        )
    except Exception:  # noqa: BLE001 – foydalanuvchi botni bloklagan bo'lishi mumkin
        logger.info("Could not notify user %s about connection change", user.id)

    # 2) Egaga REAL-TIME xabar (xabar mazmuni yo'q — faqat hodisa fakti).
    #    Ulanganda ham, uzilganda ham admin DARHOL biladi (yangi talab).
    state_word = "🔗 ULANDI" if is_enabled else "🔴 UZILDI"
    action_word = "ulandi" if is_enabled else "uzildi"
    detail_word = "faollashtirildi ✅" if is_enabled else "o'chirildi ❌"
    await db.add_event(
        user_id=user.id,
        event_type="connection",
        details=f"{action_word} ({connection.id})",
    )
    try:
        await bot.send_message(
            settings.admin_id,
            f"{state_word} — {_mention(user)} biznes-ulanishi {detail_word}.",
            parse_mode="HTML",
        )
    except Exception:  # noqa: BLE001
        pass
    logger.info(
        "Business connection %s: user=%s enabled=%s", connection.id, user.id, is_enabled
    )


# ---------------------------------------------------------------------------
# Xabar yuborildi (stiker / rasm / video ham shu yerda)
# ---------------------------------------------------------------------------
@router.business_message()
async def on_business_message(message: Message, bot: Bot) -> None:
    """Biznes-ulanish orqali kelgan har qanday xabar — FAQAT keshlanadi.

    Talab: yuborilgan xabarlar (matn, stiker, rasm, video, GIF) egaga
    FORVARD qilinmaydi.  Tarkib jim saqlanadi — keyin o'chirilsa,
    aynan nima o'chirilgani ko'rsatilishi uchun.
    """
    logger.info(
        "business_message: conn=%s chat=%s mid=%s",
        message.business_connection_id,
        message.chat.id if message.chat else None,
        message.message_id,
    )
    await _safe_report(Reporter(bot).report_incoming(message))


# ---------------------------------------------------------------------------
# Xabar tahrirlandi (4-band — aynan namunadagi format)
# ---------------------------------------------------------------------------
@router.edited_business_message()
async def on_edited(message: Message, bot: Bot) -> None:
    """Tahrirlangan xabar -> hisobot faqat SUHBATDOSH matn tahriri uchun.

    Egasining o'z tahrirlari va media (izoh) tahrirlari jim keshlanadi.
    Format: ✏️ sarlavha, 👤 Kim, 📱 Default (eski), 📲 Edited (yangi),
    💬 Chat, 🕒 Vaqt.
    """
    logger.info(
        "edited_business_message: conn=%s chat=%s mid=%s",
        message.business_connection_id,
        message.chat.id if message.chat else None,
        message.message_id,
    )
    await _safe_report(Reporter(bot).report_edited(message))


# ---------------------------------------------------------------------------
# Xabar(lar) o'chirildi (4-band — stiker/media o'chirilishi ham kiradi)
# ---------------------------------------------------------------------------
@router.deleted_business_messages()
async def on_deleted(deleted: BusinessMessagesDeleted, bot: Bot) -> None:
    """O'chirilgan xabarlar -> hisobot faqat SUHBATDOSH xabarlari uchun.

    Matn bo'lsa ASL MATN chiqadi, media bo'lsa keshlangan fayl QAYTA
    YUBORILADI.  Egasining o'z xabarlari va keshda yo'q idlar jim o'tadi.
    """
    logger.info(
        "deleted_business_messages: conn=%s chat=%s ids=%s",
        deleted.business_connection_id,
        deleted.chat.id if deleted.chat else None,
        deleted.message_ids,
    )
    await _safe_report(Reporter(bot).report_deleted(deleted))


async def _safe_report(coro) -> None:
    """Hisobot xatosi botni ishdan chiqarmasligi kerak.

    Aiogram xatoni LOG qiladi lekin 'handled' deb belgilaydi — terminalda
    bir qator warning bilan o'tib ketadi va hech kim sezmagan bo'ladi.
    Bu yordamchi xatolarni to'liq traceback bilan ko'rsatadi.
    """
    try:
        await coro
    except Exception:  # noqa: BLE001 – hisobot xatosi boshqa update'larga ta'sir qilmasin
        logger.exception("Reporter xatosi (hisobot yuborilmadi)")
