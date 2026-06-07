"""
Voice Live handler — bridges browser WebSocket ↔ Azure Voice Live SDK (Foundry agent mode).
Adapted from microsoft-foundry/voicelive-samples (voice-live-universal-assistant).
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, Coroutine, List, Optional, Union

from azure.ai.voicelive.aio import connect
from azure.ai.voicelive.models import (
    AssistantMessageItem,
    AudioEchoCancellation,
    AudioInputTranscriptionOptions,
    AudioNoiseReduction,
    AzureSemanticVad,
    AzureSemanticVadEn,
    AzureSemanticVadMultilingual,
    AzureStandardVoice,
    InputAudioFormat,
    InputTextContentPart,
    InterimResponseTrigger,
    LlmInterimResponseConfig,
    MessageItem,
    Modality,
    OpenAIVoice,
    OutputAudioFormat,
    OutputTextContentPart,
    RequestSession,
    ResponseCreateParams,
    ServerEventType,
    ServerVad,
    StaticInterimResponseConfig,
)

logger = logging.getLogger(__name__)

SendMessageFn = Callable[[dict], Coroutine[Any, Any, None]]

VAD_TYPES = {
    "azure_semantic": AzureSemanticVad,
    "azure_semantic_en": AzureSemanticVadEn,
    "azure_semantic_multilingual": AzureSemanticVadMultilingual,
    "server": ServerVad,
}


@dataclass
class SessionConfig:
    mode: str = "agent"
    model: str = "gpt-realtime"
    voice: str = "en-US-Ava:DragonHDLatestNeural"
    voice_type: str = "azure-standard"
    instructions: str = ""
    temperature: float = 0.7
    vad_type: str = "azure_semantic"
    noise_reduction: bool = True
    echo_cancellation: bool = True
    transcribe_model: str = "azure-speech"
    input_language: str = ""
    agent_name: Optional[str] = None
    project_name: Optional[str] = None
    agent_version: Optional[str] = None
    conversation_id: Optional[str] = None
    foundry_resource_override: Optional[str] = None
    auth_identity_client_id: Optional[str] = None
    proactive_greeting: bool = False
    greeting_type: str = "llm"
    greeting_text: str = ""
    interim_response: bool = False
    interim_response_type: str = "llm"
    interim_trigger_tool: bool = True
    interim_trigger_latency: bool = True
    interim_latency_ms: int = 100
    interim_instructions: str = ""
    interim_static_texts: str = ""

    def get_voice(self) -> Union[AzureStandardVoice, OpenAIVoice]:
        if self.voice_type == "openai":
            return OpenAIVoice(name=self.voice)
        return AzureStandardVoice(name=self.voice)

    def get_turn_detection(self) -> Union[AzureSemanticVad, AzureSemanticVadEn, AzureSemanticVadMultilingual, ServerVad]:
        vad_cls = VAD_TYPES.get(self.vad_type, AzureSemanticVad)
        return vad_cls()

    def get_interim_response_config(
        self,
    ) -> Optional[Union[LlmInterimResponseConfig, StaticInterimResponseConfig]]:
        if not self.interim_response:
            return None

        triggers: List[InterimResponseTrigger] = []
        if self.interim_trigger_tool:
            triggers.append(InterimResponseTrigger.TOOL)
        if self.interim_trigger_latency:
            triggers.append(InterimResponseTrigger.LATENCY)
        if not triggers:
            return None

        latency_ms = self.interim_latency_ms if self.interim_trigger_latency else None

        if self.interim_response_type == "static":
            texts = [t.strip() for t in self.interim_static_texts.split("\n") if t.strip()]
            return StaticInterimResponseConfig(
                triggers=triggers,
                latency_threshold_ms=latency_ms,
                texts=texts or ["One moment please..."],
            )

        instructions = (
            self.interim_instructions
            or "Create friendly interim responses indicating wait time due to ongoing processing, if any."
        )
        return LlmInterimResponseConfig(
            triggers=triggers,
            latency_threshold_ms=latency_ms,
            instructions=instructions,
        )

    def get_agent_session_config(self) -> dict[str, str | None]:
        return {
            "agent_name": self.agent_name or "",
            "project_name": self.project_name or "",
            "agent_version": self.agent_version if self.agent_version else None,
            "conversation_id": self.conversation_id if self.conversation_id else None,
            "foundry_resource_override": self.foundry_resource_override if self.foundry_resource_override else None,
            "authentication_identity_client_id": (
                self.auth_identity_client_id
                if self.auth_identity_client_id and self.foundry_resource_override
                else None
            ),
        }

    def build_agent_session(self) -> RequestSession:
        kwargs: dict = {
            "modalities": [Modality.TEXT, Modality.AUDIO],
            "input_audio_format": InputAudioFormat.PCM16,
            "output_audio_format": OutputAudioFormat.PCM16,
            "voice": self.get_voice(),
            "turn_detection": self.get_turn_detection(),
        }
        if self.echo_cancellation:
            kwargs["input_audio_echo_cancellation"] = AudioEchoCancellation()
        if self.noise_reduction:
            kwargs["input_audio_noise_reduction"] = AudioNoiseReduction(type="azure_deep_noise_suppression")

        interim = self.get_interim_response_config()
        if interim is not None:
            kwargs["interim_response"] = interim

        return RequestSession(**kwargs)


class VoiceLiveHandler:
    """Manages one Voice Live session for a browser WebSocket client."""

    def __init__(
        self,
        client_id: str,
        endpoint: str,
        credential: Any,
        send_message: SendMessageFn,
        config: SessionConfig,
        api_version: str = "2026-01-01-preview",
    ):
        self.client_id = client_id
        self.endpoint = endpoint
        self.credential = credential
        self.send = send_message
        self.config = config
        self.api_version = api_version
        self.greeting_sent = False
        self.connection = None
        self.is_running = False
        self._event_task: Optional[asyncio.Task] = None
        self._assistant_transcript = ""
        self._service_session_id = ""

    async def start(self) -> None:
        self.is_running = True
        self._event_task = asyncio.create_task(self._run())

    async def send_audio(self, audio_base64: str) -> None:
        if self.connection:
            try:
                await self.connection.input_audio_buffer.append(audio=audio_base64)
            except Exception as exc:
                logger.error("[%s] Error forwarding audio: %s", self.client_id, exc)

    async def interrupt(self) -> None:
        if self.connection:
            try:
                await self.connection.response.cancel()
            except Exception as exc:
                logger.debug("[%s] No response to cancel: %s", self.client_id, exc)

    async def send_text(self, text: str) -> None:
        if self.connection and text.strip():
            try:
                await self.connection.conversation.item.create(
                    item=MessageItem(
                        role="user",
                        content=[InputTextContentPart(text=text.strip())],
                    )
                )
                await self.connection.response.create()
            except Exception as exc:
                logger.error("[%s] Error sending text: %s", self.client_id, exc)

    async def stop(self) -> None:
        self.is_running = False
        if self._event_task and not self._event_task.done():
            self._event_task.cancel()
            try:
                await self._event_task
            except (asyncio.CancelledError, Exception):
                pass
        self.connection = None
        logger.info("[%s] Handler stopped", self.client_id)

    async def _run(self) -> None:
        try:
            logger.info(
                "[%s] Connecting in %s mode (agent=%s, project=%s)",
                self.client_id,
                self.config.mode,
                self.config.agent_name,
                self.config.project_name,
            )

            if self.config.mode == "agent":
                agent_cfg = self.config.get_agent_session_config()
                connect_kwargs = {
                    "endpoint": self.endpoint,
                    "credential": self.credential,
                    "api_version": self.api_version,
                    "agent_name": agent_cfg["agent_name"],
                    "project_name": agent_cfg["project_name"],
                    "agent_version": agent_cfg.get("agent_version"),
                    "conversation_id": agent_cfg.get("conversation_id"),
                    "foundry_resource_override": agent_cfg.get("foundry_resource_override"),
                    "authentication_identity_client_id": agent_cfg.get(
                        "authentication_identity_client_id"
                    ),
                }
            else:
                connect_kwargs = {
                    "endpoint": self.endpoint,
                    "credential": self.credential,
                    "model": self.config.model,
                    "api_version": self.api_version,
                }

            async with connect(**connect_kwargs) as connection:
                self.connection = connection
                await self._configure_session(connection)
                await self._process_events(connection)
        except asyncio.CancelledError:
            logger.info("[%s] Event loop cancelled", self.client_id)
        except Exception as exc:
            logger.error("[%s] VoiceLive error: %s", self.client_id, exc)
            await self.send({"type": "error", "message": str(exc)})
        finally:
            self.is_running = False
            self.connection = None

    async def _configure_session(self, connection) -> None:
        session_config = self.config.build_agent_session()
        await connection.session.update(session=session_config)
        logger.info("[%s] Session config sent (%s mode)", self.client_id, self.config.mode)

    async def _send_pre_generated_greeting(self, connection) -> None:
        text = self.config.greeting_text or "Welcome! How can I help you today?"
        try:
            await connection.response.create(
                response=ResponseCreateParams(
                    pre_generated_assistant_message=AssistantMessageItem(
                        content=[OutputTextContentPart(text=text)]
                    )
                )
            )
        except Exception as exc:
            logger.warning("[%s] Pre-generated greeting failed: %s", self.client_id, exc)

    async def _send_llm_generated_greeting(self, connection) -> None:
        instruction = (
            self.config.greeting_text
            or "Greet the user warmly and briefly in English."
        )
        try:
            await connection.conversation.item.create(
                item=MessageItem(
                    role="system",
                    content=[InputTextContentPart(text=instruction)],
                )
            )
            await connection.response.create()
        except Exception as exc:
            logger.warning("[%s] LLM greeting failed: %s", self.client_id, exc)

    async def _process_events(self, connection) -> None:
        async for event in connection:
            if not self.is_running:
                break
            try:
                await self._handle_event(event, connection)
            except Exception as exc:
                logger.error("[%s] Event handling error: %s", self.client_id, exc)

    async def _handle_event(self, event, connection) -> None:
        event_type = event.type

        if event_type == ServerEventType.SESSION_CREATED:
            session_obj = getattr(event, "session", None)
            self._service_session_id = getattr(session_obj, "id", "") if session_obj else ""

        elif event_type == ServerEventType.SESSION_UPDATED:
            session_obj = getattr(event, "session", None)
            if not self._service_session_id:
                self._service_session_id = getattr(session_obj, "id", "") if session_obj else ""

            await self.send(
                {
                    "type": "session_started",
                    "session_id": self._service_session_id or self.client_id,
                    "config": {
                        "mode": self.config.mode,
                        "agent_name": self.config.agent_name,
                        "voice": self.config.voice,
                    },
                }
            )
            await self.send({"type": "status", "state": "listening"})

            if self.config.proactive_greeting and not self.greeting_sent:
                self.greeting_sent = True
                if self.config.greeting_type == "pregenerated":
                    await self._send_pre_generated_greeting(connection)
                else:
                    await self._send_llm_generated_greeting(connection)

        elif event_type == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STARTED:
            await self.send({"type": "status", "state": "listening"})
            await self.send({"type": "stop_playback"})
            try:
                await connection.response.cancel()
            except Exception:
                pass

        elif event_type == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STOPPED:
            await self.send({"type": "status", "state": "thinking"})

        elif event_type == ServerEventType.RESPONSE_CREATED:
            await self.send({"type": "status", "state": "speaking"})

        elif event_type == ServerEventType.RESPONSE_AUDIO_DELTA:
            if hasattr(event, "delta") and event.delta:
                audio_b64 = base64.b64encode(event.delta).decode("utf-8")
                await self.send(
                    {
                        "type": "audio_data",
                        "data": audio_b64,
                        "format": "pcm16",
                        "sampleRate": 24000,
                        "channels": 1,
                    }
                )

        elif event_type == ServerEventType.RESPONSE_DONE:
            if self._assistant_transcript:
                await self.send(
                    {
                        "type": "transcript",
                        "role": "assistant",
                        "text": self._assistant_transcript,
                        "isFinal": True,
                    }
                )
                self._assistant_transcript = ""
            await self.send({"type": "status", "state": "listening"})

        elif event_type == ServerEventType.CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_COMPLETED:
            transcript = getattr(event, "transcript", "")
            if transcript:
                await self.send(
                    {
                        "type": "transcript",
                        "role": "user",
                        "text": transcript,
                        "isFinal": True,
                    }
                )

        elif event_type == ServerEventType.RESPONSE_AUDIO_TRANSCRIPT_DELTA:
            delta_text = getattr(event, "delta", "")
            if delta_text:
                self._assistant_transcript += delta_text
                await self.send(
                    {
                        "type": "transcript",
                        "role": "assistant",
                        "text": self._assistant_transcript,
                        "isFinal": False,
                    }
                )

        elif event_type == ServerEventType.ERROR:
            error_msg = getattr(event, "error", None)
            message = getattr(error_msg, "message", str(error_msg)) if error_msg else str(event)
            code = getattr(error_msg, "code", "") if error_msg else ""
            if code == "response_cancel_not_active" or "no active response" in message.lower():
                return
            logger.error("[%s] VoiceLive error event: %s", self.client_id, message)
            await self.send({"type": "error", "message": message})
