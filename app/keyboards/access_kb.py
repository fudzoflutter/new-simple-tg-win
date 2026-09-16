"""
Admin (ega) uchun klaviaturalar — ruxsat berish / rad etish / ban / unban.

Ikki ekran:

* :func:`request_card` – yangi foydalanuvchi so'rovi ustidagi
  «✅ Ruxsat berish / ❌ Rad etish» tugmalari (adminga keladi);
* :func:`users_panel`  – foydalanuvchilar ro'yxati: har bir qator uchun
  bitta amal tugmasi (ban / ruxsat berish / blokdan chiqarish) va sahifalash.

Callback formatlari (Telegram 64 BAYT chegarasidan ancha qisqa)::

    access:allow:<user_id>
    access:deny:<user_id>
    access:ban:<user_id>:<page>
    access:unban:<user_id>:<page>
    user:users:p:<page>
"""

from __future__ import annotations

from typing import Optional, Sequence

from aiogram.types import InlineKeyboardMarkup

from app.keyboards.user_kb import back_btn
from app.utils.ui import BtnStyle, btn, kb

CB_ALLOW = "access:allow"
CB_DENY = "access:deny"
CB_BAN = "access:ban"
CB_UNBAN = "access:unban"
CB_USERS_PAGE = "user:users:p"

# Tugma matni juda uzun bo'lmasin (Telegram 64 belgi bilan cheklaydi).
LABEL_MAX = 18

# Amal -> (belgi, so'z).  Bitta tugma holatga qarab ban YOKI ruxsat berish
# vazifasini bajaradi:
#   ban   – ruxsatli odamni bloklash
#   grant – so'rov kutayotgan / tasdiqlanmagan odamga ruxsat berish
#   unban – banlangan yoki rad etilgan odamni blokdan chiqarish
ACTIONS = {
    "ban": ("🚫", "Ban"),
    "grant": ("✅", "Ruxsat berish"),
    "unban": ("✅", "Blokdan chiqarish"),
}


def short_label(
    username: Optional[str], first_name: Optional[str], user_id: int
) -> str:
    """Ro'yxat/tugma uchun qisqa ism (bo'sh bo'lsa — ID)."""
    name = (first_name or "").strip() or (f"@{username}" if username else str(user_id))
    if len(name) > LABEL_MAX:
        name = name[: LABEL_MAX - 1] + "…"
    return name


def request_card(user_id: int) -> InlineKeyboardMarkup:
    """Yangi foydalanuvchi so'rovi: ruxsat berish yoki rad etish."""
    return kb(
        [
            [
                btn("✅ Ruxsat berish", f"{CB_ALLOW}:{user_id}", style=BtnStyle.SUCCESS),
                btn("❌ Rad etish", f"{CB_DENY}:{user_id}", style=BtnStyle.DANGER),
            ]
        ]
    )


def empty() -> InlineKeyboardMarkup:
    """Bo'sh markup — qaror qabul qilingach tugmalarni olib tashlash uchun."""
    return kb([])


def users_panel(
    rows: Sequence[tuple[int, str, str]],
    page: int,
    pages: int,
) -> InlineKeyboardMarkup:
    """Foydalanuvchilar ro'yxati.

    ``rows`` – ``(user_id, label, action)`` uchliklari; ``action`` —
    ``"ban"`` (ruxsatli), ``"grant"`` (so'rov kutayapti) yoki ``"unban"``
    (banlangan/rad etilgan).
    """
    lines: list[list] = []
    for user_id, label, action in rows:
        icon, word = ACTIONS.get(action, ACTIONS["ban"])
        blocked = action != "ban"
        lines.append(
            [
                btn(
                    f"{icon} {word} · {label} · {user_id}",
                    f"{CB_UNBAN if blocked else CB_BAN}:{user_id}:{page}",
                    style=BtnStyle.SUCCESS if blocked else BtnStyle.DANGER,
                )
            ]
        )

    nav = []
    if page > 1:
        nav.append(btn("⬅️", f"{CB_USERS_PAGE}:{page - 1}", style=BtnStyle.PRIMARY))
    if page < pages:
        nav.append(btn("➡️", f"{CB_USERS_PAGE}:{page + 1}", style=BtnStyle.PRIMARY))
    if nav:
        lines.append(nav)

    lines.append([back_btn()])
    return kb(lines)
