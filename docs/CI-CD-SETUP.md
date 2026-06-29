# CI/CD — GitHub Actions → Azure App Service

Pushes to `main` build the dashboard, pre-install Python dependencies in a Linux container (same image as App Service), zip the backend, and deploy to Azure. Pull requests run the same build without deploying.

## Pipeline

| Trigger | Jobs |
|---------|------|
| Pull request → `main` | Build, lint, validate |
| Push → `main` | Build + deploy to Azure |
| Manual (`workflow_dispatch`) | Build + deploy |

The workflow uses the **pre-built `antenv`** path (see [DEPLOY-AZURE.md](./DEPLOY-AZURE.md)) so deploys finish in minutes instead of waiting for Oryx on the server.

## One-time Azure + GitHub setup

### 1. App Service must already exist

```bash
./scripts/create-azure-webapp.sh UserRegistrationBot rg-voicebot-sose26
./scripts/configure-azure-app.sh UserRegistrationBot rg-voicebot-sose26
```

`configure-azure-app.sh` reads `backend/.env` locally and sets app settings (AI endpoints, SQL, managed identity). That step stays manual — CI only uploads code.

### 2. Create OIDC credentials for GitHub Actions

```bash
./scripts/setup-github-actions-azure.sh \
  UserRegistrationBot \
  rg-voicebot-sose26 \
  christianNan2/bot-parlant
```

The script prints three secrets and two variables to add in GitHub.

### 3. Configure GitHub

**Settings → Secrets and variables → Actions → Variables**

| Name | Example |
|------|---------|
| `AZURE_WEBAPP_NAME` | `UserRegistrationBot` |
| `AZURE_RESOURCE_GROUP` | `rg-voicebot-sose26` |

**Settings → Secrets and variables → Actions → Secrets**

| Name | Source |
|------|--------|
| `AZURE_CLIENT_ID` | App registration from setup script |
| `AZURE_TENANT_ID` | `az account show --query tenantId` |
| `AZURE_SUBSCRIPTION_ID` | `az account show --query id` |

**Optional:** create a **production** environment under Settings → Environments to require manual approval before deploy.

### 4. Enable Actions

Push the workflow to `main`. The first run appears under **Actions → CI/CD**.

## Verify after deploy

```bash
HOST=$(az webapp show -g rg-voicebot-sose26 -n UserRegistrationBot --query defaultHostName -o tsv)
curl -sS "https://${HOST}/health"
```

## Troubleshooting

| Symptom | What to check |
|---------|----------------|
| `AZURE_WEBAPP_NAME` empty | Repository variables not set |
| Azure login fails | OIDC federated credential subject must match `repo:<org>/<repo>:ref:refs/heads/main` |
| Deploy OK, 503 on `/health` | App settings / SQL / managed identity — run `az webapp log tail` |
| Build fails on Docker step | GitHub-hosted runners include Docker; re-run the job |

Local equivalent of the pipeline:

```bash
./scripts/build-deploy-zip-linux.sh
az webapp config appsettings set -g <rg> -n <app> --settings SCM_DO_BUILD_DURING_DEPLOYMENT=false
./scripts/deploy-to-azure.sh <app> <rg> --prebuilt
```
