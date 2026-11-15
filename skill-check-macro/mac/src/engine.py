from __future__ import annotations

import os
import queue
import shutil
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable

import cv2
import numpy as np

import detector
import imgio
from detector import Reading, Ring
from predictor import Needle, plan, zones, _cw

BASE_LEAD_SEC = 0.025
SEARCH_GAP_SEC = 0.0
SEARCH_GAP_KNOWN_SEC = 0.10
CHECK_END_SEC = 0.25
SPIN_SEC = 0.004
RING_R_MIN, RING_R_MAX = 0.035, 0.12
REARM_MIN_SEC = 0.12
SPEED_MIN, SPEED_MAX = 60.0, 1500.0
STOP_SEC = 0.045
STOP_FRAMES = 2.5
WATCH_SEC = 0.35
LATE_LEARN_MAX_SEC = 0.10
LEARN_RATE = 0.5
LOCK_NEAR_DEG = 20.0
CHAIN_SPEED_MIN, CHAIN_SPEED_MAX = 0.9, 1.3
CHAIN_SPEED_STEP = 1.03
CHAIN_TRUST_SAMPLES = 5
OFFSET_LIMIT = 400.0
LEARN_MAX_ERR_MS = 500.0
MAX_CHECK_FOLDERS = 150
MAX_SNAPSHOT_FOLDERS = 20
MAX_TRACE_FRAMES = 4000


@dataclass
class Settings:
    enabled: bool = True
    key: str = "Space"
    prefer_great: bool = True
    allow_good: bool = True
    offset_ms: float = 0.0
    good_aim: float = 0.3
    safe_always: bool = False
    safe_chain: bool = True
    hold_sec: float = 0.03
    keep_log: bool = True
    auto_timing: bool = True
    save_shots: bool = True
    search_area: tuple[float, float, float, float] = (0.22, 0.12, 0.56, 0.76)


class Engine:
    def __init__(self, settings: Settings,
                 window: Callable[[], tuple[int, int, int, int] | None],
                 foreground: Callable[[], bool],
                 grab: Callable[[int, int, int, int], np.ndarray | None],
                 press: Callable[[str, float], None],
                 status: Callable[[str], None] = lambda s: None,
                 clock: Callable[[], float] = time.perf_counter,
                 sleep: Callable[[float], None] = time.sleep,
                 log_path: str | None = None,
                 shots_dir: str | None = None,
                 spin_sec: float = SPIN_SEC) -> None:
        self.s = settings
        self.spin_sec = spin_sec
        self.window = window
        self.foreground = foreground
        self.grab = grab
        self.press_fn = press
        self.status = status
        self.clock = clock
        self.sleep = sleep
        self.log_path = log_path
        self.shots_dir = shots_dir
        self._shot_q: queue.Queue | None = None
        self.check_id = ""
        self._shot_seq = 0
        self._check_frames = 0
        self._trace: list = []
        self._mid_frames: list = []
        self._check_t0 = 0.0
        self._lock = None
        self._local_ring = None
        self.last_live = None
        self.ring: Ring | None = None
        self.needle = Needle()
        self.in_check = False
        self.pressed = False
        self.pressed_zone = None
        self.pressed_at = -1e9
        self.in_chain = False
        self.chain_speed = 0.0
        self.chain_sign = 1.0
        self._skip = ""
        self.watch = None
        self.landings: deque[str] = deque(maxlen=200)
        self.hits_in = 0
        self.hits_out = 0
        self.last_landing = None
        self.state = "starting"
        self._win_size = None
        self.learned = None
        self.last_active = -1e9
        self.last_search = -1e9
        self.frame_dt = 0.012
        self._gaps: deque[float] = deque(maxlen=31)
        self.checks = 0
        self.presses = 0
        self.last_rd: Reading | None = None
        self.last_img: np.ndarray | None = None
        self.log: deque[str] = deque(maxlen=500)
        self._status = ""
        self.search_ms = 0.0
        self.snapshot_requested = False
        self.snapshot_note = ""

    def _say(self, msg: str) -> None:
        if msg != self._status:
            self._status = msg
            self.status(msg)

    @property
    def game_dt(self) -> float:
        if len(self._gaps) < 5:
            return self.frame_dt
        g = sorted(self._gaps)
        return g[len(g) // 2]

    @property
    def aim_dt(self) -> float:
        g = self.game_dt
        if len(self._gaps) >= 5 and g > 1.3 * self.frame_dt:
            return g
        return min(g, 1.0 / 60.0)

    def _grab_timed(self, x: int, y: int, w: int, h: int):
        t0 = self.clock()
        img = self.grab(x, y, w, h)
        t1 = self.clock()
        return img, (t0 + t1) / 2.0

    def _search(self, win) -> bool:
        wx, wy, ww, wh = win
        ax, ay, aw, ah = self.s.search_area
        x0, y0 = int(ww * ax), int(wh * ay)
        img, _ = self._grab_timed(wx + x0, wy + y0, int(ww * aw), int(wh * ah))
        if img is None:
            return False
        t = self.clock()
        hint = Ring(self.ring.cx - x0, self.ring.cy - y0, self.ring.r) if self.ring else None
        ring, rd = detector.find_ring(img, min_r=max(18, int(wh * RING_R_MIN)), max_r=int(wh * RING_R_MAX), hint=hint)
        self.search_ms = (self.clock() - t) * 1000.0
        if ring is None:
            return False
        self.ring = Ring(ring.cx + x0, ring.cy + y0, ring.r)
        return True

    def _crop_box(self, win) -> tuple[int, int, int, int, Ring]:
        wx, wy, ww, wh = win
        r = self.ring
        half = int(r.r * 1.3) + 4
        x0 = int(round(r.cx)) - half
        y0 = int(round(r.cy)) - half
        return wx + x0, wy + y0, 2 * half, 2 * half, Ring(r.cx - x0, r.cy - y0, r.r)

    def _rearm(self, rd: Reading, t: float) -> bool:
        if self.pressed_zone is None or t - self.pressed_at < REARM_MIN_SEC:
            return False
        ps, pe = self.pressed_zone
        for z in zones(rd):
            overlap = _cw(ps, z.start) <= _cw(ps, pe) or _cw(z.start, ps) <= z.width
            if not overlap and min(_cw(ps, z.start), _cw(z.start, ps)) > 10.0:
                self.pressed = False
                self.pressed_zone = None
                self.in_chain = True
                self.checks += 1
                self._lock = None
                self._new_check(self.last_img, self._local_ring, rd, chain=True)
                last = self.needle.samples[-1] if self.needle.samples else None
                self.needle.reset()
                if last is not None:
                    self.needle.add(*last)
                if self.chain_speed > 0:
                    self.needle.prior = self.chain_sign * self.chain_speed * CHAIN_SPEED_STEP
                self._skip = ""
                self._say("Skill check #%d (continuous, new zone at %.0f deg)" % (self.checks, z.start))
                return True
        return False

    def _stable(self, rd: Reading) -> Reading:
        def dist(a, s, e):
            return 0.0 if _cw(s, a) <= _cw(s, e) else min(_cw(e, a), _cw(a, s))
        spans = rd.great + rd.good + (self._lock[0] + self._lock[1] if self._lock else [])
        near = rd.needle is not None and any(dist(rd.needle, s, e) <= LOCK_NEAR_DEG for s, e in spans)
        if not near:
            if rd.great or rd.good:
                self._lock = (list(rd.great), list(rd.good), list(rd.white))
            return rd
        if self._lock is None:
            return rd
        return Reading(ring_score=rd.ring_score, great=self._lock[0], good=self._lock[1], white=self._lock[2],
                       needle=rd.needle, needle_strength=rd.needle_strength)

    def _do_press(self, why: str, p, press_at: float | None = None) -> None:
        t_down = self.clock()
        behind = max(0.0, t_down - press_at) if press_at is not None else 0.0
        self.press_fn(self.s.key, self.s.hold_sec)
        self.chain_speed = abs(p.speed)
        self.chain_sign = 1.0 if p.speed > 0 else -1.0
        self.pressed = True
        self.pressed_zone = (p.zone.start, p.zone.end)
        self.pressed_at = self.clock()
        self.watch = {"t": self.pressed_at, "aim": p.aim, "target": p.target, "kind": p.kind,
                      "speed": p.speed, "angle": None, "since": None, "behind": behind,
                      "zone": (p.zone.start, p.zone.end), "bar": p.zone.great}
        self.presses += 1
        msg = "Pressed %s (%s): needle %.0f deg, aim %.0f deg, %.0f deg/s%s" % (
            self.s.key, why, p.angle_now, p.aim, p.speed,
            ", %.0f ms behind plan" % (behind * 1000.0) if behind >= 0.002 else "")
        self.log.append(msg)
        self._say("Skill check #%d: %s" % (self.checks, msg))
        self._write("PRESS   #%d %s | zone %.0f-%.0f%s" % (
            self.checks, msg, p.zone.start, p.zone.end,
            ", white bar %.0f-%.0f" % p.zone.great if p.zone.great else ""))
        if self.last_img is not None and self.last_rd is not None:
            self._shot("press", self.last_img, self._local_ring, self.last_rd, p)

    def _write(self, line: str) -> None:
        if self.check_id and not line.startswith("SNAPSHOT"):
            line = "%s  [%s]" % (line, self.check_id)
            self._details(line)
        if not self.s.keep_log or self.log_path is None:
            return
        try:
            if os.path.exists(self.log_path) and os.path.getsize(self.log_path) > 1_000_000:
                with open(self.log_path, encoding="utf-8", errors="replace") as f:
                    keep = f.readlines()[-3000:]
                with open(self.log_path, "w", encoding="utf-8") as f:
                    f.writelines(keep)
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write("%s  %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), line))
        except OSError:
            pass

    def _forget_check(self, why: str = "") -> None:
        if self.in_check:
            self._write("END     #%d: %s (%s), %d frames with the check on screen" % (
                self.checks, "pressed" if self.pressed else "NOT pressed", why or "stopped looking",
                self._check_frames))
            self._dump_trace()
        self.in_check = False
        self.in_chain = False
        self.chain_speed = 0.0
        self.pressed = False
        self.pressed_zone = None
        self.watch = None
        self._lock = None
        self.needle.reset()

    def step(self) -> float:
        if not self.s.enabled:
            self._forget_check("turned off")
            self.state = "off"
            self._say("Off (F6 turns it on)")
            return 0.1
        win = self.window()
        if win is None:
            self._forget_check("Roblox window gone")
            if self.snapshot_requested:
                self.snapshot_requested = False
                self.snapshot_note = "Snapshot failed: Roblox isn't open (or is minimised)."
            self.state = "waiting"
            self._say("Waiting for Roblox (not open, or minimised)")
            return 0.5
        if self.snapshot_requested:
            self.snapshot_requested = False
            self._snapshot(win)
        if not self.foreground():
            self._forget_check("Roblox not in front")
            self.state = "paused"
            self._say("Paused, Roblox isn't the active window")
            return 0.1
        if self._win_size != (win[2], win[3]):
            if self._win_size is not None and not self.in_check:
                self.ring = None
            self._win_size = (win[2], win[3])
        now = self.clock()
        idle = now - self.last_active
        if self.ring is None or (idle > 1.0 and now - self.last_search > SEARCH_GAP_KNOWN_SEC):
            gap = SEARCH_GAP_SEC if self.ring is None else SEARCH_GAP_KNOWN_SEC
            if now - self.last_search >= gap:
                self.last_search = now
                found = self._search(win)
                if not found and self.ring is None:
                    self.state = "watching"
                    self._say("Watching for skill checks...")
                    return 0.01
            elif self.ring is None:
                return 0.01

        x, y, w, h, local = self._crop_box(win)
        img, t_cap = self._grab_timed(x, y, w, h)
        if img is None:
            return 0.01
        rd = detector.read(img, local)
        live = rd.active and detector.plausible(rd)
        self.last_img, self.last_rd, self._local_ring = img, rd, local
        t_after = self.clock()
        self.frame_dt = 0.8 * self.frame_dt + 0.2 * max(0.002, min(0.05, t_after - now))
        if self.in_check and self.s.save_shots and len(self._trace) < MAX_TRACE_FRAMES:
            self._trace.append((t_cap - self._check_t0, live, rd.needle, rd.great, rd.good, rd.ring_score))
            if live and len(self._trace) % 8 == 0:
                self._mid_frames.append((img, local, rd))
                if len(self._mid_frames) > 24:
                    self._mid_frames = self._mid_frames[::2]

        if not live:
            if self.in_check and t_cap - self.last_active > CHECK_END_SEC:
                self.in_check = False
                if not self.pressed:
                    why = self._skip or (self._why_not() if len(self.needle.samples) >= 3 else (
                        "needle seen on only %d frames" % len(self.needle.samples)))
                    self._write("NO PRESS #%d: %s" % (self.checks, why))
                    for fr in self._mid_frames[-12:]:
                        self._shot("during", *fr)
                    if self.last_live is not None:
                        self._shot("nopress", *self.last_live)
                elif self.last_live is not None:
                    self._shot("end", *self.last_live)
                self._write("END     #%d: %s, %d frames with the check on screen" % (
                    self.checks, "pressed" if self.pressed else "NOT pressed", self._check_frames))
                self._dump_trace()
                self.state = "watching"
                self._say("Watching for skill checks... (%d seen, %d pressed)" % (self.checks, self.presses))
            elif not self.in_check:
                self.state = "watching"
            return 0.005 if not self.in_check else 0.0

        if self.in_check and t_cap - self.last_active > 1.0:
            self._forget_check("lost sight of it for %.1f s" % (t_cap - self.last_active))
        self.last_live = (img, local, rd)
        self._check_frames += 1
        self.state = "check"
        if not self.in_check:
            self.in_check = True
            self.in_chain = False
            self.chain_speed = 0.0
            self.pressed = False
            self.pressed_zone = None
            self.checks += 1
            self.needle.reset()
            self._skip = ""
            self._lock = None
            self._new_check(img, local, rd, chain=False)
            self._say("Skill check #%d" % self.checks)
        self.last_active = t_cap
        if rd.needle is not None:
            last = self.needle.samples[-1][1] % 360.0 if self.needle.samples else None
            if last is None or abs((rd.needle - last + 180.0) % 360.0 - 180.0) > 0.3:
                ts = t_cap - 0.5 * self.frame_dt
                if self.needle.samples and 0.004 < ts - self.needle.samples[-1][0] < 0.15:
                    self._gaps.append(ts - self.needle.samples[-1][0])
                self.needle.add(ts, rd.needle)
        if self.watch is not None:
            self._watch_landing(rd, t_cap)
        if self.pressed:
            if not self._rearm(rd, t_cap):
                return 0.0
        safe = self.s.allow_good and (self.s.safe_always or (self.in_chain and self.s.safe_chain))
        p = plan(self._stable(rd), self.needle, self.s.prefer_great and not safe, self.s.allow_good,
                 0.5 if safe else self.s.good_aim, game_dt=self.aim_dt)
        if p is None or not (SPEED_MIN <= abs(p.speed) <= SPEED_MAX):
            self._skip = ("no zone to aim for, or the needle wasn't seen on enough frames" if p is None
                          else "needle speed read as %.0f deg/s, which can't be right" % abs(p.speed))
            return 0.0
        if self.in_chain and self.chain_speed > 0 and len(self.needle.samples) < CHAIN_TRUST_SAMPLES:
            lo, hi = CHAIN_SPEED_MIN * self.chain_speed, CHAIN_SPEED_MAX * self.chain_speed
            sp = abs(p.speed)
            if not lo <= sp <= hi:
                new = max(lo, min(hi, sp))
                p.eta = p.eta * sp / new
                p.speed = new if p.speed > 0 else -new
        lead = BASE_LEAD_SEC + self.s.offset_ms / 1000.0
        press_at = p.t_ref + p.eta - lead
        now = self.clock()
        wait = press_at - now
        self._skip = "last plan: zone %.0f-%.0f, needle %.0f deg at %.0f deg/s, press due in %+.0f ms" % (
            p.zone.start, p.zone.end, p.angle_now, p.speed, wait * 1000.0)
        if wait > self.frame_dt * 1.5:
            return 0.0
        why = p.kind
        if wait < -0.5 * self.frame_dt:
            land = p.angle_now + p.speed * (now - p.t_ref + lead)
            if not _inside(land, p.target):
                if p.kind == "great" and self.s.allow_good and _inside(land, (p.zone.start, p.zone.end)):
                    why = "late, zone"
                else:
                    self._skip += "; too late, a press then would have landed at %.0f deg, outside the zone" % (land % 360.0)
                    return 0.0
        self._wait_until(press_at)
        self._do_press(why, p, press_at)
        return 0.0

    def _snapshot(self, win) -> None:
        wx, wy, ww, wh = win
        img = self.grab(wx, wy, ww, wh)
        if img is None:
            self.snapshot_note = "Snapshot failed: couldn't capture the Roblox window."
            return
        ax, ay, aw, ah = self.s.search_area
        x0, y0 = int(ww * ax), int(wh * ay)
        area = img[y0:y0 + int(wh * ah), x0:x0 + int(ww * aw)]
        t = self.clock()
        ring, rd = detector.find_ring(area, min_r=max(18, int(wh * RING_R_MIN)), max_r=int(wh * RING_R_MAX), slow=True)
        ms = (self.clock() - t) * 1000.0
        if ring is None:
            found = "no skill check found"
        else:
            found = "ring at (%.0f, %.0f) r=%.0f, white bar %s, zone %s, needle %s" % (
                ring.cx + x0, ring.cy + y0, ring.r, rd.great, rd.good,
                "%.0f" % rd.needle if rd.needle is not None else "not seen")
        self._write("SNAPSHOT window %dx%d, search %.0f ms: %s | status: %s" % (ww, wh, ms, found, self._status))
        if ring is not None:
            self._shot("snapshot", img, Ring(ring.cx + x0, ring.cy + y0, ring.r), rd, force=True)
        else:
            self._shot("snapshot_nothing_found", img, None, None, force=True)
        self.snapshot_note = "Snapshot written to log.txt: %s" % found

    def _watch_landing(self, rd: Reading, t: float) -> None:
        w = self.watch
        window = WATCH_SEC + max(0.0, self.s.offset_ms) / 1000.0
        if t - w["t"] > window or rd.needle is None:
            if t - w["t"] > window:
                self.watch = None
            return
        a = rd.needle
        if w["angle"] is None or abs((a - w["angle"] + 180.0) % 360.0 - 180.0) > 0.6:
            w["angle"], w["since"] = a, t
            return
        if t - w["since"] < max(STOP_SEC, STOP_FRAMES * self.game_dt):
            return
        self.watch = None
        sign = 1.0 if w["speed"] > 0 else -1.0
        err_deg = ((a - w["aim"] + 180.0) % 360.0 - 180.0) * sign
        err_ms = err_deg / abs(w["speed"]) * 1000.0
        behind_ms = w.get("behind", 0.0) * 1000.0
        timing_err = err_ms - behind_ms
        s, e = w["target"]
        inside = (a - s) % 360.0 <= (e - s) % 360.0
        msg = "landed at %.0f deg (%s %.0f-%.0f): %s by %.0f ms" % (
            a, "white bar" if w["kind"] == "great" else "zone", s, e, "late" if err_ms > 0 else "early", abs(err_ms))
        if behind_ms >= 2.0:
            msg += " (pressed %.0f ms behind plan%s)" % (
                behind_ms, ", not used for timing" if behind_ms > LATE_LEARN_MAX_SEC * 1000.0 else "")
        self.landings.append(("IN  " if inside else "OUT ") + msg)
        if inside:
            self.hits_in += 1
        else:
            self.hits_out += 1
        self.last_landing = {"zone": w.get("zone"), "bar": w.get("bar"), "aim": w["aim"], "angle": a,
                             "inside": inside, "err_ms": err_ms, "kind": w["kind"]}
        self.log.append(msg)
        if (self.s.auto_timing and abs(timing_err) < LEARN_MAX_ERR_MS
                and behind_ms <= LATE_LEARN_MAX_SEC * 1000.0):
            rate = LEARN_RATE if abs(timing_err) < 60 else 0.8
            new = max(-OFFSET_LIMIT, min(OFFSET_LIMIT, self.s.offset_ms + rate * timing_err))
            if abs(new - self.s.offset_ms) >= 1.0:
                self.s.offset_ms = round(new, 1)
                self.learned = self.s.offset_ms
        self._say("Skill check #%d: %s%s" % (self.checks, msg,
                  " (timing offset now %+.0f ms)" % self.s.offset_ms if self.s.auto_timing else ""))
        self._write("LANDED  %s | timing offset %+.1f ms" % (self.landings[-1], self.s.offset_ms))
        if self.last_img is not None:
            self._shot("landed_" + ("IN" if inside else "OUT"), self.last_img, self._local_ring, rd)

    def _new_check(self, img, ring, rd, chain: bool) -> None:
        self.check_id = "%s_C%03d%s" % (time.strftime("%Y%m%d_%H%M%S"), self.checks, "_chain" if chain else "")
        self._shot_seq = 0
        self._check_frames = 0
        self._trace, self._mid_frames = [], []
        self._check_t0 = self.clock()
        s = self.s
        aim = ("middle of zone" if s.safe_always else "white bar only" if not s.allow_good
               else "white bar, else zone") + (" (chain: middle of zone)" if chain and s.safe_chain and s.allow_good else "")
        self._details("Skill check #%d%s   id %s" % (self.checks, " (continuous chain)" if chain else "", self.check_id))
        self._details("settings: key %s | aim %s | timing offset %+.1f ms | auto-adjust %s | capture ~%.0f fps" % (
            s.key, aim, s.offset_ms, "on" if s.auto_timing else "off", 1.0 / max(1e-3, self.frame_dt)))
        if ring is not None:
            self._details("ring r=%.0f px | zones %s | white bar %s | needle %s" % (
                ring.r, rd.good, rd.great, "%.0f deg" % rd.needle if rd.needle is not None else "not seen"))
        if img is not None and ring is not None:
            self._shot("seen", img, ring, rd)

    def _dump_trace(self) -> None:
        if not (self.s.save_shots and self.check_id and self._trace):
            return
        fmt = lambda zs: " ".join("%.0f-%.0f" % z for z in zs) or "-"
        lines = ["", "frame by frame (seconds since the check appeared | live | needle | white bar | zone | ring score):"]
        for t, live, nd, great, good, sc in self._trace:
            lines.append("  %6.3f  %s  %7s  %-12s  %-14s %.2f" % (
                t, "LIVE" if live else "lost", "%.1f" % nd if nd is not None else "none", fmt(great), fmt(good), sc))
        self._queue(("txt", self.check_id, "\n".join(lines)))

    def _queue(self, item) -> None:
        if self.shots_dir is None:
            return
        if self._shot_q is None:
            self._shot_q = queue.Queue(maxsize=100)
            threading.Thread(target=self._shot_writer, daemon=True).start()
        try:
            self._shot_q.put_nowait(item)
        except queue.Full:
            pass

    def _details(self, line: str) -> None:
        if self.s.save_shots and self.check_id:
            self._queue(("txt", self.check_id, time.strftime("%H:%M:%S") + "  " + line))

    def _shot(self, tag: str, img, ring, rd, p=None, force: bool = False) -> None:
        if not (self.s.save_shots or force) or img is None:
            return
        if tag.startswith("snapshot"):
            folder, name = "snapshot_" + time.strftime("%Y%m%d_%H%M%S"), tag + ".png"
        else:
            if not self.check_id:
                return
            self._shot_seq += 1
            folder, name = self.check_id, "%d_%s.png" % (self._shot_seq, tag)
        self._queue(("png", folder, name, img.copy(), ring, rd, p))

    def _shot_writer(self) -> None:
        while True:
            item = self._shot_q.get()
            try:
                folder = os.path.join(self.shots_dir, item[1])
                new = not os.path.isdir(folder)
                os.makedirs(folder, exist_ok=True)
                if item[0] == "txt":
                    with open(os.path.join(folder, "details.txt"), "a", encoding="utf-8") as f:
                        f.write(item[2] + "\n")
                else:
                    _, _, name, img, ring, rd, p = item
                    out = annotate(img, ring, rd, p) if ring is not None and rd is not None else img
                    if out.shape[0] < 300:
                        k = max(2, -(-300 // max(1, out.shape[0])))
                        out = cv2.resize(out, None, fx=k, fy=k, interpolation=cv2.INTER_NEAREST)
                    imgio.imwrite(os.path.join(folder, name), out)
                    if out is not img:
                        k = out.shape[0] // max(1, img.shape[0])
                        plain = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_NEAREST) if k > 1 else img
                        imgio.imwrite(os.path.join(folder, name[:-4] + "_raw.png"), plain)
                if new:
                    dirs = sorted(d for d in os.listdir(self.shots_dir)
                                  if os.path.isdir(os.path.join(self.shots_dir, d)))
                    snaps = [d for d in dirs if d.startswith("snapshot_")]
                    checks = [d for d in dirs if not d.startswith("snapshot_")]
                    for d in checks[:-MAX_CHECK_FOLDERS] + snaps[:-MAX_SNAPSHOT_FOLDERS]:
                        shutil.rmtree(os.path.join(self.shots_dir, d), ignore_errors=True)
            except Exception:
                pass

    def _why_not(self) -> str:
        if len(self.needle.samples) < 3:
            return "needle seen on %d frames (need 3); is it red?" % len(self.needle.samples)
        f = self.needle.fit()
        if f is not None and abs(f[2]) < 20:
            return "needle not moving"
        return "no target zone in the needle's path (White bar only mode with no white bar?)"

    def _wait_until(self, t: float) -> None:
        while True:
            left = t - self.clock()
            if left <= 0:
                return
            if left > self.spin_sec:
                self.sleep(left - self.spin_sec)
            else:
                self.sleep(0)

    def run(self, stop: threading.Event) -> None:
        while not stop.is_set():
            try:
                pause = self.step()
            except Exception as exc:
                self.state = "error"
                self._say("Error: %s" % exc)
                pause = 0.5
            if pause > 0:
                self.sleep(pause)


def _inside(a: float, span: tuple[float, float]) -> bool:
    s, e = span
    return (a - s) % 360.0 <= (e - s) % 360.0


def annotate(img: np.ndarray, ring: Ring, rd: Reading, p=None) -> np.ndarray:
    out = img.copy()
    c = (int(round(ring.cx)), int(round(ring.cy)))

    def pt(deg: float, frac: float):
        a = np.deg2rad(deg - 90.0)
        return int(round(ring.cx + ring.r * frac * np.cos(a))), int(round(ring.cy + ring.r * frac * np.sin(a)))

    cv2.circle(out, c, int(round(ring.r)), (255, 255, 0), 1)
    for z in zones(rd):
        cv2.ellipse(out, c, (int(ring.r * 1.15),) * 2, -90, z.start, z.start + z.width, (0, 200, 255), 2)
    for s, e in rd.great:
        cv2.ellipse(out, c, (int(ring.r * 1.22),) * 2, -90, s, s + ((e - s) % 360), (0, 255, 0), 2)
    if rd.needle is not None:
        cv2.line(out, c, pt(rd.needle, 1.0), (255, 0, 255), 1)
    if p is not None:
        cv2.line(out, pt(p.aim, 0.8), pt(p.aim, 1.3), (0, 255, 0), 2)
    return out
