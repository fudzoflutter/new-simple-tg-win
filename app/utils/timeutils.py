"""
Umumiy vaqt yordamchilari (DB qatlamlari uchun).

Ikkala backend (SQLite va Supabase Postgres) bir xil vaqt formatini
ishlatadi: ISO-8601 TEXT, mahalliy vaqt.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

# "Onlayn" hisobi uchun oyna (sekund) — count_online bilan bir xil qiymat.
ONLINE_WINDOW_SECONDS = 120


def now_iso() -> str:
    """Current local time as ISO string (single place to change format)."""
    return datetime.now().isoformat(timespec="seconds")


def iso_before(seconds: int) -> str:
    """Shu soniya oldingi vaqt (ISO) — DBdagi 'online' chegarasi bilan bir xil."""
    return (datetime.now() - timedelta(seconds=seconds)).isoformat(timespec="seconds")


def is_online(
    last_activity: Optional[str], window_seconds: int = ONLINE_WINDOW_SECONDS
) -> bool:
    """``last_activity`` shu oyna ichidami?

    DB qatlamlari bilan BIR XIL mantiq: ISO-8601 satrlar leksikografik
    taqqoslanadi (format bir xil bo'lgani uchun to'g'ri ishlaydi).  Shu
    tufayli "online" sonini qo'shimcha DB so'rovisiz hisoblash mumkin.
    """
    return bool(last_activity) and str(last_activity) >= iso_before(window_seconds)


def parse_dt(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO timestamp stored in the DB (None-safe)."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
