"""
Premium emoji constants and inline keyboard factory.

* ``CustomEmoji``     – central place for all custom-emoji IDs (premium
  emojis are referenced by ID, so changing the ID here changes the emoji
  everywhere without touching handler code).
* ``kb``              – small builder helpers so keyboards stay one-liners:
  colored buttons (``style=``) and premium emoji icons
  (``icon_custom_emoji_id=``) are supported natively by aiogram 3.31
  (Bot API 9.4+).

NOTE on premium emojis: a bot can display ``icon_custom_emoji_id`` on its
buttons/messages only if the *bot account itself* has Telegram Premium or
owns a Fragment username; otherwise Telegram silently shows plain text.
Keep IDs here even then — the day you add Premium to the bot account they
start rendering automatically.
"""

from __future__ import annotations

from typing import Optional, Sequence

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    CopyTextButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.emoji_config import EMOJI, tg_e  # noqa: F401  (tg_e — eski importlar uchun)


class CustomEmoji:
    """Tugma ikonkalari — HAMMASI ``app/emoji_config.py`` dan olinadi.

    Emoji IDlarini shu faylda emas, ``emoji_config.py`` da almashtiring:
    bu klass faqat ko'prik (delegation).
    """

    STATS = EMOJI.menu_stats.emoji_id  # 📊 chart
    PREMIUM = EMOJI.menu_premium.emoji_id  # 💎 gem
    CONNECT = EMOJI.menu_connect.emoji_id  # 🔗 link
    ADMIN = EMOJI.btn_users.emoji_id  # 🛡 shield
    HELP = EMOJI.info.emoji_id  # ℹ️ info
    BROADCAST = EMOJI.btn_broadcast.emoji_id  # 📣 megaphone
    BACK = EMOJI.menu_back.emoji_id  # ↩️ back arrow

    # Cheap "icon" fallbacks used inside message *text* (always visible).
    GLYPH_STATS = "📊"
    GLYPH_PREMIUM = "💎"
    GLYPH_CONNECT = "🔗"
    GLYPH_ADMIN = "🛡"
    GLYPH_HELP = "ℹ️"
    GLYPH_BROADCAST = "📣"
    GLYPH_BACK = "🔙"
    GLYPH_OK = "✅"
    GLYPH_FAIL = "❌"
    GLYPH_WARN = "⚠️"
    GLYPH_USER = "👤"
    GLYPH_BAN = "🚫"
    GLYPH_ONLINE = "🟢"
    GLYPH_OFFLINE = "⚪️"
    GLYPH_CARD = "💳"
    GLYPH_MONEY = "💰"
    GLYPH_CLOCK = "🕒"
    GLYPH_EDIT = "✏️"
    GLYPH_TRASH = "🗑"
    GLYPH_STICKER = "🎨"
    GLYPH_PHOTO = "🖼"
    GLYPH_VIDEO = "🎬"
    GLYPH_PLAN = "🗓"


# ---------------------------------------------------------------------------
# Button styles (Bot API 9.4+): 'danger' = red, 'success' = green,
# 'primary' = blue.  Plain buttons (style omitted) use the app default.
# ---------------------------------------------------------------------------
class BtnStyle:
    DANGER = "danger"
    SUCCESS = "success"
    PRIMARY = "primary"


def btn(
    text: str,
    callback_data: Optional[str] = None,
    *,
    url: Optional[str] = None,
    style: Optional[str] = None,
    emoji_id: Optional[str] = None,
    copy_text: Optional[str] = None,
) -> InlineKeyboardButton:
    """Build one inline button with optional color / premium emoji / copy.

    Exactly one *action* is required: callback_data, url or copy_text.
    """
    payload: dict = {"text": text}
    if callback_data:
        payload["callback_data"] = callback_data
    if url:
        payload["url"] = url
    if copy_text:
        payload["copy_text"] = CopyTextButton(text=copy_text)
    if style:
        payload["style"] = style
    if emoji_id:
        payload["icon_custom_emoji_id"] = emoji_id
    return InlineKeyboardButton(**payload)


def kb(rows: Sequence[Sequence[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    """Build an InlineKeyboardMarkup from rows of buttons."""
    return InlineKeyboardMarkup(inline_keyboard=[list(row) for row in rows])


async def edit_or_send(
    message: Message, text: str, reply_markup: InlineKeyboardMarkup | None = None
) -> None:
    """Xabarni joyida tahrirlash; bo'lmasa yangi xabar sifatida yuborish.

    Admin paneli bir xil tugma bosilganda Telegram "message is not
    modified" (400) bilan yiqilardi — paneldagi TUGMALAR eskirgan holatda
    qolardi.  Bu yordamchi:
      * "not modified" -> jim o'tadi (aynan shu ko'rinish ekranda turibdi);
      * "message can't be edited" (eski/servis xabarlar) -> yangi xabar;
      * boshqa Telegram xatolari ham botni ishdan chiqarmaydi.
    """
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "not modified" in str(exc).lower():
            return
        try:
            await message.answer(text, reply_markup=reply_markup)
        except Exception:  # noqa: BLE001 – foydalanuvchi botni bloklagan
            pass
    except Exception:  # noqa: BLE001 – hech qachon handler yiqilmasin
        try:
            await message.answer(text, reply_markup=reply_markup)
        except Exception:  # noqa: BLE001
            pass
