# ClickyWin Setup

## Prerequisites

- **Python 3.12** via [uv](https://docs.astral.sh/uv/getting-started/installation/)
- **Git**

---

## 1. Install espeak-ng (required for TTS)

Download and run the Windows `.msi` installer from:
https://github.com/espeak-ng/espeak-ng/releases

Install to the default path. Kokoro-82M TTS will not work without it.

---

## 2. Install Ollama (local brain)

Download and install from https://ollama.com, then pull the vision model:

```powershell
ollama pull qwen2.5vl:7b
```

Ollama must be running in the background when ClickyWin starts.

---

## 3. CUDA support for faster-whisper (optional, Windows GPU)

faster-whisper on Windows with CUDA requires cuBLAS and cuDNN DLLs that are **not** included with the standard CUDA toolkit installer.

Download the prebuilt DLL package from Purfview's whisper-standalone-win releases:
https://github.com/Purfview/whisper-standalone-win/releases

Extract the DLLs and either:
- Place them in a folder that is on your system `PATH`, or
- Place them next to the `clicky` executable.

If you skip this step or don't have a CUDA GPU, set `device = "cpu"` in `config.toml` instead.

---

## 4. Clone and install Python dependencies

```powershell
git clone <repo-url>
cd clicky-win\clicky-py
uv sync
```

---

## 5. Configure

```powershell
copy config.example.toml config.toml
```

Open `config.toml` and edit as needed:

- **Local Ollama brain** — no changes required if Ollama is running on the default port.
- **Gemini brain** — set the `GOOGLE_API_KEY` environment variable, or add it to a `.env` file in `clicky-py/`. Then switch the brain provider in the tray icon menu.
- **Cloud/remote worker** — set `worker_url` to your endpoint.
- **CPU mode** — set `device = "cpu"` under the Ears (STT) section if you skipped the CUDA DLLs.

---

## 6. Run

```powershell
uv run python -m clicky
```

A tray icon will appear in the system notification area.

---

## Hotkeys

| Action | Hotkey |
|--------|--------|
| Push-to-talk (hold to record, release to process) | `Ctrl + Alt` |

---

## Tray Icon

Right-click the tray icon → **Models** to switch Brain, Ears (STT), or Mouth (TTS) providers live without restarting.
