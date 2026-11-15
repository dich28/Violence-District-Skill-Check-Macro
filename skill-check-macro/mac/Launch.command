#!/bin/bash
cd "$(dirname "$0")"
if ! .venv/bin/python3 -c "import cv2, mss, numpy, tkinter, Quartz" >/dev/null 2>&1; then
  PY="$(bash src/find_python.sh)"
  if [ -z "$PY" ]; then
    echo " Python 3.10-3.13 was not found. Install it from https://www.python.org/downloads/macos/"
    read -n 1 -s -r -p " Press any key to close..."
    exit 1
  fi
  "$PY" src/setup_env.py || { read -n 1 -s -r -p " Press any key to close..."; exit 1; }
fi
echo " Skill Check Macro is running. Keep this Terminal window open (closing it quits the macro)."
.venv/bin/python3 src/app.py
