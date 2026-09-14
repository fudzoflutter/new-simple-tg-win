"""
Application entrypoint / wiring.

Reads top-to-bottom to understand how the bot is assembled:

1. config + logging + database
2. middlewares (registration, ban guard)
3. routers (business first, then admin-filtered, then user)
4. long polling + background watchdog
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import ensure_configured, settings
from app.database import db
from app.filters import IsAdmin
from app.handlers import (
    admin_broadcast,
    admin_panel,
    admin_payments,
    admin_plans,
    business,
    user,
)
from app.middlewares import AccessGuardMiddleware, RegisterUserMiddleware
from app.services.watchdog import run_watchdog
from app.utils.logger import setup_logging

logger = logging.getLogger(__name__)


def _friendly_setup_errors(func):
    """Translate raw driver errors into clear setup instructions."""
    import asyncpg
    from aiogram.exceptions import (
        TelegramConflictError,
        TelegramNetworkError,
        TelegramUnauthorizedError,
    )

    async def wrapper():
        try:
            await func()
        except TelegramConflictError:
            logger.error(
                "BOT ALLAQACHON ISHLAB TURIBDI (409 Conflict).\n"
                "Boshqa terminal/VS Code oynasida run.py ochiq bo'lishi mumkin.\n"
                "O'sha oynani yoping (yoki Ctrl+C) va faqat BITTA nusxani ishga tushiring."
            )
            raise
        except TelegramUnauthorizedError:
            logger.error(
                "BOT_TOKEN rejected by Telegram (401 Unauthorized).\n"
                "Check .env: the token must be the CURRENT one from @BotFather "
                "(if you ever revoked it, the old one stops working)."
            )
            raise
        except TelegramNetworkError:
            logger.error(
                "Internet/Telegram aloqasi yo'q (network error).\n"
                "Ulanishni tekshirib, qaytadan ishga tushiring."
            )
            raise
        except (RuntimeError, asyncpg.InvalidPasswordError, OSError) as exc:
            logger.error("Setup problem: %s", exc)
            raise

    return wrapper


async def _drain_pending_updates(bot: Bot) -> None:
    """Ishga tushishdan oldin TO'PLANIB QOLGAN update'larni bir marta ko'rish.

    Bot o'chirik turib foydalanuvchi /start bosgan yoki biznes-botni
    ULANGAN bo'lsa — Telegram bu update'larni saqlab qo'yadi. Ular shu
    funksiyada bir marta o'qilib, TASDIQLANADI (offset yuboriladi) — shu
    tariqa keyingi start_polling ularni qayta yubormaydi.

    Nega shunday: drop_pending_updates=True ularni O'QMASDAN o'chirardi —
    natijada 1) 'ulanish established' xabari chiqmasdi, 2) /start so'rovi
    admin panelga tushmasdi (ikki real xato shu sababli bo'lgan).
    """
    from aiogram.exceptions import TelegramConflictError

    try:
        drained: set[int] = set()
        for _ in range(20):  # xavfsizlik cheklovi
            updates = await bot.get_updates(offset=0, timeout=0)
            if not updates:
                break
            drained.update(u.update_id for u in updates)
            # Oxirgi partiyani tasdiqlash (offset = eng katta id + 1).
            await bot.get_updates(offset=max(drained) + 1, timeout=0)
        if drained:
            logger.info(
                "Bot o'chirik bo'lgan davrda %d ta update to'plangan bo'lib, "
                "ular endi qayta yuborilmaydi (so'rovlar panelda ko'rinadi).",
                len(drained),
            )
    except TelegramConflictError:
        logger.warning("Boshqa nusxa polling qilmoqda — drain o'tkazib yuborildi")


async def _watchdog_supervisor() -> None:
    """run_watchdog ni doim yashab turadi (o'lsa 30 s dan keyin tiklaydi)."""
    while True:
        try:
            await run_watchdog()
        except asyncio.CancelledError:
            raise  # o'chirish signali — qayta boshlamaymiz
        except Exception:  # noqa: BLE001 – watchdog hech qachon o'lib qolmasin
            logger.exception("Watchdog task crashed - restarting in 30s")
            await asyncio.sleep(30)


@_friendly_setup_errors
async def main() -> None:
    """Build and run the bot; runs until cancelled."""
    setup_logging()
    ensure_configured()
    await db.init()

    bot = Bot(
        token=settings.bot_token,
        # HTML everywhere by default – handlers can simply include tags.
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # --- middlewares (run for every update, in this order) ------------------
    # 1) RegisterUser: foydalanuvchini DBga yozadi (yangi so'rov = 'pending')
    # 2) AccessGuard:  ban + kirish tasdiqlash tekshiruvi (yangi talab)
    dp.update.outer_middleware(RegisterUserMiddleware())
    dp.update.outer_middleware(AccessGuardMiddleware())

    # --- routers -------------------------------------------------------------
    # 1) business_* updates: connection notices + activity reports.
    dp.include_router(business.router)

    # 2) admin-only screens; IsAdmin gates every handler in these routers.
    #    Checked first so a normal user can never trigger admin callbacks.
    admin_routers = [
        admin_broadcast.router,  # FSM: broadcast post must win over receipts
        admin_panel.router,
        admin_plans.router,
        admin_payments.router,
    ]
    for router in admin_routers:
        router.message.filter(IsAdmin())
        router.callback_query.filter(IsAdmin())
        dp.include_router(router)

    # 3) everything else (regular users) goes last.
    dp.include_router(user.router)

    # --- background jobs ------------------------------------------------------
    # Superevizor: watchdog faqat NOTO'G'RI kod tufayli o'lsa ham
    # (cancel/shutdown bundan mustasno) 30 sekunddan keyin qayta
    # ishga tushadi — bazani tozalovchi vazifa hech qachon "o'lik"
    # bo'lib qolmaydi.
    watchdog_task = asyncio.create_task(_watchdog_supervisor())

    # --- run ------------------------------------------------------------------
    logger.info("Bot is starting (admin=%s)...", settings.admin_id)
    try:
        await bot.delete_webhook(drop_pending_updates=False)
        await _drain_pending_updates(bot)
        await dp.start_polling(bot)
    finally:
        watchdog_task.cancel()
        await db.close()
        await bot.session.close()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
