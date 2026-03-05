#!/usr/bin/env python3
"""
Centralized logger for EverMemOS hooks
Provides both stderr and file logging capabilities
"""

import sys
import os
from datetime import datetime
from pathlib import Path

class EverMemOSLogger:
    """Logger that outputs to both stderr and a log file"""

    def __init__(self, log_name="evermemos_hooks"):
        self.log_dir = Path.home() / ".claude" / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / f"{log_name}.log"

        # Optional: Environment variable to control logging level
        self.debug_enabled = os.environ.get('EVERMEMOS_DEBUG', '').lower() in ('1', 'true', 'yes')

    def _log(self, level, message, to_file=True, to_stderr=True):
        """Internal logging method"""
        timestamp = datetime.now().isoformat()
        formatted_msg = f"[{timestamp}] [{level}] {message}"

        # Always write to file for debugging
        if to_file:
            try:
                with open(self.log_file, 'a', encoding='utf-8') as f:
                    f.write(formatted_msg + "\n")
                    f.flush()
            except Exception as e:
                # Fallback to stderr if file write fails
                print(f"[ERROR] Failed to write to log file: {e}", file=sys.stderr)

        # Only write to stderr if debug is enabled or it's a warning/error
        if to_stderr and (self.debug_enabled or level in ('WARNING', 'ERROR')):
            print(formatted_msg, file=sys.stderr)

    def debug(self, message):
        """Debug level logging"""
        self._log('DEBUG', message, to_file=True, to_stderr=self.debug_enabled)

    def info(self, message):
        """Info level logging"""
        self._log('INFO', message, to_file=True, to_stderr=False)

    def warning(self, message):
        """Warning level logging"""
        self._log('WARNING', message, to_file=True, to_stderr=True)

    def error(self, message):
        """Error level logging"""
        self._log('ERROR', message, to_file=True, to_stderr=True)

# Per-name singleton instances
_loggers = {}

def get_logger(log_name="evermemos_hooks"):
    """Get or create a logger instance by name"""
    global _loggers
    if log_name not in _loggers:
        _loggers[log_name] = EverMemOSLogger(log_name)
    return _loggers[log_name]


if __name__ == "__main__":
    # Test the logger
    logger = get_logger()
    logger.debug("This is a debug message")
    logger.info("This is an info message")
    logger.warning("This is a warning message")
    logger.error("This is an error message")

    print(f"\n✅ Log file created at: {logger.log_file}")
    print(f"📝 To enable stderr output, set: export EVERMEMOS_DEBUG=1")
