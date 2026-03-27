"""
MultiUserAuthMiddleware — server-side per-user authentication middleware.

For every request to /api/v1/* endpoints:
  1. Validates the Bearer API key via ApiKeyAuthProviderImpl.
  2. On success: sets scope["state"].user_id and activates the per-user
     ZeroGKVStorage context via UserAwareKVStorageProxy.
  3. On failure: returns HTTP 401.

Endpoints outside /api/v1/ (health, metrics, etc.) are passed through without auth.
The user registration endpoint (POST /api/v1/users/register) is also exempted.

Implementation note: this is a *pure ASGI middleware* (not BaseHTTPMiddleware).
BaseHTTPMiddleware internally creates Request objects whose body stream async
generators are abandoned on GC, triggering a uvloop + Python 3.12 bug that
gradually corrupts the event loop and crashes the process.  A pure ASGI
middleware never touches the request body stream, so this class of bug cannot
occur.
"""

import json

from starlette.types import ASGIApp, Receive, Scope, Send

from core.observation.logger import get_logger

logger = get_logger(__name__)

# Paths that do not require authentication
_AUTH_EXEMPT_PATHS = {
    "/api/v1/users/register",
}

# Only paths under this prefix require auth
_AUTH_PREFIX = "/api/v1/"


class MultiUserAuthMiddleware:
    """
    Pure ASGI authentication + KV context middleware for server-side multi-user mode.
    Does NOT extend BaseHTTPMiddleware — no Request objects are created here.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._auth_provider = None
        self._kv_proxy = None

    def _get_auth_provider(self):
        if self._auth_provider is None:
            from core.di.utils import get_bean_by_type
            from core.component.auth_provider import AuthProvider

            self._auth_provider = get_bean_by_type(AuthProvider)
        return self._auth_provider

    def _get_kv_proxy(self):
        if self._kv_proxy is None:
            from core.di.utils import get_bean_by_type
            from infra_layer.adapters.out.persistence.kv_storage.kv_storage_interface import (
                KVStorageInterface,
            )

            kv = get_bean_by_type(KVStorageInterface)
            from infra_layer.adapters.out.persistence.kv_storage.user_aware_kv_storage import (
                UserAwareKVStorageProxy,
            )

            if isinstance(kv, UserAwareKVStorageProxy):
                self._kv_proxy = kv
        return self._kv_proxy

    async def _send_401(self, send: Send) -> None:
        body = json.dumps({"detail": "Invalid or missing API key"}).encode()
        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": [
                [b"content-type", b"application/json"],
                [b"content-length", str(len(body)).encode()],
            ],
        })
        await send({
            "type": "http.response.body",
            "body": body,
            "more_body": False,
        })

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Pass through non-HTTP connections (WebSocket, lifespan, etc.)
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        # Skip auth for paths outside /api/v1/ or explicitly exempted
        if not path.startswith(_AUTH_PREFIX) or path in _AUTH_EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return

        # Extract Authorization header directly from scope — no Request object created
        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        auth_bytes = headers.get(b"authorization", b"")
        auth_str = auth_bytes.decode("latin-1")
        if auth_str.lower().startswith("bearer "):
            api_key = auth_str[len("bearer "):].strip()
        else:
            api_key = ""

        if not api_key:
            logger.warning("Unauthorized request to %s (missing API key)", path)
            await self._send_401(send)
            return

        # Authenticate via auth provider
        auth_provider = self._get_auth_provider()
        user_data = await auth_provider.get_optional_user_data_by_key(api_key)

        if user_data is None:
            logger.warning("Unauthorized request to %s (invalid API key)", path)
            await self._send_401(send)
            return

        # Store user_id so route handlers can read request.state.user_id.
        # In Starlette 0.46+, scope["state"] is a plain dict {}; State(scope["state"])
        # wraps it. Writing into the dict is the correct way to set state from ASGI middleware.
        scope.setdefault("state", {})
        scope["state"]["user_id"] = user_data["user_id"]

        # Activate per-user KV context
        kv_proxy = self._get_kv_proxy()
        if kv_proxy and "zerog_stream_id" in user_data:
            kv_proxy.set_user_context(
                user_id=user_data["user_id"],
                stream_id=user_data["zerog_stream_id"],
                enc_key_hex=user_data["zerog_encryption_key"],
                wallet_key=user_data["zerog_wallet_key"],
            )

        try:
            await self.app(scope, receive, send)
        finally:
            if kv_proxy:
                kv_proxy.clear_user_context()


__all__ = ["MultiUserAuthMiddleware"]
