// AudioWorklet processor for playing back PCM16 audio data
class AudioPlaybackProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.bufferQueue = [];
    this.currentBuffer = null;
    this.currentOffset = 0;

    this.port.onmessage = (event) => {
      if (event.data === null) {
        this.bufferQueue = [];
        this.currentBuffer = null;
        this.currentOffset = 0;
      } else {
        this.bufferQueue.push(event.data);
      }
    };
  }

  process(_inputs, outputs) {
    const output = outputs[0];
    if (output.length === 0) return true;

    const channel = output[0];

    for (let i = 0; i < channel.length; i++) {
      if (!this.currentBuffer || this.currentOffset >= this.currentBuffer.length) {
        if (this.bufferQueue.length > 0) {
          this.currentBuffer = new Int16Array(this.bufferQueue.shift());
          this.currentOffset = 0;
        } else {
          channel[i] = 0;
          continue;
        }
      }
      channel[i] = this.currentBuffer[this.currentOffset] / 32768.0;
      this.currentOffset++;
    }
    return true;
  }
}

registerProcessor("audio-playback-processor", AudioPlaybackProcessor);
