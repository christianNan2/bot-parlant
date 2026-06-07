import os
from pathlib import Path
from threading import Lock

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request
from flask_sock import Sock

from openapi_loader import backend_public_url, dump_register_user_openapi_yaml, load_register_user_openapi
from user_repository import UserRegistrationError, is_sql_configured, register_user, user_from_payload
from voice_service import handle_voice_websocket, is_voice_configured, public_voice_config

app = Flask(__name__)
load_dotenv(Path(__file__).with_name(".env"))
sock = Sock(app)


class FoundryChatService:
    """Tiny wrapper around Foundry Agent Service for request/response chat."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._credential = DefaultAzureCredential()
        self._client: AIProjectClient | None = None

        endpoint = os.getenv("AZURE_AI_ENDPOINT") or os.getenv("AZURE_EXISTING_AIPROJECT_ENDPOINT")
        existing_agent_id = os.getenv("AZURE_EXISTING_AGENT_ID")
        agent_name = os.getenv("AZURE_EXISTING_AGENT_NAME")
        agent_version = os.getenv("AZURE_EXISTING_AGENT_VERSION")

        self._endpoint = (endpoint or "").strip()
        self._agent_id = (existing_agent_id or "").strip() or self._build_agent_id(agent_name, agent_version)
        self._agent_name = self._agent_id.split(":", 1)[0].strip()

    @staticmethod
    def _build_agent_id(agent_name: str | None, agent_version: str | None) -> str:
        name = (agent_name or "").strip()
        version = (agent_version or "").strip()
        if name and version:
            return f"{name}:{version}"
        return name

    def is_configured(self) -> bool:
        return bool(self._endpoint and self._agent_name)

    def _get_client(self) -> AIProjectClient:
        with self._lock:
            if self._client is None:
                self._client = AIProjectClient(
                    endpoint=self._endpoint,
                    credential=self._credential,
                )
            return self._client

    @staticmethod
    def _build_input(message: str, history: list[dict[str, str]] | None) -> str | list[dict[str, str]]:
        """Build Responses API input from prior turns plus the new user message."""
        max_turns = 20
        input_items: list[dict[str, str]] = []

        for turn in history or []:
            role = (turn.get("role") or "").strip()
            content = (turn.get("content") or "").strip()
            if role in ("user", "assistant") and content:
                input_items.append({"role": role, "content": content, "type": "message"})

        if len(input_items) > max_turns * 2:
            input_items = input_items[-(max_turns * 2) :]

        input_items.append({"role": "user", "content": message, "type": "message"})
        return input_items if len(input_items) > 1 else message

    def ask(self, message: str, history: list[dict[str, str]] | None = None) -> str:
        if not self.is_configured():
            raise RuntimeError(
                "Foundry is not configured. Set AZURE_AI_ENDPOINT (or AZURE_EXISTING_AIPROJECT_ENDPOINT), "
                "AZURE_EXISTING_AGENT_NAME (or AZURE_EXISTING_AGENT_ID) in backend/.env."
            )

        client = self._get_client()
        openai_client = client.get_openai_client()
        response = openai_client.responses.create(
            input=self._build_input(message, history),
            extra_body={
                "agent_reference": {
                    "name": self._agent_name,
                    "type": "agent_reference",
                }
            },
        )

        if getattr(response, "output_text", None):
            return response.output_text.strip()

        output_items = getattr(response, "output", []) or []
        text_chunks: list[str] = []
        for item in output_items:
            for part in getattr(item, "content", []) or []:
                text_value = getattr(part, "text", None)
                if text_value:
                    text_chunks.append(text_value)

        if text_chunks:
            return "\n".join(text_chunks).strip()

        raise RuntimeError("Foundry returned an empty response.")


foundry_service = FoundryChatService()


def _registration_api_key_ok() -> bool:
    expected = (os.getenv("REGISTRATION_API_KEY") or "").strip()
    if not expected:
        return True
    provided = (request.headers.get("X-API-Key") or request.headers.get("Authorization") or "").strip()
    if provided.lower().startswith("bearer "):
        provided = provided[7:].strip()
    return provided == expected


@app.get("/openapi/register-user.json")
def openapi_register_user_json():
    """OpenAPI 3 spec for Foundry (servers.url uses BACKEND_PUBLIC_URL when set)."""
    try:
        spec = load_register_user_openapi()
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify(spec)


@app.get("/openapi/register-user.yaml")
def openapi_register_user_yaml():
    try:
        spec = load_register_user_openapi()
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 500
    return Response(dump_register_user_openapi_yaml(), mimetype="application/yaml")


@app.post("/api/users/register")
def api_register_user():
    """Called by the Foundry agent tool when the user confirms their details."""
    if not _registration_api_key_ok():
        return jsonify({"error": "Unauthorized"}), 401

    if not is_sql_configured():
        return jsonify({"error": "Database is not configured on the server."}), 503

    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "JSON body required."}), 400

    try:
        user = user_from_payload(payload)
        result = register_user(user)
    except UserRegistrationError as exc:
        return jsonify({"error": exc.message}), exc.status_code

    return jsonify(result), 201


@app.get("/")
def home():
    return render_template("chat.html")


@app.post("/chat")
def chat():
    payload = request.get_json(silent=True) or {}
    user_message = (payload.get("message") or "").strip()
    if not user_message:
        return jsonify({"reply": "Please type or say a message first."}), 400

    raw_history = payload.get("history")
    history: list[dict[str, str]] | None = None
    if isinstance(raw_history, list):
        history = [turn for turn in raw_history if isinstance(turn, dict)]

    try:
        bot_reply = foundry_service.ask(user_message, history=history)
    except Exception as exc:
        app.logger.exception("Foundry /chat request failed")
        return jsonify({"reply": f"Foundry error: {exc}"}), 500

    return jsonify({"reply": bot_reply})


@app.get("/voice/config")
def voice_config():
    return jsonify(public_voice_config())


@sock.route("/voice/ws/<client_id>")
def voice_websocket(ws, client_id: str):
    handle_voice_websocket(ws, client_id)


@app.get("/health")
def health_check():
    return jsonify(
        {
            "status": "ok",
            "message": "Flask server is running",
            "foundryConfigured": foundry_service.is_configured(),
            "voiceConfigured": is_voice_configured(),
            "sqlConfigured": is_sql_configured(),
            "backendPublicUrl": backend_public_url() or None,
            "registrationOpenApi": "/openapi/register-user.json",
        }
    )


if __name__ == "__main__":
    # Python 3.14 + Flask's stat reloader can exit immediately after "Restarting with stat".
    use_reloader = (os.getenv("FLASK_USE_RELOADER") or "").strip().lower() in ("1", "true", "yes")
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5444")), debug=True, use_reloader=use_reloader)
