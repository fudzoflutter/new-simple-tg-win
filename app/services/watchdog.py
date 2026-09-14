"""
Background maintenance task.

A tiny watchdog loop that runs once a day: prunes the events table so the
database never grows forever.  Hook more periodic jobs (expiry warnings,
auto-digests, ...) into :func:`run_watchdog` the same way.
"""

from __future__ import annotations

import asyncio
import logging

from app.database import db

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 24 * 60 * 60  # once a day


async def run_watchdog() -> None:
    """Endless loop with daily housekeeping; cancel on shutdown."""
    while True:
        try:
            await db.prune_events()
            logger.info("Watchdog: events pruned")
        except Exception:  # noqa: BLE001
            logger.exception("Watchdog cycle failed")
        await asyncio.sleep(INTERVAL_SECONDS)
