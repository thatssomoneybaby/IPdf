#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${ROOT_DIR}/app"
VENV_DIR="${ROOT_DIR}/.venv-deps"

python3 -m venv "${VENV_DIR}"
source "${VENV_DIR}/bin/activate"
python -m pip install --upgrade pip
python -m pip install -r "${APP_DIR}/requirements.txt"
python -m pip freeze > "${APP_DIR}/constraints.txt"

echo "Wrote ${APP_DIR}/constraints.txt"
