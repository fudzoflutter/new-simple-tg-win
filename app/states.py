"""
FSM (finite state machine) states.

Each wizard gets its own ``StatesGroup`` so dialogs never mix.  Add a new
state here when you extend a wizard.
"""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class PlanWizard(StatesGroup):
    """Admin creates a premium plan step by step (spec item 5)."""

    title = State()      # waiting for plan title
    duration = State()   # waiting for duration in days
    price = State()      # waiting for price
    description = State()  # waiting for description (any text)
    editing = State()    # editing one field of an EXISTING plan (yangi talab)


class BroadcastWizard(StatesGroup):
    """Admin prepares a broadcast post."""

    waiting_content = State()  # waiting for the post (text/photo/video/…)


class AdminGrant(StatesGroup):
    """Admin grants premium days to a specific user (yangi talab)."""

    days = State()  # waiting for the number of days
