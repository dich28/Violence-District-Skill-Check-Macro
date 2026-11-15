#!/bin/bash
cd "$(dirname "$0")"
PY="$(bash src/find_python.sh)"
if [ -z "$PY" ]; then
  echo
  echo " Python 3.10-3.13 was not found."
  echo " Install it from https://www.python.org/downloads/macos/ and run Setup.command again."
  echo
  read -n 1 -s -r -p " Press any key to close..."
  exit 1
fi
echo " Using $PY"
if "$PY" src/setup_env.py; then
  echo
  echo " Setup finished. Start it with Launch.command."
else
  echo
  echo " Setup did not finish, see above."
fi
echo
read -n 1 -s -r -p " Press any key to close..."
