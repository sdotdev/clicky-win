"""CompanionManager — orchestration state machine for ClickyWin.

Owns the hotkey → mic → transcription → screen-capture → LLM pipeline and
emits high-level Qt signals that the UI layer (panel, tray) can bind to
without knowing the plumbing details.

Replaces the ad-hoc closure wiring in ``app.py``.  In Task 4.9 the
application entry point will be refactored to instantiate a
``CompanionManager`` and delegate to it.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from collections import deque
from collections.abc import AsyncGenerator, Callable
from typing import Any, Protocol

from PySide6.QtCore import QByteArray, QObject, Signal

from clicky.active_window import get_foreground_window_title
from clicky.clients.llm_client import LLMClient
from clicky.clients.transcription_client import TranscriptionClient
from clicky.clients.tts_client import TTSClient
from clicky.config import Config
from clicky.conversation_history import ConversationHistory
from clicky.hotkey import HotkeyMonitor
from clicky.knowledge_base import load_kb_from_disk, match_app, select_content
from clicky.mic_capture import MicCapture
from clicky.point_mapper import map_point_to_screen
from clicky.point_parser import PointTag, parse_point_tag
from clicky.prompts import build_system_prompt
from clicky.step_parser import Step, parse_steps
from clicky.screen_capture import ScreenshotImage
from clicky.state import VoiceState

logger = logging.getLogger(__name__)


class CaptureVisibilityController(Protocol):
    """Protocol for hiding/restoring UI during screen capture."""

    def hide_for_capture(self) -> None:
        """Temporarily hide during screen capture."""
        ...

    def restore_after_capture(self) -> None:
        """Restore after screen capture."""
        ...

    def fly_to(self, x: int, y: int) -> None:
        """Animate companion to target screen position."""
        ...


class CompanionManager(QObject):
    """Orchestration state machine for the voice companion pipeline.

    Coordinates hotkey detection, microphone capture, transcription,
    screen capture, and LLM streaming into a single coherent lifecycle
    with cancellation support.
    """

    # ---- Qt signals ----
    state_changed = Signal(VoiceState)
    audio_level = Signal(float)
    interim_transcript = Signal(str)
    final_transcript = Signal(str)
    response_delta = Signal(str)
    response_complete = Signal(str)
    step_text = Signal(str)           # text for the current step (drives output widget in step mode)
    step_progress = Signal(int, int)  # (current_1indexed, total) for progress bar
    show_region_requested = Signal(int, int, int, int, str)  # x1,y1,x2,y2,label
    show_arrow_requested = Signal(int, int, int, int)        # x1,y1,x2,y2
    success_turn_completed = Signal()
    steps_complete = Signal()  # all guided steps finished
    error = Signal(str)

    def __init__(
        self,
        config: Config,
        mic: MicCapture,
        hotkey: HotkeyMonitor,
        transcription: TranscriptionClient,
        llm: LLMClient,
        tts: TTSClient,
        screen_capture_fn: Callable[[], list[ScreenshotImage]],
        panel_visibility_controller: CaptureVisibilityController,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)

        self._config = config
        self._mic = mic
        self._hotkey = hotkey
        self._transcription = transcription
        self._llm = llm
        self._tts = tts
        self._screen_capture_fn = screen_capture_fn
        self._panel_visibility_controller = panel_visibility_controller

        # Internal state
        self._state: VoiceState = VoiceState.IDLE
        self._current_task: asyncio.Task[None] | None = None
        self._history = ConversationHistory()
        self._knowledge_dir = config.knowledge_dir  # Path | None
        self._current_model: str = config.default_model
        self._cancel_flag: bool = False
        self._current_screenshots: list[ScreenshotImage] = []
        self._speak_task: asyncio.Task[None] | None = None
        self._context_addendum: str = ""
        self._steps: list[Step] = []
        self._step_index: int = 0

        # PCM deque bridge — same pattern as app.py.  Replaced on every
        # hotkey-press cycle so a stale generator cannot leak chunks.
        self._pcm: dict[str, Any] = {
            "deque": deque(),
            "event": asyncio.Event(),
            "done": False,
        }

        # ---- Signal wiring ----
        hotkey.pressed.connect(self._on_hotkey_pressed)
        hotkey.released.connect(self._on_hotkey_released)
        hotkey.cancelled.connect(self._on_hotkey_cancelled)

        mic.audio_level.connect(self.audio_level)
        mic.pcm_chunk.connect(self._on_pcm_chunk)

        transcription.interim_transcript.connect(self.interim_transcript)
        transcription.final_transcript.connect(self._on_final_transcript)
        transcription.error.connect(self._on_error)

        llm.delta.connect(self._on_llm_delta)
        llm.error.connect(self._on_error)

        tts.error.connect(self._on_error)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_model(self, model_id: str) -> None:
        """Update the model used for LLM requests."""
        self._current_model = model_id

    def set_context_addendum(self, text: str) -> None:
        """Prepend extra context to the next turn's system prompt (one-shot)."""
        self._context_addendum = text

    def update_config(self, cfg: "Config") -> None:
        """Hot-swap config (e.g. when settings are saved without a full restart)."""
        self._config = cfg
        if not cfg.tts_enabled:
            from clicky.clients.tts_null import NullTTSClient
            self._tts.stop()
            self._tts = NullTTSClient(parent=self)

    def advance_step(self) -> None:
        """Advance to the next step. Called when the user's cursor reaches a POINT target."""
        if self._cancel_flag:
            return
        # Cancel in-flight TTS for the current step before starting the next one.
        if self._speak_task is not None and not self._speak_task.done():
            self._speak_task.cancel()
        self._step_index += 1
        if self._step_index >= len(self._steps):
            self.steps_complete.emit()
            self._set_state(VoiceState.IDLE)
            return
        self._show_step(self._step_index)

    def _show_step(self, index: int) -> None:
        step = self._steps[index]
        self.step_text.emit(step.text)
        self.step_progress.emit(index + 1, len(self._steps))

        if step.region is not None:
            r = step.region
            self.show_region_requested.emit(r.x1, r.y1, r.x2, r.y2, r.label)
            logger.info("step %d REGION: (%d,%d)→(%d,%d) label=%s", index, r.x1, r.y1, r.x2, r.y2, r.label)
        elif step.arrow is not None:
            a = step.arrow
            p1 = PointTag(x=a.x1, y=a.y1, label="", screen=a.screen)
            p2 = PointTag(x=a.x2, y=a.y2, label="", screen=a.screen)
            c1 = map_point_to_screen(p1, self._current_screenshots)
            c2 = map_point_to_screen(p2, self._current_screenshots)
            if c1 is not None and c2 is not None:
                self.show_arrow_requested.emit(c1[0], c1[1], c2[0], c2[1])
                logger.info("step %d ARROW: (%d,%d)→(%d,%d) label=%s", index, c1[0], c1[1], c2[0], c2[1], a.label)
            self.advance_step()
        elif step.point is not None:
            coords = map_point_to_screen(step.point, self._current_screenshots)
            if coords is not None:
                self._panel_visibility_controller.fly_to(coords[0], coords[1])
                logger.info("step %d POINT: (%d, %d) label=%s", index, coords[0], coords[1], step.point.label)
        elif step.refresh:
            if step.text:
                self.step_text.emit(step.text)
            
            async def _refresh_flow():
                if step.text:
                    if self._config.tts_enabled:
                        try:
                            await self._tts.speak(step.text)
                        except Exception as e:
                            logger.error("tts error: %s", e)
                    else:
                        await asyncio.sleep(max(2.0, len(step.text) * 0.05))
                if self._current_task is not None and not self._current_task.done():
                    self._current_task.cancel()
                self._cancel_flag = False
                self._current_task = asyncio.ensure_future(self._run_turn("I completed the step, continue."))
            
            asyncio.ensure_future(_refresh_flow())

        elif step.add_task is not None:
            from clicky.tasks_store import add_task
            add_task(step.add_task.text, step.add_task.date)
            
            if step.text:
                self.step_text.emit(step.text)
                
            async def _add_task_flow():
                if step.text:
                    if self._config.tts_enabled:
                        try:
                            await self._tts.speak(step.text)
                        except Exception as e:
                            logger.error("tts error: %s", e)
                    else:
                        await asyncio.sleep(max(2.0, len(step.text) * 0.05))
                self.advance_step()
                
            asyncio.ensure_future(_add_task_flow())

        else:
            is_last = (index + 1 >= len(self._steps))
            if is_last:
                # Final step — go idle after TTS or brief dwell.
                if self._config.tts_enabled:
                    self._speak_task = asyncio.ensure_future(self._speak(step.text))
                else:
                    delay = max(2.0, len(step.text) * 0.05) if step.text else 0.4
                    asyncio.ensure_future(self._delayed_idle(delay))
            else:
                # Intermediate text-only step — auto-advance after dwell.
                delay = max(3.0, len(step.text) * 0.05) if step.text else 0.5
                asyncio.ensure_future(self._delayed_advance(delay))

    def handle_text_input(self, text: str) -> None:
        """Inject typed text directly into the turn pipeline (skip mic/STT)."""
        if not text.strip():
            return
        if self._current_task is not None and not self._current_task.done():
            self._current_task.cancel()
        self._cancel_flag = False
        self._current_task = asyncio.ensure_future(self._run_turn(text))

    # ------------------------------------------------------------------
    # PCM deque bridge
    # ------------------------------------------------------------------

    def _on_pcm_chunk(self, chunk: QByteArray) -> None:
        self._pcm["deque"].append(chunk)
        self._pcm["event"].set()

    async def _pcm_async_generator(self) -> AsyncGenerator[QByteArray, None]:
        """Async generator that yields QByteArray chunks from the deque.

        Snapshots the deque and event refs at first iteration.  The ``done``
        flag is read from the live dict — stale generators from a previous
        session are terminated via ``task.cancel()`` in ``_on_hotkey_pressed``,
        not via the done flag.
        """
        dq: deque[QByteArray] = self._pcm["deque"]
        ev: asyncio.Event = self._pcm["event"]
        while True:
            await ev.wait()
            ev.clear()
            while dq:
                yield dq.popleft()
            if self._pcm["done"]:
                return

    def _reset_pcm_bridge(self) -> None:
        """Replace the PCM bridge state for a fresh session."""
        self._pcm["deque"] = deque()
        self._pcm["event"] = asyncio.Event()
        self._pcm["done"] = False

    def _stop_pcm_bridge(self) -> None:
        """Signal the PCM generator to terminate."""
        self._pcm["done"] = True
        self._pcm["event"].set()

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def _set_state(self, new_state: VoiceState) -> None:
        self._state = new_state
        self.state_changed.emit(new_state)

    # ------------------------------------------------------------------
    # Hotkey handlers
    # ------------------------------------------------------------------

    def _on_hotkey_pressed(self) -> None:
        logger.debug("hotkey pressed (state=%s)", self._state)

        # Stop TTS playback immediately.
        self._tts.stop()
        if self._speak_task is not None and not self._speak_task.done():
            self._speak_task.cancel()

        # Interrupt any in-flight turn OR lingering stream task.
        if self._state != VoiceState.IDLE:
            self._cancel_flag = True
        if self._current_task is not None and not self._current_task.done():
            self._current_task.cancel()

        # Reset PCM bridge for a fresh session.
        self._reset_pcm_bridge()

        # Transition to LISTENING, start mic, start transcription.
        self._set_state(VoiceState.LISTENING)
        self._mic.start()

        self._current_task = asyncio.ensure_future(
            self._transcription.start_stream(self._pcm_async_generator())
        )

    def _on_hotkey_released(self) -> None:
        logger.debug("hotkey released")
        self._set_state(VoiceState.PROCESSING)
        self._mic.stop()
        self._stop_pcm_bridge()
        asyncio.ensure_future(self._transcription.stop_stream())

    def _on_hotkey_cancelled(self) -> None:
        logger.debug("hotkey cancelled")
        self._mic.stop()
        self._stop_pcm_bridge()
        asyncio.ensure_future(self._transcription.stop_stream())
        # Transition to IDLE directly — the transcription client may not
        # emit a final_transcript if the session never fully started.
        self._set_state(VoiceState.IDLE)

    # ------------------------------------------------------------------
    # Transcription handler
    # ------------------------------------------------------------------

    def _on_final_transcript(self, text: str) -> None:
        if not text:
            # User pressed and released without speaking enough.
            self._set_state(VoiceState.IDLE)
            return

        # Reset cancel flag here (not in _run_turn) so a rapid
        # press between task assignment and coroutine start cannot
        # have its cancellation silently undone.
        self._cancel_flag = False
        self._current_task = asyncio.ensure_future(self._run_turn(text))

    # ------------------------------------------------------------------
    # LLM delta relay (only when not cancelled)
    # ------------------------------------------------------------------

    def _on_llm_delta(self, text: str) -> None:
        if not self._cancel_flag:
            self.response_delta.emit(text)

    # ------------------------------------------------------------------
    # Error handler
    # ------------------------------------------------------------------

    def _on_error(self, msg: str) -> None:
        logger.error("companion error: %s", msg)
        self.error.emit(msg)
        self._set_state(VoiceState.IDLE)

    # ------------------------------------------------------------------
    # TTS playback (async, fire-and-forget)
    # ------------------------------------------------------------------

    async def _speak(self, text: str) -> None:
        """Speak text via TTS. State stays RESPONDING during playback."""
        try:
            await self._tts.speak(text)
        except asyncio.CancelledError:
            logger.debug("TTS cancelled")
        except Exception as exc:  # noqa: BLE001
            logger.error("TTS error: %s", exc)
            self.error.emit(str(exc))
        finally:
            # Only transition to IDLE if we're still RESPONDING
            # (a new hotkey press may have already changed state)
            if self._state == VoiceState.RESPONDING:
                self._set_state(VoiceState.IDLE)

    # ------------------------------------------------------------------
    # Turn pipeline (async)
    # ------------------------------------------------------------------

    async def _run_turn(self, text: str) -> None:
        """Execute the full turn: screen capture → LLM request → history.

        This coroutine becomes ``_current_task`` and supports cancellation
        via ``_cancel_flag`` (cooperative) and ``task.cancel()`` (hard).
        """
        try:
            # Yield control so stop_stream (which is still draining after
            # the recv loop emitted final_transcript synchronously) can
            # finish before we do any work that pumps the Qt event loop
            # (hide_for_capture calls processEvents, which would re-enter
            # the stop_stream task and trigger a RuntimeError).
            await asyncio.sleep(0)

            # Emit the final transcript so the UI can display it.
            self.final_transcript.emit(text)

            # Hide the panel so it doesn't appear in the screenshot.
            # The async sleep lets qasync process the Qt opacity change
            # AND lets pending asyncio tasks (stop_stream cleanup) settle
            # — avoids re-entrancy that processEvents() would cause.
            self._panel_visibility_controller.hide_for_capture()
            await asyncio.sleep(0.05)
            try:
                screenshots = await asyncio.to_thread(self._screen_capture_fn)
                self._current_screenshots = screenshots
            finally:
                self._panel_visibility_controller.restore_after_capture()

            # Build image content blocks.
            image_blocks: list[dict[str, Any]] = []
            for screenshot in screenshots:
                b64 = base64.b64encode(screenshot.jpeg_bytes).decode("ascii")
                image_blocks.append({"type": "text", "text": screenshot.label})
                image_blocks.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": b64,
                        },
                    }
                )

            # Build messages from conversation history.
            messages = self._history.messages_for_request(
                current_user_text=text,
                current_images=image_blocks,
            )

            # Detect active app and load KB
            window_title = get_foreground_window_title()
            kb_content = None
            app_name = None
            if self._knowledge_dir is not None:
                apps = load_kb_from_disk(self._knowledge_dir)
                matched = match_app(window_title, apps)
                if matched is not None:
                    app_name = matched.name
                    kb_content = select_content(matched, text)
                    logger.info("KB loaded: %s (%d chars)", app_name, len(kb_content))
                else:
                    logger.debug("no KB match for window: %s", window_title)

            from clicky.tasks_store import tasks_for_date
            from datetime import date
            tasks = tasks_for_date(date.today().isoformat())
            if tasks:
                tasks_ctx = "User's tasks for today:\n" + "\n".join(f"  {i+1}. [{'x' if t.done else ' '}] {t.text}" for i, t in enumerate(tasks))
            else:
                tasks_ctx = "The user has no tasks for today."
                
            ctx_str = tasks_ctx
            if self._context_addendum:
                ctx_str += "\n\n" + self._context_addendum

            system_prompt = build_system_prompt(
                kb_content, app_name, ctx_str
            )
            self._context_addendum = ""  # clear after use

            # Transition to RESPONDING.
            self._set_state(VoiceState.RESPONDING)

            # Send to LLM.
            full_text = await self._llm.send(
                messages,
                system=system_prompt,
                model=self._current_model,
                max_tokens=4096,
            )

            # Only commit to history and emit completion if not cancelled.
            if not self._cancel_flag:
                self._history.append(text, full_text)
                self.response_complete.emit(full_text)
                self.success_turn_completed.emit()

                self._steps = parse_steps(full_text)
                self._step_index = 0
                self._show_step(0)

        except asyncio.CancelledError:
            logger.debug("turn cancelled")
            self._set_state(VoiceState.IDLE)

        except Exception as exc:  # noqa: BLE001
            logger.error("turn pipeline error: %s", exc)
            self.error.emit(str(exc))
            self._set_state(VoiceState.IDLE)

        # On success, stay in RESPONDING so the response text remains
        # visible until the next hotkey press resets to LISTENING.

    async def _delayed_idle(self, delay: float) -> None:
        """Transition to IDLE after a delay — used when fly_to runs with TTS off."""
        await asyncio.sleep(delay)
        if self._state == VoiceState.RESPONDING and not self._cancel_flag:
            self._set_state(VoiceState.IDLE)

    async def _delayed_advance(self, delay: float) -> None:
        """Advance to next step after a dwell — used for text-only intermediate steps."""
        await asyncio.sleep(delay)
        if not self._cancel_flag:
            self.advance_step()
