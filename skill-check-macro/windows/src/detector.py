from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

N_ANG = 720
DEG_PER_ROW = 360.0 / N_ANG

WHITE_MIN = 165
EDGE_MIN = 115
DARK_MAX = 85
RING_MIN = 120
RING_CONTRAST = 25
RING_SPREAD = 90
SCORE_MIN = 0.85
BAR_MIN_DEG = 3.5


@dataclass
class Ring:
    cx: float
    cy: float
    r: float


@dataclass
class Reading:
    ring_score: float = 0.0
    great: list[tuple[float, float]] = field(default_factory=list)
    good: list[tuple[float, float]] = field(default_factory=list)
    white: list[tuple[float, float]] = field(default_factory=list)
    needle: float | None = None
    needle_strength: int = 0

    @property
    def active(self) -> bool:
        return self.ring_score >= 0.7 and bool(self.great or self.good)


def _runs(mask: np.ndarray, min_len: int) -> list[tuple[int, int]]:
    n = len(mask)
    if mask.all():
        return [(0, n)]
    if not mask.any():
        return []
    start = int(np.flatnonzero(~mask)[0])
    rolled = np.roll(mask, -start)
    out = []
    i = 0
    while i < n:
        if rolled[i]:
            j = i
            while j < n and rolled[j]:
                j += 1
            if j - i >= min_len:
                out.append(((i + start) % n, (j + start) % n or n))
            i = j
        else:
            i += 1
    return out


def _deg(run: tuple[int, int]) -> tuple[float, float]:
    return run[0] * DEG_PER_ROW, run[1] * DEG_PER_ROW


def polar(img: np.ndarray, ring: Ring) -> tuple[np.ndarray, int]:
    rmax = int(ring.r * 1.25) + 2
    pol = cv2.warpPolar(img, (rmax, N_ANG), (ring.cx, ring.cy), rmax, cv2.WARP_POLAR_LINEAR)
    return np.roll(pol, N_ANG // 4, axis=0), rmax


def _cols(r: float, a: float, b: float) -> slice:
    return slice(max(0, int(round(r * a))), max(1, int(round(r * b))) + 1)


def _smooth(counts: np.ndarray) -> np.ndarray:
    return np.convolve(np.concatenate([counts[-4:], counts, counts[:4]]), np.ones(5), "same")[4:-4]


def read(img: np.ndarray, ring: Ring) -> Reading:
    pol, _ = polar(img, ring)
    r = ring.r
    px = pol.astype(np.int16)
    vmax = px.max(axis=2)
    vmin = px.min(axis=2)
    bch, gch, rch = px[..., 0], px[..., 1], px[..., 2]

    band = _cols(r, 0.92, 1.05)
    inner_edge = _cols(r, 0.86, 0.975)
    interior = _cols(r, 0.985, 1.02)
    outer_edge = _cols(r, 1.025, 1.12)
    ring_band = _cols(r, 0.93, 1.05)

    near_in = np.median(vmax[:, _cols(r, 0.80, 0.86)], axis=1)
    near_out = np.median(vmax[:, _cols(r, 1.14, 1.22)], axis=1)
    white_frac = (vmin[:, band] >= WHITE_MIN).mean(axis=1)
    great = (white_frac >= 0.6) & (np.minimum(near_in, near_out) <= WHITE_MIN - 25)
    good = ((vmax[:, inner_edge].max(axis=1) >= EDGE_MIN)
            & (vmax[:, outer_edge].max(axis=1) >= EDGE_MIN)
            & (vmax[:, interior].max(axis=1) <= DARK_MAX))
    rb = vmax[:, ring_band]
    pk = rb.argmax(axis=1)
    peak = rb[np.arange(N_ANG), pk]
    spread = peak - vmin[:, ring_band][np.arange(N_ANG), pk]
    ring_seen = ((peak >= RING_MIN) & (peak - np.minimum(near_in, near_out) >= RING_CONTRAST + 15)
                 & (spread <= RING_SPREAD))

    res = Reading()
    res.ring_score = float((ring_seen | good | great).mean())
    min_run = max(2, int(BAR_MIN_DEG / DEG_PER_ROW))
    res.great = [_deg(x) for x in _runs(great, min_run)]
    res.white = [_deg(x) for x in _runs(great, 2)]
    res.good = [_deg(x) for x in _runs(good & ~great, int(4.0 / DEG_PER_ROW))]

    redall = (rch >= 130) & (rch - gch >= 65) & (rch - bch >= 45)
    counts = _smooth(redall[:, _cols(r, 0.30, 0.95)].sum(axis=1).astype(np.float32))
    peak = int(np.argmax(counts))
    strength = int(counts[peak])
    need = max(6, int(r * 0.12))
    if strength >= need:
        idx = (np.arange(peak - 6, peak + 7)) % N_ANG
        w = counts[idx]
        offs = np.arange(-6, 7)
        res.needle = float(((peak + (w * offs).sum() / max(1e-6, w.sum())) * DEG_PER_ROW) % 360.0)
        res.needle_strength = strength
    return res


def refine(img: np.ndarray, ring: Ring, lo: float = 0.88, hi: float = 1.10) -> Ring:
    pol, _ = polar(img, Ring(ring.cx, ring.cy, ring.r * max(1.0, hi / 1.10)))
    v = pol.max(axis=2).astype(np.int16)
    sl = _cols(ring.r, lo, hi)
    sub = v[:, sl]
    best = sub.argmax(axis=1) + sl.start
    bright = (sub >= RING_MIN).sum(axis=1)
    ok = (bright >= 1) & (bright <= max(3, int(round(ring.r * 0.06))))
    if ok.sum() < N_ANG * 0.3:
        return ring
    ang = np.deg2rad(np.arange(N_ANG)[ok] * DEG_PER_ROW - 90.0)
    rad = best[ok].astype(np.float64)
    xs = ring.cx + rad * np.cos(ang)
    ys = ring.cy + rad * np.sin(ang)
    a = np.column_stack([xs, ys, np.ones_like(xs)])
    bvec = -(xs ** 2 + ys ** 2)
    try:
        d, e, f = np.linalg.lstsq(a, bvec, rcond=None)[0]
    except np.linalg.LinAlgError:
        return ring
    cx, cy = -d / 2.0, -e / 2.0
    rr = float(np.sqrt(max(1.0, cx * cx + cy * cy - f)))
    lim = ring.r * max(0.15, (hi - lo) * 0.8)
    if abs(cx - ring.cx) > lim or abs(cy - ring.cy) > lim or abs(rr - ring.r) > lim:
        return ring
    return Ring(float(cx), float(cy), rr)


def _check(img: np.ndarray, cands, best=None, best_read=None, coarse: bool = False):
    for cx, cy, r in cands:
        ring = Ring(float(cx), float(cy), float(r))
        if coarse:
            for _ in range(3):
                ring = refine(img, ring, 0.80, 1.20)
        ring = refine(img, ring)
        rd = read(img, ring)
        if rd.active and (best_read is None or rd.ring_score > best_read.ring_score):
            best, best_read = ring, rd
    return best, best_read


def centre_ring(img: np.ndarray, min_r: int, max_r: int) -> list[tuple[float, float, float]]:
    h, w = img.shape[:2]
    out = []
    for dx, dy in ((0, 0), (0, -0.03), (0, 0.03), (-0.02, 0), (0.02, 0)):
        cx, cy = w / 2.0 + dx * w, h / 2.0 + dy * h
        rmax = min(max_r, int(min(cx, cy, w - cx, h - cy)) - 2)
        if rmax <= min_r:
            continue
        pol = cv2.warpPolar(img, (rmax, 360), (cx, cy), rmax, cv2.WARP_POLAR_LINEAR)
        bright = (pol.max(axis=2) >= RING_MIN).astype(np.uint8)
        spread = cv2.dilate(bright, np.ones((1, max(3, int(rmax * 0.05)) | 1), np.uint8))
        cover = spread.mean(axis=0)
        cover[:min_r] = 0
        col = int(np.argmax(cover))
        if cover[col] >= 0.6:
            out.append((cx, cy, float(col)))
    return out


def blob_rings(img: np.ndarray, min_r: int, max_r: int) -> list[tuple[float, float, float]]:
    b, g, r = cv2.split(img)
    mn = cv2.min(cv2.min(b, g), r)
    _, white = cv2.threshold(mn, WHITE_MIN - 26, 255, cv2.THRESH_BINARY)
    k = 0.5 if min(img.shape[:2]) > 400 else 1.0
    if k != 1.0:
        white = cv2.resize(white, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
        _, white = cv2.threshold(white, 40, 255, cv2.THRESH_BINARY)
    white = cv2.dilate(white, np.ones((3, 3), np.uint8))
    n, _lab, stats, _c = cv2.connectedComponentsWithStats(white, connectivity=8)
    lo, hi = 2 * min_r * k, 2 * max_r * 1.25 * k
    out = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if w < lo or h < lo or w > hi or h > hi:
            continue
        if abs(w - h) > 0.18 * max(w, h):
            continue
        if area > 0.30 * w * h:
            continue
        out.append(((x + w / 2.0) / k, (y + h / 2.0) / k, ((w + h) / 4.0 - 1.0) / k))
    out.sort(key=lambda c: -c[2])
    return out[:6]


def plausible(rd: Reading) -> bool:
    if rd.ring_score < SCORE_MIN:
        return False
    total = sum((e - s) % 360 for s, e in rd.good + rd.great)
    return 4.0 <= total <= 150.0


def find_ring(img: np.ndarray, min_r: int = 25, max_r: int | None = None,
              hint: Ring | None = None, slow: bool = False) -> tuple[Ring | None, Reading | None]:
    h, w = img.shape[:2]
    max_r = max_r or int(min(h, w) * 0.48)
    cands = ([(hint.cx, hint.cy, hint.r)] if hint else []) + blob_rings(img, min_r, max_r)
    best, best_read = _check(img, cands, coarse=True)
    if best is not None and plausible(best_read):
        return best, best_read
    if not slow:
        return None, None
    best, best_read = _check(img, centre_ring(img, min_r, max_r), coarse=True)
    if best is not None and plausible(best_read):
        return best, best_read
    gray = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (3, 3), 0)
    circles = cv2.HoughCircles(gray, cv2.HOUGH_GRADIENT, dp=1.2, minDist=max(20, min_r), param1=120, param2=28,
                               minRadius=min_r, maxRadius=max_r)
    if circles is None:
        return None, None
    best, best_read = _check(img, [tuple(c) for c in circles[0][:40]])
    return (best, best_read) if best is not None and plausible(best_read) else (None, None)
