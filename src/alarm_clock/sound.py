"""Audible alarm playback.

The terminal bell (``\\a``) is unreliable — most terminals ship with it
muted or set to a silent visual flash — so a ringing alarm plays a real
sound file through whatever command-line player the machine has. If
there is no file or no player, callers fall back to the bell.

Playback is a plain subprocess: no audio library, no extra dependency,
and nothing to clean up beyond the process itself.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Sequence

#: The sound file looked for when none is named explicitly.
SOUND_FILENAME = "sound.mp3"

#: Players tried in order, first one installed wins. Each entry is the
#: command plus its flags; the file path is appended as the last
#: argument. Flags are chosen so nothing is printed and no window opens.
PLAYERS: Sequence[Sequence[str]] = (
    ("afplay",),                                              # macOS
    ("paplay",),                                              # PulseAudio
    ("ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"),  # ffmpeg
    ("mpg123", "-q"),
    ("mpv", "--no-video", "--really-quiet"),
    ("aplay", "-q"),                                          # ALSA, WAV only
)


def find_player() -> Optional[List[str]]:
    """The first available player command, or None if there is none."""
    for command in PLAYERS:
        if shutil.which(command[0]):
            return list(command)
    return None


def default_sound_path() -> Optional[Path]:
    """Locate a sound file without being told where to look.

    Checked in order: the working directory, the installed package, and
    the project root above it (which is what an editable install hits).
    """
    here = Path(__file__).resolve()
    candidates = [
        Path.cwd() / SOUND_FILENAME,
        here.parent / SOUND_FILENAME,
        here.parents[2] / SOUND_FILENAME,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


class AlarmSound:
    """Keeps a sound file playing for as long as an alarm is ringing.

    ``ensure_playing`` is safe to call on every frame: it starts the
    clip if nothing is playing and restarts it when it runs out, which
    is what makes a short file ring continuously.
    """

    def __init__(
        self,
        path: Optional[Path] = None,
        player: Optional[List[str]] = None,
    ) -> None:
        """``path`` and ``player`` are both resolved by the caller.

        Discovery lives in ``find_player`` and ``default_sound_path`` so
        that ``None`` here means exactly one thing — "nothing to play
        with" — rather than doubling as "go and look". An instance with
        either missing is inert, and the caller falls back to the bell.
        """
        self._path = path
        self._player = player
        self._process: Optional["subprocess.Popen[bytes]"] = None

    @property
    def available(self) -> bool:
        """Whether a real sound can be played at all."""
        return bool(self._player) and self._path is not None and self._path.is_file()

    @property
    def path(self) -> Optional[Path]:
        return self._path

    def describe(self) -> str:
        """A one-line explanation, for --help style output and errors."""
        if self._path is None:
            return "no sound file found; using the terminal bell"
        if self._player is None:
            return f"no audio player installed; using the terminal bell (found {self._path.name})"
        return f"{self._path.name} via {self._player[0]}"

    def _playing(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def _spawn(self) -> None:
        assert self._player is not None and self._path is not None
        self._process = subprocess.Popen(
            [*self._player, str(self._path)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def ensure_playing(self) -> None:
        """Start the sound, or restart it if the clip has run out."""
        if not self.available or self._playing():
            return
        try:
            self._spawn()
        except OSError:
            # The player vanished between the check and the call, or
            # cannot be executed. Fall back to silence rather than
            # taking the alarm down with it.
            self._player = None
            self._process = None

    def stop(self) -> None:
        """Silence playback. Safe to call when nothing is playing."""
        process, self._process = self._process, None
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=1)
