# Skill Check Macro (Windows)

Hits the circular skill check (red needle, white bar) in the Roblox DBD-style
game automatically. It watches the screen, follows the needle's speed and
direction, and presses at the predicted moment the needle is over the white bar.
It never reads or changes the game's memory. It only looks at the screen and
presses a key, like you would.

This folder is the Windows version. The Mac version is in the `mac` folder.

## Setup

1. Install Python 3.10-3.13 (64-bit) from python.org. Leave the installer's options as they are
   ("tcl/tk and IDLE" has to stay ticked).
2. Double-click **Skill Check Macro.exe**. The first time, a small "first launch" box shows while it
   downloads three Python packages into this folder (a minute or two, needs internet). Then the
   macro's window opens.
3. From then on the same file opens the macro straight away. Keep Roblox as the active window.

No black command window opens at any point. Windows may show "Windows protected your PC" the first
time, because the file isn't signed: click **More info**, then **Run anyway**.

### What you need

Not installed for you (have these before the first launch):

- Windows 10 or 11, 64-bit
- Python 3.10, 3.11, 3.12 or 3.13, 64-bit, from python.org, with "tcl/tk and IDLE" ticked (it is by default)
- An internet connection for the first launch

Installed by itself on the first launch, into a `.venv` folder next to the exe (nothing system-wide):

- `numpy`
- `opencv-python`
- `mss`

**F6** turns it on and off. **F7** writes a snapshot of what it sees to log.txt. **F8** quits. It only acts while the Roblox window is in front, and the hotkeys only work while Roblox or the macro's own window is in front (so F8 in another app doesn't quit it).

## Files

- **Skill Check Macro.exe**: sets things up the first time, then starts the macro. It is a small
  launcher: it finds Python, runs `src/setup_env.py` if needed, and starts `src/app.py`. Its
  source is `launcher/launcher.c`.
- **src**: the program. `winapi.py` is the Windows-only part.
- Made while it runs: `.venv`, `config.json` (your settings), `log.txt`, `debug_screenshots`,
  and `setup-log.txt` (what the first launch did).

## The window

- The dial at the top left shows the skill check as the macro sees it while one is on screen (ring, zone, white bar,
  red needle). Between checks it shows where the last press landed: green = on target, red = missed.
- Next to it: what the macro is doing (Watching, Skill check, Paused, Waiting for Roblox, Off) and a tally,
  e.g. "14 seen, 13 pressed, 12 of 13 on target".
- Only one copy runs at a time. Starting it again just tells you it is already running.

## Settings

- **Press**: the key the game uses for skill checks (Space by default, or Left click, E, F...).
- **Aim for**:
  - *White bar, else outlined zone*: aims for the middle of the white bar; if a check has no white bar, it aims for the outlined zone.
    At low game fps (or with a very fast needle) a press can only land on whole game frames, so it aims at the part of
    the white bar next to the rest of the zone: missing the bar on that side is still a normal hit, missing it on the
    other side misses the zone. If a press comes too late for the white bar but the needle is still in the zone, it
    presses for a normal hit.
  - *White bar only*: never settles for the outlined zone.
  - *Middle of zone (safest, best on Mac)*: aims for the middle of the whole zone. Gives a normal
    hit instead of a great, but has ~25 degrees of room either side. The white bar sits at the very
    start of the zone, so aiming at it leaves almost no room for an early press.
  - Continuous checks (Merciless-style chains) always aim for the middle of the zone, unless
    *White bar only* is picked: a normal hit keeps the chain going, a miss ends it.
- **Timing offset (ms)**: if presses land slightly late, raise it (presses earlier). If early, lower it. Start at 0. Change it in steps of 5-10.
- **Adjust timing by itself** (on by default): after each press the game freezes the needle where the press landed. The macro measures that and corrects the timing offset by itself, so it adapts to your PC's delay. Every press and landing is written to `log.txt` (IN/OUT, early/late by how many ms). A press that went down late because the skill check was spotted too late is not blamed on the offset (the log says "behind plan"), and at low game fps it waits a few game frames before deciding the needle has really stopped.

## How it works

1. It looks for the ring on every frame (a fast search, about 5 ms), so it catches a skill check the moment it appears. It then follows it at about 100 frames per second.
2. It unwraps the ring and reads three things by angle:
   - the outlined zone: white edges with a black inside
   - the white bar: solid white across the ring
   - the red needle: red inside the ring only, so red objects in the background are ignored
3. It measures the needle's speed and direction over the last few frames, works out when the needle will be over the middle of the white bar, and presses then. It allows for the delay between the key press and the game reading it.
4. One press per skill check. For continuous checks (a Merciless-style perk where the needle keeps spinning and a new zone appears after each hit), it re-arms as soon as the zone jumps to a new spot, and re-measures the needle speed because it speeds up after each hit.
5. To avoid pressing on look-alikes in the scenery, the ring must be a thin grey/white line that stands out from its surroundings, be a normal skill-check size, and sit near the middle of the screen.

All of it scales with the ring size, so any window size or resolution works.

## If it misses

- Open **log.txt** (**Open log** button in the window). Each skill check gets a PRESS line (needle, aim, speed, zone) and a LANDED line (where the press actually landed, IN or OUT of the white bar, early/late in ms). Checks it didn't press on say why.
- Press **F7** while a skill check is on screen to add a line saying what it detects right then.
- Click **Test a screenshot** in the macro's window and pick a screenshot of a skill check to see what it detects in that picture.
- Always a bit late or early: leave **Adjust timing by itself** on, or adjust **Timing offset** by hand.
- The log keeps itself under about 1 MB.
- **Debug folders (on by default):** every skill check gets its own folder in `debug_screenshots`
  (button: **Open pictures**), named with the time and check number, e.g.
  `20261109_152710_C005` (`_chain` = the next zone of a continuous check). Inside:
  `1_seen.png` (when it appeared), `2_press.png` (the frame it pressed on), `3_landed_IN/OUT.png`
  (where the press landed), `nopress.png` or `end.png` (the last frame with the check on screen),
  each with a `_raw` copy without markings, plus `details.txt` (settings, fps, what it saw, every log line for that check, and a
  frame-by-frame list of the needle angle and zones). Checks it didn't press also get up to 12
  `during` pictures from the middle of the check. The same id is at the end of each line in log.txt.
  Colors: cyan = ring, orange = zone, green = white bar (thick green tick = where it aimed),
  purple = needle. The newest 150 checks are kept. **F7** also saves a snapshot folder of the whole
  window. **To report a problem, open an issue with the log lines for the checks that went wrong.** Look at the pictures before you post any: they are screenshots of your game and can show your username.
