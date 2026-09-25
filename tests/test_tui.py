"""Key handling, exercised without a terminal.

``_dispatch`` only ever touches the terminal through ``_ask``, so a
subclass with scripted answers covers the whole decision tree.
"""

import io
from datetime import datetime, time

from rich.console import Console

from alarm_clock.clock import FakeClock
from alarm_clock.scheduler import AlarmScheduler
from alarm_clock.tui import AlarmClockApp

NOW = datetime(2026, 9, 23, 8, 0)


class ScriptedApp(AlarmClockApp):
    """An app whose prompts are answered from a list instead of a tty."""

    def __init__(self, answers=()):
        clock = FakeClock(NOW)
        super().__init__(
            AlarmScheduler(clock),
            clock,
            console=Console(file=io.StringIO(), width=80),
        )
        self._answers = list(answers)
        self.questions = []

    def _ask(self, live, keys, question):
        self.questions.append(question)
        return self._answers.pop(0) if self._answers else ""

    def press(self, *keys):
        for key in keys:
            self._dispatch(key, live=None, keys=None)
        return self

    @property
    def scheduler(self):
        return self._scheduler

    @property
    def message(self):
        return self._message

    @property
    def clock(self):
        return self._clock


# -- adding ---------------------------------------------------------------

def test_a_adds_an_alarm_with_a_label():
    app = ScriptedApp(["09:30", "standup"]).press("a")
    alarm = app.scheduler.list()[0]
    assert (alarm.fire_at, alarm.label) == (datetime(2026, 9, 23, 9, 30), "standup")
    assert "Added alarm #1" in app.message


def test_a_accepts_an_empty_label():
    app = ScriptedApp(["09:30", ""]).press("a")
    assert app.scheduler.list()[0].label == ""


def test_a_with_a_bad_time_reports_and_adds_nothing():
    app = ScriptedApp(["99:99"]).press("a")
    assert app.scheduler.has_alarms() is False
    assert "invalid time" in app.message


def test_a_cancelled_at_the_time_prompt_adds_nothing():
    app = ScriptedApp([""]).press("a")
    assert app.scheduler.has_alarms() is False
    assert app.message == ""


# -- delete / toggle ------------------------------------------------------

def test_d_deletes_by_id():
    app = ScriptedApp(["09:30", "a", "10:30", "b", "1"]).press("a", "a", "d")
    assert [alarm.label for alarm in app.scheduler.list()] == ["b"]
    assert "Deleted alarm #1" in app.message


def test_t_toggles_by_id():
    app = ScriptedApp(["09:30", "a", "1"]).press("a", "t")
    assert app.scheduler.list()[0].enabled is False
    assert "disabled" in app.message

    app._answers.append("1")
    app.press("t")
    assert app.scheduler.list()[0].enabled is True


def test_delete_reports_an_unknown_id_without_touching_anything():
    app = ScriptedApp(["09:30", "a", "99"]).press("a", "d")
    assert app.scheduler.has_alarms() is True
    assert "No alarm with id 99" in app.message


def test_delete_rejects_a_non_numeric_id():
    app = ScriptedApp(["09:30", "a", "abc"]).press("a", "d")
    assert app.scheduler.has_alarms() is True
    assert "not an alarm id" in app.message


def test_delete_with_no_alarms_does_not_even_ask():
    app = ScriptedApp().press("d")
    assert app.questions == []
    assert "No alarms yet" in app.message


# -- snooze ---------------------------------------------------------------

def test_s_snoozes_the_next_alarm():
    app = ScriptedApp(["09:30", "standup"]).press("a", "s")
    alarm = app.scheduler.list()[0]
    assert alarm.fire_at == datetime(2026, 9, 23, 8, 5)  # five minutes from now
    assert alarm.snoozes == 1


def test_s_with_nothing_armed_says_so():
    app = ScriptedApp().press("s")
    assert "Nothing armed" in app.message


# -- clear ----------------------------------------------------------------

def test_c_clears_everything_after_confirmation():
    app = ScriptedApp(["09:30", "a", "10:30", "b", "y"]).press("a", "a", "c")
    assert app.scheduler.has_alarms() is False
    assert "Cleared 2 alarms" in app.message


def test_c_keeps_everything_when_not_confirmed():
    app = ScriptedApp(["09:30", "a", "n"]).press("a", "c")
    assert app.scheduler.has_alarms() is True
    assert app.message == "Cancelled."


def test_c_with_no_alarms_does_not_ask():
    app = ScriptedApp().press("c")
    assert app.questions == []


# -- quitting -------------------------------------------------------------

def test_q_stops_the_loop():
    app = ScriptedApp()
    assert app._running is True
    app.press("q")
    assert app._running is False


def test_keys_are_case_insensitive():
    app = ScriptedApp(["09:30", "standup"]).press("A")
    assert app.scheduler.has_alarms() is True


def test_an_unrecognised_key_is_ignored():
    app = ScriptedApp().press("z", "7", "!")
    assert app.message == ""
    assert app._running is True


# -- while an alarm is ringing --------------------------------------------

def ringing_app(answers=()):
    app = ScriptedApp(["09:00", "wake up", *answers])
    app.press("a")
    app.clock.advance(seconds=3600)  # 09:00 — the alarm is now due
    assert app.scheduler.due_now(), "expected the alarm to be ringing"
    app.questions.clear()  # forget the prompts used to set the alarm up
    return app


def test_ringing_s_snoozes_and_stops_the_alert():
    app = ringing_app().press("s")
    assert app.scheduler.due_now() == []
    assert app.scheduler.list()[0].fire_at == datetime(2026, 9, 23, 9, 5)


def test_ringing_d_dismisses_the_alarm_for_good():
    app = ringing_app().press("d")
    assert app.scheduler.has_alarms() is False
    assert "Dismissed" in app.message


def test_ringing_enter_also_dismisses():
    assert ringing_app().press("\r").scheduler.has_alarms() is False


def test_ringing_ignores_keys_that_would_reconfigure_the_alarm():
    """A stray 'a' or 'c' must not quietly change things mid-alert."""
    app = ringing_app().press("a", "c", "t")
    assert app.questions == []  # nothing was prompted for
    assert app.scheduler.has_alarms() is True
    assert app.scheduler.due_now() != []


def test_ringing_q_still_quits():
    app = ringing_app().press("q")
    assert app._running is False


def test_two_alarms_due_at_once_are_dismissed_together():
    app = ScriptedApp(["09:00", "one", "09:00", "two"])
    app.press("a", "a")
    app.clock.advance(seconds=3600)
    assert len(app.scheduler.due_now()) == 2
    app.press("d")
    assert app.scheduler.has_alarms() is False
    assert "Dismissed 2 alarms" in app.message


# -- the bell -------------------------------------------------------------

class CountingConsole(Console):
    bells = 0

    def bell(self):
        CountingConsole.bells += 1


def test_the_bell_rings_once_per_second_not_once_per_frame():
    CountingConsole.bells = 0
    clock = FakeClock(NOW)
    app = AlarmClockApp(
        AlarmScheduler(clock), clock, console=CountingConsole(file=io.StringIO())
    )
    app._scheduler.add(time(9, 0))
    clock.advance(seconds=3600)  # due

    for _ in range(8):  # eight frames inside the same second
        app._render()
    assert CountingConsole.bells == 1

    clock.advance(seconds=1)
    app._render()
    assert CountingConsole.bells == 2


def test_no_bell_when_nothing_is_ringing():
    CountingConsole.bells = 0
    clock = FakeClock(NOW)
    app = AlarmClockApp(
        AlarmScheduler(clock), clock, console=CountingConsole(file=io.StringIO())
    )
    app._scheduler.add(time(9, 0))
    for _ in range(8):
        app._render()
    assert CountingConsole.bells == 0


# -- audible alarm --------------------------------------------------------

class FakeSound:
    """Stands in for AlarmSound, recording what the app asked of it."""

    def __init__(self, available=True):
        self.available = available
        self.plays = 0
        self.stops = 0
        self.playing = False

    def ensure_playing(self):
        self.plays += 1
        self.playing = True

    def stop(self):
        self.stops += 1
        self.playing = False


def app_with_sound(sound, console=None):
    clock = FakeClock(NOW)
    app = AlarmClockApp(
        AlarmScheduler(clock),
        clock,
        console=console if console is not None else Console(file=io.StringIO()),
        sound=sound,
    )
    app._scheduler.add(time(9, 0), "wake up")
    return app, clock


def test_the_sound_starts_when_an_alarm_comes_due():
    sound = FakeSound()
    app, clock = app_with_sound(sound)
    app._render()
    assert sound.plays == 0  # nothing due yet

    clock.advance(seconds=3600)
    app._render()
    assert sound.playing is True


def test_the_sound_is_nudged_every_frame_so_a_short_clip_loops():
    sound = FakeSound()
    app, clock = app_with_sound(sound)
    clock.advance(seconds=3600)
    for _ in range(5):
        app._render()
    assert sound.plays == 5


def test_dismissing_silences_the_alarm_immediately():
    sound = FakeSound()
    app, clock = app_with_sound(sound)
    clock.advance(seconds=3600)
    app._render()
    app._dispatch("d", live=None, keys=None)
    assert sound.playing is False
    assert sound.stops >= 1


def test_snoozing_silences_the_alarm_immediately():
    sound = FakeSound()
    app, clock = app_with_sound(sound)
    clock.advance(seconds=3600)
    app._render()
    app._dispatch("s", live=None, keys=None)
    assert sound.playing is False


def test_the_sound_stops_once_nothing_is_ringing():
    sound = FakeSound()
    app, clock = app_with_sound(sound)
    clock.advance(seconds=3600)
    app._render()
    app._dispatch("d", live=None, keys=None)
    app._render()
    assert sound.playing is False


def test_the_bell_is_only_used_when_no_sound_is_available():
    """With real audio there's no reason to also rattle the terminal."""
    CountingConsole.bells = 0
    audible = FakeSound(available=True)
    app, clock = app_with_sound(audible, console=CountingConsole(file=io.StringIO()))
    clock.advance(seconds=3600)
    for _ in range(4):
        app._render()
    assert CountingConsole.bells == 0
    assert audible.plays == 4

    CountingConsole.bells = 0
    silent = FakeSound(available=False)
    app, clock = app_with_sound(silent, console=CountingConsole(file=io.StringIO()))
    clock.advance(seconds=3600)
    for _ in range(4):
        app._render()
    assert CountingConsole.bells == 1  # once per second, not per frame
    assert silent.plays == 0
