from __future__ import annotations

import time

import Quartz

KEY_CHOICES = ("Space", "Left click", "E", "F", "Q", "R", "Shift", "Enter")

KEYCODES = {
    "Space": 49, "E": 14, "F": 3, "Q": 12, "R": 15, "Shift": 56, "Enter": 36,
}
VK = {"F6": 97, "F7": 98, "F8": 100}

ROBLOX_OWNERS = {"Roblox", "RobloxPlayer"}
TITLE_BAR = 28
CACHE_SEC = 0.2

_src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
_cache = {"t": -1.0, "rect": None, "front": False}


def _call(name: str, default=True):
    fn = getattr(Quartz, name, None)
    if fn is None:
        return default
    try:
        return bool(fn())
    except Exception:
        return default


def missing_permissions(ask: bool = True) -> list[str]:
    missing = []
    if not _call("CGPreflightScreenCaptureAccess"):
        missing.append("Screen Recording")
        if ask:
            _call("CGRequestScreenCaptureAccess")
    if not _call("CGPreflightPostEventAccess"):
        missing.append("Accessibility")
        if ask:
            _call("CGRequestPostEventAccess")
    if not _call("CGPreflightListenEventAccess"):
        missing.append("Input Monitoring")
        if ask:
            _call("CGRequestListenEventAccess")
    return missing


def set_dpi_aware() -> None:
    pass


def fine_timer() -> None:
    pass


def _main_display_size() -> tuple[float, float]:
    b = Quartz.CGDisplayBounds(Quartz.CGMainDisplayID())
    return b.size.width, b.size.height


def _refresh() -> None:
    now = time.perf_counter()
    if now - _cache["t"] < CACHE_SEC:
        return
    _cache["t"] = now
    opts = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    wins = Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID) or []
    rect, front, first_normal = None, False, True
    for w in wins:
        if w.get("kCGWindowLayer", 1) != 0:
            continue
        owner = w.get("kCGWindowOwnerName", "")
        b = w.get("kCGWindowBounds") or {}
        x, y, ww, wh = b.get("X", 0), b.get("Y", 0), b.get("Width", 0), b.get("Height", 0)
        if owner in ROBLOX_OWNERS and ww >= 100 and wh >= 100:
            if first_normal:
                front = True
            if rect is None:
                sw, sh = _main_display_size()
                if wh < sh - 1:
                    y, wh = y + TITLE_BAR, wh - TITLE_BAR
                rect = (int(x), int(y), int(ww), int(wh))
        first_normal = False
        if rect is not None:
            break
    _cache["rect"], _cache["front"] = rect, front


def roblox_window():
    _refresh()
    return _cache["rect"]


def roblox_in_front(_handle) -> bool:
    _refresh()
    return bool(_cache["front"])


def client_rect(_handle):
    _refresh()
    return _cache["rect"]


def hotkey_down(name: str) -> bool:
    try:
        return bool(Quartz.CGEventSourceKeyState(Quartz.kCGEventSourceStateHIDSystemState, VK[name]))
    except Exception:
        return False


def _post(ev) -> None:
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)


def press(key: str, hold_sec: float = 0.03) -> None:
    if key == "Left click":
        loc = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
        down = Quartz.CGEventCreateMouseEvent(_src, Quartz.kCGEventLeftMouseDown, loc, Quartz.kCGMouseButtonLeft)
        up = Quartz.CGEventCreateMouseEvent(_src, Quartz.kCGEventLeftMouseUp, loc, Quartz.kCGMouseButtonLeft)
        _post(down)
        time.sleep(hold_sec)
        _post(up)
        return
    code = KEYCODES.get(key, KEYCODES["Space"])
    _post(Quartz.CGEventCreateKeyboardEvent(_src, code, True))
    time.sleep(hold_sec)
    _post(Quartz.CGEventCreateKeyboardEvent(_src, code, False))
