"""
Text formatting helpers (HTML parse mode).

All user-facing messages are HTML.  Centralising escaping/mention helpers here
keeps handler code short and prevents markup injection from user content.
"""

from __future__ import annotations

import html
from datetime import datetime
from typing import Optional

from aiogram.types import User as TgUser


def esc(value: Optional[str]) -> str:
    """Escape a value for safe inclusion in HTML text."""
    return html.escape(str(value)) if value is not None else ""


def user_mention(user: TgUser) -> str:
    """Clickable mention that works even when the user has no username."""
    name = user.first_name or "User"
    if user.username:
        return f'<a href="https://t.me/{user.username}">{esc(name)}</a>'
    return f'<a href="tg://user?id={user.id}">{esc(name)}</a>'


def mention_by_id(user_id: int, name: str, username: Optional[str] = None) -> str:
    """Mention built from stored DB values (user may be long gone)."""
    label = name or (f"@{username}" if username else str(user_id))
    if username:
        return f'<a href="https://t.me/{username}">{esc(label)}</a>'
    return f'<a href="tg://user?id={user_id}">{esc(label)}</a>'


def strip_html(value: str) -> str:
    """HTML teglarini olib tashlaydi.

    Callback «alert» (``show_alert=True``) matnini HTML sifatida
    o'qimaydi — u yerda teglar ko'rinib qolmasligi uchun ishlatiladi.
    """
    import re

    return re.sub(r"<[^>]+>", "", value or "")


def fmt_time(dt: Optional[datetime]) -> str:
    """Format a datetime as HH:MM:SS (used in report messages)."""
    return dt.strftime("%H:%M:%S") if dt else "--:--:--"


def fmt_date(dt: Optional[datetime]) -> str:
    """Format a datetime as DD.MM.YYYY."""
    return dt.strftime("%d.%m.%Y") if dt else "—"


def fmt_datetime(dt: Optional[datetime]) -> str:
    """Format a datetime as DD.MM.YYYY HH:MM."""
    return dt.strftime("%d.%m.%Y %H:%M") if dt else "—"


def fmt_number(value: int) -> str:
    """1234567 -> '1 234 567' (space as thousands separator)."""
    return f"{value:,}".replace(",", " ")


def days_left(deadline: Optional[datetime]) -> int:
    """Whole days remaining until `deadline` (0 when expired/None)."""
    if deadline is None:
        return 0
    delta = deadline - datetime.now()
    return max(0, delta.days)


def progress_bar(fraction: float, width: int = 10) -> str:
    """Textual loading bar, e.g. '▰▰▰▱▱▱▱▱▱▱'."""
    fraction = min(1.0, max(0.0, fraction))
    filled = round(fraction * width)
    return "▰" * filled + "▱" * (width - filled)
