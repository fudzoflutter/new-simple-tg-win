"""
Central configuration for the whole bot.

Every tunable value lives here (or in ``.env``) so that you never have to dig
through handler files to change something.  ``settings`` is created once at
import time and validated immediately: if something is missing the bot tells
you exactly what instead of failing later in a random handler.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load secret keys BEFORE reading the values below.
BASE_DIR = Path(__file__).resolve().parent.parent
# Ikki manba, BIR XIL format (KEY=VALUE):
#   env.txt  – foydalanuvchi kalitlari (BOT_TOKEN, ADMIN_ID, SUPABASE_DB_URL...)
#   .env     – zaxira/klassik fayl
# dotenv mavjud kalitlarni BOSIB YOZMAYDI, shuning uchun BIRINCHI o'qilgan
# fayl g'alaba qiladi.  env.txt birinchi turadi — yaqinda to'ldirilgan
# qiymatlar eskirgan .env qiymatlarini teskari bosib olmaydi.
load_dotenv(BASE_DIR / "env.txt")
load_dotenv(BASE_DIR / ".env")


def _env(key: str, default: str = "") -> str:
    """Small helper so the dataclass below stays readable."""
    import os

    return os.getenv(key, default).strip()


def _env_int(key: str, default: int) -> int:
    """Read an integer from the environment, falling back to `default`."""
    import os

    raw = os.getenv(key, "").strip()
    return int(raw) if raw.isdigit() else default


@dataclass(frozen=True)
class Settings:
    """Immutable snapshot of all configuration values."""

    # --- Telegram -----------------------------------------------------------
    bot_token: str = field(default_factory=lambda: _env("BOT_TOKEN"))
    admin_id: int = field(default_factory=lambda: _env_int("ADMIN_ID", 0))

    # --- Storage ------------------------------------------------------------
    db_path: str = field(default_factory=lambda: _env("DB_PATH", "bot.db"))

    # --- Supabase Postgres (primary storage) --------------------------------
    # .env dagi SUPABASE_DB_URL - Supabase Dashboard -> Connect ->
    # "Connection pooling" URI (postgresql://postgres.xxxx:...:6543/postgres).
    supabase_db_url: str = field(default_factory=lambda: _env("SUPABASE_DB_URL"))

    # --- Payments (shown on the premium checkout screen) ---------------------
    # Edit these directly here, no .env needed.
    payment_card_number: str = "4728 8700 0481 4561"
    payment_card_holder: str = "J. N"
    # Optional bank name shown above the card number.

    # --- Premium section visibility (new requirement) -------------------------
    # Premium tugmasi standartda YASHIRIN.  Admin paneldagi "Premium bo'limi"
    # tugmasi orqali yoqiladi.  Bu boshlang'ich qiymat — holat DBda saqlanadi.
    premium_enabled_by_default: bool = False

    # --- Premium emoji IDs ---------------------------------------------------
    # These IDs point to custom (premium) emoji packs.  Replace them with IDs
    # of emojis from packs YOUR bot can use: the bot account must own a
    # Fragment username or have Telegram Premium to display them.  If an
    # invalid/empty ID is used the button simply shows text only.
    emoji_stats: str = field(default_factory=lambda: _env("EMOJI_ID_STATS", "5368324170671202286"))
    emoji_premium: str = field(default_factory=lambda: _env("EMOJI_ID_PREMIUM", "5445585590822480435"))
    emoji_connect: str = field(default_factory=lambda: _env("EMOJI_ID_CONNECT", "5333163668629442693"))
    emoji_admins: str = field(default_factory=lambda: _env("EMOJI_ID_ADMINS", "5455669926782445014"))
    emoji_help: str = field(default_factory=lambda: _env("EMOJI_ID_HELP", "5368324170671202286"))
    emoji_broadcast: str = field(default_factory=lambda: _env("EMOJI_ID_BROADCAST", "5455669926782445014"))
    emoji_back: str = field(default_factory=lambda: _env("EMOJI_ID_BACK", "5445585590822480435"))

    # Premium emoji used INSIDE message texts (statistics screen, reports).
    emoji_user: str = field(default_factory=lambda: _env("EMOJI_ID_USER", "6145672251489391716"))
    emoji_idcard: str = field(default_factory=lambda: _env("EMOJI_ID_IDCARD", "5837071798935492251"))
    emoji_inbox: str = field(default_factory=lambda: _env("EMOJI_ID_INBOX", "5472239203590888751"))
    emoji_edit: str = field(default_factory=lambda: _env("EMOJI_ID_EDIT", "5395444784611480792"))
    emoji_trash: str = field(default_factory=lambda: _env("EMOJI_ID_TRASH", "5445267414562389170"))
    emoji_chat: str = field(default_factory=lambda: _env("EMOJI_ID_CHAT", "5443038326535759644"))
    emoji_clock: str = field(default_factory=lambda: _env("EMOJI_ID_CLOCK", "5787488119490088755"))

    @property
    def supabase_host(self) -> str:
        """Short host name for logs (no password inside)."""
        try:
            from urllib.parse import urlparse

            return urlparse(self.supabase_db_url).hostname or "?"
        except Exception:  # noqa: BLE001
            return "?"

    @property
    def is_configured(self) -> bool:
        """True when required values are present."""
        return bool(self.bot_token) and self.admin_id > 0

    def missing_keys(self) -> list[str]:
        """List of human readable names of required-but-missing settings."""
        missing: list[str] = []
        if not self.bot_token:
            missing.append("BOT_TOKEN")
        if not self.admin_id:
            missing.append("ADMIN_ID")
        return missing


settings = Settings()


def ensure_configured() -> None:
    """Raise a clear error when required .env values are missing."""
    if not settings.is_configured:
        missing = ", ".join(settings.missing_keys())
        raise RuntimeError(
            f"Missing required settings: {missing}. "
            "Copy .env.example to .env and fill them in."
        )
