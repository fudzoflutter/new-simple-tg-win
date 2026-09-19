"""
Application entrypoint / wiring.

Reads top-to-bottom to understand how the bot is assembled:

1. config + logging + database + access cache
2. middlewares (access check + registration)
3. routers (business, admin, then user)
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
from app.handlers import admin, business, user
from app.middlewares import RegisterUserMiddleware
from app.services import access, instance_lock
from app.services.duplicate_watch import install as watch_duplicate_polling
from app.services.watchdog import run_watchdog
from app.utils import texts
from app.utils.logger import setup_logging
from app.utils.tasks import drain

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
                "ular endi qayta yuborilmaydi (so'rovlar shu yerda ko'rinadi).",
                len(drained),
            )
    except TelegramConflictError:
        logger.warning("Boshqa nusxa polling qilmoqda — drain o'tkazib yuborildi")


async def _notify_duplicate_poller(bot: Bot, total: int) -> None:
    """409 Conflict — botni boshqa nusxa ham poll qilyapti (jimgina qolmasin).

    Bu xabar eng muhim diagnostika: aiogram 409 xatosini o'zi yutib qo'yadi,
    ya'ni bot "ishlayapti" ko'rinadi-yu, update'larning bir qismi BOSHQA
    nusxaga ketadi va ba'zi hisobotlar umuman kelmaydi.
    """
    logger.error(
        "409 CONFLICT: botni boshqa nusxa ham poll qilmoqda (jami %s ta) — "
        "update'lar ikki nusxa orasida bo'linib ketmoqda!",
        total,
    )
    try:
        await bot.send_message(
            settings.admin_id,
            texts.DUPLICATE_POLLER.format(count=total),
            parse_mode="HTML",
        )
    except Exception:  # noqa: BLE001 – ogohlantirish yuborilmasa ham davom
        logger.info("409 ogohlantirishini yuborib bo'lmadi (admin chat?)")


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

    # Kirish nazorati keshini BIR MARTA yuklaymiz: shundan keyin har bir
    # update'dagi ruxsat tekshiruvi xotiradan (dict) o'qiladi — DB so'rovisiz.
    await access.load()

    # --- BIR NUSXA QULFI ------------------------------------------------------
    # Telegram bitta tokenga faqat BITTA getUpdates beradi: ikki nusxa birga
    # ishlasa update'lar bo'linib ketadi (ba'zi hisobotlar kelmaydi).
    # Shuning uchun ikkinchi nusxa polling boshlamaydi va sababini aytadi.
    holder = await instance_lock.acquire()
    if holder is not None:
        logger.error(instance_lock.duplicate_start_message(holder))
        await db.close()
        return
    bot = Bot(
        token=settings.bot_token,
        # HTML everywhere by default – handlers can simply include tags.
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # --- middlewares (run for every update) ---------------------------------
    # RegisterUser: foydalanuvchini DBga yozadi + faollikni yangilaydi.
    dp.update.outer_middleware(RegisterUserMiddleware())

    # --- routers -------------------------------------------------------------
    # 1) business_* updates: connection notices + activity reports.
    dp.include_router(business.router)

    # 2) admin panel: ruxsat berish / rad etish / ban / unban (faqat ega).
    dp.include_router(admin.router)

    # 3) regular users (menyu, statistika, havola tozalash) go last.
    dp.include_router(user.router)

    # --- background jobs ------------------------------------------------------
    # Superevizor: watchdog faqat NOTO'G'RI kod tufayli o'lsa ham
    # (cancel/shutdown bundan mustasno) 30 sekunddan keyin qayta
    # ishga tushadi — bazani tozalovchi vazifa hech qachon "o'lik"
    # bo'lib qolmaydi.
    watchdog_task = asyncio.create_task(_watchdog_supervisor())

    # Qulf boshqa nusxaga (masalan YANGI deployga) o'tsa, eski nusxa
    # pollingni to'xtatishi SHART — aks holda ikki nusxa birga update
    # o'qib, 409 Conflict boshlanadi va xabarlar bo'linib ketadi.
    async def _on_lock_lost() -> None:
        try:
            await dp.stop_polling()
        except RuntimeError:
            pass  # polling hali boshlanmagan bo'lsa — to'xtatadigan narsa yo'q

    # Bir nusxa qulfining heartbeat'i: 20 sekundda bitta yengil UPDATE.
    lock_task = asyncio.create_task(
        instance_lock.heartbeat_loop(on_lost=_on_lock_lost)
    )

    # 409 (boshqa nusxa polling qilmoqda) bo'lsa adminga ANIQ xabar yuboriladi
    # — aks holda muammo jimgina davom etadi va faqat "ba'zi hisobot
    # kelmayapti" ko'rinishida seziladi.
    watch_duplicate_polling(
        lambda total: _notify_duplicate_poller(bot, total)
    )

    # --- run ------------------------------------------------------------------
    logger.info("Bot is starting (admin=%s)...", settings.admin_id)
    try:
        await bot.delete_webhook(drop_pending_updates=False)
        await _drain_pending_updates(bot)
        await dp.start_polling(bot)
    finally:
        watchdog_task.cancel()
        lock_task.cancel()
        # Fonda ketayotgan yozuvlar (masalan ro'yxatga olish) tugasin —
        # aks holda baza yopilgach ular xato beradi.
        await drain()
        # Qulfni bo'shatamiz: keyingi start darhol ishga tushadi (aks holda
        # qulf STALE_SECONDS gacha "band" bo'lib turadi).
        await instance_lock.release()
        await db.close()
        await bot.session.close()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
