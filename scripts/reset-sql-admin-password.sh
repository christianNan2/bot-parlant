#!/usr/bin/env bash
# Reset the Azure SQL server administrator password (the login shown as CloudSA... in connection strings).
# Usage: ./scripts/reset-sql-admin-password.sh <resource-group> <sql-server-name> <new-password>
set -euo pipefail

RESOURCE_GROUP="${1:?Usage: $0 <resource-group> <sql-server-name> <new-password>}"
SQL_SERVER="${2:?Usage: $0 <resource-group> <sql-server-name> <new-password>}"
NEW_PASSWORD="${3:?Usage: $0 <resource-group> <sql-server-name> <new-password>}"

ADMIN_USER="$(az sql server show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$SQL_SERVER" \
  --query administratorLogin -o tsv)"

echo "Resetting password for SQL admin '${ADMIN_USER}' on server '${SQL_SERVER}'..."
az sql server update \
  --resource-group "$RESOURCE_GROUP" \
  --name "$SQL_SERVER" \
  --admin-user "$ADMIN_USER" \
  --admin-password "$NEW_PASSWORD" \
  --output none

echo "Done. Add to backend/.env:"
echo "  AZURE_SQL_USER=${ADMIN_USER}"
echo "  AZURE_SQL_PASSWORD=<the password you just set>"
echo "  AZURE_SQL_USE_AAD=false"
