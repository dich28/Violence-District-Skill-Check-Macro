from __future__ import annotations

import sys
import time

WINDOWS = sys.platform == "win32"

SCANCODES = {
    "Space": 0x39, "E": 0x12, "F": 0x21, "Q": 0x10, "R": 0x13,
    "Shift": 0x2A, "Enter": 0x1C,
}
KEY_CHOICES = ("Space", "Left click", "E", "F", "Q", "R", "Shift", "Enter")
VK = {"F6": 0x75, "F7": 0x76, "F8": 0x77}

if WINDOWS:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    ULONG_PTR = ctypes.c_size_t

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]

    class _U(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = [("type", wintypes.DWORD), ("u", _U)]

    INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
    KEYEVENTF_KEYUP, KEYEVENTF_SCANCODE = 0x0002, 0x0008
    MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004

    user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.FindWindowW.restype = wintypes.HWND
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    user32.GetAsyncKeyState.restype = ctypes.c_short
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetParent.argtypes = [wintypes.HWND]
    user32.GetParent.restype = wintypes.HWND
    _ENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [_ENUMPROC, wintypes.LPARAM]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                    ctypes.POINTER(wintypes.DWORD)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE

_mutex = None
_found = {"hwnd": None, "looked": -1e9}


def set_dpi_aware() -> None:
    if not WINDOWS:
        return
    try:
        ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def fine_timer() -> None:
    if not WINDOWS:
        return
    try:
        ctypes.WinDLL("winmm").timeBeginPeriod(1)
    except Exception:
        pass


def single_instance() -> bool:
    global _mutex
    if not WINDOWS:
        return True
    try:
        _mutex = kernel32.CreateMutexW(None, False, "SkillCheckMacro_one_copy")
        return ctypes.get_last_error() != 183
    except Exception:
        return True


def dark_titlebar(widget_id: int) -> None:
    if not WINDOWS:
        return
    try:
        hwnd = user32.GetParent(widget_id) or widget_id
        on = ctypes.c_int(1)
        dwm = ctypes.WinDLL("dwmapi")
        if dwm.DwmSetWindowAttribute(wintypes.HWND(hwnd), 20, ctypes.byref(on), ctypes.sizeof(on)) != 0:
            dwm.DwmSetWindowAttribute(wintypes.HWND(hwnd), 19, ctypes.byref(on), ctypes.sizeof(on))
    except Exception:
        pass


def _title(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(64)
    user32.GetWindowTextW(hwnd, buf, 64)
    return buf.value


def _exe_name(hwnd: int) -> str:
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return ""
    h = kernel32.OpenProcess(0x1000, False, pid.value)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(520)
        size = wintypes.DWORD(520)
        if not kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return ""
        return buf.value.replace("/", "\\").rsplit("\\", 1)[-1].lower()
    finally:
        kernel32.CloseHandle(h)


def _find_roblox() -> int | None:
    hits: list[tuple[int, int]] = []

    def each(hwnd, _lparam):
        try:
            if user32.IsWindowVisible(hwnd) and _title(hwnd) == "Roblox":
                exe = _exe_name(hwnd)
                if exe.startswith("roblox") or exe in ("windows10universal.exe", "applicationframehost.exe"):
                    hits.append((0, int(hwnd)))
                elif not exe:
                    hits.append((1, int(hwnd)))
        except Exception:
            pass
        return True

    user32.EnumWindows(_ENUMPROC(each), 0)
    return min(hits)[1] if hits else None


def roblox_window() -> int | None:
    if not WINDOWS:
        return None
    try:
        hwnd = _found["hwnd"]
        if hwnd and user32.IsWindow(hwnd) and _title(hwnd) == "Roblox":
            return hwnd
        _found["hwnd"] = None
        now = time.monotonic()
        if now - _found["looked"] < 0.5:
            return None
        _found["looked"] = now
        _found["hwnd"] = _find_roblox()
        return _found["hwnd"]
    except Exception:
        hwnd = user32.FindWindowW(None, "Roblox")
        return int(hwnd) if hwnd else None


def roblox_in_front(hwnd: int | None) -> bool:
    if not WINDOWS:
        return True
    return bool(hwnd) and int(user32.GetForegroundWindow() or 0) == hwnd


def client_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    if not WINDOWS or not hwnd or user32.IsIconic(hwnd):
        return None
    rc = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rc)):
        return None
    pt = wintypes.POINT(0, 0)
    if not user32.ClientToScreen(hwnd, ctypes.byref(pt)):
        return None
    w, h = rc.right - rc.left, rc.bottom - rc.top
    if w < 100 or h < 100:
        return None
    return pt.x, pt.y, w, h


def hotkey_down(name: str) -> bool:
    if not WINDOWS:
        return False
    return bool(user32.GetAsyncKeyState(VK[name]) & 0x8001)


def _send(*inputs) -> None:
    arr = (INPUT * len(inputs))(*inputs)
    user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))


def press(key: str, hold_sec: float = 0.03) -> None:
    if not WINDOWS:
        return
    if key == "Left click":
        _send(INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTDOWN, 0, 0)))
        time.sleep(hold_sec)
        _send(INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTUP, 0, 0)))
        return
    sc = SCANCODES.get(key, SCANCODES["Space"])
    _send(INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(0, sc, KEYEVENTF_SCANCODE, 0, 0)))
    time.sleep(hold_sec)
    _send(INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(0, sc, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, 0, 0)))
