"""
Cyber Trade - Universal Logger (Resilient Fallback Engine)
==========================================================
Provides Loguru logger if available, or a 100% compatible standard logging
fallback to ensure zero runtime crashes on fresh environments.
"""

import sys
import logging

try:
    from loguru import logger
except ImportError:
    class FallbackLogger:
        """Compatible fallback for loguru logger."""

        def __init__(self):
            self._logger = logging.getLogger("cyber_trade")
            if not self._logger.handlers:
                handler = logging.StreamHandler(sys.stdout)
                formatter = logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s", datefmt="%H:%M:%S")
                handler.setFormatter(formatter)
                self._logger.addHandler(handler)
                self._logger.setLevel(logging.INFO)

        def info(self, msg, *args, **kwargs):
            self._logger.info(msg, *args, **kwargs)

        def debug(self, msg, *args, **kwargs):
            self._logger.debug(msg, *args, **kwargs)

        def warning(self, msg, *args, **kwargs):
            self._logger.warning(msg, *args, **kwargs)

        def error(self, msg, *args, **kwargs):
            self._logger.error(msg, *args, **kwargs)

        def success(self, msg, *args, **kwargs):
            self._logger.info(f"SUCCESS: {msg}", *args, **kwargs)

        def remove(self, *args, **kwargs):
            pass

        def add(self, *args, **kwargs):
            pass

    logger = FallbackLogger()
