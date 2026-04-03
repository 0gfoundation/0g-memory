"""
Recovery gate middleware

Blocks all API requests with 503 while startup data recovery is in progress.
Health-check and metrics paths are always passed through.
"""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from core.startup.startup_state import is_recovering
from core.observation.logger import get_logger

logger = get_logger(__name__)

# Paths that must remain reachable during recovery (e.g. load-balancer probes)
_BYPASS_PREFIXES = ("/health", "/metrics", "/healthz", "/ready")


class RecoveryGateMiddleware(BaseHTTPMiddleware):
    """
    Returns 503 for all non-health API requests while startup recovery is running.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        if is_recovering():
            path = request.url.path
            if not any(path.startswith(p) for p in _BYPASS_PREFIXES):
                logger.debug("Recovery gate: blocking request to %s", path)
                return JSONResponse(
                    status_code=503,
                    content={
                        "error": "Service is recovering startup data, please retry shortly"
                    },
                    headers={"Retry-After": "30"},
                )
        return await call_next(request)
