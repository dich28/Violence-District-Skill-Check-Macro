from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import threading
import time
import tk_fix
tk_fix.fix()
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

import cv2
import mss
import numpy as np

import platform_api as winapi
from engine import OFFSET_LIMIT, SPIN_SEC, Engine, Settings
from predictor import zones

MAC = sys.platform == "darwin"
SETUP_FILE = "Setup.command" if MAC else "Skill Check Macro.exe"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "config.json")
LOG = os.path.join(ROOT, "log.txt")
SHOTS = os.path.join(ROOT, "debug_screenshots")
AIMS = ("White bar, else outlined zone", "White bar only", "Middle of zone (safest, best on Mac)")

INK = "#1c1a24"
PANEL = "#262331"
LINE = "#383447"
TEXT = "#eeecf4"
MUTED = "#9c98ad"
RING = "#6f6a84"
ZONE = "#5d5874"
NEEDLE = "#f0525f"
HIT = "#62d394"
WAIT = "#f1bb5e"

STATES = {
    "starting": ("Starting", MUTED),
    "off": ("Off", MUTED),
    "waiting": ("Waiting for Roblox", WAIT),
    "paused": ("Paused", WAIT),
    "watching": ("Watching", HIT),
    "check": ("Skill check", NEEDLE),
    "error": ("Something went wrong", NEEDLE),
}


def load() -> dict:
    cfg = {"key": "Space", "aim": AIMS[0], "offset_ms": 0, "keep_log": True, "on_top": True, "auto_timing": True,
           "debug_shots": True}
    if MAC:
        cfg["offset_ms"] = 150
        cfg["aim"] = AIMS[2]
    try:
        with open(CONFIG, encoding="utf-8") as f:
            saved = json.load(f)
    except (OSError, ValueError):
        return cfg
    if not isinstance(saved, dict):
        return cfg
    for k, default in list(cfg.items()):
        v = saved.get(k)
        if isinstance(default, bool):
            if isinstance(v, bool):
                cfg[k] = v
        elif k == "offset_ms":
            if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
                cfg[k] = int(max(-OFFSET_LIMIT, min(OFFSET_LIMIT, round(v))))
        elif k == "key":
            if v in winapi.KEY_CHOICES:
                cfg[k] = v
        elif k == "aim":
            if v in AIMS:
                cfg[k] = v
    return cfg


def spin_for_this_pc() -> float:
    worst = 0.0
    for _ in range(5):
        t = time.perf_counter()
        time.sleep(0.001)
        worst = max(worst, time.perf_counter() - t)
    return SPIN_SEC if worst < 0.004 else min(0.025, worst + 0.003)


def save(cfg: dict) -> None:
    try:
        tmp = CONFIG + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        os.replace(tmp, CONFIG)
    except OSError:
        pass


class Grabber:

    def __init__(self) -> None:
        self._sct = None

    def __call__(self, x: int, y: int, w: int, h: int) -> np.ndarray | None:
        try:
            if self._sct is None:
                self._sct = mss.mss()
            shot = self._sct.grab({"left": int(x), "top": int(y), "width": int(w), "height": int(h)})
        except Exception:
            try:
                if self._sct is not None:
                    self._sct.close()
            except Exception:
                pass
            self._sct = None
            return None
        img = np.asarray(shot, dtype=np.uint8)[:, :, :3]
        if img.shape[1] != int(w) or img.shape[0] != int(h):
            img = cv2.resize(img, (int(w), int(h)), interpolation=cv2.INTER_AREA)
        return np.ascontiguousarray(img)


class Switch(tk.Canvas):

    def __init__(self, master, variable: tk.BooleanVar, command, k: float) -> None:
        self.w, self.h = int(38 * k), int(20 * k)
        super().__init__(master, width=self.w, height=self.h + 4, bg=master["bg"], highlightthickness=0,
                         takefocus=1, cursor="hand2")
        self.var, self.command = variable, command
        self.bind("<Button-1>", self.toggle)
        self.bind("<space>", self.toggle)
        self.bind("<Return>", self.toggle)
        self.bind("<FocusIn>", lambda _e: self.draw())
        self.bind("<FocusOut>", lambda _e: self.draw())
        variable.trace_add("write", lambda *_: self.draw())
        self.draw()

    def toggle(self, _event=None) -> None:
        self.focus_set()
        self.var.set(not self.var.get())
        self.command()

    def draw(self) -> None:
        self.delete("all")
        on = bool(self.var.get())
        w, h, y = self.w, self.h, 2
        track = HIT if on else LINE
        try:
            focused = self.focus_get() is self
        except (KeyError, tk.TclError):
            focused = False
        if focused:
            self._pill(0, y - 2, w, h + 4, TEXT)
            self._pill(2, y, w - 4, h, track)
        else:
            self._pill(2, y, w - 4, h, track)
        d = h - 6
        x = w - 5 - d if on else 5
        self.create_oval(x, y + 3, x + d, y + 3 + d, fill=INK if on else MUTED, outline="")

    def _pill(self, x: int, y: int, w: int, h: int, colour: str) -> None:
        self.create_oval(x, y, x + h, y + h, fill=colour, outline="")
        self.create_oval(x + w - h, y, x + w, y + h, fill=colour, outline="")
        self.create_rectangle(x + h // 2, y, x + w - h // 2, y + h + 1, fill=colour, outline="")


class Button(tk.Label):

    def __init__(self, master, text: str, command, font, k: float) -> None:
        super().__init__(master, text=text, font=font, bg=PANEL, fg=TEXT, padx=int(12 * k), pady=int(7 * k),
                         cursor="hand2", takefocus=1, highlightthickness=1, highlightbackground=LINE,
                         highlightcolor=TEXT)
        self.command = command
        self.bind("<Enter>", lambda _e: self.configure(bg=LINE))
        self.bind("<Leave>", lambda _e: self.configure(bg=PANEL))
        self.bind("<ButtonRelease-1>", self._click)
        self.bind("<space>", self._click)
        self.bind("<Return>", self._click)

    def _click(self, event) -> None:
        if event.type == tk.EventType.ButtonRelease and not (
                0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height()):
            return
        self.command()


class Dial(tk.Canvas):

    def __init__(self, master, size: int, k: float) -> None:
        super().__init__(master, width=size, height=size, bg=INK, highlightthickness=0)
        self.size, self.k = size, k
        self._last = None

    def show(self, state: str, zone_list=(), needle=None, landing=None) -> None:
        key = (state, tuple(zone_list), None if needle is None else round(needle, 1),
               None if landing is None else (landing["angle"], landing["inside"]))
        if key == self._last:
            return
        self._last = key
        self.delete("all")
        k, c = self.k, self.size / 2.0
        r = self.size * 0.36
        live = state == "check"
        band = max(5.0, 8.0 * k)
        self.create_oval(c - r - band, c - r - band, c + r + band, c + r + band, fill=PANEL, outline="")
        self.create_oval(c - r, c - r, c + r, c + r, outline=TEXT if live else RING, width=max(1.0, 1.5 * k))
        if state in ("off", "starting"):
            self.create_line(c, c, c, c - r * 0.55, fill=LINE, width=max(2.0, 2.5 * k), capstyle="round")
            self.create_oval(c - 3 * k, c - 3 * k, c + 3 * k, c + 3 * k, fill=LINE, outline="")
            return

        def arc(span, colour, width) -> None:
            s, e = span
            ext = (e - s) % 360.0 or 359.9
            self.create_arc(c - r, c - r, c + r, c + r, start=90.0 - s - ext, extent=ext, style="arc",
                            outline=colour, width=width)

        def tip(deg: float, frac: float) -> tuple[float, float]:
            a = math.radians(deg - 90.0)
            return c + r * frac * math.cos(a), c + r * frac * math.sin(a)

        shown = list(zone_list)
        if not live and landing is not None and landing.get("zone"):
            shown = [(landing["zone"], landing.get("bar"))]
        for zone, bar in shown:
            arc(zone, TEXT if live and bar is None else ZONE, band)
            if bar is not None:
                arc(bar, TEXT, band)
        angle, colour = (needle, NEEDLE) if live else (
            (landing["angle"], HIT if landing["inside"] else NEEDLE) if landing is not None else (None, NEEDLE))
        if angle is not None:
            x, y = tip(angle, 1.0 + band / (2 * r))
            self.create_line(c, c, x, y, fill=colour, width=max(2.0, 2.5 * k), capstyle="round")
            if not live:
                d = 4.0 * k
                self.create_oval(x - d, y - d, x + d, y + d, fill=colour, outline=INK, width=max(1.0, 1.5 * k))
        self.create_oval(c - 3 * k, c - 3 * k, c + 3 * k, c + 3 * k, fill=TEXT if live else RING, outline="")


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.withdraw()
        self.title("Skill Check Macro")
        self.resizable(False, False)
        self.configure(bg=INK)
        self.cfg = load()
        self.settings = Settings()
        self._hwnd = None
        self._closing = False
        self._apply()

        k = self.k = max(1.0, self.winfo_fpixels("1i") / 96.0)
        fams = set(tkfont.families(self))
        ui = "Helvetica Neue" if MAC and "Helvetica Neue" in fams else "Helvetica" if MAC else (
            "Segoe UI" if "Segoe UI" in fams else "TkDefaultFont")
        show = "Bahnschrift" if "Bahnschrift" in fams else "Avenir Next" if "Avenir Next" in fams else ui
        up = 2 if MAC else 0
        self.f_body = (ui, 10 + up)
        self.f_small = (ui, 9 + up)
        self.f_state = (show, 21 + up, "bold")
        self.f_num = (show, 11 + up)
        self._theme()

        pad = int(18 * k)
        wide = int(420 * k)
        body = tk.Frame(self, bg=INK)
        body.pack(padx=pad, pady=(int(16 * k), int(14 * k)))

        head = tk.Frame(body, bg=INK)
        head.pack(fill="x")
        dial_px = int(104 * k)
        self.dial = Dial(head, dial_px, k)
        self.dial.pack(side="left")
        words = tk.Frame(head, bg=INK)
        words.pack(side="left", fill="both", expand=True, padx=(int(14 * k), 0))
        self.state_word = tk.StringVar(value="Starting")
        self.state_lbl = tk.Label(words, textvariable=self.state_word, font=self.f_state, bg=INK, fg=MUTED, anchor="w")
        self.state_lbl.pack(fill="x")
        self.status = tk.StringVar(value="")
        tk.Label(words, textvariable=self.status, font=self.f_small, bg=INK, fg=MUTED, anchor="nw", justify="left",
                 wraplength=wide - dial_px - int(14 * k), height=2).pack(fill="x")
        self.tally = tk.StringVar(value="")
        tk.Label(words, textvariable=self.tally, font=self.f_num, bg=INK, fg=TEXT, anchor="w").pack(
            fill="x", pady=(int(4 * k), 0))

        self._rule(body, k, top=14)

        self.on = tk.BooleanVar(value=True)
        self._switch_row(body, "Macro on", "F6 turns it on and off while you play", self.on)

        self._rule(body, k)

        grid = tk.Frame(body, bg=INK)
        grid.pack(fill="x")
        grid.columnconfigure(1, weight=1)

        def field(row: int, label: str) -> None:
            tk.Label(grid, text=label, font=self.f_body, bg=INK, fg=TEXT, anchor="w").grid(
                row=row, column=0, sticky="w", pady=int(5 * k), padx=(0, int(16 * k)))

        field(0, "Press")
        self.key = tk.StringVar(value=self.cfg["key"])
        ttk.Combobox(grid, textvariable=self.key, values=winapi.KEY_CHOICES, state="readonly", width=12,
                     font=self.f_body).grid(row=0, column=1, sticky="w")
        self.key.trace_add("write", lambda *_: self._changed())

        field(1, "Aim for")
        self.aim = tk.StringVar(value=self.cfg["aim"])
        ttk.Combobox(grid, textvariable=self.aim, values=AIMS, state="readonly", width=34,
                     font=self.f_body).grid(row=1, column=1, sticky="we")
        self.aim.trace_add("write", lambda *_: self._changed())

        field(2, "Timing offset")
        box = tk.Frame(grid, bg=INK)
        box.grid(row=2, column=1, sticky="w")
        self.offset = tk.IntVar(value=int(self.cfg["offset_ms"]))
        ttk.Spinbox(box, from_=-int(OFFSET_LIMIT), to=int(OFFSET_LIMIT), increment=5, textvariable=self.offset,
                    width=6, font=self.f_body, command=self._changed).pack(side="left")
        tk.Label(box, text="ms", font=self.f_body, bg=INK, fg=MUTED).pack(side="left", padx=(int(6 * k), 0))
        self.offset.trace_add("write", lambda *_: self._changed())
        tk.Label(grid, text="Presses land late: raise it. Early: lower it.", font=self.f_small, bg=INK,
                 fg=MUTED, anchor="w").grid(row=3, column=1, sticky="w", pady=(0, int(4 * k)))

        self.auto = tk.BooleanVar(value=bool(self.cfg["auto_timing"]))
        self._switch_row(body, "Adjust timing by itself", "Learns from where each press lands", self.auto)

        self._rule(body, k)

        self.shots = tk.BooleanVar(value=bool(self.cfg["keep_log"]))
        self._switch_row(body, "Keep a log of presses", "Every press and landing goes in log.txt", self.shots)
        self.save_shots = tk.BooleanVar(value=bool(self.cfg["debug_shots"]))
        self._switch_row(body, "Save pictures of every skill check", "For working out why one was missed",
                         self.save_shots)
        self.top = tk.BooleanVar(value=bool(self.cfg["on_top"]))
        self._switch_row(body, "Keep this window on top", "", self.top)

        self._rule(body, k)

        btns = tk.Frame(body, bg=INK)
        btns.pack(fill="x")
        Button(btns, "Test a screenshot", self._test_image, self.f_body, k).pack(side="left")
        Button(btns, "Open log", self._open_log, self.f_body, k).pack(side="left", padx=int(8 * k))
        Button(btns, "Open pictures", self._open_shots, self.f_body, k).pack(side="left")

        foot = tk.Frame(body, bg=INK)
        foot.pack(fill="x", pady=(int(12 * k), 0))
        tk.Label(foot, text="F7 saves a snapshot of what it sees. F8 quits." + ("  On a Mac hold fn." if MAC else ""),
                 font=self.f_small, bg=INK, fg=MUTED, anchor="w").pack(side="left")
        self.speed = tk.StringVar(value="")
        tk.Label(foot, textvariable=self.speed, font=self.f_small, bg=INK, fg=MUTED, anchor="e").pack(side="right")
        tk.Frame(body, bg=INK, width=wide, height=1).pack()

        self.attributes("-topmost", bool(self.cfg["on_top"]))
        self._msgs: list[str] = []
        self.engine = Engine(self.settings, self._window, self._front, Grabber(), winapi.press,
                             status=self._msgs.append, log_path=LOG, shots_dir=SHOTS, spin_sec=spin_for_this_pc())
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self.engine.run, args=(self._stop,), daemon=True)
        self._thread.start()
        self._f6 = self._f7 = self._f8 = False
        for name in ("F6", "F7", "F8"):
            winapi.hotkey_down(name)
        self.protocol("WM_DELETE_WINDOW", self._quit)
        self.update_idletasks()
        winapi.dark_titlebar(self.winfo_id())
        self.deiconify()
        self.after(50, self._tick)
        self.after(300, self._check_permissions)

    def _theme(self) -> None:
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        for name in ("TCombobox", "TSpinbox"):
            st.configure(name, fieldbackground=PANEL, background=PANEL, foreground=TEXT, arrowcolor=MUTED,
                         bordercolor=LINE, lightcolor=PANEL, darkcolor=PANEL, insertcolor=TEXT,
                         selectbackground=PANEL, selectforeground=TEXT, padding=int(4 * self.k),
                         arrowsize=int(13 * self.k))
            st.map(name,
                   fieldbackground=[("readonly", PANEL), ("disabled", INK)],
                   foreground=[("readonly", TEXT), ("disabled", MUTED)],
                   selectbackground=[("readonly", PANEL), ("!readonly", LINE)],
                   selectforeground=[("readonly", TEXT)],
                   background=[("active", LINE), ("pressed", LINE)],
                   arrowcolor=[("active", TEXT)],
                   bordercolor=[("focus", MUTED)])
        self.option_add("*TCombobox*Listbox.background", PANEL)
        self.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.option_add("*TCombobox*Listbox.selectBackground", LINE)
        self.option_add("*TCombobox*Listbox.selectForeground", TEXT)
        self.option_add("*TCombobox*Listbox.font", self.f_body)
        self.option_add("*TCombobox*Listbox.borderWidth", 0)

    def _rule(self, parent, k: float, top: int = 10) -> None:
        tk.Frame(parent, bg=LINE, height=1).pack(fill="x", pady=(int(top * k), int(10 * k)))

    def _switch_row(self, parent, title: str, hint: str, var: tk.BooleanVar) -> None:
        row = tk.Frame(parent, bg=INK)
        row.pack(fill="x", pady=int(4 * self.k))
        sw = Switch(row, var, self._changed, self.k)
        sw.pack(side="right")
        text = tk.Frame(row, bg=INK)
        text.pack(side="left", fill="x", expand=True)
        parts = [row, text, tk.Label(text, text=title, font=self.f_body, bg=INK, fg=TEXT, anchor="w")]
        parts[-1].pack(fill="x")
        if hint:
            parts.append(tk.Label(text, text=hint, font=self.f_small, bg=INK, fg=MUTED, anchor="w"))
            parts[-1].pack(fill="x")
        for w in parts:
            w.bind("<Button-1>", sw.toggle)

    def _check_permissions(self) -> None:
        missing = winapi.missing_permissions(ask=True)
        if not missing:
            return
        messagebox.showwarning(
            "Permissions needed",
            "macOS is blocking: %s.\n\n"
            "Open System Settings > Privacy & Security and turn on Terminal under "
            "each of those sections (Screen Recording, Accessibility, Input Monitoring).\n\n"
            "Then quit Terminal completely (Cmd+Q) and start Launch.command again."
            % ", ".join(missing))

    def _window(self):
        hwnd = winapi.roblox_window()
        self._hwnd = hwnd
        return winapi.client_rect(hwnd) if hwnd else None

    def _front(self) -> bool:
        return winapi.roblox_in_front(self._hwnd)

    def _apply(self) -> None:
        s = self.settings
        s.key = self.cfg["key"]
        s.allow_good = self.cfg["aim"] != AIMS[1]
        s.prefer_great = True
        s.safe_always = self.cfg["aim"] == AIMS[2]
        s.safe_chain = True
        s.offset_ms = float(self.cfg["offset_ms"])
        s.keep_log = bool(self.cfg["keep_log"])
        s.auto_timing = bool(self.cfg["auto_timing"])
        s.save_shots = bool(self.cfg["debug_shots"])

    def _changed(self) -> None:
        try:
            off = int(self.offset.get())
        except (tk.TclError, ValueError):
            return
        if abs(off) > OFFSET_LIMIT:
            self.offset.set(int(max(-OFFSET_LIMIT, min(OFFSET_LIMIT, off))))
            return
        self.cfg.update(key=self.key.get(), aim=self.aim.get(), offset_ms=off,
                        keep_log=bool(self.shots.get()), on_top=bool(self.top.get()),
                        auto_timing=bool(self.auto.get()), debug_shots=bool(self.save_shots.get()))
        self.settings.enabled = bool(self.on.get())
        self._apply()
        self.attributes("-topmost", bool(self.top.get()))
        save(self.cfg)

    def _hotkeys_active(self) -> bool:
        try:
            if self.focus_get() is not None:
                return True
        except (KeyError, tk.TclError):
            return True
        return winapi.roblox_in_front(winapi.roblox_window())

    def _tick(self) -> None:
        try:
            if self._poll():
                return
        except Exception:
            pass
        if not self._closing:
            self.after(30, self._tick)

    def _poll(self) -> bool:
        f6, f7, f8 = winapi.hotkey_down("F6"), winapi.hotkey_down("F7"), winapi.hotkey_down("F8")
        if (f6 or f7 or f8) and not self._hotkeys_active():
            f6 = f7 = f8 = False
        if f7 and not self._f7:
            self.engine.snapshot_requested = True
            self.status.set("Taking a snapshot...")
        self._f7 = f7
        if self.engine.snapshot_note:
            self._msgs.append(self.engine.snapshot_note)
            self.engine.snapshot_note = ""
        if f6 and not self._f6:
            self.on.set(not self.on.get())
            self._changed()
        if f8 and not self._f8:
            self._quit()
            return True
        self._f6, self._f8 = f6, f8
        if self._msgs:
            self.status.set(self._msgs[-1])
            self._msgs.clear()
        e = self.engine
        if e.learned is not None:
            self.offset.set(int(round(e.learned)))
            e.learned = None
        self._paint(e)
        return False

    def _paint(self, e: Engine) -> None:
        state = e.state if self.on.get() else "off"
        word, colour = STATES.get(state, STATES["starting"])
        if self.state_word.get() != word:
            self.state_word.set(word)
            self.state_lbl.configure(fg=colour)
        landed = e.hits_in + e.hits_out
        tally = "%d seen, %d pressed" % (e.checks, e.presses)
        if landed:
            tally += ", %d of %d on target" % (e.hits_in, landed)
        if self.tally.get() != tally:
            self.tally.set(tally)
        speed = "%.0f fps, search %.0f ms" % (1.0 / max(1e-3, e.frame_dt), e.search_ms)
        if self.speed.get() != speed:
            self.speed.set(speed)
        rd = e.last_rd
        if state == "check" and rd is not None:
            self.dial.show(state, [((z.start, z.end), z.great) for z in zones(rd)], rd.needle)
        else:
            self.dial.show(state, landing=e.last_landing)

    def _test_image(self) -> None:
        path = filedialog.askopenfilename(title="Pick a screenshot with a skill check on it",
                                          filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp")])
        if not path:
            return
        from check_image import describe
        messagebox.showinfo("Skill check test", describe(path))

    def _open_log(self) -> None:
        try:
            if not os.path.exists(LOG):
                open(LOG, "a").close()
            if sys.platform == "win32":
                os.startfile(LOG)
            elif MAC:
                subprocess.Popen(["open", "-t", LOG])
        except OSError as exc:
            messagebox.showerror("Skill Check Macro", "Couldn't open log.txt:\n%s\n\nIt is here:\n%s" % (exc, LOG))

    def _open_shots(self) -> None:
        try:
            os.makedirs(SHOTS, exist_ok=True)
            if sys.platform == "win32":
                os.startfile(SHOTS)
            elif MAC:
                subprocess.Popen(["open", SHOTS])
        except OSError as exc:
            messagebox.showerror("Skill Check Macro", "Couldn't open the pictures folder:\n%s\n\nIt is here:\n%s"
                                 % (exc, SHOTS))

    def _quit(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._stop.set()
        self._thread.join(timeout=1.0)
        self.destroy()


def main() -> None:
    winapi.set_dpi_aware()
    if not winapi.single_instance():
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("Skill Check Macro", "The macro is already running.\n\n"
                            "Look for its window (it may be behind Roblox), or press F8 in Roblox to quit it first.")
        root.destroy()
        return
    winapi.fine_timer()
    App().mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        err = traceback.format_exc()
        try:
            with open(os.path.join(ROOT, "crash.txt"), "w", encoding="utf-8") as f:
                f.write(err)
            messagebox.showerror("Skill Check Macro crashed",
                                 err[-1500:] + "\n\nSaved to crash.txt. Running " + SETUP_FILE + " again often fixes it.")
        except Exception:
            pass
        raise
