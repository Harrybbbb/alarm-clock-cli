"""Domain model: what an alarm is, and the moment it fires."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import datetime, time, timedelta


@dataclass(frozen=True)
class Alarm:
    """A single alarm, resolved to the exact moment it will fire.

    ``id`` is assigned by the scheduler and is the identity used for
    removal. ``fire_at`` is a concrete datetime, fixed once when the
    alarm is created and never recomputed — that is what lets two
    alarms share a wall-clock time and still both fire, and what stops
    an alarm being silently pushed to tomorrow while the user sits at
    the prompt.

    ``created_at`` is kept so the UI can show how far through the wait
    we are; ``snoozes`` counts how many times the alarm has been pushed
    back, which is worth surfacing rather than hiding.
    """

    id: int
    fire_at: datetime
    created_at: datetime
    label: str = ""
    enabled: bool = True
    snoozes: int = 0

    @property
    def time(self) -> time:
        """The wall-clock time of day this alarm fires at."""
        return self.fire_at.time()

    def toggled(self) -> "Alarm":
        """A copy with ``enabled`` flipped."""
        return dataclasses.replace(self, enabled=not self.enabled)

    def snoozed(self, now: datetime, minutes: int) -> "Alarm":
        """A copy pushed ``minutes`` past ``now``, re-enabled and counted.

        The new wait is measured from ``now``, so progress displays
        restart rather than showing a bar that is already full.
        """
        return dataclasses.replace(
            self,
            fire_at=now + timedelta(minutes=minutes),
            created_at=now,
            enabled=True,
            snoozes=self.snoozes + 1,
        )

    def progress(self, now: datetime) -> float:
        """How far through the wait we are, from 0.0 to 1.0."""
        total = (self.fire_at - self.created_at).total_seconds()
        if total <= 0:
            return 1.0
        elapsed = (now - self.created_at).total_seconds()
        return max(0.0, min(1.0, elapsed / total))


def next_occurrence(alarm_time: time, now: datetime) -> datetime:
    """Return the next datetime at which ``alarm_time`` occurs after ``now``.

    If ``alarm_time`` has already passed today (or is exactly ``now``),
    the next occurrence is tomorrow — asking for an alarm at the very
    minute you are typing means tomorrow, not "immediately".

    This is applied once, by ``AlarmScheduler.add``, and the result
    stored on the ``Alarm``; nothing re-derives a fire time from a
    moving "now" afterwards.
    """
    candidate = datetime.combine(now.date(), alarm_time)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate
