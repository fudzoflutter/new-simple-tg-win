"""
Umumiy vaqt yordamchilari (DB qatlamlari uchun).

Ikkala backend (SQLite va Supabase Postgres) bir xil vaqt formatini
ishlatadi: ISO-8601 TEXT, mahalliy vaqt.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional


def now_iso() -> str:
    """Current local time as ISO string (single place to change format)."""
    return datetime.now().isoformat(timespec="seconds")


def parse_dt(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO timestamp stored in the DB (None-safe)."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
