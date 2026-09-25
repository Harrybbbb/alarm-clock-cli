"""In-memory alarm collection and deadline-based waiting.

This module never performs I/O and never touches the real clock — all
time access goes through the injected ``Clock``, which is what makes it
testable without real delays.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import List, Optional

from alarm_clock.clock import Clock
from alarm_clock.models import Alarm, next_occurrence

#: How close to a deadline counts as having arrived. A real
#: ``time.sleep`` can return a hair early, and without a tolerance the
#: wait loop would keep re-sleeping on sub-millisecond remainders.
ARRIVAL_TOLERANCE_SECONDS = 0.001

#: Minutes an alarm is pushed back by one press of the snooze key.
DEFAULT_SNOOZE_MINUTES = 5


class SchedulerError(Exception):
    """Base class for every error this module raises."""


class AlarmNotFoundError(SchedulerError):
    """Raised when addressing an alarm id that doesn't exist."""


class NoAlarmsError(SchedulerError):
    """Raised when asked to wait for an alarm but none are set."""


class ClockError(SchedulerError):
    """Raised when the injected clock stops advancing mid-wait."""


def _fire_order(alarm: Alarm) -> tuple[datetime, int]:
    """Sort key: when it fires, then creation order to break ties.

    The tie-break matters: two alarms set for the same minute are a
    supported case, and without it their firing order would depend on
    dict iteration order.
    """
    return (alarm.fire_at, alarm.id)


class AlarmScheduler:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._alarms: dict[int, Alarm] = {}
        self._next_id = 1

    # -- mutation ---------------------------------------------------------

    def add(self, alarm_time: time, label: str = "") -> Alarm:
        """Set an alarm for the next occurrence of ``alarm_time``."""
        now = self._clock.now()
        alarm = Alarm(
            id=self._next_id,
            fire_at=next_occurrence(alarm_time, now),
            created_at=now,
            label=label,
        )
        self._alarms[alarm.id] = alarm
        self._next_id += 1
        return alarm

    def remove(self, alarm_id: int) -> Alarm:
        try:
            return self._alarms.pop(alarm_id)
        except KeyError:
            raise AlarmNotFoundError(alarm_id) from None

    def toggle(self, alarm_id: int) -> Alarm:
        """Enable a disabled alarm, or disable an enabled one."""
        alarm = self.get(alarm_id).toggled()
        self._alarms[alarm_id] = alarm
        return alarm

    def snooze(self, alarm_id: int, minutes: int = DEFAULT_SNOOZE_MINUTES) -> Alarm:
        """Push an alarm ``minutes`` into the future from right now."""
        alarm = self.get(alarm_id).snoozed(self._clock.now(), minutes)
        self._alarms[alarm_id] = alarm
        return alarm

    # -- queries ----------------------------------------------------------

    def get(self, alarm_id: int) -> Alarm:
        try:
            return self._alarms[alarm_id]
        except KeyError:
            raise AlarmNotFoundError(alarm_id) from None

    def list(self) -> List[Alarm]:
        """Every alarm, enabled or not, in the order they will fire."""
        return sorted(self._alarms.values(), key=_fire_order)

    def has_alarms(self) -> bool:
        return bool(self._alarms)

    def next_due(self) -> Optional[Alarm]:
        """The soonest *enabled* alarm, or None if there is none.

        Disabled alarms are skipped entirely: they stay in the list and
        keep their time, but they never come due.
        """
        pending = [alarm for alarm in self._alarms.values() if alarm.enabled]
        if not pending:
            return None
        return min(pending, key=_fire_order)

    def due_now(self) -> List[Alarm]:
        """Every enabled alarm whose deadline has arrived.

        This is the non-blocking counterpart to ``wait_for_next``, for
        a UI that redraws on a timer instead of sleeping.
        """
        now = self._clock.now()
        return [
            alarm
            for alarm in sorted(self._alarms.values(), key=_fire_order)
            if alarm.enabled and (alarm.fire_at - now).total_seconds() <= ARRIVAL_TOLERANCE_SECONDS
        ]

    # -- blocking wait ----------------------------------------------------

    def wait_for_next(self) -> Alarm:
        """Block (via the injected clock) until the earliest alarm is due.

        Sleeps for the whole remaining interval rather than polling, and
        only sleeps again if that sleep came back early — a real
        ``time.sleep`` can be cut short by a signal, and ringing an
        alarm ahead of its time is worse than sleeping twice. An alarm
        whose deadline has already passed fires immediately instead of
        waiting out another day.

        The fired alarm is removed from the scheduler and returned.
        """
        alarm = self.next_due()
        if alarm is None:
            raise NoAlarmsError("no alarms to wait for")

        while True:
            remaining = (alarm.fire_at - self._clock.now()).total_seconds()
            if remaining <= ARRIVAL_TOLERANCE_SECONDS:
                break
            before = self._clock.now()
            self._clock.sleep(remaining)
            if self._clock.now() <= before:
                # A clock that never advances would spin this loop
                # forever; fail loudly instead of hanging in silence.
                raise ClockError(f"clock stuck at {before}, cannot reach {alarm.fire_at}")

        del self._alarms[alarm.id]
        return alarm
