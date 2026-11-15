from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from detector import Reading

MERGE_GAP_DEG = 9.0
MIN_SAMPLES = 3
MIN_GOOD_ONLY_DEG = 15.0
FIT_WINDOW_SEC = 0.30
SCATTER_MARGIN_DEG = 2.0


@dataclass
class Zone:
    start: float
    end: float
    great: tuple[float, float] | None = None

    @property
    def width(self) -> float:
        return (self.end - self.start) % 360.0 or 360.0


def _cw(a: float, b: float) -> float:
    return (b - a) % 360.0


def _within(a: float, start: float, end: float) -> bool:
    return _cw(start, a) <= _cw(start, end)


def _near(a: float, b: float, tol: float = 1.5) -> bool:
    return abs((a - b + 180.0) % 360.0 - 180.0) <= tol


def _caps_only(zs: float, ze: float, bar, pieces: list, white: list) -> bool:
    if bar is None:
        return False
    bs, be = bar
    at_s, at_e = _near(bs, zs), _near(be, ze)
    if at_s == at_e:
        return False
    span = _cw(zs, ze)
    inside = [p for p in list(pieces) + list(white) if p != bar and _cw(zs, p[0] + 0.5 * _cw(*p)) <= span]
    if any(not (_near(p[0], zs) or _near(p[1], ze)) for p in inside):
        return False
    end = ze if at_s else zs
    width = _cw(bs, be)
    return any(b != bar and (_near(b[0], end) or _near(b[1], end)) and abs(_cw(*b) - width) < 2.0
               for b in white)


def zones(rd: Reading) -> list[Zone]:
    parts = sorted([(s, e, False) for s, e in rd.good] + [(s, e, True) for s, e in rd.great])
    merged: list[list] = []
    for s, e, is_great in parts:
        if merged and _cw(merged[-1][1], s) <= MERGE_GAP_DEG:
            merged[-1][1] = e if _cw(merged[-1][0], e) > _cw(merged[-1][0], merged[-1][1]) else merged[-1][1]
            if is_great and (merged[-1][2] is None or _cw(s, e) > _cw(*merged[-1][2])):
                merged[-1][2] = (s, e)
            if is_great:
                merged[-1][3].append((s, e))
        else:
            merged.append([s, e, (s, e) if is_great else None, [(s, e)] if is_great else []])
    if len(merged) > 1 and _cw(merged[-1][1], merged[0][0]) <= MERGE_GAP_DEG:
        last = merged.pop()
        merged[0][0] = last[0]
        if last[2] is not None and (merged[0][2] is None or _cw(*last[2]) > _cw(*merged[0][2])):
            merged[0][2] = last[2]
        merged[0][3] = last[3] + merged[0][3]
    out = [Zone(s, e, None if _caps_only(s, e, g, pieces, rd.white) else g) for s, e, g, pieces in merged]
    out = [z for z in out if z.great is not None or z.width >= MIN_GOOD_ONLY_DEG]
    if any(z.great is not None for z in out):
        out = [z for z in out if z.great is not None]
    return out


class Needle:
    def __init__(self) -> None:
        self.samples: deque[tuple[float, float]] = deque(maxlen=9)

    prior: float | None = None

    def reset(self) -> None:
        self.prior = None
        self.samples.clear()

    def add(self, t: float, angle: float) -> None:
        if self.samples:
            last = self.samples[-1][1]
            d = (angle - last + 180.0) % 360.0 - 180.0
            angle = last + d
        self.samples.append((t, angle))
        while self.samples and t - self.samples[0][0] > FIT_WINDOW_SEC and len(self.samples) > MIN_SAMPLES:
            self.samples.popleft()

    def fit(self) -> tuple[float, float, float] | None:
        n = len(self.samples)
        if n < MIN_SAMPLES:
            if self.prior is not None and n >= 1:
                return self.samples[-1][0], self.samples[-1][1], self.prior
            return None
        ts = [s[0] for s in self.samples]
        an = [s[1] for s in self.samples]
        slopes = [(an[j] - an[i]) / (ts[j] - ts[i]) for i in range(n) for j in range(i + 1, n)
                  if ts[j] - ts[i] > 1e-4]
        if not slopes:
            return None
        slopes.sort()
        w = slopes[len(slopes) // 2]
        t0 = ts[-1]
        offs = sorted(a - w * (t - t0) for t, a in zip(ts, an))
        return t0, offs[len(offs) // 2], w


@dataclass
class Plan:
    zone: Zone
    aim: float
    target: tuple[float, float]
    kind: str
    eta: float
    angle_now: float
    speed: float
    t_ref: float = 0.0


def _bar_aim(z: Zone, s: float, e: float, frame_deg: float) -> float:
    width = _cw(s, e)
    mid = (s + 0.5 * width) % 360.0
    need = 0.5 * frame_deg + SCATTER_MARGIN_DEG
    if width <= 0.0 or need <= 0.5 * width:
        return mid
    room_s, room_e = _cw(z.start, s), _cw(e, z.end)
    q = min(0.9, need / width)
    if room_e > room_s + 2.0:
        return (s + q * width) % 360.0
    if room_s > room_e + 2.0:
        return (e - q * width) % 360.0
    return mid


def plan(rd: Reading, needle: Needle, prefer_great: bool, allow_good: bool, good_aim: float = 0.3,
         game_dt: float = 0.0) -> Plan | None:
    f = needle.fit()
    if f is None:
        return None
    t0, a_now, w = f
    if abs(w) < 20.0:
        return None
    cw = w > 0
    best = None
    for z in zones(rd):
        if z.great is not None and prefer_great:
            tgt, kind = z.great, "great"
        elif allow_good:
            tgt, kind = (z.start, z.end), "good"
        else:
            continue
        s, e = tgt
        width = _cw(s, e)
        if kind == "great":
            aim = _bar_aim(z, s, e, abs(w) * game_dt)
        else:
            entry, sign = (s, 1.0) if cw else (e, -1.0)
            aim = (entry + sign * good_aim * width) % 360.0
        left = _cw(aim, e) if cw else _cw(s, aim)
        dist = _cw(a_now % 360.0, aim) if cw else _cw(aim, a_now % 360.0)
        if dist > 360.0 - left:
            dist -= 360.0
        eta = dist / abs(w)
        if best is None or (eta >= -0.05 and (best.eta < -0.05 or eta < best.eta)):
            best = Plan(z, aim, tgt, kind, eta, a_now % 360.0, w, t0)
    return best
