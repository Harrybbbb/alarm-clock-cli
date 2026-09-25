"""Composition root: wires the real clock and scheduler into a front end."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from alarm_clock.cli import run_repl
from alarm_clock.clock import SystemClock
from alarm_clock.scheduler import AlarmScheduler
from alarm_clock.sound import AlarmSound, default_sound_path, find_player
from alarm_clock.tui import run_tui


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alarm-clock",
        description="An interactive command-line alarm clock.",
    )
    parser.add_argument(
        "--classic",
        action="store_true",
        help="use the plain line-based prompt instead of the live display",
    )
    parser.add_argument(
        "--sound",
        metavar="FILE",
        type=Path,
        help="audio file to play when an alarm rings "
        "(default: sound.mp3, looked for next to the project or in the "
        "working directory)",
    )
    parser.add_argument(
        "--no-sound",
        action="store_true",
        help="never play audio; fall back to the terminal bell",
    )
    return parser


def resolve_sound(args: argparse.Namespace) -> AlarmSound:
    """Pick the alarm sound, failing loudly only on an explicit bad path."""
    if args.no_sound:
        return AlarmSound()
    if args.sound is not None:
        if not args.sound.is_file():
            raise SystemExit(f"alarm-clock: no such sound file: {args.sound}")
        return AlarmSound(path=args.sound, player=find_player())
    return AlarmSound(path=default_sound_path(), player=find_player())


def main(argv: Optional[List[str]] = None) -> None:
    args = build_parser().parse_args(argv)

    # Resolved before choosing a front end, so a bad --sound path is
    # reported even in classic mode, which doesn't use it.
    sound = resolve_sound(args)

    clock = SystemClock()
    scheduler = AlarmScheduler(clock)

    # The live display needs a terminal to put into cbreak mode and to
    # redraw over. Piped or redirected input gets the line-based prompt
    # instead of a crash or a screenful of escape codes.
    if args.classic or not sys.stdin.isatty():
        run_repl(scheduler, now_fn=clock.now)
    else:
        run_tui(scheduler, clock, sound=sound)


if __name__ == "__main__":
    main()
