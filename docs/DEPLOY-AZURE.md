# Deploy to Azure App Service

## Single app, two paths

Everything runs on **one Flask instance** (local or Azure App Service):

| Path | App |
|------|-----|
| `/` | Registration chat agent (voice + text) |
| `/dashboard/` | Users dashboard (React, built into `backend/static/dashboard/`) |
| `/api/*` | Shared JSON API (chat, registration, dashboard) |
| `/health` | Health check |

Build the dashboard before deploy (included in the scripts below):

```bash
./scripts/build-frontend.sh   # npm build → backend/static/dashboard/
cd backend && python app.py   # one server on PORT (default 5444)
```

- Chat: http://localhost:5444/
- Dashboard: http://localhost:5444/dashboard/

The frontend is **not** a separate host in production — `frontend/` is only the source; output is static files served by Flask.

## What went wrong

Zip deploy with `SCM_DO_BUILD_DURING_DEPLOYMENT=true` runs **Oryx** on the server: it `pip install`s everything in `requirements.txt`, including heavy packages (`azure-ai-voicelive`, `azure-ai-projects`, `gevent`, `pyodbc`). That step often takes **20–35 minutes** on a small plan. Stopping the CLI with Ctrl+C leaves the site in a bad state (503) until a full deploy finishes.

## Recommended flow

```bash
# 1. Create the web app (once) — skip if it already exists in the portal
./scripts/create-azure-webapp.sh UserRegistrationBot rg-voicebot-sose26

# 2. Push env vars, Python 3.12, startup.sh, managed identity
./scripts/configure-azure-app.sh UserRegistrationBot rg-voicebot-sose26

# 3a. Standard deploy (slow first time; wait until the CLI exits)
./scripts/deploy-to-azure.sh UserRegistrationBot rg-voicebot-sose26

# 3b. Faster deploy (build deps locally with Docker, then upload)
./scripts/build-deploy-zip-linux.sh
az webapp config appsettings set -g rg-voicebot-sose26 -n UserRegistrationBot \
  --settings SCM_DO_BUILD_DURING_DEPLOYMENT=false
./scripts/deploy-to-azure.sh UserRegistrationBot rg-voicebot-sose26 --prebuilt
```

## Verify

```bash
HOST=$(az webapp show -g rg-voicebot-sose26 -n UserRegistrationBot --query defaultHostName -o tsv)
curl -sS "https://${HOST}/health"
```

For agent → SQL registration (OpenAPI tool, Entra ID, confirmation flow), see [USER-REGISTRATION.md](./USER-REGISTRATION.md).

## If deploy fails or the app shows “Application Error”

1. Run deploy again **without** cancelling; use `--clean true` (the deploy script does this).
2. Tail logs: `az webapp log tail -g rg-voicebot-sose26 -n UserRegistrationBot`
3. In Kudu → Deployment Center → latest deployment → **View log** for Oryx/pip errors.
4. For SQL: ensure managed identity has access to Azure SQL; ODBC driver 18 is on the App Service Python image—avoid `AZURE_SQL_INSTALL_ODBC=true` unless you use a custom container (startup `apt-get` does not work on default App Service).

## Resource group note

`UserRegistrationBot` must exist as `Microsoft.Web/sites` in the resource group. If `az webapp list` is empty, create the app with `create-azure-webapp.sh` or the Azure Portal before deploying.
