#!/usr/bin/env bash
# One-time App Service setup: env vars, startup command, managed identity, RBAC.
# Usage: ./scripts/configure-azure-app.sh <webapp-name> <resource-group>
set -euo pipefail

WEBAPP_NAME="${1:?Usage: $0 <webapp-name> <resource-group>}"
RESOURCE_GROUP="${2:?Usage: $0 <webapp-name> <resource-group>}"
ENV_FILE="${3:-$(cd "$(dirname "$0")/.." && pwd)/backend/.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing env file: $ENV_FILE"
  exit 1
fi

# Load non-secret config from local .env (do not commit .env).
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

HOST="$(az webapp show --resource-group "$RESOURCE_GROUP" --name "$WEBAPP_NAME" --query defaultHostName -o tsv 2>/dev/null || true)"
BACKEND_URL="${BACKEND_PUBLIC_URL:-}"
if [[ -z "$BACKEND_URL" && -n "$HOST" ]]; then
  BACKEND_URL="https://${HOST}"
fi

az webapp config appsettings set \
  --resource-group "$RESOURCE_GROUP" \
  --name "$WEBAPP_NAME" \
  --settings \
    BACKEND_PUBLIC_URL="${BACKEND_URL}" \
    AZURE_AI_ENDPOINT="${AZURE_AI_ENDPOINT:-}" \
    AZURE_EXISTING_AIPROJECT_ENDPOINT="${AZURE_EXISTING_AIPROJECT_ENDPOINT:-}" \
    AZURE_EXISTING_AGENT_NAME="${AZURE_EXISTING_AGENT_NAME:-}" \
    AZURE_EXISTING_AGENT_VERSION="${AZURE_EXISTING_AGENT_VERSION:-}" \
    AZURE_PROJECT_NAME="${AZURE_PROJECT_NAME:-}" \
    AZURE_AI_RESOURCE_NAME="${AZURE_AI_RESOURCE_NAME:-}" \
    AZURE_VOICELIVE_ENDPOINT="${AZURE_VOICELIVE_ENDPOINT:-}" \
    VOICELIVE_API_VERSION="${VOICELIVE_API_VERSION:-2026-01-01-preview}" \
    AZURE_SQL_SERVER="${AZURE_SQL_SERVER:-}" \
    AZURE_SQL_DATABASE="${AZURE_SQL_DATABASE:-}" \
    AZURE_SQL_USER="${AZURE_SQL_USER:-}" \
    AZURE_SQL_USE_AAD="${AZURE_SQL_USE_AAD:-true}" \
    SCM_DO_BUILD_DURING_DEPLOYMENT=true \
    SCM_COMMAND_IDLE_TIMEOUT=3600 \
    WEBSITES_CONTAINER_START_TIME_LIMIT=600 \
    ENABLE_ORYX_BUILD=true

if [[ -n "${AZURE_SQL_PASSWORD:-}" ]]; then
  az webapp config appsettings set \
    --resource-group "$RESOURCE_GROUP" \
    --name "$WEBAPP_NAME" \
    --settings "AZURE_SQL_PASSWORD=${AZURE_SQL_PASSWORD}" \
    --output none
fi

if [[ -n "${REGISTRATION_API_KEY:-}" ]]; then
  az webapp config appsettings set \
    --resource-group "$RESOURCE_GROUP" \
    --name "$WEBAPP_NAME" \
    --settings "REGISTRATION_API_KEY=${REGISTRATION_API_KEY}" \
    --output none
fi

az webapp config set \
  --resource-group "$RESOURCE_GROUP" \
  --name "$WEBAPP_NAME" \
  --startup-file "startup.sh" \
  --linux-fx-version "PYTHON|3.12"

echo "Enabling system-assigned managed identity..."
PRINCIPAL_ID="$(az webapp identity assign \
  --resource-group "$RESOURCE_GROUP" \
  --name "$WEBAPP_NAME" \
  --query principalId -o tsv)"

if [[ -n "${AZURE_EXISTING_RESOURCE_ID:-}" ]]; then
  echo "Granting Cognitive Services User on Foundry account..."
  az role assignment create \
    --assignee-object-id "$PRINCIPAL_ID" \
    --assignee-principal-type ServicePrincipal \
    --role "Cognitive Services User" \
    --scope "$AZURE_EXISTING_RESOURCE_ID" \
    --output none 2>/dev/null || echo "(Role may already exist — OK)"
else
  echo "Set AZURE_EXISTING_RESOURCE_ID in .env to auto-assign RBAC, or assign manually in the portal."
fi

echo "Configured ${WEBAPP_NAME}. Run ./scripts/deploy-to-azure.sh next."
