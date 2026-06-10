"""No-op TTS client used when tts_enabled=False in config."""
from __future__ import annotations
import asyncio
from PySide6.QtCore import QObject, Signal

class NullTTSClient(QObject):
    """Drop-in TTS client that does nothing. Prevents Kokoro model load when TTS is off."""
    error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

    def stop(self) -> None:
        pass

    async def speak(self, text: str) -> None:  # noqa: ARG002
        pass
