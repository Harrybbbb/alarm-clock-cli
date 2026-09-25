from datetime import datetime, time

import pytest

from alarm_clock.cli import (
    format_alarm_list,
    handle_add,
    handle_list,
    handle_remove,
    parse_command,
    parse_time,
    run_repl,
    run_start,
)
from alarm_clock.clock import Clock, FakeClock
from alarm_clock.scheduler import AlarmScheduler


# -- pure parsing --------------------------------------------------------

def test_parse_time_valid():
    assert parse_time("07:30") == time(7, 30)


@pytest.mark.parametrize("text", ["25:00", "7:30pm", "", "abc", "7-30"])
def test_parse_time_invalid_raises(text):
    with pytest.raises(ValueError):
        parse_time(text)


def test_parse_command_splits_command_and_args():
    assert parse_command("add 07:30 wake up") == ("add", "07:30 wake up")


def test_parse_command_no_args():
    assert parse_command("list") == ("list", "")


def test_parse_command_blank_line():
    assert parse_command("   ") == ("", "")


def test_parse_command_is_case_insensitive():
    assert parse_command("ADD 07:30") == ("add", "07:30")


# -- handlers against a real scheduler + FakeClock -----------------------

def make_scheduler(now: datetime) -> AlarmScheduler:
    return AlarmScheduler(FakeClock(now))


def test_handle_add_success_message():
    scheduler = make_scheduler(datetime(2026, 9, 19, 8, 0))
    message = handle_add(scheduler, "07:30 wake up")
    assert message == "Added alarm #1 for 07:30 (wake up)"


def test_handle_add_invalid_time_message():
    scheduler = make_scheduler(datetime(2026, 9, 19, 8, 0))
    message = handle_add(scheduler, "not-a-time")
    assert message.startswith("Error:")


def test_handle_add_missing_args():
    scheduler = make_scheduler(datetime(2026, 9, 19, 8, 0))
    assert handle_add(scheduler, "") == "Usage: add HH:MM [label]"


def test_handle_list_empty():
    scheduler = make_scheduler(datetime(2026, 9, 19, 8, 0))
    assert handle_list(scheduler, datetime(2026, 9, 19, 8, 0)) == "No alarms set."


def test_handle_list_shows_added_alarm():
    scheduler = make_scheduler(datetime(2026, 9, 19, 8, 0))
    handle_add(scheduler, "09:00 standup")
    output = handle_list(scheduler, datetime(2026, 9, 19, 8, 0))
    assert "#1" in output and "09:00" in output and "standup" in output


def test_handle_remove_existing():
    scheduler = make_scheduler(datetime(2026, 9, 19, 8, 0))
    handle_add(scheduler, "09:00")
    assert handle_remove(scheduler, "1") == "Removed alarm #1."


def test_handle_remove_nonexistent():
    scheduler = make_scheduler(datetime(2026, 9, 19, 8, 0))
    assert handle_remove(scheduler, "42") == "No alarm with id 42."


def test_handle_remove_non_numeric():
    scheduler = make_scheduler(datetime(2026, 9, 19, 8, 0))
    assert handle_remove(scheduler, "abc") == "Usage: remove <id>"


def test_format_alarm_list_labels_today_vs_tomorrow():
    now = datetime(2026, 9, 19, 8, 0)
    scheduler = make_scheduler(now)
    handle_add(scheduler, "09:00 later today")
    handle_add(scheduler, "07:00 already passed")
    output = format_alarm_list(scheduler.list(), now)
    assert "today" in output
    assert "tomorrow" in output


# -- REPL loop, driven with scripted input --------------------------------

def test_repl_add_list_quit_end_to_end():
    scheduler = make_scheduler(datetime(2026, 9, 19, 8, 0))
    scripted_input = iter(["add 09:00 standup", "list", "quit"])
    outputs = []

    run_repl(
        scheduler,
        now_fn=lambda: datetime(2026, 9, 19, 8, 0),
        input_fn=lambda prompt: next(scripted_input),
        print_fn=outputs.append,
    )

    joined = "\n".join(outputs)
    assert "Added alarm #1" in joined
    assert "09:00" in joined
    assert "Goodbye." in joined


def test_repl_unknown_command():
    scheduler = make_scheduler(datetime(2026, 9, 19, 8, 0))
    scripted_input = iter(["frobnicate", "quit"])
    outputs = []

    run_repl(
        scheduler,
        now_fn=lambda: datetime(2026, 9, 19, 8, 0),
        input_fn=lambda prompt: next(scripted_input),
        print_fn=outputs.append,
    )

    assert any("Unknown command" in line for line in outputs)


def test_run_start_fires_alarms_in_order_and_clears_them():
    scheduler = make_scheduler(datetime(2026, 9, 19, 8, 0))
    handle_add(scheduler, "10:00 second")
    handle_add(scheduler, "09:00 first")
    outputs = []

    run_start(scheduler, print_fn=outputs.append)

    joined = "\n".join(outputs)
    first_index = joined.index("first")
    second_index = joined.index("second")
    assert first_index < second_index
    assert "\a" in joined
    assert "ALARM!" in joined
    assert "All alarms have fired." in joined
    assert scheduler.has_alarms() is False


class InterruptingClock:
    """A Clock whose sleep() simulates Ctrl+C arriving during a real wait.

    now() stays fixed and sleep() never actually waits, so a test using
    this clock is deterministic and instantaneous.
    """

    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def sleep(self, seconds: float) -> None:
        raise KeyboardInterrupt


def test_run_start_ctrl_c_returns_to_prompt_and_keeps_unfired_alarms():
    clock: Clock = InterruptingClock(datetime(2026, 9, 19, 8, 0))
    scheduler = AlarmScheduler(clock)
    handle_add(scheduler, "09:00 target")
    outputs: list[str] = []

    run_start(scheduler, print_fn=outputs.append)

    assert any("Interrupted — returning to prompt." in line for line in outputs)
    assert scheduler.has_alarms() is True
    assert [a.label for a in scheduler.list()] == ["target"]


def test_repl_start_with_no_alarms_does_not_block():
    scheduler = make_scheduler(datetime(2026, 9, 19, 8, 0))
    scripted_input = iter(["start", "quit"])
    outputs = []

    run_repl(
        scheduler,
        now_fn=lambda: datetime(2026, 9, 19, 8, 0),
        input_fn=lambda prompt: next(scripted_input),
        print_fn=outputs.append,
    )

    assert any("No alarms set" in line for line in outputs)


# -- regressions ----------------------------------------------------------

def test_handle_remove_rejects_non_ascii_digits():
    """'١'.isdigit() is True and int() accepts it — but no such id was shown."""
    scheduler = make_scheduler(datetime(2026, 9, 19, 8, 0))
    handle_add(scheduler, "09:00")
    assert handle_remove(scheduler, "١") == "Usage: remove <id>"
    assert scheduler.has_alarms() is True


def test_unknown_command_advertises_help():
    scheduler = make_scheduler(datetime(2026, 9, 19, 8, 0))
    scripted_input = iter(["frobnicate", "quit"])
    outputs = []

    run_repl(
        scheduler,
        now_fn=lambda: datetime(2026, 9, 19, 8, 0),
        input_fn=lambda prompt: next(scripted_input),
        print_fn=outputs.append,
    )

    assert any("Unknown command" in line and "help" in line for line in outputs)


def test_repl_ctrl_c_at_prompt_cancels_the_line_and_keeps_alarms():
    """Ctrl+C used to exit outright, silently discarding every alarm."""
    scheduler = make_scheduler(datetime(2026, 9, 19, 8, 0))
    handle_add(scheduler, "09:00 keep me")
    calls = iter([KeyboardInterrupt, "list", "quit"])

    def input_fn(prompt):
        value = next(calls)
        if value is KeyboardInterrupt:
            raise KeyboardInterrupt
        return value

    outputs = []
    run_repl(
        scheduler,
        now_fn=lambda: datetime(2026, 9, 19, 8, 0),
        input_fn=input_fn,
        print_fn=outputs.append,
    )

    assert any("keep me" in line for line in outputs), "survived Ctrl+C and still listed"
    assert scheduler.has_alarms() is True


def test_repl_ctrl_d_exits():
    scheduler = make_scheduler(datetime(2026, 9, 19, 8, 0))

    def input_fn(prompt):
        raise EOFError

    outputs = []
    run_repl(
        scheduler,
        now_fn=lambda: datetime(2026, 9, 19, 8, 0),
        input_fn=input_fn,
        print_fn=outputs.append,
    )

    assert any("Goodbye." in line for line in outputs)


def test_format_alarm_list_marks_an_overdue_alarm():
    scheduler = make_scheduler(datetime(2026, 9, 19, 8, 0))
    handle_add(scheduler, "09:00 missed")
    later = datetime(2026, 9, 19, 10, 0)
    assert "overdue" in format_alarm_list(scheduler.list(), later)


def test_run_start_fires_two_alarms_set_for_the_same_time():
    scheduler = make_scheduler(datetime(2026, 9, 19, 8, 0))
    handle_add(scheduler, "09:00 alpha")
    handle_add(scheduler, "09:00 beta")
    outputs = []

    run_start(scheduler, print_fn=outputs.append)

    joined = "\n".join(outputs)
    assert "alpha" in joined and "beta" in joined
    assert "All alarms have fired." in joined
