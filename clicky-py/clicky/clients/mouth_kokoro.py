"""Kokoro-82M TTS client with QMediaPlayer playback.

Synthesises speech locally via the ``kokoro`` Python package and plays the
resulting audio through ``QMediaPlayer`` — the same playback path used by the
ElevenLabs ``TTSClient``.  Synthesis runs in a thread executor so the Qt /
asyncio event loop stays responsive during the GPU/CPU-bound synthesis step.

Requires:
    pip install kokoro
    espeak-ng  (Windows MSI from https://github.com/espeak-ng/espeak-ng/releases)
"""

from __future__ import annotations

import asyncio
import io
import logging
import wave

import numpy as np
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QObject, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

logger = logging.getLogger(__name__)

# Kokoro outputs 24 kHz mono float32.
_KOKORO_SAMPLE_RATE = 24000


class KokoroTTSClient(QObject):
    """Local TTS client backed by Kokoro-82M.

    Drop-in replacement for ``TTSClient`` — same Qt signals, same ``speak()``
    and ``stop()`` interface.

    Signals:
        playback_started:  Emitted when audio playback begins.
        playback_finished: Emitted when audio playback completes normally.
        error(str):        Emitted on synthesis or playback errors.
    """

    playback_started = Signal()
    playback_finished = Signal()
    error = Signal(str)

    def __init__(
        self,
        voice: str = "af_heart",
        *,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._voice = voice
        self._pipeline = None  # loaded lazily on first speak()

        self._player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_output)
        self._player.mediaStatusChanged.connect(self._on_media_status)

        # Keep Qt objects alive for the duration of playback.
        self._current_bytearray: QByteArray | None = None
        self._current_buffer: QBuffer | None = None
        self._playback_future: asyncio.Future[bool] | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def speak(self, text: str) -> None:
        """Synthesise ``text`` and play it, awaiting until playback finishes."""
        try:
            loop = asyncio.get_running_loop()
            wav_bytes = await loop.run_in_executor(None, self._synthesize, text)
        except Exception as exc:
            msg = f"Kokoro synthesis failed: {exc}"
            logger.error(msg)
            self.error.emit(msg)
            return

        try:
            self._current_bytearray = QByteArray(wav_bytes)
            self._current_buffer = QBuffer(self._current_bytearray, parent=self)
            self._current_buffer.open(QIODevice.OpenModeFlag.ReadOnly)

            self._player.setSourceDevice(self._current_buffer)
            self._player.play()
            self.playback_started.emit()

            loop = asyncio.get_running_loop()
            self._playback_future = loop.create_future()
            await self._playback_future
        except Exception as exc:
            msg = f"Kokoro playback failed: {exc}"
            logger.error(msg)
            self.error.emit(msg)

    def stop(self) -> None:
        """Stop playback and resolve the pending future."""
        self._player.stop()
        if self._playback_future and not self._playback_future.done():
            self._playback_future.set_result(False)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _on_media_status(self, status: QMediaPlayer.MediaStatus) -> None:
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self._playback_future and not self._playback_future.done():
                self._playback_future.set_result(True)
            self.playback_finished.emit()
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            err = self._player.errorString() or "invalid media"
            if self._playback_future and not self._playback_future.done():
                self._playback_future.set_result(False)
            self.error.emit(err)

    def _synthesize(self, text: str) -> bytes:
        """Blocking synthesis — runs in a thread executor.

        Returns WAV bytes (16-bit PCM, 24 kHz, mono) ready for QMediaPlayer.
        """
        if self._pipeline is None:
            self._pipeline = self._load_pipeline()

        # kokoro >= 0.9: KPipeline.__call__ returns an iterator of (gs, ps, audio)
        # where audio is a numpy float32 array at _KOKORO_SAMPLE_RATE Hz.
        audio_chunks: list[np.ndarray] = []
        for _, _, audio in self._pipeline(text, voice=self._voice):
            if audio is not None and len(audio) > 0:
                audio_chunks.append(audio)

        if not audio_chunks:
            # Return a tiny silent WAV so the playback path doesn't hang.
            return _silent_wav()

        samples = np.concatenate(audio_chunks)
        return _numpy_to_wav(samples, _KOKORO_SAMPLE_RATE)

    def _load_pipeline(self):
        from kokoro import KPipeline  # type: ignore[import]

        logger.info("Loading Kokoro TTS pipeline (voice=%s) ...", self._voice)
        return KPipeline(lang_code="a")  # 'a' = American English


def _numpy_to_wav(samples: np.ndarray, sample_rate: int) -> bytes:
    """Convert float32 numpy array → 16-bit mono WAV bytes."""
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


def _silent_wav() -> bytes:
    """Return a minimal valid WAV with 100ms of silence."""
    silence = np.zeros(int(_KOKORO_SAMPLE_RATE * 0.1), dtype=np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(_KOKORO_SAMPLE_RATE)
        wf.writeframes(silence.tobytes())
    return buf.getvalue()
