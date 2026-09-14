"""
Foydalanuvchiga qaratilgan inline klaviaturalar (o'zbek tilida).

Har bir klaviatura kichik funksiya — handlerlar toza qoladi.  Ranglar
(``style=``) va premium emoji ikonkalari (``icon_custom_emoji_id``)
:func:`app.utils.ui.btn` orqali beriladi.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.database import Database
from app.utils.texts import plan_button_label
from app.utils.ui import BtnStyle, CustomEmoji, btn, kb

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
    connect_label = "🔗 Ulangan ✓" if connected else "🔗 Ulanish"
    rows = [
        [
            btn(
                "📊 Statistika",
                CB_STATS,
                style=BtnStyle.PRIMARY,
                emoji_id=CustomEmoji.STATS,
            )
        ],
        [
            btn(
                connect_label,
                CB_CONNECT,
                style=BtnStyle.SUCCESS if connected else BtnStyle.PRIMARY,
                emoji_id=CustomEmoji.CONNECT,
            )
        ],
    ]
    if premium_enabled:
        rows.append(
            [
                btn(
                    "💎 Premium",
                    CB_PREMIUM,
                    style=BtnStyle.SUCCESS,
                    emoji_id=CustomEmoji.PREMIUM,
                )
            ]
        )
    # Yangi talab: obuna holatini tekshirish tugmasi (hamma uchun ko'rinadi —
    # bosganda 'faol emas' yoki qolgan vaqt ko'rsatiladi).
    rows.append(
        [
            btn(
                "💎 Mening obunam",
                CB_MY_SUB,
                style=BtnStyle.PRIMARY,
                emoji_id=CustomEmoji.PREMIUM,
            )
        ]
    )
    return kb(rows)


def my_sub_menu() -> InlineKeyboardMarkup:
    """«Mening obunam» ekrani: tariflarga va menyuga qaytish."""
    return kb(
        [
            [btn("💎 Tariflar", CB_PREMIUM, style=BtnStyle.SUCCESS, emoji_id=CustomEmoji.PREMIUM)],
            [btn("🔙 Menyuga qaytish", CB_BACK_MENU, style=BtnStyle.DANGER, emoji_id=CustomEmoji.BACK)],
        ]
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
        "text": "⚙️ Sozlamalarni ochish",
        "url": "tg://settings/edit",
        "style": BtnStyle.SUCCESS,
    }
    return kb(
        [
            [InlineKeyboardButton(**settings_button)],
            [btn("🔙 Menyuga qaytish", CB_BACK_MENU, style=BtnStyle.DANGER, emoji_id=CustomEmoji.BACK)],
        ]
    )


async def premium_plans(db: Database) -> InlineKeyboardMarkup:
    """Har bir faol tarif uchun bitta rangli tugma ('30 kun - 10 000')."""
    plans = await db.active_plans()
    if not plans:
        return kb([[btn("🔙 Menyuga qaytish", CB_BACK_MENU, style=BtnStyle.DANGER)]])

    rows = [
        [
            btn(
                plan_button_label(p["title"], p["duration_days"], p["price"]),
                f"{CB_PLAN}{p['id']}",
                style=BtnStyle.SUCCESS,
                emoji_id=CustomEmoji.PREMIUM,
            )
        ]
        for p in plans
    ]
    rows.append([btn("🔙 Menyuga qaytish", CB_BACK_MENU, style=BtnStyle.DANGER, emoji_id=CustomEmoji.BACK)])
    return kb(rows)


def premium_checkout(plan_id: int) -> InlineKeyboardMarkup:
    """To'lov oynasi: tariflarga va menyuga qaytish (chek — foto sifatida)."""
    return kb(
        [
            [btn("🔙 Tariflarga", CB_PREMIUM, style=BtnStyle.PRIMARY, emoji_id=CustomEmoji.BACK)],
            [btn("🔙 Menyuga qaytish", CB_BACK_MENU, style=BtnStyle.DANGER)],
        ]
    )


def back_to_menu() -> InlineKeyboardMarkup:
    return kb([[btn("🔙 Menyuga qaytish", CB_BACK_MENU, style=BtnStyle.DANGER, emoji_id=CustomEmoji.BACK)]])
