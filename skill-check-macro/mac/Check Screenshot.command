#!/bin/bash
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python3 ]; then
  echo " Run Setup.command first."
  read -n 1 -s -r -p " Press any key to close..."
  exit 1
fi
echo " Drag a screenshot of a skill check into this window, then press Return:"
read -r IMG
IMG="${IMG%\"}"; IMG="${IMG#\"}"; IMG="${IMG%\'}"; IMG="${IMG#\'}"
IMG="$(printf '%s' "$IMG" | sed -e 's/[[:space:]]*$//' -e 's/\\\(.\)/\1/g')"
.venv/bin/python3 src/check_image.py "$IMG"
read -n 1 -s -r -p " Press any key to close..."
