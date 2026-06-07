(() => {
  const chatForm = document.getElementById("chat-form");
  const chatInput = document.getElementById("chat-input");
  const chatSend = document.getElementById("chat-send");
  const chatLog = document.getElementById("chat-log");

  const voiceBar = document.getElementById("voice-bar");
  const voiceToggle = document.getElementById("voice-toggle");
  const voiceStatus = document.getElementById("voice-status");

  let chatHistory = [];
  let chatBusy = false;
  let voiceClient = null;

  function setStatus(el, message, tone = "") {
    el.textContent = message;
    el.classList.remove("is-error", "is-success");
    if (tone) el.classList.add(tone);
  }

  function appendMessage(role, text) {
    const bubble = document.createElement("div");
    bubble.className =
      role === "user" ? "msg msg--user" : role === "system" ? "msg msg--system" : "msg msg--bot";
    bubble.textContent = text;
    chatLog.appendChild(bubble);
    chatLog.scrollTop = chatLog.scrollHeight;
    return bubble;
  }

  function resetChat() {
    chatHistory = [];
    chatLog.innerHTML = "";
    appendMessage("system", "Conversation reset. Say hello to start again.");
  }

  async function sendChatMessage(message) {
    if (chatBusy) return;
    chatBusy = true;
    chatSend.disabled = true;
    chatInput.disabled = true;

    appendMessage("user", message);
    chatHistory.push({ role: "user", content: message });

    try {
      const response = await fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, history: chatHistory.slice(0, -1) }),
      });
      const data = await response.json();
      const reply = (data.reply || "No response.").trim();
      appendMessage("bot", reply);
      chatHistory.push({ role: "assistant", content: reply });
    } catch (error) {
      appendMessage("bot", `Could not reach the server: ${error.message}`);
    } finally {
      chatBusy = false;
      chatSend.disabled = false;
      chatInput.disabled = false;
      chatInput.focus();
    }
  }

  chatForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = chatInput.value.trim();
    if (!message) return;

    chatInput.value = "";
    if (message.toLowerCase() === "reset") {
      resetChat();
      return;
    }

    await sendChatMessage(message);
  });

  class VoiceClient {
    constructor(onTranscript, onStatus) {
      this.onTranscript = onTranscript;
      this.onStatus = onStatus;
      this.clientId = crypto.randomUUID();
      this.ws = null;
      this.audioContext = null;
      this.captureNode = null;
      this.playbackNode = null;
      this.mediaStream = null;
      this.active = false;
      this.pendingAssistantBubble = null;
    }

    async start(config) {
      if (this.active) return;

      this.audioContext = new AudioContext({ sampleRate: 24000 });
      await this.audioContext.audioWorklet.addModule("/static/audio-playback-worklet.js");
      await this.audioContext.audioWorklet.addModule("/static/audio-capture-worklet.js");

      this.playbackNode = new AudioWorkletNode(this.audioContext, "audio-playback-processor");
      this.playbackNode.connect(this.audioContext.destination);

      this.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const source = this.audioContext.createMediaStreamSource(this.mediaStream);
      this.captureNode = new AudioWorkletNode(this.audioContext, "audio-capture-processor");
      this.captureNode.port.onmessage = (event) => {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
        const bytes = new Uint8Array(event.data.buffer);
        let binary = "";
        for (let i = 0; i < bytes.length; i += 1) binary += String.fromCharCode(bytes[i]);
        this.ws.send(
          JSON.stringify({
            type: "audio_chunk",
            data: btoa(binary),
          })
        );
      };
      source.connect(this.captureNode);

      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      this.ws = new WebSocket(`${protocol}//${window.location.host}/voice/ws/${this.clientId}`);

      await new Promise((resolve, reject) => {
        this.ws.onopen = () => {
          this.ws.send(
            JSON.stringify({
              type: "start_session",
              mode: config.mode || "agent",
              voice: config.voice,
              agent_name: config.agentName,
              project: config.project,
              agent_version: config.agentVersion,
              proactive_greeting: true,
              greeting_type: "llm",
            })
          );
          resolve();
        };
        this.ws.onerror = () => reject(new Error("Voice connection failed."));
      });

      this.ws.onmessage = (event) => this.handleMessage(JSON.parse(event.data));
      this.ws.onclose = () => this.onStatus("Voice session ended.");
      this.active = true;
    }

    handleMessage(message) {
      if (message.type === "status") {
        const label = {
          listening: "Listening...",
          thinking: "Thinking...",
          speaking: "Speaking...",
        }[message.state];
        if (label) this.onStatus(label);
        return;
      }

      if (message.type === "audio_data" && message.data) {
        const binary = atob(message.data);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
        this.playbackNode.port.postMessage(bytes.buffer);
        return;
      }

      if (message.type === "stop_playback") {
        this.playbackNode.port.postMessage(null);
        return;
      }

      if (message.type === "transcript" && message.text) {
        this.onTranscript(message.role, message.text, message.isFinal);
        return;
      }

      if (message.type === "error") {
        this.onStatus(message.message || "Voice error.", true);
      }
    }

    async stop() {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: "stop_session" }));
        this.ws.close();
      }

      this.mediaStream?.getTracks().forEach((track) => track.stop());
      this.captureNode?.disconnect();
      this.playbackNode?.disconnect();

      if (this.audioContext) {
        await this.audioContext.close();
      }

      this.ws = null;
      this.audioContext = null;
      this.captureNode = null;
      this.playbackNode = null;
      this.mediaStream = null;
      this.active = false;
      this.pendingAssistantBubble = null;
    }
  }

  function handleVoiceTranscript(client, role, text, isFinal) {
    if (role === "user" && isFinal) {
      appendMessage("user", text);
      chatHistory.push({ role: "user", content: text });
      return;
    }

    if (role === "assistant") {
      if (!client.pendingAssistantBubble) {
        client.pendingAssistantBubble = appendMessage("bot", text);
      } else {
        client.pendingAssistantBubble.textContent = text;
      }

      if (isFinal) {
        chatHistory.push({ role: "assistant", content: text });
        client.pendingAssistantBubble = null;
      }
    }
  }

  async function initVoice() {
    if (!voiceBar || !voiceToggle) return;

    try {
      const response = await fetch("/voice/config");
      const config = await response.json();
      if (!config.voiceConfigured) return;

      voiceBar.hidden = false;
      voiceToggle.addEventListener("click", async () => {
        if (!voiceClient) {
          voiceClient = new VoiceClient(
            (role, text, isFinal) => handleVoiceTranscript(voiceClient, role, text, isFinal),
            (message, isError = false) => setStatus(voiceStatus, message, isError ? "is-error" : "")
          );
        }

        if (voiceClient.active) {
          await voiceClient.stop();
          voiceToggle.textContent = "Start voice";
          voiceToggle.classList.remove("is-active");
          voiceToggle.setAttribute("aria-pressed", "false");
          setStatus(voiceStatus, "Voice stopped.");
          return;
        }

        try {
          voiceToggle.disabled = true;
          setStatus(voiceStatus, "Starting voice session...");
          await voiceClient.start(config);
          voiceToggle.textContent = "Stop voice";
          voiceToggle.classList.add("is-active");
          voiceToggle.setAttribute("aria-pressed", "true");
          setStatus(voiceStatus, "Voice ready.");
        } catch (error) {
          setStatus(voiceStatus, error.message, "is-error");
        } finally {
          voiceToggle.disabled = false;
        }
      });
    } catch (error) {
      setStatus(voiceStatus, "Voice config unavailable.", "is-error");
    }
  }

  async function initChat() {
    try {
      const response = await fetch("/health");
      const health = await response.json();
      if (health.foundryConfigured) {
        await sendChatMessage("Hello");
      } else {
        appendMessage(
          "system",
          "Text chat is unavailable until Foundry is configured in backend/.env."
        );
      }
    } catch (error) {
      appendMessage("system", "Could not reach the backend health endpoint.");
    }
  }

  initVoice();
  initChat();
})();
