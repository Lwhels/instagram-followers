#!/usr/bin/env bash
# Runner for Instagram Follower Analyzer on macOS
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." >/dev/null 2>&1 && pwd )"
cd "$DIR"

# Check if .venv exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "[*] Creating virtual environment..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
fi

export PYTHONPATH="$DIR:$PYTHONPATH"
echo "[*] Launching Instagram Follower Analyzer (macOS Desktop Mode)..."
python macos/app.py
