"""Qt logging handler — bridges Python's logging to Qt signals.

Extracted from settings_window so it can be instantiated early in app startup
independently of the settings UI.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal


class QtLogHandler(QObject, logging.Handler):
    """logging.Handler that emits each formatted record as a Qt signal."""

    log_record = Signal(str)

    def __init__(self, parent=None):
        QObject.__init__(self, parent)
        logging.Handler.__init__(self)
        self.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)-8s %(name)s — %(message)s",
                datefmt="%H:%M:%S",
            )
        )

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.log_record.emit(self.format(record))
        except Exception:
            self.handleError(record)
