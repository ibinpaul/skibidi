#!/usr/bin/env bash
set -e
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -f .env ]; then
  echo ".env not found in $ROOT_DIR. Create it from .env.template and add your keys."
  exit 1
fi

# export all vars from .env
set -a
# shellcheck disable=SC1091
source .env
set +a

# Run the checker using the project's venv python
./.venv/bin/python tools/check_supabase.py
