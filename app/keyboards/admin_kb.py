"""
Faqat admin uchun inline klaviaturalar (o'zbek tilida).

Premium tugmasi (2-band) hammaga ko'rinadigan asosiy menyuda, lekin admin
panel (5-band) faqat ``settings.admin_id`` egasiga ochiq — bu
:class:`app.filters.IsAdmin` filtri bilan ta'minlangan.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup

from app.emoji_config import EMOJI
from app.utils.ui import BtnStyle, btn, kb

# Callback prefikslari.
CB_PANEL = "adm:panel"
CB_USERS = "adm:users"
CB_USER = "adm:user:"
CB_USER_BAN = "adm:ban:"
CB_USER_UNBAN = "adm:unban:"
CB_USER_GRANT = "adm:grant:"
CB_USER_PREM_OFF = "adm:premoff:"
CB_ONLINE = "adm:online"
CB_PLANS = "adm:plans"
CB_PLAN_ADD = "adm:plan:add"
CB_PLAN_VIEW = "adm:plan:view:"
CB_PLAN_TOGGLE = "adm:plan:toggle:"
CB_PLAN_DELETE = "adm:plan:del:"
CB_PLAN_EDIT = "adm:plan:edit:"
CB_PAYMENTS = "adm:pays"
CB_PAYMENT = "adm:pay:"
CB_PAYMENT_OK = "adm:pay:ok:"
CB_PAYMENT_NO = "adm:pay:no:"
CB_BROADCAST = "adm:bcast"
CB_BROADCAST_SEND = "adm:bcast:go"
CB_CANCEL = "adm:cancel"
CB_BACK_MENU = "user:menu"  # foydalanuvchi tomoni bilan umumiy

# -- Premium bo'limini yoqish/o'chirish (yangi talab) -------------------------
CB_PREMIUM_TOGGLE = "adm:premium:toggle"

# Foydalanuvchi kartochkasi qo'shimcha boshqaruvi (yangi funksiyalar).
CB_USER_TEXT_VIEW = "adm:text:view:"
CB_USER_TEXT_SET = "adm:text:set:"
CB_USER_TEXT_DEL = "adm:text:del:"
CB_USER_LIMIT = "adm:limit:"

PAGE_SIZE = 5


def panel(
    pending_payments: int = 0,
    premium_enabled: bool = False,
) -> InlineKeyboardMarkup:
    """Admin panel: foydalanuvchilar, onlayn, tariflar, to'lovlar va
    Premium bo'limini yoqish/o'chirish tugmasi."""
    pays_label = f"💳 To'lovlar ({pending_payments})" if pending_payments else "💳 To'lovlar"
    return kb(
        [
            [
                btn(
                    f"{EMOJI.btn_users.fallback} Foydalanuvchilar",
                    CB_USERS,
                    style=BtnStyle.PRIMARY,
                    emoji_id=EMOJI.btn_users.emoji_id,
                ),
                btn(
                    f"{EMOJI.btn_online.fallback} Onlayn",
                    CB_ONLINE,
                    style=BtnStyle.SUCCESS,
                    emoji_id=EMOJI.btn_online.emoji_id,
                ),
            ],
            [
                btn(
                    f"{EMOJI.btn_plans.fallback} Premium tariflar",
                    CB_PLANS,
                    style=BtnStyle.PRIMARY,
                    emoji_id=EMOJI.btn_plans.emoji_id,
                ),
                btn(
                    pays_label,
                    CB_PAYMENTS,
                    style=BtnStyle.SUCCESS,
                    emoji_id=EMOJI.btn_payments.emoji_id,
                ),
            ],
            [
                btn(
                    f"{EMOJI.btn_broadcast.fallback} Ommaviy xabar",
                    CB_BROADCAST,
                    style=BtnStyle.DANGER,
                    emoji_id=EMOJI.btn_broadcast.emoji_id,
                )
            ],
            [
                btn(
                    (
                        f"{EMOJI.btn_premium_toggle.fallback} Premium bo'limi: YOQISH"
                        if not premium_enabled
                        else f"{EMOJI.btn_premium_toggle.fallback} Premium bo'limi: O'CHIRISH"
                    ),
                    CB_PREMIUM_TOGGLE,
                    style=BtnStyle.SUCCESS if not premium_enabled else BtnStyle.DANGER,
                    emoji_id=EMOJI.btn_premium_toggle.emoji_id,
                )
            ],
            [
                btn(
                    f"{EMOJI.menu_back.fallback} Menyuga qaytish",
                    CB_BACK_MENU,
                    style=BtnStyle.DANGER,
                    emoji_id=EMOJI.menu_back.emoji_id,
                )
            ],
        ]
    )


def users_pager(page: int, pages: int, user_rows: list[list] | None = None) -> InlineKeyboardMarkup:
    """Foydalanuvchi tugmalari + ◀️ ▶️ navigatsiya."""
    rows: list = list(user_rows or [])
    nav: list = []
    if page > 1:
        nav.append(btn("◀️", f"{CB_USERS}{page - 1}"))
    nav.append(btn(f"{page}/{pages}", CB_USERS, style=BtnStyle.PRIMARY))
    if page < pages:
        nav.append(btn("▶️", f"{CB_USERS}{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append(
        [btn("🟢 Onlayn", CB_ONLINE, style=BtnStyle.SUCCESS), btn("🔙 Panel", CB_PANEL, style=BtnStyle.DANGER)]
    )
    return kb(rows)


def user_buttons(pairs: list[tuple[str, int]]) -> list[list]:
    """Har bir foydalanuvchi uchun qator-tugma -> kartochka (adm:user:<id>)."""
    return [[btn(label, f"{CB_USER}{user_id}") for label, user_id in [pair]] for pair in pairs]


def user_card(user_id: int, banned: bool, premium_active: bool = False) -> InlineKeyboardMarkup:
    """Profil havolasi + obuna berish/olish + cheklash + qo'shimcha boshqaruv.

    Premium (obuna) faol bo'lsa — foydalanuvchining o'ziga to'liq boshqaruv
    beriladi: saqlangan xabarni ko'rish, almashtirish, o'chirish va kunlik
    limitni o'rnatish/olib tashlash (limit = premiumning teskari tomoni).
    """
    rows = [
        [
            btn(
                "🔗 Profilni ochish",
                url=f"tg://user?id={user_id}",
                style=BtnStyle.PRIMARY,
            )
        ],
        # Yangi talab: DBdagi aynan shu foydalanuvchiga obuna berish.
        [btn("🎁 Obuna berish", f"{CB_USER_GRANT}{user_id}", style=BtnStyle.SUCCESS)],
    ]
    if premium_active:
        rows.append(
            [btn("🗑 Obunani olib qo'yish", f"{CB_USER_PREM_OFF}{user_id}", style=BtnStyle.DANGER)]
        )
    else:
        # Premium YO'Q foydalanuvchiga ishlash hajmini cheklash mumkin
        # ("premium giving gift" teskari tomoni — ishlashni limitlash).
        rows.append(
            [btn("⏳ Kunlik limit o'rnatish", f"{CB_USER_LIMIT}{user_id}", style=BtnStyle.PRIMARY)]
        )
    # Nusxalangan xabar boshqaruvi (har qanday foydalanuvchi uchun mavjud).
    rows.append(
        [
            btn("📝 Nusxa ko'rish", f"{CB_USER_TEXT_VIEW}{user_id}", style=BtnStyle.PRIMARY),
            btn("♻️ Almashtirish", f"{CB_USER_TEXT_SET}{user_id}", style=BtnStyle.SUCCESS),
        ]
    )
    rows.append([btn("🗑 Nusxani o'chirish", f"{CB_USER_TEXT_DEL}{user_id}", style=BtnStyle.DANGER)])
    if banned:
        rows.append([btn("✅ Bandan chiqarish", f"{CB_USER_UNBAN}{user_id}", style=BtnStyle.SUCCESS)])
    else:
        rows.append([btn("⛔️ Cheklash", f"{CB_USER_BAN}{user_id}", style=BtnStyle.DANGER)])
    rows.append([btn("🔙 Ro'yxatga", CB_USERS, style=BtnStyle.DANGER, emoji_id=EMOJI.menu_back.emoji_id)])
    return kb(rows)


def online_list() -> InlineKeyboardMarkup:
    return kb([[btn("🔙 Panel", CB_PANEL, style=BtnStyle.DANGER, emoji_id=EMOJI.menu_back.emoji_id)]])


def plans_menu() -> InlineKeyboardMarkup:
    return kb(
        [
            [btn("➕ Tarif yaratish", CB_PLAN_ADD, style=BtnStyle.SUCCESS, emoji_id=EMOJI.menu_premium.emoji_id)],
            [btn("🔙 Panel", CB_PANEL, style=BtnStyle.DANGER, emoji_id=EMOJI.menu_back.emoji_id)],
        ]
    )


def plans_menu_with(plan_rows: list[list]) -> InlineKeyboardMarkup:
    """Tariflar ro'yxati: har bir tarif NOMI tugma (kartochka ochiladi) + ➕."""
    return kb(
        list(plan_rows)
        + [
            [btn("➕ Tarif yaratish", CB_PLAN_ADD, style=BtnStyle.SUCCESS, emoji_id=EMOJI.menu_premium.emoji_id)],
            [btn("🔙 Panel", CB_PANEL, style=BtnStyle.DANGER, emoji_id=EMOJI.menu_back.emoji_id)],
        ]
    )


def plan_row(plan_id: int) -> InlineKeyboardMarkup:
    """Bitta tarifni boshqarish: tahrirlash, yashirish/ko'rsatish, o'chirish."""
    return kb(
        [
            [btn("✏️ Tahrirlash", f"{CB_PLAN_EDIT}{plan_id}", style=BtnStyle.PRIMARY)],
            [
                btn("👁 Yashirish / ko'rsatish", f"{CB_PLAN_TOGGLE}{plan_id}", style=BtnStyle.PRIMARY),
                btn("🗑 O'chirish", f"{CB_PLAN_DELETE}{plan_id}", style=BtnStyle.DANGER),
            ],
            [btn("🔙 Barcha tariflar", CB_PLANS, style=BtnStyle.DANGER, emoji_id=EMOJI.menu_back.emoji_id)],
        ]
    )


def plan_edit_menu(plan_id: int) -> InlineKeyboardMarkup:
    """Tahrirlash oynasi: nom / davomiylik / narx / tavsif."""
    return kb(
        [
            [btn("✏️ Nom", f"{CB_PLAN_EDIT}{plan_id}:title", style=BtnStyle.PRIMARY),
             btn("🗓 Kun", f"{CB_PLAN_EDIT}{plan_id}:duration", style=BtnStyle.PRIMARY)],
            [btn("💰 Narx", f"{CB_PLAN_EDIT}{plan_id}:price", style=BtnStyle.PRIMARY),
             btn("📝 Tavsif", f"{CB_PLAN_EDIT}{plan_id}:desc", style=BtnStyle.PRIMARY)],
            [btn("🔙 Tarifga", f"{CB_PLAN_VIEW}{plan_id}", style=BtnStyle.SUCCESS)],
            [btn("🔙 Barcha tariflar", CB_PLANS, style=BtnStyle.DANGER, emoji_id=EMOJI.menu_back.emoji_id)],
        ]
    )


def plan_delete_confirm(plan_id: int) -> InlineKeyboardMarkup:
    return kb(
        [
            [
                btn("✅ Ha, o'chirish", f"{CB_PLAN_DELETE}{plan_id}:confirm", style=BtnStyle.DANGER),
                btn("❌ Bekor qilish", CB_PLANS, style=BtnStyle.PRIMARY),
            ]
        ]
    )


def payments_menu() -> InlineKeyboardMarkup:
    return kb([[btn("🔙 Panel", CB_PANEL, style=BtnStyle.DANGER, emoji_id=EMOJI.menu_back.emoji_id)]])


def payment_decision(payment_id: int) -> InlineKeyboardMarkup:
    """Chek ostidagi Tasdiqlash / Rad etish tugmalari."""
    return kb(
        [
            [
                btn("✅ Tasdiqlash", f"{CB_PAYMENT_OK}{payment_id}", style=BtnStyle.SUCCESS),
                btn("❌ Rad etish", f"{CB_PAYMENT_NO}{payment_id}", style=BtnStyle.DANGER),
            ]
        ]
    )


def broadcast_confirm() -> InlineKeyboardMarkup:
    return kb(
        [
            [
                btn("🚀 Hammaga yuborish", CB_BROADCAST_SEND, style=BtnStyle.DANGER),
                btn("❌ Bekor qilish", CB_BROADCAST, style=BtnStyle.PRIMARY),
            ]
        ]
    )


def cancel_to_panel() -> InlineKeyboardMarkup:
    return kb([[btn("🔙 Bekor qilish", CB_CANCEL, style=BtnStyle.DANGER, emoji_id=EMOJI.menu_back.emoji_id)]])


def user_text_view(user_id: int, has_text: bool) -> InlineKeyboardMarkup:
    """Saqlangan xabar ko'rish ekrani: almashtirish / o'chirish / orqaga."""
    rows = [
        [btn("♻️ Almashtirish", f"{CB_USER_TEXT_SET}{user_id}", style=BtnStyle.SUCCESS)],
    ]
    if has_text:
        rows.append(
            [btn("🗑 Nusxani o'chirish", f"{CB_USER_TEXT_DEL}{user_id}", style=BtnStyle.DANGER)]
        )
    rows.append([btn("🔙 Kartochkaga", f"{CB_USER}{user_id}", style=BtnStyle.DANGER, emoji_id=EMOJI.menu_back.emoji_id)])
    return kb(rows)


def cancel_to_user_card(user_id: int) -> InlineKeyboardMarkup:
    """FSM so'rovlarini bekor qilib foydalanuvchi kartochkasiga qaytish."""
    return kb([[btn("🔙 Bekor qilish", f"{CB_USER}{user_id}", style=BtnStyle.DANGER, emoji_id=EMOJI.menu_back.emoji_id)]])
