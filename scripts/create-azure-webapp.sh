#!/usr/bin/env bash
# Create a Linux Python 3.12 App Service (plan + web app) if missing.
# Usage: ./scripts/create-azure-webapp.sh <webapp-name> <resource-group> [app-service-plan-name]
# Default plan SKU is F1 (Free). Override: AZURE_APP_SERVICE_SKU=B1 ./scripts/create-azure-webapp.sh ...
set -euo pipefail

WEBAPP_NAME="${1:?Usage: $0 <webapp-name> <resource-group> [plan-name]}"
RESOURCE_GROUP="${2:?Usage: $0 <webapp-name> <resource-group> [plan-name]}"
PLAN_NAME="${3:-asp-$(echo "$WEBAPP_NAME" | tr '[:upper:]' '[:lower:]')}"
LOCATION="${AZURE_LOCATION:-germanywestcentral}"
SKU="${AZURE_APP_SERVICE_SKU:-F1}"

if az webapp show --resource-group "$RESOURCE_GROUP" --name "$WEBAPP_NAME" &>/dev/null; then
  HOST="$(az webapp show --resource-group "$RESOURCE_GROUP" --name "$WEBAPP_NAME" --query defaultHostName -o tsv)"
  echo "Web app already exists: https://${HOST}"
  exit 0
fi

if ! az group show --name "$RESOURCE_GROUP" &>/dev/null; then
  echo "Creating resource group ${RESOURCE_GROUP} (${LOCATION})..."
  az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none
fi

if ! az appservice plan show --resource-group "$RESOURCE_GROUP" --name "$PLAN_NAME" &>/dev/null; then
  echo "Creating App Service plan ${PLAN_NAME} (${SKU}, Linux)..."
  az appservice plan create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$PLAN_NAME" \
    --location "$LOCATION" \
    --sku "$SKU" \
    --is-linux \
    --output none
fi

echo "Creating web app ${WEBAPP_NAME}..."
az webapp create \
  --resource-group "$RESOURCE_GROUP" \
  --plan "$PLAN_NAME" \
  --name "$WEBAPP_NAME" \
  --runtime "PYTHON:3.12" \
  --output none

HOST="$(az webapp show --resource-group "$RESOURCE_GROUP" --name "$WEBAPP_NAME" --query defaultHostName -o tsv)"
echo "Created https://${HOST}"
echo "Next: ./scripts/configure-azure-app.sh ${WEBAPP_NAME} ${RESOURCE_GROUP}"
