#!/usr/bin/env bash
# Smoke-test POST /api/users/register
# Usage: ./scripts/test-register-api.sh [base-url]
set -euo pipefail

BASE="${1:-http://localhost:5440}"
STAMP="$(date +%s)"
EMAIL="test-${STAMP}@example.com"

HEADERS=(-H "Content-Type: application/json")
if [[ -n "${REGISTRATION_API_KEY:-}" ]]; then
  HEADERS+=(-H "X-API-Key: ${REGISTRATION_API_KEY}")
fi

echo "POST ${BASE}/api/users/register"
RESP="$(curl -sS -w "\n%{http_code}" -X POST "${BASE}/api/users/register" \
  "${HEADERS[@]}" \
  -d "{
    \"firstName\": \"Test\",
    \"lastName\": \"User\",
    \"email\": \"${EMAIL}\",
    \"city\": \"Paris\",
    \"country\": \"France\"
  }")"

BODY="$(echo "$RESP" | sed '$d')"
CODE="$(echo "$RESP" | tail -n 1)"

echo "HTTP ${CODE}"
echo "$BODY" | python3 -m json.tool 2>/dev/null || echo "$BODY"

if [[ "$CODE" != "201" ]]; then
  echo "Expected 201 — check SQL config and Azure AD / password." >&2
  exit 1
fi

echo "OK — registered ${EMAIL}"
