#!/usr/bin/env bash
# One-time setup: Azure AD app + OIDC for GitHub Actions deploy to App Service.
#
# Usage:
#   ./scripts/setup-github-actions-azure.sh <webapp-name> <resource-group> [github-org/repo]
#
# Example:
#   ./scripts/setup-github-actions-azure.sh UserRegistrationBot rg-voicebot-sose26 christianNan2/bot-parlant
#
# Then add the printed values to GitHub → Settings → Secrets and variables → Actions.
set -euo pipefail

WEBAPP_NAME="${1:?Usage: $0 <webapp-name> <resource-group> [github-org/repo]}"
RESOURCE_GROUP="${2:?Usage: $0 <webapp-name> <resource-group> [github-org/repo]}"
GITHUB_REPO="${3:-christianNan2/bot-parlant}"
APP_NAME="github-actions-${WEBAPP_NAME}"
BRANCH="${GITHUB_DEPLOY_BRANCH:-main}"

if ! az account show &>/dev/null; then
  echo "Run 'az login' first."
  exit 1
fi

if ! az webapp show --resource-group "$RESOURCE_GROUP" --name "$WEBAPP_NAME" &>/dev/null; then
  echo "Web app '${WEBAPP_NAME}' not found in '${RESOURCE_GROUP}'."
  exit 1
fi

SUBSCRIPTION_ID="$(az account show --query id -o tsv)"
TENANT_ID="$(az account show --query tenantId -o tsv)"
WEBAPP_ID="$(az webapp show --resource-group "$RESOURCE_GROUP" --name "$WEBAPP_NAME" --query id -o tsv)"

echo "Creating app registration '${APP_NAME}' (skip if it already exists)..."
APP_ID="$(az ad app create --display-name "$APP_NAME" --query appId -o tsv 2>/dev/null || true)"
if [[ -z "$APP_ID" ]]; then
  APP_ID="$(az ad app list --display-name "$APP_NAME" --query "[0].appId" -o tsv)"
fi

SP_OBJECT_ID="$(az ad sp list --filter "appId eq '$APP_ID'" --query "[0].id" -o tsv)"
if [[ -z "$SP_OBJECT_ID" || "$SP_OBJECT_ID" == "null" ]]; then
  az ad sp create --id "$APP_ID" --output none
  SP_OBJECT_ID="$(az ad sp show --id "$APP_ID" --query id -o tsv)"
fi

CRED_NAME="github-${GITHUB_REPO//\//-}-${BRANCH}"
echo "Adding federated credential '${CRED_NAME}' for repo ${GITHUB_REPO} (branch ${BRANCH})..."
az ad app federated-credential create \
  --id "$APP_ID" \
  --parameters "{
    \"name\": \"${CRED_NAME}\",
    \"issuer\": \"https://token.actions.githubusercontent.com\",
    \"subject\": \"repo:${GITHUB_REPO}:ref:refs/heads/${BRANCH}\",
    \"description\": \"GitHub Actions deploy from ${GITHUB_REPO}\",
    \"audiences\": [\"api://AzureADTokenExchange\"]
  }" \
  --output none 2>/dev/null || echo "(Federated credential may already exist — OK)"

echo "Granting Website Contributor on ${WEBAPP_NAME}..."
az role assignment create \
  --assignee-object-id "$SP_OBJECT_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Website Contributor" \
  --scope "$WEBAPP_ID" \
  --output none 2>/dev/null || echo "(Role may already exist — OK)"

echo ""
echo "=== GitHub configuration ==="
echo ""
echo "Repository variables (Settings → Secrets and variables → Actions → Variables):"
echo "  AZURE_WEBAPP_NAME      = ${WEBAPP_NAME}"
echo "  AZURE_RESOURCE_GROUP   = ${RESOURCE_GROUP}"
echo ""
echo "Repository secrets (Settings → Secrets and variables → Actions → Secrets):"
echo "  AZURE_CLIENT_ID        = ${APP_ID}"
echo "  AZURE_TENANT_ID        = ${TENANT_ID}"
echo "  AZURE_SUBSCRIPTION_ID  = ${SUBSCRIPTION_ID}"
echo ""
echo "Optional: create a 'production' environment in GitHub for deploy approval gates."
echo "Workflow file: .github/workflows/ci-cd.yml"
echo ""
echo "Ensure App Service app settings are configured once:"
echo "  ./scripts/configure-azure-app.sh ${WEBAPP_NAME} ${RESOURCE_GROUP}"
