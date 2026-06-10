# Draft: ClickyWin Local AI Models Upgrade

## User's Stated Requirements
- Allow use of open-source/local models alongside existing cloud API models
- Easy switching between AI models from a selectable list
- Easy to add more models
- Default local models:
  - Brain: Qwen2.5-VL-7B (vision + reasoning)
  - Ears: faster-whisper + distil-large-v3 (streaming STT)
  - Mouth: Kokoro-82M (TTS)

## Research Findings

### Qwen2.5-VL-7B via Ollama ✅
- **Ollama model**: `qwen2.5vl:7b` — requires Ollama 0.7.0+
- **VRAM**: ~5GB (Q4_K_M quantization), ~16GB (full BF16)
- **API**: OpenAI-compatible at `http://localhost:11434/v1` — chat completions with streaming
- **Vision**: Images as base64 data URIs in `image_url` blocks
- **Client**: `openai` Python SDK with custom `base_url`, or `ollama` Python package
- **Streaming**: Full SSE streaming support via `stream=True`
- **Token budget**: ~1,280 tokens per 1024×1024 image; 128K context window handles multi-image + history

### faster-whisper + distil-large-v3 ✅
- **Install**: `pip install faster-whisper` — Python 3.9+, works on Windows
- **Model**: `WhisperModel("distil-large-v3", device="cuda", compute_type="float16")`
- **VRAM**: ~3GB for distil-large-v3
- **Mode**: Primarily **batch/utterance-based** (not true streaming). Since ClickyWin uses push-to-talk, we already know utterance boundaries — record PCM during hotkey hold, transcribe the full buffer on release.
- **Streaming alternative**: `whisper-livekit` or `Whisper-Streaming` if interim transcripts needed
- **Windows CUDA**: May need Purfview's whisper-standalone-win CUDA libs

### Kokoro-82M ⚠️ Direct Python package (NOT Ollama-compatible)
- **NOT available via Ollama** — must run as direct Python package
- **Install**: `pip install kokoro` + espeak-ng (Windows MSI installer)
- **ONNX option**: `pip install pykokoro` for GPU acceleration (CUDA/DirectML)
- **Model size**: ~300MB download from HuggingFace
- **Output**: 24kHz WAV via numpy audio arrays
- **Speed**: ~200-500ms for synthesis (ONNX), ~2-3 seconds (pure PyTorch)
- **Voices**: 54+ built-in voices, blendable
- **Playback**: Can write to QBuffer/QByteArray for existing QMediaPlayer path

## User Decisions
- **Model serving**: Ollama for brain (Qwen) + mouth (Kokoro). faster-whisper as direct Python package.
- **Remote fallback**: Keep both paths switchable via config (per-role provider selection).
- **Config format**: Per-role blocks — `[brain]`, `[ears]`, `[mouth]` with `provider` + `model` fields.
- **UI**: Config-file + tray menu dropdown (presets/quick-switch).

## Scope Boundaries (tentative)
- INCLUDE: Abstract client interfaces, plugin registry, local model implementations, config changes, dependency management, tray menu preset switching
- EXCLUDE: Panel UI for model controls, Docker/container deployment
