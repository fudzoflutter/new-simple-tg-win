"""
Foydalanuvchiga qaratilgan inline klaviaturalar (o'zbek tilida).

Har bir klaviatura kichik funksiya — handlerlar toza qoladi.  Ranglar
(``style=``) va premium emoji ikonkalari (``icon_custom_emoji_id``)
:func:`app.utils.ui.btn` orqali beriladi.

Premium/obuna bo'limlari OLIB TASHLANGAN (yangi talab): menyu faqat
Statistika, Ulanish, Foydalanuvchilar va Havola tozalashdan iborat.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.emoji_config import EMOJI
from app.utils.ui import BtnStyle, btn, kb

# Callback data prefikslari — handlerlar ham shulardan foydalanadi.
CB_STATS = "user:stats"
CB_CONNECT = "user:connect"
CB_USERS = "user:users"
CB_BACK_MENU = "user:menu"


def main_menu(*, connected: bool = False) -> InlineKeyboardMarkup:
    """Start menyusi: Statistika, Ulanish, Foydalanuvchilar, Havola tozalash."""
    connect_label = (
        f"{EMOJI.menu_connect.fallback} Ulangan ✓"
        if connected
        else f"{EMOJI.menu_connect.fallback} Ulanish"
    )
    rows = [
        [
            btn(
                f"{EMOJI.menu_stats.fallback} Statistika",
                CB_STATS,
                style=BtnStyle.PRIMARY,
                emoji_id=EMOJI.menu_stats.emoji_id,
            )
        ],
        [
            btn(
                connect_label,
                CB_CONNECT,
                style=BtnStyle.SUCCESS if connected else BtnStyle.PRIMARY,
                emoji_id=EMOJI.menu_connect.emoji_id,
            )
        ],
        [
            btn(
                f"{EMOJI.users.fallback} Foydalanuvchilar",
                CB_USERS,
                style=BtnStyle.PRIMARY,
            )
        ],
    ]
    return kb(rows)


def back_btn():
    """«Menyuga qaytish» tugmasi — emoji registrydan."""
    return btn(
        f"{EMOJI.menu_back.fallback} Menyuga qaytish",
        CB_BACK_MENU,
        style=BtnStyle.DANGER,
        emoji_id=EMOJI.menu_back.emoji_id,
    )


def connect_menu(bot_username: str = "") -> InlineKeyboardMarkup:
    """«Ulanish» yo'riqnomi ostidagi tugmalar.

    1-qator mijoz sozlamalarini ``tg://settings/edit`` chuqur havolasi
    orqali ochadi — bu faqat Premium/Business emas, balki BARCHA
    foydalanuvchilar uchun ishlaydi.  So'ng yuqoridagi yo'riqnoma
    Business → Chatbotlar bo'limiga olib boradi.

    MUHIM: sozlamalar tugmasi maxsus lug'at (dict) orqali qurilgan —
    aiogram ``InlineKeyboardButton`` url maydonini HTTP(S) deb tekshiradi
    va tg:// havolasini rad etadi, garchi Telegramning o'zi inline tugmada
    tg:// ni qabul qilsa.
    """
    settings_button = {
        "text": f"{EMOJI.menu_settings.fallback} Sozlamalarni ochish",
        "url": "tg://settings/edit",
        "style": BtnStyle.SUCCESS,
    }
    return kb(
        [
            [InlineKeyboardButton(**settings_button)],
            [back_btn()],
        ]
    )


def back_to_menu() -> InlineKeyboardMarkup:
    return kb([[back_btn()]])
