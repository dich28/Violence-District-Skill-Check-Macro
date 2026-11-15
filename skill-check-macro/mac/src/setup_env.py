import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VENV = os.path.join(ROOT, ".venv")
PY = os.path.join(VENV, "Scripts", "python.exe") if os.name == "nt" else os.path.join(VENV, "bin", "python3")
REQ = os.path.join(HERE, "requirements.txt")
STAMP = os.path.join(VENV, ".installed")


def venv_ok() -> bool:
    cfg = os.path.join(VENV, "pyvenv.cfg")
    try:
        with open(cfg, encoding="utf-8") as f:
            for line in f:
                key, _, val = line.partition("=")
                if key.strip().lower() == "home":
                    return os.path.isdir(val.strip())
    except OSError:
        return False
    return False


def pip_ok() -> bool:
    try:
        return subprocess.call([PY, "-m", "pip", "--version"], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=60) == 0
    except Exception:
        return False


def tk_check() -> bool:
    if subprocess.call([PY, os.path.join(HERE, "tk_fix.py")], cwd=HERE) == 0:
        return True
    print()
    print(" The window toolkit (Tcl/Tk) that comes with Python is missing or broken.")
    if os.name == "nt":
        print(" Fix: open Settings > Apps > Installed apps > Python 3.x > Modify (or run the python.org")
        print(" installer again > Modify), make sure 'tcl/tk and IDLE' is ticked, finish, then start")
        print(" Skill Check Macro.exe again. If that doesn't help, choose Repair in the same installer.")
    else:
        print(" Fix: install Python from python.org (it includes Tcl/Tk), then run Setup.command again.")
    return False


def main() -> int:
    try:
        import tkinter
    except ImportError:
        if sys.platform == "darwin":
            print(" This Python has no tkinter. Install Python from python.org (not Homebrew), "
                  "or run: brew install python-tk")
        else:
            print(" This Python has no tkinter. Re-run the python.org installer and tick 'tcl/tk and IDLE'.")
        return 1
    if os.path.exists(VENV) and not venv_ok():
        print(" .venv was made on another PC (or by another Python), rebuilding it...")
        shutil.rmtree(VENV, ignore_errors=True)
    if os.path.exists(PY) and not pip_ok():
        print(" .venv is damaged (broken pip, e.g. an interrupted setup), rebuilding it...")
        shutil.rmtree(VENV, ignore_errors=True)
    want = open(REQ, "rb").read()
    if os.path.exists(STAMP) and open(STAMP, "rb").read() == want:
        return 0 if tk_check() else 1
    for attempt in (1, 2):
        if not os.path.exists(PY):
            print(" Creating .venv (first time only)...")
            if subprocess.call([sys.executable, "-m", "venv", VENV]) != 0:
                return 1
        print(" Installing packages (a minute or two)...")
        if subprocess.call([PY, "-m", "pip", "install", "--disable-pip-version-check", "-q", "-r", REQ,
                            "--only-binary=:all:"]) == 0:
            break
        if attempt == 1:
            print(" Install failed, starting over with a fresh .venv...")
            shutil.rmtree(VENV, ignore_errors=True)
    else:
        print(" Install failed again. Check your internet, move this folder out of OneDrive / Downloads"
              " (e.g. to Documents), and if you use an antivirus, let it allow this folder.")
        return 1
    with open(STAMP, "wb") as f:
        f.write(want)
    if not tk_check():
        return 1
    print(" Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
