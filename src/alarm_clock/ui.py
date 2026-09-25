"""Rendering: turns scheduler state into Rich renderables.

Every function here is pure — state in, renderable out, no I/O and no
clock access. That keeps the look of the app testable with a recording
console, and keeps ``tui.py`` down to loop-and-dispatch.
"""

from __future__ import annotations

from datetime import datetime

from rich.align import Align
from rich.box import HEAVY, ROUNDED
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from alarm_clock.models import Alarm

# -- palette --------------------------------------------------------------
# Named once, used everywhere, so the whole app recolors from one place.

ACCENT = "#22d3ee"
MUTED = "#64748b"
ON = "#4ade80"
OFF = "#64748b"
WARN = "#fbbf24"
RING = "#f87171"

#: Vertical gradient for the big clock, bright at the top like a display.
CLOCK_RAMP = ("#67e8f9", "#22d3ee", "#38bdf8", "#60a5fa", "#818cf8")
RINGING_RAMP = ("#fecaca", "#fca5a5", "#f87171", "#ef4444", "#dc2626")

# -- seven-segment digits -------------------------------------------------
# Five rows per glyph, three columns wide, so "HH:MM:SS" lands at 32
# columns — comfortable inside an 80-column terminal.

_GLYPHS = {
    "0": ("███", "█ █", "█ █", "█ █", "███"),
    "1": ("  █", "  █", "  █", "  █", "  █"),
    "2": ("███", "  █", "███", "█  ", "███"),
    "3": ("███", "  █", "███", "  █", "███"),
    "4": ("█ █", "█ █", "███", "  █", "  █"),
    "5": ("███", "█  ", "███", "  █", "███"),
    "6": ("███", "█  ", "███", "█ █", "███"),
    "7": ("███", "  █", "  █", "  █", "  █"),
    "8": ("███", "█ █", "███", "█ █", "███"),
    "9": ("███", "█ █", "███", "  █", "███"),
    ":": ("   ", " █ ", "   ", " █ ", "   "),
    " ": ("   ", "   ", "   ", "   ", "   "),
}

GLYPH_HEIGHT = 5


def big_text(text: str, ramp: tuple[str, ...] = CLOCK_RAMP) -> Text:
    """Render ``text`` as seven-segment blocks, shaded top to bottom.

    Deliberately *not* centred here. Three glyphs — 2, 5 and 6 — have a
    row ending in a space, and Rich strips trailing whitespace from a
    line before applying ``justify``, so a per-line centre would shift
    exactly those rows one column left and visibly break the digits
    once every few seconds. Wrap the result in ``Align.center`` instead:
    it pads every row by the same amount, so the block stays square.

    Characters with no glyph are rendered as blanks rather than raising,
    so a caller can never crash the display over a stray character.
    """
    rendered = Text(no_wrap=True, end="")
    for row in range(GLYPH_HEIGHT):
        line = " ".join(_GLYPHS.get(char, _GLYPHS[" "])[row] for char in text)
        rendered.append(line, style=ramp[row % len(ramp)])
        if row != GLYPH_HEIGHT - 1:
            rendered.append("\n")
    return rendered


# -- formatting helpers ---------------------------------------------------


def format_countdown(delta_seconds: float) -> str:
    """A compact, human countdown: '2h 05m', '18 min', '42 sec', 'now'."""
    seconds = int(delta_seconds)
    if seconds <= 0:
        return "now"
    if seconds < 60:
        return f"{seconds} sec"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} min"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h {minutes:02d}m"
    days, hours = divmod(hours, 24)
    return f"{days}d {hours}h"


def describe_when(fire_at: datetime, now: datetime) -> str:
    """Say which day an alarm falls on, relative to ``now``."""
    if fire_at <= now:
        return "overdue"
    if fire_at.date() == now.date():
        return "today"
    return "tomorrow"


def progress_bar(fraction: float, width: int = 24) -> Text:
    """A filled/unfilled bar, drawn with block characters."""
    filled = int(round(max(0.0, min(1.0, fraction)) * width))
    bar = Text()
    bar.append("█" * filled, style=ACCENT)
    bar.append("░" * (width - filled), style=MUTED)
    return bar


# -- panels ---------------------------------------------------------------


def clock_panel(now: datetime, next_alarm: Alarm | None, ringing: bool = False) -> Panel:
    """The hero panel: big current time, date, and the next deadline."""
    ramp = RINGING_RAMP if ringing else CLOCK_RAMP
    body: list[RenderableType] = [
        Align.center(big_text(now.strftime("%H:%M:%S"), ramp)),
        Align.center(Text(now.strftime("%A, %d %B %Y"), style=f"bold {MUTED}")),
    ]

    if next_alarm is None:
        body.append(Align.center(Text("\nNo alarms armed", style=f"italic {MUTED}")))
    else:
        remaining = (next_alarm.fire_at - now).total_seconds()
        headline = Text("\nNext: ", style=MUTED)
        headline.append(next_alarm.fire_at.strftime("%H:%M"), style=f"bold {ACCENT}")
        if next_alarm.label:
            headline.append(f"  {next_alarm.label}", style="bold white")
        body.append(Align.center(headline))

        countdown = Text()
        countdown.append_text(progress_bar(next_alarm.progress(now)))
        countdown.append("  ")
        countdown.append(format_countdown(remaining), style=f"bold {WARN}")
        body.append(Align.center(countdown))

    return Panel(
        Group(*body),
        box=ROUNDED,
        border_style=RING if ringing else ACCENT,
        padding=(1, 2),
    )


def alarm_table(alarms: list[Alarm], now: datetime) -> Table:
    """The alarm list: state dot, time, label, and when it lands."""
    table = Table(
        box=ROUNDED,
        border_style=MUTED,
        header_style=f"bold {ACCENT}",
        expand=True,
        pad_edge=False,
        padding=(0, 1),
    )
    table.add_column("", width=1, justify="center")
    table.add_column("ID", width=2, justify="right", style=MUTED)
    table.add_column("TIME", width=5, style="bold")
    table.add_column("LABEL", ratio=1, overflow="ellipsis")
    table.add_column("WHEN", width=8)
    table.add_column("STATUS", width=6, justify="right")

    if not alarms:
        table.add_row("", "", "", Text("no alarms yet — press A to add one", style=f"italic {MUTED}"), "", "")
        return table

    for alarm in alarms:
        when = describe_when(alarm.fire_at, now)
        if not alarm.enabled:
            dot, status, row_style = "○", Text("OFF", style=OFF), OFF
        elif when == "overdue":
            dot, status, row_style = "●", Text("DUE", style=f"bold {RING}"), RING
        else:
            dot, status, row_style = "●", Text("ON", style=ON), "white"

        label = Text(alarm.label or "—", style=row_style)
        if alarm.snoozes:
            label.append(f"  (snoozed ×{alarm.snoozes})", style=f"italic {WARN}")

        table.add_row(
            Text(dot, style=ON if alarm.enabled else OFF),
            str(alarm.id),
            Text(alarm.fire_at.strftime("%H:%M"), style=row_style),
            label,
            Text(when, style=WARN if when == "overdue" else MUTED),
            status,
        )
    return table


def _key(key: str, action: str) -> Text:
    hint = Text()
    hint.append(f" {key} ", style=f"bold black on {ACCENT}")
    hint.append(f" {action}", style=MUTED)
    return hint


def footer(ringing: bool = False) -> Group:
    """The key hints along the bottom, laid out in rows that always fit."""
    rows = (
        [[("S", "Snooze 5m"), ("D", "Dismiss"), ("Q", "Quit")]]
        if ringing
        else [
            [("A", "Add"), ("T", "Toggle"), ("S", "Snooze")],
            [("D", "Delete"), ("C", "Clear all"), ("Q", "Quit")],
        ]
    )
    lines = []
    for row in rows:
        line = Text(justify="center")
        for index, (key, action) in enumerate(row):
            if index:
                line.append("   ")
            line.append_text(_key(key, action))
        lines.append(Align.center(line))
    return Group(*lines)


def banner(ringing: list[Alarm]) -> Panel:
    """The full-width alert shown while one or more alarms are ringing."""
    body = Text(justify="center")
    body.append("\n")
    for alarm in ringing:
        body.append("⏰  ", style=RING)
        body.append(alarm.fire_at.strftime("%H:%M"), style=f"bold {RING}")
        if alarm.label:
            body.append(f"  —  {alarm.label}", style="bold white")
        body.append("\n")
    body.append("\n")
    title = "ALARM" if len(ringing) == 1 else f"{len(ringing)} ALARMS"
    return Panel(
        body,
        title=Text(f"🔔  {title} RINGING", style=f"bold {RING}"),
        box=HEAVY,
        border_style=RING,
        padding=(0, 2),
    )


def status_line(message: str, style: str = MUTED) -> Text:
    return Text(message, style=style, justify="center")


def dashboard(
    alarms: list[Alarm],
    now: datetime,
    next_alarm: Alarm | None,
    ringing: list[Alarm] | None = None,
    message: str = "",
) -> Group:
    """The whole screen, assembled top to bottom."""
    ringing = ringing or []
    parts: list[RenderableType] = [
        Align.center(Text("⏰  A L A R M   C L O C K", style=f"bold {ACCENT}")),
        clock_panel(now, next_alarm, ringing=bool(ringing)),
    ]
    if ringing:
        parts.append(banner(ringing))
    parts.append(alarm_table(alarms, now))
    parts.append(status_line(message or " "))
    parts.append(footer(ringing=bool(ringing)))
    return Group(*parts)
