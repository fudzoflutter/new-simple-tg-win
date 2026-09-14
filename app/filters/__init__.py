"""
Custom aiogram filters.

* :class:`IsAdmin` – passes only for the bot owner (``ADMIN_ID`` in .env).
  Extra admins can be promoted at runtime via ``users.is_admin`` in DB.
"""

from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.config import settings
from app.database import db


class IsAdmin(BaseFilter):
    """Owner from .env OR a user flagged as admin in the database."""

    async def __call__(self, event: TelegramObject) -> bool:
        user = getattr(event, "from_user", None)
        if user is None:
            # business_* updates may carry no from_user of our own – deny.
            return False
        if user.id == settings.admin_id:
            return True
        row = await db.get_user(user.id)
        return bool(row and row.get("is_admin"))


def is_owner(user_id: int) -> bool:
    """Quick check without DB access (used in guards)."""
    return user_id == settings.admin_id
