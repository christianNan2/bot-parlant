"""Load register-user OpenAPI with the public backend base URL injected."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

OPENAPI_PATH = Path(__file__).with_name("openapi") / "register-user.yaml"


def backend_public_url() -> str:
    """HTTPS base URL where Foundry can reach this Flask app (no trailing slash)."""
    explicit = (os.getenv("BACKEND_PUBLIC_URL") or os.getenv("PUBLIC_BACKEND_URL") or "").strip()
    if explicit:
        return explicit.rstrip("/")
    return ""


def load_register_user_openapi() -> dict[str, Any]:
    if not OPENAPI_PATH.is_file():
        raise FileNotFoundError(f"Missing OpenAPI file: {OPENAPI_PATH}")

    with OPENAPI_PATH.open(encoding="utf-8") as handle:
        spec: dict[str, Any] = yaml.safe_load(handle)

    base_url = backend_public_url()
    if base_url:
        spec["servers"] = [{"url": base_url, "description": "Voicebot registration API"}]
    elif "servers" not in spec:
        spec["servers"] = [
            {
                "url": "https://YOUR_APP.azurewebsites.net",
                "description": "Set BACKEND_PUBLIC_URL in .env, or edit servers.url before uploading to Foundry",
            }
        ]

    return spec


def dump_register_user_openapi_yaml() -> str:
    return yaml.safe_dump(load_register_user_openapi(), sort_keys=False, allow_unicode=True)
