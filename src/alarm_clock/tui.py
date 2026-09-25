"""The live, full-screen alarm clock interface.

Loop-and-dispatch only: every pixel comes from ``ui.py`` and every
decision about time comes from the injected clock via the scheduler.
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable, List, Optional

from rich.console import Console, RenderableType
from rich.live import Live

from alarm_clock import ui
from alarm_clock.cli import parse_time
from alarm_clock.clock import Clock
from alarm_clock.keyboard import KeyReader
from alarm_clock.models import Alarm
from alarm_clock.sound import AlarmSound
from alarm_clock.scheduler import (
    DEFAULT_SNOOZE_MINUTES,
    AlarmNotFoundError,
    AlarmScheduler,
)

#: How long to wait for a keypress before redrawing anyway. Four
#: redraws a second keeps the seconds digit honest without busy-looping.
TICK_SECONDS = 0.25


class AlarmClockApp:
    def __init__(
        self,
        scheduler: AlarmScheduler,
        clock: Clock,
        console: Optional[Console] = None,
        sound: Optional[AlarmSound] = None,
    ) -> None:
        self._scheduler = scheduler
        self._clock = clock
        self._console = console if console is not None else Console()
        self._sound = sound if sound is not None else AlarmSound()
        self._message = ""
        self._running = True
        self._last_bell_second = -1

    # -- main loop --------------------------------------------------------

    def run(self) -> None:
        """Draw and dispatch until the user quits or interrupts."""
        with KeyReader() as keys:
            with Live(
                self._render(),
                console=self._console,
                screen=True,
                refresh_per_second=8,
                transient=False,
            ) as live:
                while self._running:
                    try:
                        live.update(self._render())
                        key = keys.read(TICK_SECONDS)
                        if key is not None:
                            self._dispatch(key, live, keys)
                    except KeyboardInterrupt:
                        self._running = False
        self._sound.stop()
        self._console.print(ui.status_line("Goodbye.", style=ui.ACCENT))

    def _render(self) -> RenderableType:
        now = self._clock.now()
        ringing = self._scheduler.due_now()
        self._alert(ringing, now)
        return ui.dashboard(
            alarms=self._scheduler.list(),
            now=now,
            next_alarm=self._scheduler.next_due(),
            ringing=ringing,
            # A leftover status line ("Added alarm #1...") is noise next
            # to a ringing alarm; say what the keys do instead.
            message="Snooze for 5 minutes, or dismiss it." if ringing else self._message,
        )

    def _alert(self, ringing: List[Alarm], now: datetime) -> None:
        """Make noise while an alarm is ringing, and stop when none is.

        A sound file rings continuously; the terminal bell is only the
        fallback for machines with no player or no file, since most
        terminals render it silently if at all.
        """
        if not ringing:
            self._sound.stop()
            return
        if self._sound.available:
            self._sound.ensure_playing()
        else:
            self._ring_bell(now.second)

    def _ring_bell(self, second: int) -> None:
        """Emit the terminal bell at most once a second while ringing."""
        if second != self._last_bell_second:
            self._last_bell_second = second
            self._console.bell()

    # -- input ------------------------------------------------------------

    def _dispatch(self, key: str, live: Live, keys: KeyReader) -> None:
        ringing = self._scheduler.due_now()
        key = key.lower()

        if key == "q":
            self._running = False
        elif ringing:
            # While something is ringing, the only sensible verbs are
            # "stop it" and "not yet" — everything else is ignored so a
            # stray keypress can't silently reconfigure the alarm.
            if key == "s":
                self._snooze_all(ringing)
            elif key in ("d", "\r", "\n", " "):
                self._dismiss_all(ringing)
        elif key == "a":
            self._add(live, keys)
        elif key == "d":
            self._delete(live, keys)
        elif key == "t":
            self._toggle(live, keys)
        elif key == "s":
            self._snooze_next()
        elif key == "c":
            self._clear(live, keys)

    def _ask(self, live: Live, keys: KeyReader, question: str) -> str:
        """Pause the live display and ask a plain question."""
        live.stop()
        try:
            with keys.paused():
                return self._console.input(question).strip()
        except (EOFError, KeyboardInterrupt):
            return ""
        finally:
            live.start(refresh=True)

    def _ask_alarm_id(self, live: Live, keys: KeyReader, verb: str) -> Optional[Alarm]:
        """Ask for an id and resolve it, reporting anything that's wrong."""
        if not self._scheduler.has_alarms():
            self._message = "No alarms yet — press A to add one."
            return None
        answer = self._ask(live, keys, f"[bold]{verb} which alarm?[/] id: ")
        if not answer:
            self._message = ""
            return None
        if not (answer.isascii() and answer.isdigit()):
            self._message = f"'{answer}' is not an alarm id."
            return None
        try:
            return self._scheduler.get(int(answer))
        except AlarmNotFoundError:
            self._message = f"No alarm with id {answer}."
            return None

    # -- actions ----------------------------------------------------------

    def _add(self, live: Live, keys: KeyReader) -> None:
        answer = self._ask(live, keys, "[bold]Time[/] (24-hour HH:MM): ")
        if not answer:
            self._message = ""
            return
        try:
            alarm_time = parse_time(answer)
        except ValueError as exc:
            self._message = str(exc)
            return
        label = self._ask(live, keys, "[bold]Label[/] (optional): ")
        alarm = self._scheduler.add(alarm_time, label)
        self._message = f"Added alarm #{alarm.id} for {alarm.fire_at.strftime('%H:%M')}."

    def _delete(self, live: Live, keys: KeyReader) -> None:
        alarm = self._ask_alarm_id(live, keys, "Delete")
        if alarm is None:
            return
        self._scheduler.remove(alarm.id)
        self._message = f"Deleted alarm #{alarm.id}."

    def _toggle(self, live: Live, keys: KeyReader) -> None:
        alarm = self._ask_alarm_id(live, keys, "Toggle")
        if alarm is None:
            return
        updated = self._scheduler.toggle(alarm.id)
        state = "enabled" if updated.enabled else "disabled"
        self._message = f"Alarm #{updated.id} {state}."

    def _snooze_next(self) -> None:
        alarm = self._scheduler.next_due()
        if alarm is None:
            self._message = "Nothing armed to snooze."
            return
        updated = self._scheduler.snooze(alarm.id, DEFAULT_SNOOZE_MINUTES)
        self._message = (
            f"Snoozed #{updated.id} to {updated.fire_at.strftime('%H:%M')}."
        )

    def _snooze_all(self, ringing: List[Alarm]) -> None:
        self._sound.stop()
        for alarm in ringing:
            self._scheduler.snooze(alarm.id, DEFAULT_SNOOZE_MINUTES)
        self._message = f"Snoozed for {DEFAULT_SNOOZE_MINUTES} minutes."

    def _dismiss_all(self, ringing: List[Alarm]) -> None:
        self._sound.stop()
        for alarm in ringing:
            self._scheduler.remove(alarm.id)
        self._message = "Dismissed." if len(ringing) == 1 else f"Dismissed {len(ringing)} alarms."

    def _clear(self, live: Live, keys: KeyReader) -> None:
        if not self._scheduler.has_alarms():
            self._message = "Nothing to clear."
            return
        count = len(self._scheduler.list())
        answer = self._ask(live, keys, f"[bold]Delete all {count} alarms?[/] (y/N): ")
        if answer.lower() not in ("y", "yes"):
            self._message = "Cancelled."
            return
        for alarm in self._scheduler.list():
            self._scheduler.remove(alarm.id)
        self._message = f"Cleared {count} alarms."


def run_tui(
    scheduler: AlarmScheduler,
    clock: Clock,
    sound: Optional[AlarmSound] = None,
    console_factory: Callable[[], Console] = Console,
) -> None:
    AlarmClockApp(scheduler, clock, console_factory(), sound).run()
