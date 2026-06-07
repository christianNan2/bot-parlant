#!/usr/bin/env bash
# Build the React dashboard into backend/static/dashboard/ for Flask to serve.
# Usage: ./scripts/build-frontend.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FRONTEND="${ROOT}/frontend"
OUT="${ROOT}/backend/static/dashboard/index.html"

if ! command -v npm >/dev/null 2>&1; then
  echo "Error: npm is required to build the dashboard." >&2
  exit 1
fi

echo "Building dashboard frontend..."
(
  cd "$FRONTEND"
  if [[ -f package-lock.json ]]; then
    npm ci
  else
    npm install
  fi
  npm run build
)

if [[ ! -f "$OUT" ]]; then
  echo "Error: build did not produce ${OUT}" >&2
  exit 1
fi

echo "Dashboard ready at backend/static/dashboard/ (served by Flask at /dashboard/)"
