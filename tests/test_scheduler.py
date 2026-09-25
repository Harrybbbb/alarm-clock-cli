import time as time_module
from datetime import datetime, time, timedelta

import pytest

from alarm_clock.clock import FakeClock
from alarm_clock.scheduler import (
    DEFAULT_SNOOZE_MINUTES,
    AlarmNotFoundError,
    AlarmScheduler,
    ClockError,
    NoAlarmsError,
)


def make_scheduler(now: datetime) -> tuple[AlarmScheduler, FakeClock]:
    clock = FakeClock(now)
    return AlarmScheduler(clock), clock


def test_add_assigns_sequential_ids():
    scheduler, _ = make_scheduler(datetime(2026, 9, 19, 8, 0))
    first = scheduler.add(time(9, 0))
    second = scheduler.add(time(10, 0))
    assert (first.id, second.id) == (1, 2)


def test_add_resolves_fire_at_once_at_creation():
    scheduler, clock = make_scheduler(datetime(2026, 9, 19, 8, 0))
    alarm = scheduler.add(time(9, 0))
    clock.advance(seconds=2 * 3600)  # now 10:00, the alarm is overdue
    assert scheduler.list()[0].fire_at == alarm.fire_at == datetime(2026, 9, 19, 9, 0)


def test_list_is_sorted_by_next_occurrence_not_insertion_order():
    scheduler, _ = make_scheduler(datetime(2026, 9, 19, 8, 0))
    later_today = scheduler.add(time(20, 0), label="added first, fires later")
    sooner_today = scheduler.add(time(9, 0), label="added second, fires sooner")
    assert [a.id for a in scheduler.list()] == [sooner_today.id, later_today.id]


def test_list_breaks_ties_by_creation_order():
    scheduler, _ = make_scheduler(datetime(2026, 9, 19, 8, 0))
    first = scheduler.add(time(9, 0), label="a")
    second = scheduler.add(time(9, 0), label="b")
    assert [a.id for a in scheduler.list()] == [first.id, second.id]


def test_remove_existing_alarm():
    scheduler, _ = make_scheduler(datetime(2026, 9, 19, 8, 0))
    alarm = scheduler.add(time(9, 0))
    removed = scheduler.remove(alarm.id)
    assert removed.id == alarm.id
    assert scheduler.has_alarms() is False


def test_remove_nonexistent_alarm_raises():
    scheduler, _ = make_scheduler(datetime(2026, 9, 19, 8, 0))
    with pytest.raises(AlarmNotFoundError):
        scheduler.remove(999)


def test_has_alarms_reflects_state():
    scheduler, _ = make_scheduler(datetime(2026, 9, 19, 8, 0))
    assert scheduler.has_alarms() is False
    scheduler.add(time(9, 0))
    assert scheduler.has_alarms() is True


def test_next_due_picks_earliest_among_several():
    scheduler, _ = make_scheduler(datetime(2026, 9, 19, 8, 0))
    scheduler.add(time(12, 0))
    soonest = scheduler.add(time(9, 0))
    scheduler.add(time(23, 0))
    alarm = scheduler.next_due()
    assert alarm.id == soonest.id
    assert alarm.fire_at == datetime(2026, 9, 19, 9, 0)


def test_next_due_none_when_empty():
    scheduler, _ = make_scheduler(datetime(2026, 9, 19, 8, 0))
    assert scheduler.next_due() is None


def test_wait_for_next_returns_and_removes_fired_alarm():
    scheduler, clock = make_scheduler(datetime(2026, 9, 19, 8, 0))
    scheduler.add(time(9, 0), label="target")
    later = scheduler.add(time(10, 0), label="later")

    fired = scheduler.wait_for_next()

    assert fired.label == "target"
    assert clock.now() == datetime(2026, 9, 19, 9, 0)
    assert [a.id for a in scheduler.list()] == [later.id]


def test_two_alarms_at_the_same_time_both_fire_that_day():
    """Regression: the second used to be pushed a full day out."""
    scheduler, clock = make_scheduler(datetime(2026, 9, 19, 8, 0))
    scheduler.add(time(9, 0), label="first")
    scheduler.add(time(9, 0), label="second")

    first = scheduler.wait_for_next()
    second = scheduler.wait_for_next()

    assert [first.label, second.label] == ["first", "second"]
    assert clock.now() == datetime(2026, 9, 19, 9, 0)
    assert scheduler.has_alarms() is False


def test_overdue_alarm_fires_immediately():
    """An alarm whose time passed at the prompt isn't deferred a day."""
    scheduler, clock = make_scheduler(datetime(2026, 9, 19, 8, 0))
    scheduler.add(time(9, 0), label="missed")
    clock.advance(seconds=2 * 3600)  # user dawdled until 10:00

    fired = scheduler.wait_for_next()

    assert fired.label == "missed"
    assert clock.now() == datetime(2026, 9, 19, 10, 0)  # fired now, not tomorrow


def test_wait_for_next_does_not_fire_early_when_sleep_returns_short():
    """A real time.sleep can be cut short by a signal; keep waiting."""

    class UndershootingClock:
        def __init__(self, start: datetime) -> None:
            self._now = start

        def now(self) -> datetime:
            return self._now

        def sleep(self, seconds: float) -> None:
            self._now += timedelta(seconds=seconds * 0.5)

    clock = UndershootingClock(datetime(2026, 9, 19, 8, 0))
    scheduler = AlarmScheduler(clock)
    scheduler.add(time(9, 0), label="target")

    scheduler.wait_for_next()

    assert clock.now() >= datetime(2026, 9, 19, 9, 0) - timedelta(milliseconds=1)


def test_wait_for_next_raises_instead_of_spinning_on_a_stuck_clock():
    class StuckClock:
        def now(self) -> datetime:
            return datetime(2026, 9, 19, 8, 0)

        def sleep(self, seconds: float) -> None:
            pass

    scheduler = AlarmScheduler(StuckClock())
    scheduler.add(time(9, 0))

    with pytest.raises(ClockError):
        scheduler.wait_for_next()


def test_wait_for_next_does_not_actually_sleep_in_real_time():
    scheduler, _ = make_scheduler(datetime(2026, 9, 19, 8, 0))
    scheduler.add(time(20, 0))  # 12 hours away

    started = time_module.monotonic()
    scheduler.wait_for_next()
    elapsed = time_module.monotonic() - started

    assert elapsed < 0.1


def test_wait_for_next_raises_when_no_alarms():
    scheduler, _ = make_scheduler(datetime(2026, 9, 19, 8, 0))
    with pytest.raises(NoAlarmsError):
        scheduler.wait_for_next()


# -- enable / disable -----------------------------------------------------

def test_toggle_disables_then_re_enables():
    scheduler, _ = make_scheduler(datetime(2026, 9, 19, 8, 0))
    alarm = scheduler.add(time(9, 0))
    assert scheduler.toggle(alarm.id).enabled is False
    assert scheduler.toggle(alarm.id).enabled is True


def test_toggle_unknown_id_raises():
    scheduler, _ = make_scheduler(datetime(2026, 9, 19, 8, 0))
    with pytest.raises(AlarmNotFoundError):
        scheduler.toggle(42)


def test_disabled_alarms_are_listed_but_never_come_due():
    scheduler, _ = make_scheduler(datetime(2026, 9, 19, 8, 0))
    off = scheduler.add(time(9, 0), "off")
    on = scheduler.add(time(10, 0), "on")
    scheduler.toggle(off.id)

    assert [a.id for a in scheduler.list()] == [off.id, on.id]  # still shown
    assert scheduler.next_due().id == on.id  # but skipped when choosing


def test_next_due_is_none_when_every_alarm_is_disabled():
    scheduler, _ = make_scheduler(datetime(2026, 9, 19, 8, 0))
    alarm = scheduler.add(time(9, 0))
    scheduler.toggle(alarm.id)
    assert scheduler.next_due() is None
    assert scheduler.has_alarms() is True


def test_wait_for_next_ignores_disabled_alarms():
    scheduler, clock = make_scheduler(datetime(2026, 9, 19, 8, 0))
    off = scheduler.add(time(9, 0), "off")
    scheduler.add(time(10, 0), "on")
    scheduler.toggle(off.id)

    assert scheduler.wait_for_next().label == "on"
    assert clock.now() == datetime(2026, 9, 19, 10, 0)


# -- snooze ---------------------------------------------------------------

def test_snooze_pushes_the_deadline_from_now_not_from_the_old_time():
    scheduler, clock = make_scheduler(datetime(2026, 9, 19, 8, 0))
    alarm = scheduler.add(time(9, 0))
    clock.advance(seconds=3600)  # it is now 09:00 and the alarm is due

    snoozed = scheduler.snooze(alarm.id, minutes=5)

    assert snoozed.fire_at == datetime(2026, 9, 19, 9, 5)
    assert snoozed.snoozes == 1


def test_snooze_uses_the_default_interval():
    scheduler, _ = make_scheduler(datetime(2026, 9, 19, 8, 0))
    alarm = scheduler.add(time(9, 0))
    snoozed = scheduler.snooze(alarm.id)
    assert snoozed.fire_at == datetime(2026, 9, 19, 8, 0) + timedelta(
        minutes=DEFAULT_SNOOZE_MINUTES
    )


def test_snoozing_a_disabled_alarm_arms_it_again():
    scheduler, _ = make_scheduler(datetime(2026, 9, 19, 8, 0))
    alarm = scheduler.add(time(9, 0))
    scheduler.toggle(alarm.id)
    assert scheduler.snooze(alarm.id).enabled is True


# -- due_now (the non-blocking counterpart to wait_for_next) --------------

def test_due_now_is_empty_before_the_deadline():
    scheduler, _ = make_scheduler(datetime(2026, 9, 19, 8, 0))
    scheduler.add(time(9, 0))
    assert scheduler.due_now() == []


def test_due_now_reports_arrived_alarms_in_fire_order():
    scheduler, clock = make_scheduler(datetime(2026, 9, 19, 8, 0))
    scheduler.add(time(9, 30), "second")
    scheduler.add(time(9, 0), "first")
    clock.advance(seconds=2 * 3600)  # 10:00 — both have arrived

    assert [a.label for a in scheduler.due_now()] == ["first", "second"]


def test_due_now_skips_disabled_alarms():
    scheduler, clock = make_scheduler(datetime(2026, 9, 19, 8, 0))
    alarm = scheduler.add(time(9, 0))
    scheduler.toggle(alarm.id)
    clock.advance(seconds=2 * 3600)
    assert scheduler.due_now() == []


def test_due_now_does_not_remove_anything():
    """A ringing alarm stays put until the user snoozes or dismisses it."""
    scheduler, clock = make_scheduler(datetime(2026, 9, 19, 8, 0))
    scheduler.add(time(9, 0))
    clock.advance(seconds=3600)
    scheduler.due_now()
    assert scheduler.has_alarms() is True
