"""
Startup state module

Tracks whether the application is still performing startup data recovery.
Used by RecoveryGateMiddleware to block API requests during recovery.
"""

_recovering: bool = False


def mark_recovering() -> None:
    """Call before launching the background recovery task."""
    global _recovering
    _recovering = True


def mark_ready() -> None:
    """Call after the recovery task finishes (success or failure)."""
    global _recovering
    _recovering = False


def is_recovering() -> bool:
    """Returns True if startup recovery is still in progress."""
    return _recovering
