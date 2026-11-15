#!/bin/bash
ok() { "$1" -c 'import sys, tkinter; sys.exit(0 if (3,10) <= sys.version_info[:2] <= (3,13) else 1)' >/dev/null 2>&1; }
for v in 3.13 3.12 3.11 3.10; do
  for p in "/Library/Frameworks/Python.framework/Versions/$v/bin/python3" \
           "/opt/homebrew/bin/python$v" "/usr/local/bin/python$v"; do
    if [ -x "$p" ] && ok "$p"; then echo "$p"; exit 0; fi
  done
done
for p in python3.13 python3.12 python3.11 python3.10 python3; do
  q="$(command -v $p 2>/dev/null)"
  if [ -n "$q" ] && ok "$q"; then echo "$q"; exit 0; fi
done
exit 1
