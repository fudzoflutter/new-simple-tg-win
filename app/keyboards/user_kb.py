"""
Foydalanuvchiga qaratilgan inline klaviaturalar (o'zbek tilida).

Har bir klaviatura kichik funksiya — handlerlar toza qoladi.  Ranglar
(``style=``) va premium emoji ikonkalari (``icon_custom_emoji_id``)
:func:`app.utils.ui.btn` orqali beriladi.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.emoji_config import EMOJI
from app.utils.texts import plan_button_label
from app.utils.ui import BtnStyle, btn, kb

# Callback data prefikslari — handlerlar ham shulardan foydalanadi.
CB_STATS = "user:stats"
CB_CONNECT = "user:connect"
CB_PREMIUM = "user:premium"
CB_MY_SUB = "user:mysub"
CB_PLAN = "user:plan:"
CB_BACK_MENU = "user:menu"


def main_menu(*, connected: bool = False, premium_enabled: bool = False) -> InlineKeyboardMarkup:
    """Start menyusi: Statistika, Ulanish, (ixtiyoriy) Premium.

    Premium tugmasi standartda YASHIRIN (yangi talab) — admin paneldagi
    "Premium bo'limi" tugmasi orqali yoqilgandagina ko'rinadi.
    """
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
    ]
    if premium_enabled:
        rows.append(
            [
                btn(
                    f"{EMOJI.menu_premium.fallback} Premium",
                    CB_PREMIUM,
                    style=BtnStyle.SUCCESS,
                    emoji_id=EMOJI.menu_premium.emoji_id,
                )
            ]
        )
    # Yangi talab: obuna holatini tekshirish tugmasi (hamma uchun ko'rinadi —
    # bosganda 'faol emas' yoki qolgan vaqt ko'rsatiladi).
    rows.append(
        [
            btn(
                f"{EMOJI.menu_my_sub.fallback} Mening obunam",
                CB_MY_SUB,
                style=BtnStyle.PRIMARY,
                emoji_id=EMOJI.menu_my_sub.emoji_id,
            )
        ]
    )
    return kb(rows)


def my_sub_menu() -> InlineKeyboardMarkup:
    """«Mening obunam» ekrani: tariflarga va menyuga qaytish."""
    return kb(
        [
            [btn(
                f"{EMOJI.menu_premium.fallback} Tariflar",
                CB_PREMIUM,
                style=BtnStyle.SUCCESS,
                emoji_id=EMOJI.menu_premium.emoji_id,
            )],
            [_back_btn()],
        ]
    )


def _back_btn():
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
            [_back_btn()],
        ]
    )


def premium_plans(plans: list[dict]) -> InlineKeyboardMarkup:
    """Har bir faol tarif uchun bitta rangli tugma ('30 kun - 10 000').

    Tariflar RO'YXATI sifatida beriladi (DBdan oldin o'qilgan) — handler
    boshqa so'rov bilan parallel oladi, ikki marta so'ramaydi.
    """
    if not plans:
        return kb([[btn("🔙 Menyuga qaytish", CB_BACK_MENU, style=BtnStyle.DANGER)]])

    rows = [
        [
            btn(
                plan_button_label(p["title"], p["duration_days"], p["price"]),
                f"{CB_PLAN}{p['id']}",
                style=BtnStyle.SUCCESS,
                emoji_id=EMOJI.menu_premium.emoji_id,
            )
        ]
        for p in plans
    ]
    rows.append([_back_btn()])
    return kb(rows)


def premium_checkout(plan_id: int) -> InlineKeyboardMarkup:
    """To'lov oynasi: tariflarga va menyuga qaytish (chek — foto sifatida)."""
    return kb(
        [
            [btn(
                f"{EMOJI.menu_back.fallback} Tariflarga",
                CB_PREMIUM,
                style=BtnStyle.PRIMARY,
                emoji_id=EMOJI.menu_back.emoji_id,
            )],
            [_back_btn()],
        ]
    )


def back_to_menu() -> InlineKeyboardMarkup:
    return kb([[_back_btn()]])
