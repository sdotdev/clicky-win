"""Local STT client using faster-whisper in batch (push-to-talk) mode.

Since ClickyWin is push-to-talk, the hotkey release is a clean utterance
boundary — we can buffer the full recording and transcribe in one pass rather
than using true streaming.  This simplifies the implementation dramatically
compared to the AssemblyAI WebSocket client while achieving the same interface.

The WhisperModel is loaded once at construction time to avoid per-turn reload
latency (~3s for distil-large-v3 on CUDA).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

import numpy as np
from PySide6.QtCore import QByteArray, QObject, Signal

logger = logging.getLogger(__name__)


class FasterWhisperClient(QObject):
    """Local push-to-talk transcription using faster-whisper.

    Mirrors the ``TranscriptionClient`` Qt signal interface exactly so
    ``CompanionManager`` requires no changes.

    Signals:
        interim_transcript(str): Not emitted in batch mode (no-op placeholder).
        final_transcript(str):   Emitted once with the full transcription result.
        error(str):              Emitted on model load or transcription failure.

    Lifecycle:
        ``start_stream(pcm_chunk_iterator)`` buffers PCM while the hotkey is held.
        ``stop_stream()`` triggers transcription and emits ``final_transcript``.
    """

    interim_transcript = Signal(str)
    final_transcript = Signal(str)
    error = Signal(str)

    def __init__(
        self,
        model_name: str = "distil-large-v3",
        device: str = "cuda",
        compute_type: str = "float16",
        *,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._model_name = model_name
        self._device = device
        self._compute_type = compute_type
        self._model = None  # loaded lazily on first use
        self._pcm_buffer = bytearray()
        self._buffer_task: asyncio.Task | None = None
        self._stopping = False
        self._session_started = False

    # ------------------------------------------------------------------
    # Public API (mirrors TranscriptionClient)
    # ------------------------------------------------------------------

    async def start_stream(self, pcm_chunk_iterator: AsyncIterator[QByteArray]) -> None:
        """Begin buffering PCM chunks from the microphone iterator."""
        self._pcm_buffer = bytearray()
        self._stopping = False
        self._session_started = True
        self._buffer_task = asyncio.create_task(self._buffer_loop(pcm_chunk_iterator))

    async def stop_stream(self) -> None:
        """Stop buffering, transcribe the accumulated PCM, and emit final_transcript."""
        if not self._session_started:
            return

        self._stopping = True

        if self._buffer_task is not None and not self._buffer_task.done():
            self._buffer_task.cancel()
            try:
                await self._buffer_task
            except (asyncio.CancelledError, Exception):
                pass
        self._buffer_task = None
        self._session_started = False

        if not self._pcm_buffer:
            self.final_transcript.emit("")
            return

        try:
            loop = asyncio.get_running_loop()
            text = await loop.run_in_executor(None, self._transcribe)
            self.final_transcript.emit(text)
        except Exception as exc:
            msg = f"faster-whisper transcription failed: {exc}"
            logger.error(msg)
            self.error.emit(msg)
            self.final_transcript.emit("")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _buffer_loop(self, pcm_chunk_iterator: AsyncIterator[QByteArray]) -> None:
        try:
            async for chunk in pcm_chunk_iterator:
                if self._stopping:
                    break
                self._pcm_buffer.extend(bytes(chunk))
        except asyncio.CancelledError:
            pass

    def _transcribe(self) -> str:
        """Blocking transcription — runs in a thread executor."""
        if self._model is None:
            self._model = self._load_model()

        # PCM is 16-bit signed LE at 16kHz — convert to float32 in [-1, 1]
        audio = np.frombuffer(self._pcm_buffer, dtype=np.int16).astype(np.float32) / 32768.0

        segments, _ = self._model.transcribe(
            audio,
            language="en",
            beam_size=5,
            vad_filter=True,
        )
        return " ".join(seg.text for seg in segments).strip()

    def _load_model(self):
        from faster_whisper import WhisperModel  # type: ignore[import]

        logger.info(
            "Loading faster-whisper model %s on %s (%s) ...",
            self._model_name,
            self._device,
            self._compute_type,
        )
        try:
            return WhisperModel(
                self._model_name,
                device=self._device,
                compute_type=self._compute_type,
            )
        except Exception:
            logger.warning(
                "Failed to load on %s, falling back to CPU int8", self._device, exc_info=True
            )
            return WhisperModel(self._model_name, device="cpu", compute_type="int8")
