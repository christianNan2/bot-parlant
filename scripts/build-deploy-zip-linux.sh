#!/usr/bin/env bash
# Build dependencies in a Linux container (matches App Service) and zip for fast deploy.
# Requires Docker. Skips Oryx on Azure (set SCM_DO_BUILD_DURING_DEPLOYMENT=false before deploy).
# Usage: ./scripts/build-deploy-zip-linux.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ZIP="${ROOT}/deploy/app.zip"
IMAGE="${ORYX_BUILD_IMAGE:-mcr.microsoft.com/azure-app-service/python:3.12}"

mkdir -p "${ROOT}/deploy"
rm -f "$ZIP"

echo "Building dashboard into backend/static/dashboard/ ..."
"${ROOT}/scripts/build-frontend.sh"

echo "Installing Python packages in ${IMAGE} (first run may pull the image)..."
docker run --rm \
  -v "${ROOT}/backend:/app" \
  -w /app \
  "$IMAGE" \
  bash -c 'rm -rf antenv && python -m venv antenv && source antenv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt'

(
  cd "${ROOT}/backend"
  zip -r "$ZIP" . \
    -x ".venv/*" \
    -x ".env" \
    -x "__pycache__/*" \
    -x "*.pyc" \
    -x "deploy.zip" \
    -x "*.zip"
)

echo "Built ${ZIP} ($(du -h "$ZIP" | cut -f1)). Deploy with:"
echo "  az webapp config appsettings set -g <rg> -n <app> --settings SCM_DO_BUILD_DURING_DEPLOYMENT=false"
echo "  ./scripts/deploy-to-azure.sh <webapp-name> <resource-group>"
