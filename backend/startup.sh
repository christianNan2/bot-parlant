#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

# On Azure App Service Linux, set AZURE_SQL_INSTALL_ODBC=true once so msodbcsql18 is available.
if [[ "${AZURE_SQL_INSTALL_ODBC:-}" == "true" ]] && ! odbcinst -q -d 2>/dev/null | grep -q "ODBC Driver 18"; then
  curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg
  curl -fsSL https://packages.microsoft.com/config/debian/12/prod.list > /etc/apt/sources.list.d/mssql-release.list
  apt-get update -qq
  ACCEPT_EULA=Y apt-get install -y -qq msodbcsql18 unixodbc-dev
fi

PORT="${PORT:-8000}"
if [[ -x "./antenv/bin/gunicorn" ]]; then
  GUNICORN="./antenv/bin/gunicorn"
else
  GUNICORN="gunicorn"
fi
exec "$GUNICORN" --bind "0.0.0.0:${PORT}" --worker-class gevent --workers 2 --timeout 120 app:app
