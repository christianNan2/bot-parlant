#!/usr/bin/env bash
# Deploy the Flask bot to Azure App Service (Linux, Python).
# Usage: ./scripts/deploy-to-azure.sh <webapp-name> <resource-group> [--prebuilt]
set -euo pipefail

WEBAPP_NAME="${1:?Usage: $0 <webapp-name> <resource-group> [--prebuilt]}"
RESOURCE_GROUP="${2:?Usage: $0 <webapp-name> <resource-group> [--prebuilt]}"
PREBUILT="${3:-}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ZIP="${ROOT}/deploy/app.zip"

build_frontend() {
  echo "Building dashboard into backend/static/dashboard/ ..."
  "${ROOT}/scripts/build-frontend.sh"
}

pack_backend_zip() {
  local exclude_antenv="${1:-false}"
  rm -f "$ZIP"
  echo "Packaging backend (Flask app + static dashboard + chat)..."
  local -a excludes=(
    -x ".venv/*"
    -x ".env"
    -x "__pycache__/*"
    -x "*.pyc"
    -x "deploy.zip"
    -x "*.zip"
  )
  if [[ "$exclude_antenv" == "true" ]]; then
    excludes+=(-x "antenv/*")
  fi
  (
    cd "${ROOT}/backend"
    zip -r "$ZIP" . "${excludes[@]}"
  )
}

if ! az webapp show --resource-group "$RESOURCE_GROUP" --name "$WEBAPP_NAME" &>/dev/null; then
  echo "Web app '${WEBAPP_NAME}' not found in '${RESOURCE_GROUP}'."
  echo "Create it first: ./scripts/create-azure-webapp.sh ${WEBAPP_NAME} ${RESOURCE_GROUP}"
  exit 1
fi

HOST="$(az webapp show --resource-group "$RESOURCE_GROUP" --name "$WEBAPP_NAME" --query defaultHostName -o tsv)"

if [[ "$PREBUILT" == "--prebuilt" ]]; then
  if [[ ! -d "${ROOT}/backend/antenv" ]]; then
    echo "Missing backend/antenv. Run: ./scripts/build-deploy-zip-linux.sh"
    exit 1
  fi
  build_frontend
  pack_backend_zip false
elif [[ ! -f "$ZIP" ]] || [[ "${REBUILD_ZIP:-}" == "1" ]]; then
  mkdir -p "${ROOT}/deploy"
  build_frontend
  pack_backend_zip true
fi

SCM_BUILD="$(az webapp config appsettings list \
  --resource-group "$RESOURCE_GROUP" \
  --name "$WEBAPP_NAME" \
  --query "[?name=='SCM_DO_BUILD_DURING_DEPLOYMENT'].value | [0]" -o tsv 2>/dev/null || true)"

if [[ "$PREBUILT" == "--prebuilt" ]]; then
  echo "Using pre-built antenv in zip (no Oryx pip install on Azure)."
elif [[ "$SCM_BUILD" == "true" ]]; then
  echo ""
  echo "Oryx will pip-install requirements on Azure (azure-ai-*, gevent, pyodbc)."
  echo "First deploy often takes 20–35 minutes on B1/F1. Do not Ctrl+C unless it fails."
  echo "Faster option: ./scripts/build-deploy-zip-linux.sh then redeploy with --prebuilt"
  echo ""
fi

echo "Deploying to ${WEBAPP_NAME} (${RESOURCE_GROUP})..."
echo "URL: https://${HOST}"

# Synchronous deploy: CLI blocks until Oryx/build finishes or errors.
az webapp deploy \
  --resource-group "$RESOURCE_GROUP" \
  --name "$WEBAPP_NAME" \
  --src-path "$ZIP" \
  --type zip \
  --clean true \
  --restart true \
  --track-status true \
  --timeout 3600000

echo ""
echo "Deployment finished. Checking /health ..."
for _ in 1 2 3 4 5 6; do
  CODE="$(curl -sS -m 20 -o /tmp/voicebot-health.txt -w "%{http_code}" "https://${HOST}/health" || true)"
  if [[ "$CODE" == "200" ]]; then
    cat /tmp/voicebot-health.txt
    echo ""
    echo "OK — https://${HOST}"
    echo "     Chat:       https://${HOST}/"
    echo "     Dashboard:  https://${HOST}/dashboard/"
    exit 0
  fi
  sleep 10
done

echo "Deploy completed but /health returned HTTP ${CODE:-unknown}."
echo "Stream logs: az webapp log tail -g ${RESOURCE_GROUP} -n ${WEBAPP_NAME}"
echo "Kudu:        https://${WEBAPP_NAME}.scm.azurewebsites.net/api/logs/docker"
exit 1
