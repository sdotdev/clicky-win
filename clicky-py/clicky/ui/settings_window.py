"""Settings window for ClickyWin — tabbed UI for config editing."""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path

import tomli_w
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from clicky.design_system import DS
from clicky.ui.history_window import HistoryWidget
from clicky.ui.log_handler import QtLogHandler

__all__ = ["QtLogHandler", "SettingsWindow"]

logger = logging.getLogger(__name__)


class SettingsWindow(QMainWindow):
    settings_saved = Signal()    # General tab saved
    provider_changed = Signal()  # Models tab saved

    def __init__(self, config_path: Path, log_handler: "QtLogHandler", parent=None):
        super().__init__(parent)
        self._config_path = config_path
        self._log_handler = log_handler

        self.setWindowTitle("ClickyWin — Settings")
        self.setMinimumSize(600, 500)
        self.resize(700, 550)

        self._apply_stylesheet()
        self._build_ui()
        self._load_config()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _apply_stylesheet(self) -> None:
        c = DS.Colors
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background-color: {c.bg_deep};
                color: {c.text_primary};
                font-family: "Segoe UI";
                font-size: 13px;
            }}
            QLabel {{ background: transparent; color: {c.text_secondary}; }}

            /* --- Tabs --- */
            QTabWidget::pane {{
                border: 1px solid {c.border};
                border-radius: {DS.CornerRadius.medium}px;
                top: -1px;
                background: {c.panel_bg};
            }}
            QTabBar::tab {{
                background: transparent;
                color: {c.text_secondary};
                padding: 8px 18px;
                margin-right: 4px;
                border: none;
                border-bottom: 2px solid transparent;
            }}
            QTabBar::tab:hover {{ color: {c.text_primary}; }}
            QTabBar::tab:selected {{
                color: {c.text_primary};
                border-bottom: 2px solid {c.accent_blue};
            }}

            /* --- Inputs --- */
            QLineEdit, QComboBox, QPlainTextEdit {{
                background: {c.surface};
                color: {c.text_primary};
                border: 1px solid {c.border};
                border-radius: {DS.CornerRadius.small}px;
                padding: 6px 8px;
                selection-background-color: {c.accent_blue};
                selection-color: {c.text_white};
            }}
            QLineEdit:hover, QComboBox:hover {{ border-color: {c.border_bright}; }}
            QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{
                border: 1px solid {c.accent_blue};
            }}
            QComboBox::drop-down {{ border: none; width: 22px; }}
            QComboBox QAbstractItemView {{
                background: {c.panel_bg_alt};
                color: {c.text_primary};
                border: 1px solid {c.border_bright};
                border-radius: {DS.CornerRadius.small}px;
                selection-background-color: {c.accent_blue};
                selection-color: {c.text_white};
                outline: none;
            }}
            QCheckBox {{ background: transparent; color: {c.text_primary}; spacing: 8px; }}
            QCheckBox::indicator {{
                width: 16px; height: 16px;
                border: 1px solid {c.border_bright};
                border-radius: {DS.CornerRadius.xs}px;
                background: {c.surface};
            }}
            QCheckBox::indicator:checked {{
                background: {c.accent_blue};
                border-color: {c.accent_blue};
            }}

            /* --- Buttons --- */
            QPushButton {{
                background: {c.surface};
                color: {c.text_primary};
                border: 1px solid {c.border_bright};
                border-radius: {DS.CornerRadius.small}px;
                padding: 7px 16px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {c.surface_hover};
                border-color: {c.accent_blue};
                color: {c.text_white};
            }}
            QPushButton:pressed {{ background: {c.panel_bg_alt}; }}

            /* --- Group boxes read like cards --- */
            QGroupBox {{
                color: {c.text_secondary};
                background: {c.panel_bg_alt};
                border: 1px solid {c.border};
                border-radius: {DS.CornerRadius.medium}px;
                margin-top: 14px;
                padding: 14px 12px 10px 12px;
                font-weight: 600;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 12px;
                padding: 0 6px;
                color: {c.accent_blue_bright};
            }}

            /* --- Sliders --- */
            QSlider::groove:horizontal {{
                background: {c.surface};
                height: 6px;
                border-radius: 3px;
            }}
            QSlider::sub-page:horizontal {{
                background: {c.accent_blue};
                height: 6px;
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: {c.accent_blue_bright};
                border: 2px solid {c.bg_deep};
                width: 18px; height: 18px;
                margin: -7px 0;
                border-radius: 9px;
            }}
            QSlider::handle:horizontal:hover {{
                background: {c.text_white};
                border-color: {c.accent_blue};
            }}
            QSlider::handle:horizontal:pressed {{ background: {c.accent_blue}; }}

            /* --- Scrollbars --- */
            QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
            QScrollBar::handle:vertical {{
                background: {c.border_strong};
                border-radius: 5px;
                min-height: 28px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        """)

    def _build_ui(self) -> None:
        tabs = QTabWidget()
        tabs.addTab(self._build_general_tab(), "General")
        tabs.addTab(self._build_models_tab(), "Models")
        tabs.addTab(self._build_logs_tab(), "Logs")
        tabs.addTab(self._build_history_tab(), "History")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(tabs)
        self.setCentralWidget(container)

    # --- General tab ---

    def _build_general_tab(self) -> QWidget:
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        form.setContentsMargins(16, 16, 16, 16)
        form.setSpacing(10)

        # Hotkey
        self._hotkey_combo = QComboBox()
        self._hotkey_combo.addItems(["ctrl+alt", "right_ctrl"])
        form.addRow("Hotkey:", self._hotkey_combo)

        # Log level
        self._log_level_combo = QComboBox()
        self._log_level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        form.addRow("Log Level:", self._log_level_combo)

        # Lerp factor
        lerp_row = QWidget()
        lerp_layout = QHBoxLayout(lerp_row)
        lerp_layout.setContentsMargins(0, 0, 0, 0)
        self._lerp_slider = QSlider(Qt.Orientation.Horizontal)
        self._lerp_slider.setRange(1, 100)
        self._lerp_slider.setValue(15)
        self._lerp_label = QLabel("0.15")
        self._lerp_label.setFixedWidth(36)
        self._lerp_slider.valueChanged.connect(
            lambda v: self._lerp_label.setText(f"{v / 100:.2f}")
        )
        lerp_layout.addWidget(self._lerp_slider)
        lerp_layout.addWidget(self._lerp_label)
        form.addRow("Lerp Factor:", lerp_row)

        # Shake sensitivity
        shake_row = QWidget()
        shake_layout = QHBoxLayout(shake_row)
        shake_layout.setContentsMargins(0, 0, 0, 0)
        self._shake_slider = QSlider(Qt.Orientation.Horizontal)
        self._shake_slider.setRange(0, 100)
        self._shake_slider.setValue(50)
        self._shake_label = QLabel("0.50")
        self._shake_label.setFixedWidth(36)
        self._shake_slider.valueChanged.connect(
            lambda v: self._shake_label.setText(f"{v / 100:.2f}")
        )
        shake_layout.addWidget(self._shake_slider)
        shake_layout.addWidget(self._shake_label)
        form.addRow("Shake Sensitivity:", shake_row)

        # Knowledge dir
        kb_row = QWidget()
        kb_layout = QHBoxLayout(kb_row)
        kb_layout.setContentsMargins(0, 0, 0, 0)
        self._knowledge_dir_edit = QLineEdit()
        self._knowledge_dir_edit.setPlaceholderText("(default)")
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_knowledge_dir)
        kb_layout.addWidget(self._knowledge_dir_edit)
        kb_layout.addWidget(browse_btn)
        form.addRow("Knowledge Dir:", kb_row)

        # TTS toggle
        self._tts_enabled_check = QCheckBox("Enable AI voice responses")
        self._tts_enabled_check.setChecked(True)
        form.addRow("Voice:", self._tts_enabled_check)

        # Viral visual effects
        effects_group = QGroupBox("Visual Effects")
        effects_layout = QVBoxLayout(effects_group)
        effects_layout.setSpacing(6)
        self._power_mode_check = QCheckBox(
            "Power Mode on launch — particle cursor, combos, screen shake (/power)"
        )
        self._neon_scan_demo_check = QCheckBox(
            "Neon Scan demo mode — synthetic boxes, no screenshot or AI (/scan)"
        )
        self._celebrate_check = QCheckBox(
            "Fireworks + confetti when a guided task finishes (/celebrate)"
        )
        effects_layout.addWidget(self._power_mode_check)
        effects_layout.addWidget(self._neon_scan_demo_check)
        effects_layout.addWidget(self._celebrate_check)
        form.addRow("Effects:", effects_group)

        # Save button
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save_general)
        form.addRow("", save_btn)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(form_widget)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll)
        return tab

    # --- Models tab ---

    def _build_models_tab(self) -> QWidget:
        content = QWidget()
        vbox = QVBoxLayout(content)
        vbox.setContentsMargins(16, 16, 16, 16)
        vbox.setSpacing(12)

        # Brain group
        brain_group = QGroupBox("Brain")
        brain_form = QFormLayout(brain_group)
        self._brain_provider = QComboBox()
        self._brain_provider.addItems(["ollama", "gemini", "anthropic_worker"])
        self._brain_model = QLineEdit()
        self._brain_base_url = QLineEdit()
        self._brain_api_key = QLineEdit()
        self._brain_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        brain_form.addRow("Provider:", self._brain_provider)
        brain_form.addRow("Model:", self._brain_model)
        brain_form.addRow("Base URL:", self._brain_base_url)
        brain_form.addRow("API Key:", self._brain_api_key)
        vbox.addWidget(brain_group)

        # Ears group
        ears_group = QGroupBox("Ears")
        ears_form = QFormLayout(ears_group)
        self._ears_provider = QComboBox()
        self._ears_provider.addItems(["faster_whisper", "assemblyai_worker"])
        self._ears_model = QLineEdit()
        self._ears_device = QComboBox()
        self._ears_device.addItems(["cuda", "cpu"])
        self._ears_compute_type = QComboBox()
        self._ears_compute_type.addItems(["float16", "int8"])
        ears_form.addRow("Provider:", self._ears_provider)
        ears_form.addRow("Model:", self._ears_model)
        ears_form.addRow("Device:", self._ears_device)
        ears_form.addRow("Compute Type:", self._ears_compute_type)
        vbox.addWidget(ears_group)

        # Mouth group
        mouth_group = QGroupBox("Mouth")
        mouth_form = QFormLayout(mouth_group)
        self._mouth_provider = QComboBox()
        self._mouth_provider.addItems(["kokoro", "elevenlabs_worker"])
        self._mouth_voice = QComboBox()
        self._mouth_voice.addItems(["af_heart", "af_bella", "am_adam", "am_michael", "bf_emma", "bm_george"])
        mouth_form.addRow("Provider:", self._mouth_provider)
        mouth_form.addRow("Voice:", self._mouth_voice)
        vbox.addWidget(mouth_group)

        # Worker URL
        worker_form = QFormLayout()
        self._worker_url_edit = QLineEdit()
        worker_form.addRow("Worker URL:", self._worker_url_edit)
        vbox.addLayout(worker_form)

        # Save button
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save_models)
        vbox.addWidget(save_btn)
        vbox.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll)
        return tab

    # --- Logs tab ---

    def _build_logs_tab(self) -> QWidget:
        tab = QWidget()
        vbox = QVBoxLayout(tab)
        vbox.setContentsMargins(8, 8, 8, 8)
        vbox.setSpacing(6)

        # Top bar: level filter + clear button
        top_row = QWidget()
        top_layout = QHBoxLayout(top_row)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.addWidget(QLabel("Filter:"))
        self._log_filter_combo = QComboBox()
        self._log_filter_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        self._log_filter_combo.setCurrentText("DEBUG")
        top_layout.addWidget(self._log_filter_combo)
        top_layout.addStretch()
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear_logs)
        top_layout.addWidget(clear_btn)
        vbox.addWidget(top_row)

        self._log_edit = QPlainTextEdit()
        self._log_edit.setReadOnly(True)
        self._log_edit.setFont(QFont("Consolas", 9))
        self._log_edit.setStyleSheet(
            f"background: {DS.Colors.panel_bg}; color: {DS.Colors.text_primary};"
            f" border: 1px solid {DS.Colors.border};"
        )
        vbox.addWidget(self._log_edit)

        # Connect log handler signal
        self._log_handler.log_record.connect(self._append_log_line)

        return tab

    # --- History tab ---

    def _build_history_tab(self) -> QWidget:
        tab = QWidget()
        vbox = QVBoxLayout(tab)
        vbox.setContentsMargins(0, 0, 0, 0)
        self.history_widget = HistoryWidget()
        vbox.addWidget(self.history_widget)
        return tab

    # ------------------------------------------------------------------
    # Config I/O
    # ------------------------------------------------------------------

    def _read_raw(self) -> dict:
        """Read the raw TOML dict from disk, return {} on error."""
        try:
            return tomllib.loads(self._config_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Could not read config for settings: %s", exc)
            return {}

    def _write_raw(self, data: dict) -> None:
        """Write dict back to config.toml via tomli_w."""
        self._config_path.write_text(tomli_w.dumps(data), encoding="utf-8")

    def _load_config(self) -> None:
        """Populate all fields from current config.toml."""
        data = self._read_raw()

        # General
        _set_combo(self._hotkey_combo, data.get("hotkey", "ctrl+alt"))
        _set_combo(self._log_level_combo, data.get("log_level", "INFO"))
        lerp = float(data.get("lerp_factor", 0.15))
        slider_val = max(1, min(100, round(lerp * 100)))
        self._lerp_slider.setValue(slider_val)
        self._lerp_label.setText(f"{slider_val / 100:.2f}")
        shake = float(data.get("shake_sensitivity", 0.5))
        shake_val = max(0, min(100, round(shake * 100)))
        self._shake_slider.setValue(shake_val)
        self._shake_label.setText(f"{shake_val / 100:.2f}")
        self._knowledge_dir_edit.setText(data.get("knowledge_dir", ""))
        self._tts_enabled_check.setChecked(bool(data.get("tts_enabled", True)))

        # Effects
        effects = data.get("effects", {}) if isinstance(data.get("effects"), dict) else {}
        self._power_mode_check.setChecked(bool(effects.get("power_mode_enabled", False)))
        self._neon_scan_demo_check.setChecked(bool(effects.get("neon_scan_demo", True)))
        self._celebrate_check.setChecked(bool(effects.get("celebrate_on_success", False)))

        # Models — brain
        brain = data.get("brain", {})
        _set_combo(self._brain_provider, brain.get("provider", "ollama"))
        self._brain_model.setText(brain.get("model", ""))
        self._brain_base_url.setText(brain.get("base_url", ""))
        self._brain_api_key.setText(brain.get("api_key", ""))

        # Models — ears
        ears = data.get("ears", {})
        _set_combo(self._ears_provider, ears.get("provider", "faster_whisper"))
        self._ears_model.setText(ears.get("model", ""))
        _set_combo(self._ears_device, ears.get("device", "cuda"))
        _set_combo(self._ears_compute_type, ears.get("compute_type", "float16"))

        # Models — mouth
        mouth = data.get("mouth", {})
        _set_combo(self._mouth_provider, mouth.get("provider", "kokoro"))
        _set_combo(self._mouth_voice, mouth.get("voice", "af_heart"))

        # Worker URL
        self._worker_url_edit.setText(data.get("worker_url", ""))

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    @Slot()
    def _save_general(self) -> None:
        data = self._read_raw()
        data["hotkey"] = self._hotkey_combo.currentText()
        data["log_level"] = self._log_level_combo.currentText()
        data["lerp_factor"] = self._lerp_slider.value() / 100
        data["shake_sensitivity"] = self._shake_slider.value() / 100
        data["tts_enabled"] = self._tts_enabled_check.isChecked()
        effects = data.setdefault("effects", {})
        effects["power_mode_enabled"] = self._power_mode_check.isChecked()
        effects["neon_scan_demo"] = self._neon_scan_demo_check.isChecked()
        effects["celebrate_on_success"] = self._celebrate_check.isChecked()
        kd = self._knowledge_dir_edit.text().strip()
        if kd:
            data["knowledge_dir"] = kd
        else:
            data.pop("knowledge_dir", None)
        try:
            self._write_raw(data)
            self.settings_saved.emit()
            logger.info("General settings saved.")
        except Exception as exc:
            logger.error("Failed to save general settings: %s", exc)

    @Slot()
    def _save_models(self) -> None:
        data = self._read_raw()

        data.setdefault("brain", {})
        data["brain"]["provider"] = self._brain_provider.currentText()
        data["brain"]["model"] = self._brain_model.text().strip()
        data["brain"]["base_url"] = self._brain_base_url.text().strip()
        data["brain"]["api_key"] = self._brain_api_key.text().strip()

        data.setdefault("ears", {})
        data["ears"]["provider"] = self._ears_provider.currentText()
        data["ears"]["model"] = self._ears_model.text().strip()
        data["ears"]["device"] = self._ears_device.currentText()
        data["ears"]["compute_type"] = self._ears_compute_type.currentText()

        data.setdefault("mouth", {})
        data["mouth"]["provider"] = self._mouth_provider.currentText()
        data["mouth"]["voice"] = self._mouth_voice.currentText()

        worker_url = self._worker_url_edit.text().strip()
        if worker_url:
            data["worker_url"] = worker_url

        try:
            self._write_raw(data)
            self.provider_changed.emit()
            logger.info("Model settings saved.")
        except Exception as exc:
            logger.error("Failed to save model settings: %s", exc)

    @Slot(str)
    def _append_log_line(self, line: str) -> None:
        """Append a log line, respecting the current filter level."""
        filter_level = getattr(logging, self._log_filter_combo.currentText(), logging.DEBUG)
        # Determine level of the incoming line from its text
        record_level = _level_from_line(line)
        if record_level >= filter_level:
            self._log_edit.appendPlainText(line)
            # Auto-scroll to bottom
            sb = self._log_edit.verticalScrollBar()
            sb.setValue(sb.maximum())

    @Slot()
    def _clear_logs(self) -> None:
        self._log_edit.clear()

    @Slot()
    def _browse_knowledge_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "Select Knowledge Directory", self._knowledge_dir_edit.text()
        )
        if directory:
            self._knowledge_dir_edit.setText(directory)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _set_combo(combo: QComboBox, value: str) -> None:
    """Set combo to value if present, else leave at index 0."""
    idx = combo.findText(value)
    if idx >= 0:
        combo.setCurrentIndex(idx)


_LEVEL_NAMES = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


def _level_from_line(line: str) -> int:
    """Best-effort parse of the level name from a formatted log line."""
    for name, level in _LEVEL_NAMES.items():
        if name in line:
            return level
    return logging.DEBUG
