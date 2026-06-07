#!/usr/bin/env python3
"""
Attach the register_user OpenAPI tool to a Foundry agent (bypasses the portal tool catalog).

Usage:
  cd backend && source .venv/bin/activate
  az login
  export BACKEND_PUBLIC_URL=https://your-app.azurewebsites.net   # required — Foundry must reach this URL
  python ../scripts/attach-register-openapi-tool.py

Optional env (from backend/.env):
  AZURE_AI_ENDPOINT, AZURE_EXISTING_AGENT_NAME, AZURE_EXISTING_AGENT_VERSION
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    OpenApiAnonymousAuthDetails,
    OpenApiFunctionDefinition,
    OpenApiTool,
    PromptAgentDefinition,
)
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND))

load_dotenv(BACKEND / ".env")

from openapi_loader import backend_public_url, load_register_user_openapi  # noqa: E402

TOOL_OPENAPI_NAME = "register_user_api"
INSTRUCTIONS_PATH = BACKEND / "prompts" / "agent-registration-instructions.md"


def _merge_instructions(existing: str | None) -> str:
    addon = INSTRUCTIONS_PATH.read_text(encoding="utf-8") if INSTRUCTIONS_PATH.is_file() else ""
    marker = "## Registration tool (register_user)"
    if existing and marker in existing:
        return existing
    block = addon.strip()
    if not block:
        return existing or ""
    if existing and existing.strip():
        return f"{existing.strip()}\n\n{marker}\n\n{block}"
    return block


def _has_register_tool(tools: list | None) -> bool:
    if not tools:
        return False
    for tool in tools:
        openapi = getattr(tool, "openapi", None)
        if openapi is None and isinstance(tool, dict):
            openapi = tool.get("openapi")
        if openapi is None:
            continue
        name = getattr(openapi, "name", None) or (openapi.get("name") if isinstance(openapi, dict) else None)
        if name == TOOL_OPENAPI_NAME:
            return True
    return False


def main() -> int:
    endpoint = (os.getenv("AZURE_AI_ENDPOINT") or os.getenv("AZURE_EXISTING_AIPROJECT_ENDPOINT") or "").strip()
    agent_name = (os.getenv("AZURE_EXISTING_AGENT_NAME") or "").strip()
    base_version = (os.getenv("AZURE_EXISTING_AGENT_VERSION") or "").strip()

    if not endpoint or not agent_name:
        print("Set AZURE_AI_ENDPOINT and AZURE_EXISTING_AGENT_NAME in backend/.env", file=sys.stderr)
        return 1

    public_url = backend_public_url()
    if not public_url or "YOUR_APP" in public_url:
        print(
            "Set BACKEND_PUBLIC_URL in backend/.env to the HTTPS URL Foundry can call "
            "(App Service hostname or an Azure Dev Tunnel).",
            file=sys.stderr,
        )
        return 1

    spec = load_register_user_openapi()
    register_tool = OpenApiTool(
        openapi=OpenApiFunctionDefinition(
            name=TOOL_OPENAPI_NAME,
            description="Persist a confirmed user in Azure SQL (call only after explicit user confirmation).",
            spec=spec,
            auth=OpenApiAnonymousAuthDetails(),
        )
    )

    client = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())

    if base_version:
        print(f"Loading agent {agent_name} version {base_version}...")
        current = client.agents.get_version(agent_name=agent_name, agent_version=base_version)
    else:
        print(f"Loading latest version of agent {agent_name}...")
        versions = list(client.agents.list_versions(agent_name=agent_name))
        if not versions:
            print(f"No versions found for agent {agent_name}", file=sys.stderr)
            return 1
        latest = max(versions, key=lambda v: int(v.version) if str(v.version).isdigit() else 0)
        current = client.agents.get_version(agent_name=agent_name, agent_version=latest.version)
        base_version = str(current.version)

    definition = current.definition
    if not isinstance(definition, PromptAgentDefinition):
        print(
            f"Agent definition kind is {getattr(definition, 'kind', type(definition))}; "
            "this script only updates prompt agents.",
            file=sys.stderr,
        )
        return 1

    tools = list(definition.tools or [])
    if _has_register_tool(tools):
        print("register_user OpenAPI tool is already on this version; creating a new version anyway.")

    tools.append(register_tool)
    instructions = _merge_instructions(definition.instructions)

    print(f"Creating new version of {agent_name} with OpenAPI tool (server={public_url})...")
    created = client.agents.create_version(
        agent_name=agent_name,
        definition=PromptAgentDefinition(
            model=definition.model,
            instructions=instructions,
            tools=tools,
            temperature=definition.temperature,
            top_p=definition.top_p,
            tool_choice=definition.tool_choice,
            text=definition.text,
            reasoning=definition.reasoning,
            rai_config=definition.rai_config,
        ),
        description="Adds register_user OpenAPI tool for dbo.Users",
    )

    new_version = created.version
    print()
    print("Success.")
    print(f"  Agent:   {agent_name}")
    print(f"  Version: {new_version}")
    print(f"  API:     {public_url}/api/users/register")
    print()
    print("Update backend/.env:")
    print(f'  AZURE_EXISTING_AGENT_VERSION="{new_version}"')
    print()
    print("If you use Voice Live, restart the Flask app so it picks up the new version.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
