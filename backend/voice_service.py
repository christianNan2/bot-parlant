"""Voice Live WebSocket bridge for Flask (Foundry agent mode)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from typing import Any
from urllib.parse import urlparse

from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential

from voice_handler import SessionConfig, VoiceLiveHandler

logger = logging.getLogger(__name__)

_handlers: dict[str, VoiceLiveHandler] = {}
_credential: Any | None = None
_voice_loop: asyncio.AbstractEventLoop | None = None
_voice_loop_thread: threading.Thread | None = None


def _ensure_voice_loop() -> asyncio.AbstractEventLoop:
    global _voice_loop, _voice_loop_thread
    if _voice_loop is None:
        _voice_loop = asyncio.new_event_loop()
        _voice_loop_thread = threading.Thread(target=_voice_loop.run_forever, daemon=True, name="voice-live")
        _voice_loop_thread.start()
    return _voice_loop


def run_voice_async(coro):
    loop = _ensure_voice_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=300)


def _get_credential() -> Any:
    global _credential
    if _credential is None:
        api_key = (os.getenv("AZURE_VOICELIVE_API_KEY") or "").strip()
        if api_key:
            _credential = AzureKeyCredential(api_key)
            logger.info("Voice Live: using API key credential")
        else:
            _credential = DefaultAzureCredential()
            logger.info("Voice Live: using DefaultAzureCredential")
    return _credential


def voice_endpoint() -> str:
    explicit = (os.getenv("AZURE_VOICELIVE_ENDPOINT") or os.getenv("VOICELIVE_ENDPOINT") or "").strip()
    if explicit:
        return explicit.rstrip("/")

    resource = (os.getenv("AZURE_AI_RESOURCE_NAME") or "").strip()
    if resource:
        return f"https://{resource}.services.ai.azure.com"

    project_endpoint = (
        os.getenv("AZURE_AI_ENDPOINT")
        or os.getenv("AZURE_EXISTING_AIPROJECT_ENDPOINT")
        or ""
    ).strip()
    if project_endpoint:
        parsed = urlparse(project_endpoint)
        if parsed.hostname:
            return f"https://{parsed.hostname}"

    return ""


def voice_api_version() -> str:
    return (os.getenv("VOICELIVE_API_VERSION") or "2026-01-01-preview").strip()


def project_name() -> str:
    explicit = (os.getenv("AZURE_VOICELIVE_PROJECT") or os.getenv("PROJECT_NAME") or "").strip()
    if explicit:
        return explicit

    project_endpoint = (
        os.getenv("AZURE_AI_ENDPOINT")
        or os.getenv("AZURE_EXISTING_AIPROJECT_ENDPOINT")
        or ""
    ).strip()
    if project_endpoint:
        path = urlparse(project_endpoint).path.rstrip("/")
        if path:
            return path.split("/")[-1]

    return (os.getenv("AZURE_PROJECT_NAME") or "").strip()


def agent_name() -> str:
    return (os.getenv("AZURE_VOICELIVE_AGENT_NAME") or os.getenv("AZURE_EXISTING_AGENT_NAME") or "").strip()


def agent_version() -> str:
    return (os.getenv("AZURE_VOICELIVE_AGENT_VERSION") or os.getenv("AZURE_EXISTING_AGENT_VERSION") or "").strip()


def is_voice_configured() -> bool:
    return bool(voice_endpoint() and agent_name() and project_name())


def public_voice_config() -> dict[str, Any]:
    return {
        "voiceConfigured": is_voice_configured(),
        "mode": "agent",
        "agentName": agent_name(),
        "project": project_name(),
        "agentVersion": agent_version(),
        "voice": os.getenv("VOICELIVE_VOICE", "en-US-Ava:DragonHDLatestNeural"),
    }


def _build_session_config(overrides: dict) -> SessionConfig:
    return SessionConfig(
        mode=overrides.get("mode", "agent"),
        voice=overrides.get("voice", os.getenv("VOICELIVE_VOICE", "en-US-Ava:DragonHDLatestNeural")),
        voice_type=overrides.get("voice_type", os.getenv("VOICELIVE_VOICE_TYPE", "azure-standard")),
        vad_type=overrides.get("vad_type", os.getenv("VOICELIVE_VAD_TYPE", "azure_semantic")),
        noise_reduction=overrides.get("noise_reduction", True),
        echo_cancellation=overrides.get("echo_cancellation", True),
        agent_name=overrides.get("agent_name") or agent_name(),
        project_name=overrides.get("project") or project_name(),
        agent_version=overrides.get("agent_version") or agent_version() or None,
        conversation_id=overrides.get("conversation_id"),
        foundry_resource_override=overrides.get("foundry_resource_override")
        or os.getenv("AZURE_VOICELIVE_FOUNDRY_RESOURCE_OVERRIDE"),
        auth_identity_client_id=overrides.get("auth_identity_client_id")
        or os.getenv("AZURE_VOICELIVE_AUTH_IDENTITY_CLIENT_ID"),
        proactive_greeting=overrides.get("proactive_greeting", False),
        greeting_type=overrides.get("greeting_type", "llm"),
        greeting_text=overrides.get("greeting_text", ""),
    )


async def _cleanup_client(client_id: str) -> None:
    handler = _handlers.pop(client_id, None)
    if handler:
        await handler.stop()


async def _start_session(client_id: str, config: dict, send_json) -> None:
    endpoint = voice_endpoint()
    if not endpoint:
        raise ValueError(
            "Voice Live is not configured. Set AZURE_VOICELIVE_ENDPOINT or AZURE_AI_RESOURCE_NAME in backend/.env."
        )

    session_config = _build_session_config(config)
    if session_config.mode == "agent" and (not session_config.agent_name or not session_config.project_name):
        raise ValueError("Agent voice mode requires AZURE_EXISTING_AGENT_NAME and AZURE_PROJECT_NAME.")

    if client_id in _handlers:
        await _handlers[client_id].stop()

    handler = VoiceLiveHandler(
        client_id=client_id,
        endpoint=endpoint,
        credential=_get_credential(),
        send_message=send_json,
        config=session_config,
        api_version=voice_api_version(),
    )
    _handlers[client_id] = handler
    await handler.start()
    logger.info("Voice session started for %s", client_id)


async def _handle_message(client_id: str, message: dict, send_json) -> None:
    msg_type = message.get("type")

    if msg_type == "start_session":
        config = {key: value for key, value in message.items() if key != "type"}
        await _start_session(client_id, config, send_json)
    elif msg_type == "stop_session":
        await _cleanup_client(client_id)
        await send_json({"type": "session_stopped"})
    elif msg_type == "audio_chunk":
        handler = _handlers.get(client_id)
        if handler:
            await handler.send_audio(message.get("data", ""))
    elif msg_type == "send_text":
        handler = _handlers.get(client_id)
        if handler:
            await handler.send_text(message.get("text", ""))
    elif msg_type == "interrupt":
        handler = _handlers.get(client_id)
        if handler:
            await handler.interrupt()
    else:
        logger.warning("Unknown voice message from %s: %s", client_id, msg_type)


def handle_voice_websocket(ws, client_id: str) -> None:
    """Sync entry point used by flask-sock."""
    client_id = client_id.replace("\n", "").replace("\r", "").replace("\t", "")

    async def send_json(msg: dict) -> None:
        await asyncio.to_thread(ws.send, json.dumps(msg))

    try:
        while True:
            raw = ws.receive()
            if raw is None:
                break
            message = json.loads(raw)
            run_voice_async(_handle_message(client_id, message, send_json))
    except Exception as exc:
        logger.exception("Voice WebSocket closed for %s: %s", client_id, exc)
    finally:
        run_voice_async(_cleanup_client(client_id))
