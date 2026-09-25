# Alarm Clock CLI

An interactive command-line alarm clock with a live, colourful terminal
UI: a seven-segment clock, a countdown to the next alarm, and an alarm
list you drive with single keypresses. Built as a take-home exercise —
see [Scope & assumptions](#scope--assumptions) for the reasoning behind
what is and isn't included.

## Requirements

- Python 3.9+
- [Rich](https://github.com/Textualize/rich) for the terminal UI — the
  only Python dependency. `pytest` and `mypy` are used for development.
- Optionally, a command-line audio player for the alarm sound: `afplay`
  (built into macOS), or `paplay`, `ffplay`, `mpg123`, `mpv` or `aplay`
  on Linux. Without one the app falls back to the terminal bell.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"   # installs the `alarm-clock` command + pytest + mypy
```

For the application alone, without the development tools, `pip install -e .`
is enough.

## Running

Once installed (per Setup above), either of these is equivalent:

```bash
alarm-clock
# or, invoking the module directly:
python3 -m alarm_clock.main
```

You'll get a live display that redraws every second:

```
                     ⏰  A L A R M   C L O C K
╭─────────────────────────────────────────────────────────────────────╮
│              ███ ███     ███ █ █     █ █ ███                        │
│                █   █  █  █ █ █ █  █  █ █   █                        │
│              ███ ███     █ █ ███     ███   █                        │
│              █     █  █  █ █   █  █    █   █                        │
│              ███ ███     ███   █       █   █                        │
│                 Wednesday, 23 September 2026                        │
│                                                                     │
│                   Next: 08:00  Morning Alarm                        │
│               ████████████████░░░░░░░░  17 min                      │
╰─────────────────────────────────────────────────────────────────────╯
╭──┬────┬───────┬────────────────────────────┬──────────┬───────╮
│  │ ID │ TIME  │ LABEL                      │ WHEN     │ STATUS│
├──┼────┼───────┼────────────────────────────┼──────────┼───────┤
│● │  1 │ 08:00 │ Morning Alarm              │ today    │     ON│
│● │  2 │ 13:30 │ Lunch                      │ today    │     ON│
│○ │  3 │ 22:00 │ Sleep                      │ today    │    OFF│
╰──┴────┴───────┴────────────────────────────┴──────────┴───────╯
                  A  Add    T  Toggle    S  Snooze
                D  Delete    C  Clear all    Q  Quit
```

## Keys

| Key | Action |
|---|---|
| `A` | Add an alarm — prompts for a 24-hour `HH:MM` and an optional label. |
| `T` | Toggle an alarm on or off. A disabled alarm keeps its place in the list but never rings. |
| `S` | Snooze the next alarm by 5 minutes. |
| `D` | Delete an alarm by id. |
| `C` | Clear every alarm (asks first). |
| `Q` | Quit. Ctrl+C also works. |

When an alarm comes due the display turns red, a `🔔 ALARM RINGING`
banner appears, and the alarm sound starts. The keys narrow to the only
two that make sense:

| Key | Action |
|---|---|
| `S` | Snooze 5 minutes. The alarm returns to the list marked `(snoozed ×1)`. |
| `D` | Dismiss — deletes the alarm. `Enter` and `Space` do the same. |

A ringing alarm keeps ringing until you answer it; it is never
dismissed for you. Keys that would reconfigure an alarm are ignored
while one is ringing, so a stray keypress can't silently change
anything.

## Sound

A ringing alarm plays `sound.mp3` on a loop until you snooze or dismiss
it — short clips restart automatically, so the alarm keeps sounding
rather than playing once and going quiet.

The file is found without configuration: the working directory first,
then the installed package, then the project root. To use a different
one, or none:

```bash
alarm-clock --sound ~/Music/wake-up.wav
alarm-clock --no-sound
```

Playback shells out to whichever player is installed (`afplay` on
macOS; `paplay`, `ffplay`, `mpg123`, `mpv` or `aplay` on Linux) — no
audio library, no extra dependency. If there is no player or no sound
file, the alarm falls back to the terminal bell (`\a`). That fallback
is genuinely a fallback: most terminals ship with the bell muted or set
to a silent visual flash, which is exactly why a real sound file is
preferred.

If today's `HH:MM` has already passed when you add the alarm (or is the
exact current minute), it is scheduled for tomorrow instead.

Two alarms may share the same `HH:MM`; both fire, in the order they were
added.

## Classic mode

The original line-based prompt is still there:

```bash
alarm-clock --classic
```

```
> add 07:30 wake up
Added alarm #1 for 07:30 (wake up)
> list
  #1  07:30 today (wake up)
> start
Waiting for alarms. Press Ctrl+C to stop and return to the prompt.
```

Commands: `add HH:MM [label]`, `list`, `remove <id>`, `start`, `help`,
`quit`. **Ctrl+C** cancels the line you're typing, or stops `start`;
either way your alarms are kept. **Ctrl+D** exits.

Piping or redirecting input selects classic mode automatically — the
live display needs a real terminal, and printing escape codes into a
pipe helps nobody:

```bash
printf 'add 09:00 standup\nlist\nquit\n' | alarm-clock
```

## Running tests

```bash
pytest          # 219 tests
mypy            # strict type check of src/alarm_clock
```

The suite runs in well under a second — including tests that exercise an
alarm "waiting" 12 hours and firing, with no real delay (see
[Design notes](#design-notes)).

## Project structure

```
src/alarm_clock/
  clock.py       # Clock abstraction: SystemClock (real), FakeClock (tests)
  models.py      # Alarm dataclass + next_occurrence() time math
  scheduler.py   # In-memory alarm store, next-due lookup, deadline wait
  ui.py          # Pure render functions: digits, panels, table, footer
  sound.py       # Finds a player and a file; loops playback while ringing
  keyboard.py    # Single-keypress terminal input with a timeout
  tui.py         # The live display's loop and key dispatch
  cli.py         # Classic mode: command parsing, handlers, REPL loop
  main.py        # Picks a front end and wires the clock + scheduler in
tests/
  test_models.py
  test_scheduler.py
  test_ui.py
  test_sound.py
  test_tui.py
  test_cli.py
```

## Design notes

- **No persistence.** Alarms exist only for the current process. This
  was an explicit choice given the "no database" constraint and time
  budget, not an oversight — see [Scope & assumptions](#scope--assumptions).
- **One injected dependency: the clock.** `AlarmScheduler` never calls
  `datetime.now()` or `time.sleep()` directly — it receives a `Clock`.
  Production uses `SystemClock`; tests use `FakeClock`, whose `sleep()`
  advances a virtual clock instead of actually waiting. This is what
  lets a test simulate an alarm firing hours later in milliseconds.
- **A fire time is resolved once, at creation.** An `Alarm` stores a
  concrete `fire_at` datetime, computed by `next_occurrence()` when the
  alarm is added and never recomputed. Deriving it repeatedly from a
  moving "now" is subtly wrong in two ways: a second alarm set for the
  same minute would be pushed a full day out the instant the first one
  fired, and an alarm whose time passed while the user was still typing
  would silently become tomorrow's alarm. `Alarm.time` is a property
  over `fire_at`, so there is only one source of truth.
- **Deadline-based waiting, not polling.** `wait_for_next()` computes
  the seconds remaining until the deadline and makes a single
  `clock.sleep(seconds)` call. It sleeps again only if that call came
  back early — `time.sleep` can be cut short by a signal, and ringing an
  alarm ahead of time is worse than sleeping twice. Sub-millisecond
  remainders count as arrival, and a clock that fails to advance at all
  raises `ClockError` rather than spinning forever.
- **CLI is a thin shell.** `cli.py` never touches time directly; it
  only calls into `AlarmScheduler`, which is what keeps the scheduling
  logic testable independent of any I/O.
- **Integer ids, not time-based identity.** Two alarms can share the
  same `HH:MM`, so alarm identity is an auto-incrementing counter
  assigned by the scheduler, not the time value itself. Ties in firing
  order are broken by id, so equal-time alarms fire in the order added.
- **Ctrl+C never destroys state.** At the prompt it abandons the
  half-typed line; during `start` it stops waiting; in the live display
  it quits cleanly, restoring the terminal. Neither discards alarms.
- **Rendering is pure.** Every function in `ui.py` takes state and
  returns a Rich renderable — no I/O, no clock access. That is what
  lets the whole look of the app be asserted against a recording
  console in `test_ui.py`, rather than eyeballed.
- **Polling in the UI, sleeping in the scheduler.** The live display
  can't block in `wait_for_next()` — it has to redraw and read keys —
  so the scheduler also exposes `due_now()`, a non-blocking "what has
  arrived?" query. Classic mode keeps the sleeping path. Both read the
  same `fire_at` field, so they can't disagree about when an alarm is
  due.
- **A ringing alarm is not auto-removed.** `due_now()` reports; only
  the user's snooze or dismiss mutates. An alarm you slept through is
  still there when you come back.
- **The big clock is centred as a block, not line by line.** Rich
  strips trailing whitespace from a line before applying `justify`, and
  three glyphs — 2, 5 and 6 — have a row that ends in a space. Centring
  each row individually therefore shifted exactly those rows one column
  left, visibly distorting the clock for 18 seconds out of every 60.
  `big_text` returns an unjustified block and the caller wraps it in
  `Align.center`, which pads every row equally. `test_ui.py` checks all
  sixty seconds.
- **Sound is a subprocess, not a dependency.** Playing audio portably
  from Python means a native extension or a large library; shelling out
  to a player that is already installed costs one `shutil.which` call
  and degrades cleanly to the terminal bell. The clip is restarted when
  it ends, which is what makes a seven-second file ring continuously,
  and stopped on the keypress rather than on the next frame so
  dismissing feels immediate.
- **cbreak, not raw, terminal mode.** Keys arrive unbuffered, but
  Ctrl+C still raises `SIGINT`, so the standard way out of a terminal
  program keeps working.
- **The terminal is checked, not assumed.** `main.py` falls back to the
  classic prompt when stdin isn't a tty, so piping into the app gives
  readable output instead of escape codes.

## Scope & assumptions

Explicitly **out of scope** for this exercise (noted here rather than
silently omitted):

- Persistence across runs (no database was a hard constraint; a
  flat-file workaround was considered and rejected as scope creep for
  a 30-minute build)
- Recurring alarms (daily / weekdays)
- Timezone handling (uses system local time)
- Sound files / external notification services
- Adding alarms concurrently while `start` is waiting, in classic mode
  (by design — avoids background-thread complexity; add all alarms,
  then `start`). The live display has no such limitation: it polls on a
  timer, so alarms can be added, toggled and snoozed at any time,
  including while another is ringing.

**Assumptions:**
- Single user, single timezone (system local time).
- Adding an alarm for the exact current minute means tomorrow, not
  "immediately" — otherwise `add` would fire before the user could
  finish setting up.
- `start` waits for *all* currently-set alarms in chronological order,
  not just the next one, returning to the prompt once the list is
  empty or the user interrupts.
- An alarm whose time passes while the user is still at the prompt is
  **overdue**, not rescheduled. `list` marks it as such and `start`
  fires it immediately. A late alarm is more useful than a silent one.

## Possible future improvements

(Not implemented — listed here rather than built, per the exercise's
guidance not to add unrequested features.)

- Optional JSON-file persistence between runs
- Recurring/daily alarms
- Editing an existing alarm's time/label instead of remove-then-add
- A configurable snooze interval (currently fixed at 5 minutes)
# alarm-clock-cli
