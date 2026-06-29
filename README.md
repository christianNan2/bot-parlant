# Bot Parlant – Mehrsprachiger Registrierungs-Sprachbot mit Azure

## Kurzbeschreibung

Bot Parlant ist ein cloudbasierter Registrierungsassistent, der Benutzer durch die Erstellung eines Benutzerkontos führt. Der Assistent unterstützt Deutsch, Englisch und Französisch, kann textbasiert und sprachbasiert genutzt werden und speichert bestätigte Registrierungsdaten in einer Azure SQL Database.

Das Projekt kombiniert Microsoft Foundry Agent Service, Azure Speech Service, ein Python/Flask Backend, Azure SQL Database und ein React Admin Dashboard.

## Hauptfunktionen

- Mehrsprachiger Registrierungsdialog in Deutsch, Englisch und Französisch
- Zwei Registrierungsmodi:
  - Schrittweise Registrierung
  - Schnellregistrierung mit Extraktion mehrerer Felder aus einem Satz
- Voice- und Textinteraktion
- Plain-Text-Ausgabe für saubere Sprachausgabe
- Validierung von Benutzereingaben
- Korrektur einzelner Felder vor dem Speichern
- Speicherung erst nach ausdrücklicher Bestätigung
- OpenAPI Tool `register_user` für den Foundry Agent
- Azure SQL Speicherung in `dbo.Users`
- Admin Dashboard zur Anzeige und Verwaltung gespeicherter Benutzer
- Health Check und API-Testmöglichkeiten

## Architektur

```text
Benutzer
  ↓
Web-Chat / Voice UI
  ↓
Microsoft Foundry Agent
  ↓
OpenAPI Tool register_user
  ↓
Python Flask Backend
  ↓
Azure SQL Database
```

Zusätzlich:

```text
Azure Speech Service
  ↔
Voice WebSocket Backend
  ↔
Browser Audio Ein- und Ausgabe
```

## Verwendete Azure-Dienste

- Microsoft Foundry Agent Service für Dialogführung und Tool-Aufruf
- Azure Speech Service für Spracheingabe und Sprachausgabe
- Azure SQL Database für persistente Speicherung der Benutzerdaten
- Azure App Service für Hosting des Backends und Dashboards
- Azure Key Vault oder App Service Application Settings für sichere Konfiguration
- Microsoft Entra ID oder SQL Login für Datenbankauthentifizierung

## Projektstruktur

```text
bot-parlant-main/
│
├── backend/
│   ├── app.py                         # Flask App, API-Routen, Chat, Dashboard, Health Check
│   ├── user_repository.py             # Azure SQL Zugriff und Benutzerverwaltung
│   ├── voice_service.py               # Voice-Konfiguration und Speech-Service-Anbindung
│   ├── voice_handler.py               # WebSocket-Voice-Handling
│   ├── dashboard_auth.py              # Dashboard-Login und Session-Verwaltung
│   ├── openapi_loader.py              # Lädt OpenAPI-Spezifikation für Foundry Tool
│   ├── openapi/register-user.yaml     # OpenAPI Tool register_user
│   ├── prompts/agent-registration-instructions.md
│   ├── requirements.txt
│   ├── runtime.txt
│   ├── startup.sh
│   ├── static/
│   └── templates/
│
├── frontend/
│   ├── src/                           # React Dashboard Source Code
│   ├── package.json
│   └── vite.config.ts
│
├── docs/
│   ├── DEPLOY-AZURE.md
│   └── USER-REGISTRATION.md
│
└── scripts/
    ├── build-frontend.sh
    ├── create-azure-webapp.sh
    ├── configure-azure-app.sh
    ├── deploy-to-azure.sh
    ├── attach-register-openapi-tool.py
    └── test-register-api.sh
```

## Lokaler Schnellstart

### 1. Repository klonen

```bash
git clone https://github.com/christianNan2/bot-parlant.git
cd bot-parlant
```

### 2. Backend vorbereiten

```bash
cd backend
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

Linux/macOS:

```bash
source .venv/bin/activate
```

Pakete installieren:

```bash
pip install -r requirements.txt
```

### 3. Umgebungsvariablen konfigurieren

Erstelle eine Datei `backend/.env`.

Beispiel mit SQL Login:

```env
FLASK_SECRET_KEY=change-me

AZURE_AI_ENDPOINT=https://<foundry-resource>.services.ai.azure.com/api/projects/<project-name>
AZURE_EXISTING_AGENT_NAME=registration-agent
AZURE_EXISTING_AGENT_VERSION=5

AZURE_SQL_SERVER=nannan.database.windows.net
AZURE_SQL_DATABASE=free-sql-db-5222099
AZURE_SQL_PORT=1433
AZURE_SQL_USER=<sql-admin-user>
AZURE_SQL_PASSWORD=<sql-password>
AZURE_SQL_USE_AAD=false

BACKEND_PUBLIC_URL=http://localhost:5444
REGISTRATION_API_KEY=
```

Beispiel mit Microsoft Entra ID:

```env
AZURE_SQL_SERVER=nannan.database.windows.net
AZURE_SQL_DATABASE=free-sql-db-5222099
AZURE_SQL_PORT=1433
AZURE_SQL_USE_AAD=true
```

Bei Entra ID lokal vorher anmelden:

```bash
az login
```

### 4. Backend starten

```bash
python app.py
```

Standardmäßig läuft die Anwendung auf:

```text
http://localhost:5444
```

### 5. Health Check prüfen

```bash
curl http://localhost:5444/health
```

Wichtige Werte:

```json
{
  "foundryConfigured": true,
  "voiceConfigured": true,
  "sqlConfigured": true
}
```

## Wichtige URLs

| URL | Beschreibung |
|---|---|
| `/` | Chat- und Voice-Oberfläche |
| `/health` | Systemstatus |
| `/voice/config` | öffentliche Voice-Konfiguration |
| `/openapi/register-user.json` | OpenAPI Tool als JSON |
| `/openapi/register-user.yaml` | OpenAPI Tool als YAML |
| `/api/users/register` | Registrierung durch Foundry Tool |
| `/dashboard/` | Admin Dashboard |
| `/api/users` | Dashboard Benutzerverwaltung |
| `/api/users/stats` | Dashboard Statistiken |

## Datenbankmodell

Empfohlene Tabelle:

```sql
CREATE TABLE dbo.Users (
    id INT IDENTITY(1,1) PRIMARY KEY,
    firstName NVARCHAR(100) NOT NULL,
    lastName NVARCHAR(100) NOT NULL,
    email NVARCHAR(255) NOT NULL UNIQUE,
    birthDate DATE NULL,
    phone NVARCHAR(50) NULL,
    street NVARCHAR(150) NULL,
    zip NVARCHAR(20) NULL,
    city NVARCHAR(100) NULL,
    country NVARCHAR(100) NULL,
    createdAt DATETIME2 DEFAULT SYSUTCDATETIME()
);
```

Je nach Projektstand können zusätzliche Spalten wie `houseNumber`, `language` oder `addressValidated` ergänzt werden.

## Registrierung über Foundry Tool

Der Foundry Agent nutzt das OpenAPI Tool `register_user`.

Ablauf:

```text
1. Agent sammelt Daten.
2. Agent fasst alle Daten zusammen.
3. Benutzer bestätigt.
4. Agent ruft register_user auf.
5. Backend validiert und speichert in Azure SQL.
6. Backend gibt userId und createdAt zurück.
7. Agent bestätigt erfolgreiche Registrierung.
```

## Beispiel-Request

```json
{
  "firstName": "Christian",
  "lastName": "Nan-Nan",
  "email": "christian@example.com",
  "birthDate": "2001-05-12",
  "phone": "017612345678",
  "street": "Hauptstraße 12",
  "zip": "10115",
  "city": "Berlin",
  "country": "Deutschland"
}
```

## Deployment auf Azure App Service

Die Anwendung läuft produktiv als eine Flask-App:

```text
App Service
  ├── Flask Backend
  ├── Chat UI
  ├── Voice WebSocket
  ├── OpenAPI Tool Endpoint
  └── React Dashboard als statische Dateien
```

Empfohlene Schritte:

```bash
./scripts/build-frontend.sh
./scripts/create-azure-webapp.sh <APP_NAME> <RESOURCE_GROUP>
./scripts/configure-azure-app.sh <APP_NAME> <RESOURCE_GROUP>
./scripts/deploy-to-azure.sh <APP_NAME> <RESOURCE_GROUP>
```

Nach Deployment:

```bash
https://<APP_NAME>.azurewebsites.net/health
```

## Demo-Ablauf

1. Health Check öffnen.
2. Chat-Oberfläche öffnen.
3. Registrierung starten.
4. Schrittweise oder Schnellregistrierung wählen.
5. Beispielwerte eingeben.
6. Validierung oder Korrektur demonstrieren.
7. Zusammenfassung bestätigen.
8. Speicherung in SQL oder Dashboard zeigen.

## Typische Fehler

| Problem | Ursache | Lösung |
|---|---|---|
| `sqlConfigured=false` | SQL Variablen fehlen | App Settings oder `.env` prüfen |
| Agent ruft Tool nicht auf | Tool nicht gespeichert oder Version nicht veröffentlicht | Tool erneut verbinden, Agent speichern/publizieren |
| Foundry kann localhost nicht erreichen | Foundry läuft in Azure | App Service URL oder Dev Tunnel/ngrok verwenden |
| SQL Login Fehler | falscher Benutzer oder Passwort | SQL Passwort zurücksetzen |
| ODBC Fehler lokal | Treiber fehlt | ODBC Driver 18 for SQL Server installieren |
| 409 E-Mail existiert | UNIQUE Constraint | andere E-Mail nutzen |

## Verantwortlichkeiten der Komponenten

| Komponente | Aufgabe |
|---|---|
| Foundry Agent | Dialog, Sprache, Datensammlung, Zusammenfassung |
| OpenAPI Tool | Verbindung zwischen Agent und Backend |
| Flask Backend | API, Validierung, SQL-Zugriff, Dashboard API |
| Azure SQL | Persistente Speicherung |
| Azure Speech | Spracheingabe und Sprachausgabe |
| React Dashboard | Anzeige und Verwaltung der Nutzer |

## Autor

Christian Hervé Nan-Nan  
Technische Hochschule Brandenburg  
Advanced Topics in Cloud Computing, Sommersemester 2026
