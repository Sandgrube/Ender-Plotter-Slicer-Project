#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[ERROR] python3 was not found. Install Python 3.10 or newer."
  exit 1
fi

python3 - <<'PYVERSION'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("[ERROR] Python 3.10 or newer is required.")
PYVERSION

if [ ! -x ".venv/bin/python" ]; then
  echo "[INFO] Creating local virtual environment: .venv"
  python3 -m venv .venv
fi

VPY="$(pwd)/.venv/bin/python"
echo "[INFO] Installing Python dependencies..."
"$VPY" -m pip install --upgrade pip setuptools wheel
"$VPY" -m pip install -r requirements.txt

echo "[INFO] Verifying imports..."
"$VPY" -c "import PySide6, svgpathtools, matplotlib, PIL; print('Imports OK')"

echo "[START] Launching Ender Plotter Slicer..."
"$VPY" -m ender_plotter_slicer
