"""Playback control, exercised with stand-in players instead of audio.

``tail -f`` stands in for a long clip and ``true`` for one that ends
immediately, so the start/restart/stop logic is tested against real
subprocesses without making a sound.
"""

import io
import time

import pytest

from alarm_clock.sound import SOUND_FILENAME, AlarmSound, default_sound_path, find_player

LONG_PLAYER = ["tail", "-f"]      # runs until terminated
INSTANT_PLAYER = ["true"]         # exits straight away


@pytest.fixture
def sound_file(tmp_path):
    path = tmp_path / "alarm.mp3"
    path.write_bytes(b"not really audio")
    return path


def wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


# -- availability ---------------------------------------------------------

def test_not_available_without_a_file():
    assert AlarmSound(path=None, player=LONG_PLAYER).available is False


def test_not_available_when_the_file_is_missing(tmp_path):
    missing = tmp_path / "nope.mp3"
    assert AlarmSound(path=missing, player=LONG_PLAYER).available is False


def test_not_available_without_a_player(sound_file):
    assert AlarmSound(path=sound_file, player=None).available is False


def test_available_with_both(sound_file):
    assert AlarmSound(path=sound_file, player=LONG_PLAYER).available is True


def test_ensure_playing_is_a_no_op_when_unavailable():
    sound = AlarmSound(path=None, player=None)
    sound.ensure_playing()  # must not raise
    assert sound._playing() is False


# -- starting and looping -------------------------------------------------

def test_ensure_playing_starts_the_player(sound_file):
    sound = AlarmSound(path=sound_file, player=LONG_PLAYER)
    try:
        sound.ensure_playing()
        assert sound._playing() is True
    finally:
        sound.stop()


def test_repeated_calls_do_not_stack_up_players(sound_file):
    """The render loop calls this several times a second."""
    sound = AlarmSound(path=sound_file, player=LONG_PLAYER)
    try:
        pids = set()
        for _ in range(25):
            sound.ensure_playing()
            pids.add(sound._process.pid)
        assert len(pids) == 1
    finally:
        sound.stop()


def test_the_clip_restarts_when_it_finishes(sound_file):
    """A short file has to loop, or the alarm falls silent after once."""
    sound = AlarmSound(path=sound_file, player=INSTANT_PLAYER)
    sound.ensure_playing()
    first = sound._process.pid
    assert wait_until(lambda: sound._process.poll() is not None), "clip should end"

    sound.ensure_playing()
    assert sound._process.pid != first


# -- stopping -------------------------------------------------------------

def test_stop_terminates_playback(sound_file):
    sound = AlarmSound(path=sound_file, player=LONG_PLAYER)
    sound.ensure_playing()
    process = sound._process
    sound.stop()
    assert process.poll() is not None
    assert sound._playing() is False


def test_stop_is_safe_when_nothing_is_playing(sound_file):
    sound = AlarmSound(path=sound_file, player=LONG_PLAYER)
    sound.stop()
    sound.ensure_playing()
    sound.stop()
    sound.stop()  # twice in a row must not raise


def test_a_player_that_cannot_be_executed_degrades_to_silence(sound_file):
    sound = AlarmSound(path=sound_file, player=["definitely-not-a-real-binary"])
    sound.ensure_playing()  # OSError is swallowed
    assert sound.available is False
    assert sound._playing() is False


# -- discovery and description --------------------------------------------

def test_find_player_returns_a_command_or_nothing():
    player = find_player()
    assert player is None or (isinstance(player, list) and player)


def test_default_sound_path_finds_the_project_file():
    """The repo ships a sound.mp3 at its root."""
    found = default_sound_path()
    assert found is not None and found.name == SOUND_FILENAME


def test_describe_explains_each_fallback(sound_file):
    assert "terminal bell" in AlarmSound(path=None, player=LONG_PLAYER).describe()
    assert "terminal bell" in AlarmSound(path=sound_file, player=None).describe()
    described = AlarmSound(path=sound_file, player=LONG_PLAYER).describe()
    assert "alarm.mp3" in described and "tail" in described


# -- command line ---------------------------------------------------------

def run_main(argv, monkeypatch):
    """main() with stdin non-interactive, so it takes the classic path."""
    import sys
    from alarm_clock import main as main_module

    monkeypatch.setattr(sys, "stdin", io.StringIO("quit\n"))
    monkeypatch.setattr(main_module, "run_repl", lambda *a, **k: None)
    monkeypatch.setattr(main_module, "run_tui", lambda *a, **k: None)
    main_module.main(argv)


def test_a_missing_sound_file_is_reported_even_in_classic_mode(monkeypatch):
    """The flag is wrong whichever front end ends up running."""
    with pytest.raises(SystemExit) as exit_info:
        run_main(["--classic", "--sound", "/definitely/not/here.mp3"], monkeypatch)
    assert "no such sound file" in str(exit_info.value)


def test_a_valid_sound_file_is_accepted(monkeypatch, sound_file):
    run_main(["--sound", str(sound_file)], monkeypatch)  # must not raise


def test_no_sound_flag_disables_audio(monkeypatch):
    import argparse
    from alarm_clock.main import resolve_sound

    sound = resolve_sound(argparse.Namespace(no_sound=True, sound=None))
    assert sound.available is False
