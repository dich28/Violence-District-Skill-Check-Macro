#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>
#include <wchar.h>

#define APP_TITLE L"Skill Check Macro"
#define PATH_MAX_W 1024
#define CMD_MAX_W 4096

static wchar_t g_dir[PATH_MAX_W];

static int file_exists(const wchar_t *path) {
    DWORD a = GetFileAttributesW(path);
    return a != INVALID_FILE_ATTRIBUTES && !(a & FILE_ATTRIBUTE_DIRECTORY);
}

static void in_dir(wchar_t *out, const wchar_t *rel) {
    _snwprintf(out, PATH_MAX_W, L"%ls\\%ls", g_dir, rel);
    out[PATH_MAX_W - 1] = 0;
}

static HANDLE start_hidden(const wchar_t *cmdline, HANDLE log) {
    wchar_t buf[CMD_MAX_W];
    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    wcsncpy(buf, cmdline, CMD_MAX_W - 1);
    buf[CMD_MAX_W - 1] = 0;
    ZeroMemory(&si, sizeof si);
    si.cb = sizeof si;
    si.dwFlags = STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;
    if (log != NULL) {
        si.dwFlags |= STARTF_USESTDHANDLES;
        si.hStdOutput = log;
        si.hStdError = log;
        si.hStdInput = NULL;
    }
    ZeroMemory(&pi, sizeof pi);
    if (!CreateProcessW(NULL, buf, NULL, NULL, log != NULL, CREATE_NO_WINDOW, NULL, g_dir, &si, &pi))
        return NULL;
    CloseHandle(pi.hThread);
    return pi.hProcess;
}

static int run_hidden(const wchar_t *cmdline, HANDLE log, HWND pump) {
    HANDLE h = start_hidden(cmdline, log);
    DWORD code = 1;
    if (h == NULL) return -1;
    for (;;) {
        DWORD r = MsgWaitForMultipleObjects(1, &h, FALSE, INFINITE, QS_ALLINPUT);
        if (r == WAIT_OBJECT_0) break;
        if (r == WAIT_OBJECT_0 + 1) {
            MSG m;
            while (PeekMessageW(&m, NULL, 0, 0, PM_REMOVE)) {
                TranslateMessage(&m);
                DispatchMessageW(&m);
            }
        } else break;
    }
    (void)pump;
    GetExitCodeProcess(h, &code);
    CloseHandle(h);
    return (int)code;
}

static int start_app(void) {
    wchar_t pyw[PATH_MAX_W], cmd[CMD_MAX_W];
    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    in_dir(pyw, L".venv\\Scripts\\pythonw.exe");
    _snwprintf(cmd, CMD_MAX_W, L"\"%ls\" \"%ls\\src\\app.py\"", pyw, g_dir);
    cmd[CMD_MAX_W - 1] = 0;
    ZeroMemory(&si, sizeof si);
    si.cb = sizeof si;
    ZeroMemory(&pi, sizeof pi);
    if (!CreateProcessW(NULL, cmd, NULL, NULL, FALSE, 0, NULL, g_dir, &si, &pi)) return 0;
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return 1;
}

static int env_ready(void) {
    wchar_t a[PATH_MAX_W], b[PATH_MAX_W], py[PATH_MAX_W], cmd[CMD_MAX_W];
    in_dir(a, L".venv\\.installed");
    in_dir(b, L".venv\\Scripts\\pythonw.exe");
    in_dir(py, L".venv\\Scripts\\python.exe");
    if (!file_exists(a) || !file_exists(b) || !file_exists(py)) return 0;
    _snwprintf(cmd, CMD_MAX_W, L"\"%ls\" -c \"import cv2, mss, numpy, tkinter\"", py);
    cmd[CMD_MAX_W - 1] = 0;
    return run_hidden(cmd, NULL, NULL) == 0;
}

static const wchar_t *CHECK =
    L"-c \"import sys, struct; sys.exit(0 if sys.version_info[:2] in [(3, 10), (3, 11), (3, 12), (3, 13)]"
    L" and struct.calcsize('P') == 8 else 1)\"";

static int python_ok(const wchar_t *prefix) {
    wchar_t cmd[CMD_MAX_W];
    _snwprintf(cmd, CMD_MAX_W, L"%ls %ls", prefix, CHECK);
    cmd[CMD_MAX_W - 1] = 0;
    return run_hidden(cmd, NULL, NULL) == 0;
}

static int find_python(wchar_t *prefix) {
    static const wchar_t *vers[] = { L"313", L"312", L"311", L"310" };
    static const wchar_t *dotted[] = { L"3.13", L"3.12", L"3.11", L"3.10" };
    wchar_t base[PATH_MAX_W], path[PATH_MAX_W];
    int i;
    if (GetEnvironmentVariableW(L"LOCALAPPDATA", base, PATH_MAX_W) > 0) {
        for (i = 0; i < 4; i++) {
            _snwprintf(path, PATH_MAX_W, L"%ls\\Programs\\Python\\Python%ls\\python.exe", base, vers[i]);
            path[PATH_MAX_W - 1] = 0;
            if (file_exists(path)) {
                _snwprintf(prefix, PATH_MAX_W + 2, L"\"%ls\"", path);
                if (python_ok(prefix)) return 1;
            }
        }
    }
    if (GetEnvironmentVariableW(L"ProgramFiles", base, PATH_MAX_W) > 0) {
        for (i = 0; i < 4; i++) {
            _snwprintf(path, PATH_MAX_W, L"%ls\\Python%ls\\python.exe", base, vers[i]);
            path[PATH_MAX_W - 1] = 0;
            if (file_exists(path)) {
                _snwprintf(prefix, PATH_MAX_W + 2, L"\"%ls\"", path);
                if (python_ok(prefix)) return 1;
            }
        }
    }
    for (i = 0; i < 4; i++) {
        _snwprintf(prefix, PATH_MAX_W + 2, L"py -%ls", dotted[i]);
        if (python_ok(prefix)) return 1;
    }
    wcscpy(prefix, L"python");
    if (python_ok(prefix)) return 1;
    return 0;
}

static LRESULT CALLBACK wnd_proc(HWND h, UINT m, WPARAM w, LPARAM l) {
    if (m == WM_CLOSE) return 0;
    return DefWindowProcW(h, m, w, l);
}

static HWND show_status(HINSTANCE inst) {
    WNDCLASSW wc;
    HWND win, label;
    int w = 460, h = 150;
    ZeroMemory(&wc, sizeof wc);
    wc.lpfnWndProc = wnd_proc;
    wc.hInstance = inst;
    wc.hCursor = LoadCursorW(NULL, IDC_WAIT);
    wc.hbrBackground = (HBRUSH)(COLOR_WINDOW + 1);
    wc.lpszClassName = L"SkillCheckMacroSetup";
    RegisterClassW(&wc);
    win = CreateWindowExW(WS_EX_TOPMOST, wc.lpszClassName, APP_TITLE L" - first launch",
                          WS_OVERLAPPED | WS_CAPTION,
                          (GetSystemMetrics(SM_CXSCREEN) - w) / 2, (GetSystemMetrics(SM_CYSCREEN) - h) / 2,
                          w, h, NULL, NULL, inst, NULL);
    if (win == NULL) return NULL;
    label = CreateWindowExW(0, L"STATIC",
                            L"Setting up for the first time.\r\n\r\n"
                            L"This downloads three Python packages into this folder and takes a minute or two. "
                            L"The macro opens by itself when it is done.",
                            WS_CHILD | WS_VISIBLE, 16, 14, w - 48, h - 60, win, NULL, inst, NULL);
    SendMessageW(label, WM_SETFONT, (WPARAM)GetStockObject(DEFAULT_GUI_FONT), TRUE);
    ShowWindow(win, SW_SHOW);
    UpdateWindow(win);
    return win;
}

static void log_tail(wchar_t *out, int max_chars) {
    wchar_t path[PATH_MAX_W];
    char raw[1201];
    HANDLE f;
    DWORD size, got = 0, start;
    out[0] = 0;
    in_dir(path, L"setup-log.txt");
    f = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_EXISTING, 0, NULL);
    if (f == INVALID_HANDLE_VALUE) return;
    size = GetFileSize(f, NULL);
    start = size > 1200 ? size - 1200 : 0;
    SetFilePointer(f, (LONG)start, NULL, FILE_BEGIN);
    if (ReadFile(f, raw, 1200, &got, NULL) && got > 0) {
        raw[got] = 0;
        MultiByteToWideChar(CP_ACP, 0, raw, -1, out, max_chars);
        out[max_chars - 1] = 0;
    }
    CloseHandle(f);
}

int WINAPI wWinMain(HINSTANCE inst, HINSTANCE prev, PWSTR args, int show) {
    wchar_t prefix[PATH_MAX_W + 2], cmd[CMD_MAX_W], path[PATH_MAX_W], tail[1300], msg[2400];
    wchar_t *slash;
    SECURITY_ATTRIBUTES sa;
    HANDLE log;
    HWND status;
    int code;
    (void)prev; (void)args; (void)show;

    if (GetModuleFileNameW(NULL, g_dir, PATH_MAX_W) == 0) return 1;
    slash = wcsrchr(g_dir, L'\\');
    if (slash == NULL) return 1;
    *slash = 0;
    SetCurrentDirectoryW(g_dir);

    in_dir(path, L"src\\app.py");
    if (!file_exists(path)) {
        MessageBoxW(NULL, L"The \"src\" folder is missing.\n\nKeep this file next to the \"src\" folder it came with "
                          L"(unzip the whole download first, don't run it from inside the zip).",
                    APP_TITLE, MB_OK | MB_ICONWARNING);
        return 1;
    }

    if (env_ready()) {
        if (!start_app())
            MessageBoxW(NULL, L"Couldn't start the macro.", APP_TITLE, MB_OK | MB_ICONERROR);
        return 0;
    }

    if (!find_python(prefix)) {
        if (MessageBoxW(NULL,
                        L"Python is needed and wasn't found on this PC.\n\n"
                        L"Install Python 3.10 to 3.13 (64-bit) from python.org, then start this again.\n\n"
                        L"Open the Python download page now?",
                        APP_TITLE, MB_YESNO | MB_ICONINFORMATION) == IDYES)
            ShellExecuteW(NULL, L"open", L"https://www.python.org/downloads/", NULL, NULL, SW_SHOWNORMAL);
        return 1;
    }

    status = show_status(inst);
    in_dir(path, L"setup-log.txt");
    ZeroMemory(&sa, sizeof sa);
    sa.nLength = sizeof sa;
    sa.bInheritHandle = TRUE;
    log = CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ, &sa, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (log == INVALID_HANDLE_VALUE) log = NULL;
    _snwprintf(cmd, CMD_MAX_W, L"%ls \"%ls\\src\\setup_env.py\"", prefix, g_dir);
    cmd[CMD_MAX_W - 1] = 0;
    code = run_hidden(cmd, log, status);
    if (log != NULL) CloseHandle(log);
    if (status != NULL) DestroyWindow(status);

    if (code != 0) {
        log_tail(tail, 1300);
        _snwprintf(msg, 2400,
                   L"Setup didn't finish.\n\n%ls\n\nThe full text is in setup-log.txt next to this file. "
                   L"Check your internet connection, and if this folder is inside OneDrive or Downloads, "
                   L"move it somewhere like Documents and try again.", tail);
        msg[2399] = 0;
        MessageBoxW(NULL, msg, APP_TITLE, MB_OK | MB_ICONWARNING);
        return 1;
    }
    if (!start_app())
        MessageBoxW(NULL, L"Setup finished, but the macro couldn't be started.", APP_TITLE, MB_OK | MB_ICONERROR);
    return 0;
}
