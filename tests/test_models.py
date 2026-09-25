import dataclasses
from datetime import datetime, time

import pytest

from alarm_clock.models import Alarm, next_occurrence

CREATED_AT = datetime(2026, 9, 19, 6, 30)
FIRE_AT = datetime(2026, 9, 19, 7, 30)


def test_next_occurrence_later_today_stays_today():
    now = datetime(2026, 9, 19, 8, 0)
    result = next_occurrence(time(9, 0), now)
    assert result == datetime(2026, 9, 19, 9, 0)


def test_next_occurrence_earlier_today_rolls_to_tomorrow():
    now = datetime(2026, 9, 19, 10, 0)
    result = next_occurrence(time(9, 0), now)
    assert result == datetime(2026, 9, 20, 9, 0)


def test_next_occurrence_exactly_now_rolls_to_tomorrow():
    now = datetime(2026, 9, 19, 9, 0)
    result = next_occurrence(time(9, 0), now)
    assert result == datetime(2026, 9, 20, 9, 0)


def test_next_occurrence_midnight_from_late_night():
    now = datetime(2026, 9, 19, 23, 59)
    result = next_occurrence(time(0, 0), now)
    assert result == datetime(2026, 9, 20, 0, 0)


def test_alarm_label_defaults_to_empty_string():
    alarm = Alarm(id=1, fire_at=FIRE_AT, created_at=CREATED_AT)
    assert alarm.label == ""


def test_alarm_time_is_derived_from_fire_at():
    alarm = Alarm(id=1, fire_at=FIRE_AT, created_at=CREATED_AT)
    assert alarm.time == time(7, 30)


def test_alarm_is_immutable():
    alarm = Alarm(id=1, fire_at=FIRE_AT, created_at=CREATED_AT, label="wake up")
    with pytest.raises(dataclasses.FrozenInstanceError):
        alarm.label = "changed"  # type: ignore[misc]


def test_alarm_defaults_to_enabled_and_unsnoozed():
    alarm = Alarm(id=1, fire_at=FIRE_AT, created_at=CREATED_AT)
    assert (alarm.enabled, alarm.snoozes) == (True, 0)


def test_toggled_flips_enabled_without_mutating_the_original():
    alarm = Alarm(id=1, fire_at=FIRE_AT, created_at=CREATED_AT)
    off = alarm.toggled()
    assert off.enabled is False
    assert alarm.enabled is True
    assert off.toggled().enabled is True


def test_snoozed_moves_the_deadline_and_restarts_the_wait():
    alarm = Alarm(id=1, fire_at=FIRE_AT, created_at=CREATED_AT)
    now = datetime(2026, 9, 19, 7, 30)
    later = alarm.snoozed(now, minutes=5)
    assert later.fire_at == datetime(2026, 9, 19, 7, 35)
    assert later.created_at == now
    assert later.snoozes == 1
    assert later.progress(now) == 0.0


def test_snoozed_re_enables_a_disabled_alarm():
    alarm = Alarm(id=1, fire_at=FIRE_AT, created_at=CREATED_AT, enabled=False)
    assert alarm.snoozed(datetime(2026, 9, 19, 7, 30), 5).enabled is True


@pytest.mark.parametrize(
    "now, expected",
    [
        (CREATED_AT, 0.0),
        (datetime(2026, 9, 19, 7, 0), 0.5),
        (FIRE_AT, 1.0),
        (datetime(2026, 9, 19, 9, 0), 1.0),  # overdue clamps, never exceeds 1
    ],
)
def test_progress_runs_from_zero_to_one(now, expected):
    alarm = Alarm(id=1, fire_at=FIRE_AT, created_at=CREATED_AT)
    assert alarm.progress(now) == pytest.approx(expected)


def test_progress_is_complete_when_the_window_is_empty():
    instant = Alarm(id=1, fire_at=CREATED_AT, created_at=CREATED_AT)
    assert instant.progress(CREATED_AT) == 1.0
