# Skill Check Macro (Mac)

Hits the circular skill check (red needle, white bar) in the Roblox DBD-style
game automatically. It watches the screen, follows the needle's speed and
direction, and presses at the predicted moment the needle is over the white bar.
It never reads or changes the game's memory. It only looks at the screen and
presses a key, like you would.

This folder is the Mac version (Intel and Apple Silicon). The Windows version is in the `windows` folder.

## Setup

1. Install Python 3.10-3.13 from https://www.python.org/downloads/macos/ (the python.org
   installer is best; it includes the Tk window toolkit).
2. Move this folder somewhere normal (Documents, Desktop), not inside iCloud Drive.
3. The first time only, open Terminal in this folder and run
   `chmod +x *.command src/find_python.sh`
   (a download from GitHub doesn't keep the "can be run" mark on these files). Then
   **right-click Setup.command > Open > Open** (macOS blocks double-clicking downloaded
   scripts the first time). It installs everything.
4. Start it with **Launch.command** (right-click > Open the first time). Keep the Terminal
   window it opens running; closing it quits the macro.
5. **Give Terminal three permissions** in System Settings > Privacy & Security:
   - **Screen Recording**, so it can see the skill check (without it, it sees nothing)
   - **Accessibility**, so it can press the key
   - **Input Monitoring**, so the F6/F7/F8 hotkeys work
   The macro asks for these the first time. After turning them on, **quit Terminal
   completely (Cmd+Q)** and start Launch.command again.

**F6** turns it on and off. **F7** writes a snapshot of what it sees to log.txt. **F8** quits. It only acts while the Roblox window is in front, and the hotkeys only work while Roblox or the macro's own window is in front (so F8 in another app doesn't quit it).
On Mac keyboards the top row is media keys by default, so press **fn+F6 / fn+F7 / fn+F8**
(or turn on "Use F1, F2, etc. keys as standard function keys" in System Settings > Keyboard).

## Files

- **Setup.command**: first-time install (makes a private Python in `.venv` inside this folder).
- **Launch.command**: starts the macro (it re-runs setup by itself if `.venv` is missing or broken).
- **Check Screenshot.command**: shows what the macro detects in a screenshot you drag into it.
- **src**: the program. `macapi.py` and `find_python.sh` are the Mac-only parts.
- Made while it runs: `config.json` (your settings), `log.txt`, `debug_screenshots`.

## Mac notes

- Works in windowed or full-screen Roblox, on Intel and Apple Silicon Macs, with Retina screens.
- Screen capture on macOS is slower than on Windows. If the fps shown in the window is low
  (under ~40), make the Roblox window smaller or lower the display resolution, and leave
  **Adjust timing by itself** on.
- macOS screen capture lags behind what's actually on screen (often 150-300 ms), so presses land
  late. The Mac version starts at a Timing offset of +150 and **Adjust timing by itself** learns the rest
  within a few skill checks. If presses still land late, raise the offset (it goes up to 400).

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
    start of the zone, so aiming at it leaves almost no room for an early press; with the timing
    jitter of Mac screen capture an early press misses the zone completely. Default on Mac.
  - Continuous checks (Merciless-style chains) always aim for the middle of the zone, unless
    *White bar only* is picked: a normal hit keeps the chain going, a miss ends it.
- **Timing offset (ms)**: if presses land slightly late, raise it (presses earlier). If early, lower it. On Mac it starts at +150 (see Mac notes). Change it in steps of 5-10.
- **Adjust timing by itself** (on by default): after each press the game freezes the needle where the press landed. The macro measures that and corrects the timing offset by itself, so it adapts to your Mac's delay. Every press and landing is written to `log.txt` (IN/OUT, early/late by how many ms). A press that went down late because the skill check was spotted too late is not blamed on the offset (the log says "behind plan"), and at low game fps it waits a few game frames before deciding the needle has really stopped.

## How it works

1. It looks for the ring on every frame (a fast search, about 5 ms), so it catches a skill check the moment it appears. It then follows it as fast as screen capture allows.
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
- Press **fn+F7** while a skill check is on screen to add a line saying what it detects right then.
- Open **Check Screenshot.command** and drag a screenshot of a skill check into its window to see what it detects in that picture.
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
  purple = needle. The newest 150 checks are kept. **fn+F7** also saves a snapshot folder of the whole
  window. **To report a problem, open an issue with the log lines for the checks that went wrong.** Look at the pictures before you post any: they are screenshots of your game and can show your username.
