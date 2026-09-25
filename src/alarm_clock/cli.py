"""Command parsing, handlers, and the interactive REPL loop.

This module never touches ``datetime.now()`` or ``time.sleep()`` directly
— all time-dependent behavior is delegated to the ``AlarmScheduler``,
which was constructed with an injected clock.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Callable

from alarm_clock.models import Alarm
from alarm_clock.scheduler import AlarmNotFoundError, AlarmScheduler

COMMANDS = ("add", "list", "remove", "start", "help", "quit")

HELP_TEXT = (
    "Commands:\n"
    "  add HH:MM [label]    Add an alarm, e.g. add 07:30 wake up\n"
    "  list                 Show alarms, soonest first\n"
    "  remove <id>          Remove an alarm by id\n"
    "  start                Wait for alarms to fire, in order\n"
    "  help                 Show this message\n"
    "  quit                 Exit (Ctrl+D also works; Ctrl+C cancels a line)"
)


def parse_time(text: str) -> time:
    """Parse a 24-hour ``HH:MM`` string. Raises ValueError if malformed."""
    text = text.strip()
    try:
        return datetime.strptime(text, "%H:%M").time()
    except ValueError:
        raise ValueError(f"invalid time '{text}', expected 24-hour HH:MM (e.g. 07:30)") from None


def parse_command(line: str) -> tuple[str, str]:
    """Split a raw input line into (command, rest-of-line-args)."""
    line = line.strip()
    if not line:
        return "", ""
    parts = line.split(maxsplit=1)
    command = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""
    return command, args


def describe_when(fire_at: datetime, now: datetime) -> str:
    """Say which day an alarm falls on, relative to ``now``."""
    if fire_at <= now:
        return "overdue"
    if fire_at.date() == now.date():
        return "today"
    return "tomorrow"


def format_alarm_list(alarms: list[Alarm], now: datetime) -> str:
    if not alarms:
        return "No alarms set."
    lines = []
    for alarm in alarms:
        when = describe_when(alarm.fire_at, now)
        label = f" ({alarm.label})" if alarm.label else ""
        lines.append(f"  #{alarm.id}  {alarm.time.strftime('%H:%M')} {when}{label}")
    return "\n".join(lines)


def handle_add(scheduler: AlarmScheduler, args: str) -> str:
    parts = args.split(maxsplit=1)
    if not parts:
        return "Usage: add HH:MM [label]"
    time_text, label = parts[0], (parts[1].strip() if len(parts) > 1 else "")
    try:
        alarm_time = parse_time(time_text)
    except ValueError as exc:
        return f"Error: {exc}"
    alarm = scheduler.add(alarm_time, label)
    label_suffix = f" ({alarm.label})" if alarm.label else ""
    return f"Added alarm #{alarm.id} for {alarm.time.strftime('%H:%M')}{label_suffix}"


def handle_list(scheduler: AlarmScheduler, now: datetime) -> str:
    return format_alarm_list(scheduler.list(), now)


def handle_remove(scheduler: AlarmScheduler, args: str) -> str:
    args = args.strip()
    # isdigit() alone would accept non-ASCII digits like "١", which int()
    # then happily converts — an id the user can never have seen printed.
    if not (args.isascii() and args.isdigit()):
        return "Usage: remove <id>"
    alarm_id = int(args)
    try:
        scheduler.remove(alarm_id)
    except AlarmNotFoundError:
        return f"No alarm with id {alarm_id}."
    return f"Removed alarm #{alarm_id}."


def run_repl(
    scheduler: AlarmScheduler,
    now_fn: Callable[[], datetime],
    input_fn: Callable[[str], str] = input,
    print_fn: Callable[[str], None] = print,
) -> None:
    """Main interactive loop.

    ``now_fn`` supplies "now" for display purposes (e.g. formatting
    ``list`` output) without the CLI calling ``datetime.now()`` itself —
    it's expected to be ``scheduler_clock.now``, threaded through from
    ``main.py``.
    """
    print_fn("Alarm Clock CLI. Type 'add HH:MM [label]' to begin, 'help' for all commands.")
    while True:
        try:
            line = input_fn("> ")
        except EOFError:
            print_fn("\nGoodbye.")
            return
        except KeyboardInterrupt:
            # Abandon the half-typed line, as any REPL would. Quitting
            # here would throw away every alarm over one stray Ctrl+C.
            print_fn("")
            continue

        command, args = parse_command(line)

        if command == "":
            continue
        elif command == "add":
            print_fn(handle_add(scheduler, args))
        elif command == "list":
            print_fn(handle_list(scheduler, now_fn()))
        elif command == "remove":
            print_fn(handle_remove(scheduler, args))
        elif command == "start":
            run_start(scheduler, print_fn)
        elif command in ("quit", "exit"):
            print_fn("Goodbye.")
            return
        elif command in ("help", "?"):
            print_fn(HELP_TEXT)
        else:
            print_fn(f"Unknown command: {command}. Available: {', '.join(COMMANDS)}.")


def run_start(
    scheduler: AlarmScheduler,
    print_fn: Callable[[str], None] = print,
) -> None:
    """Wait for each alarm to fire, in order, until none remain."""
    if not scheduler.has_alarms():
        print_fn("No alarms set. Use 'add' first.")
        return

    print_fn("Waiting for alarms. Press Ctrl+C to stop and return to the prompt.")
    try:
        while scheduler.has_alarms():
            alarm = scheduler.wait_for_next()
            print_fn(format_alarm_banner(alarm))
        print_fn("All alarms have fired.")
    except KeyboardInterrupt:
        print_fn("\nInterrupted — returning to prompt.")


def format_alarm_banner(alarm: Alarm) -> str:
    label = f" — {alarm.label}" if alarm.label else ""
    banner = (
        "\a"
        "\n"
        "=========================================\n"
        f"  ALARM! {alarm.time.strftime('%H:%M')}{label}\n"
        "=========================================\n"
    )
    return banner
