# Violence-District-Skill-Check-Macro

Hits the circular skill check (red needle, white bar) in Roblox Dead by Daylight-style games.
It watches the screen, follows the needle's speed and direction, and presses the key at the
moment the needle will be over the white bar.

It only looks at the screen and presses a key. It does not read or change the game's memory
and it injects nothing into Roblox.

> **Use it at your own risk.** A macro that plays for you may be against the rules of the game
> you use it in, or of Roblox. Check before you use it, and keep it to private matches with
> people who know.

## What it does

- Finds the skill check by itself at any window size or resolution, and works at any game
  frame rate.
- Aims for the white bar, the middle of the zone, or the white bar only: your choice.
- Handles continuous checks (a chain where a new zone appears after every hit).
- Learns your computer's delay from where each press lands and corrects its own timing.
- Shows a live dial of what it sees and where the last press landed.
- Writes a log, and pictures of every check, so a miss can be worked out afterwards.
- Only acts while Roblox is the window in front. F6 turns it on and off, F7 takes a snapshot,
  F8 quits.

## Get started

**Windows**

1. Install Python 3.10-3.13 (64-bit) from python.org.
2. Download this repository (Code > Download ZIP) and unzip it.
3. Open the `windows` folder and double-click **Skill Check Macro.exe**. The first launch sets
   itself up (a minute or two); after that the same file just opens the macro. No command
   window opens.

More in [windows/README.md](windows/README.md).

**Mac** (Intel and Apple Silicon)

1. Install Python 3.10-3.13 from python.org.
2. Download this repository, unzip it, and open Terminal in the `mac` folder.
3. Run `chmod +x *.command src/find_python.sh`, then right-click **Setup.command** > Open.
4. Give Terminal the Screen Recording, Accessibility and Input Monitoring permissions when asked.

More in [mac/README.md](mac/README.md). Screen capture on macOS is slower and lags more than
on Windows, so the Mac version is less accurate, most of all on fast continuous checks.

## If it doesn't work

- With a skill check on screen, press **F7**. The log then says what the macro found.
- Things that stop it seeing the check: colour filters (HDR, ReShade-style presets), an
  overlay drawn over the ring, a very small Roblox window.
- Each README has an "If it misses" section that explains the log and the saved pictures.

## What's in here

| Folder | What |
| --- | --- |
| `windows` | The Windows version: `Skill Check Macro.exe`, its source in `launcher`, and `src` |
| `mac` | The Mac version: `.command` files and `src` |

Both `src` folders hold the same program. Only `winapi.py` (Windows) and `macapi.py` (Mac)
differ: they find the Roblox window, read the hotkeys and press the key.

## What you need

You install these yourself, before the first launch:

| | Windows | Mac |
| --- | --- | --- |
| System | Windows 10 or 11, 64-bit | macOS on Intel or Apple Silicon |
| Python | 3.10-3.13, 64-bit, from python.org, "tcl/tk and IDLE" ticked | 3.10-3.13 from python.org |
| Other | Internet for the first launch | Internet for the first launch; Screen Recording, Accessibility and Input Monitoring allowed for Terminal |

The first launch installs these by itself, into a private `.venv` folder inside the folder you
run it from. Nothing is installed system-wide:

- `numpy`
- `opencv-python`
- `mss`

## About the exe

`windows/Skill Check Macro.exe` is a small launcher, not the macro itself. It looks for Python,
runs `src/setup_env.py` when the packages aren't there yet, and starts `src/app.py` without a
command window. Its full source is `windows/launcher/launcher.c`. To build it yourself with
[Zig](https://ziglang.org/):

```
zig cc -target x86_64-windows-gnu -O2 -s -municode -Wl,--subsystem,windows launcher.c -o "Skill Check Macro.exe" -lshell32 -luser32 -lgdi32 -lkernel32
```

The exe isn't signed, so Windows may show "Windows protected your PC" the first time
(More info > Run anyway), and some antivirus programs are wary of unsigned launchers.

## Credit

If you copy this code or build your own version on it, say so in your README and link back to
this repository.

## License

MIT. See [LICENSE](LICENSE).
