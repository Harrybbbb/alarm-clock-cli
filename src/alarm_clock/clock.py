"""Time source abstraction.

Production code talks to the real clock only through ``SystemClock``.
Tests use ``FakeClock`` so time-dependent behavior (including waiting for
an alarm to become due) can be verified without any real delay.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    """Minimal interface the scheduler needs from a clock."""

    def now(self) -> datetime:
        """Return the current date and time."""
        ...

    def sleep(self, seconds: float) -> None:
        """Block (or simulate blocking) for the given number of seconds."""
        ...


class SystemClock:
    """Real clock backed by the standard library."""

    def now(self) -> datetime:
        return datetime.now()

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            time.sleep(seconds)


class FakeClock:
    """Deterministic clock for tests.

    ``sleep`` does not actually wait — it advances the internal clock by
    the requested number of seconds, so code under test that calls
    ``clock.sleep(n)`` completes instantly while still observing the
    correct elapsed time.
    """

    def __init__(self, start: datetime) -> None:
        self._now = start

    def now(self) -> datetime:
        return self._now

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            self._now += timedelta(seconds=seconds)

    def advance(self, seconds: float) -> None:
        """Explicit test helper, equivalent to ``sleep``."""
        self.sleep(seconds)
