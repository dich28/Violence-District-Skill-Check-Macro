import glob
import os
import sys


def fix() -> None:
    if sys.platform != "win32":
        return
    roots = [sys.base_prefix, sys.prefix, os.path.dirname(sys.executable)]
    for var, pattern, marker in (("TCL_LIBRARY", "tcl[89].*", "init.tcl"),
                                 ("TK_LIBRARY", "tk[89].*", "tk.tcl")):
        cur = os.environ.get(var)
        if cur and os.path.isfile(os.path.join(cur, marker)):
            continue
        for root in roots:
            hits = sorted(glob.glob(os.path.join(root, "tcl", pattern)), reverse=True)
            hits = [h for h in hits if os.path.isfile(os.path.join(h, marker))]
            if hits:
                os.environ[var] = hits[0]
                break


def works() -> bool:
    fix()
    try:
        import tkinter
        root = tkinter.Tk()
        root.withdraw()
        root.destroy()
        return True
    except Exception as exc:
        print(" Tk error:", exc)
        return False


if __name__ == "__main__":
    sys.exit(0 if works() else 1)
