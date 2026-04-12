"""
User Controller — registration and profile endpoints for server-side deployment.

Endpoints:
  POST /api/v1/users/register  — create a new user, returns api_key
  GET  /api/v1/users/me        — return current authenticated user's info
"""

import os
import secrets
from datetime import datetime

from fastapi import HTTPException, Request as FastAPIRequest
from pydantic import BaseModel, Field

from core.di.decorators import controller
from core.interface.controller.base_controller import BaseController, get, post
from core.observation.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Request / Response DTOs
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    user_id: str = Field(..., description="Desired user identifier (must be unique)")
    zerog_wallet_key: str = Field(
        ..., description="Your EVM wallet private key (stored server-side, used for 0G KV writes)"
    )


class RegisterResponse(BaseModel):
    user_id: str
    api_key: str = Field(..., description="Bearer token to use in Authorization header")
    message: str = "Registration successful."


class UserMeResponse(BaseModel):
    user_id: str
    zerog_stream_id: str
    created_at: str


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------


@controller("user_controller", primary=True)
class UserController(BaseController):
    """User registration and info controller."""

    def __init__(self):
        super().__init__(
            prefix="/api/v1/users",
            tags=["User Controller"],
            default_auth="none",
        )

    @post(
        "/register",
        response_model=RegisterResponse,
        summary="Register a new user",
        description="""
        Register a new user for server-side EverMemOS.

        - Generates a unique 0G KV stream_id and AES-256 encryption key for this user.
        - Returns a Bearer API key.
        - Use the API key in `Authorization: Bearer <api_key>` on all subsequent requests.
        """,
    )
    async def register(
        self,
        request: FastAPIRequest,
        body: RegisterRequest,
    ) -> RegisterResponse:
        from infra_layer.adapters.out.persistence.document.user.user_secret import (
            UserSecret,
        )

        # Check for duplicate user_id
        existing = await UserSecret.find_one(UserSecret.user_id == body.user_id)
        if existing:
            if existing.zerog_wallet_key == body.zerog_wallet_key:
                # Same user re-registering (e.g. after uninstall) — return existing api_key
                logger.info("User '%s' re-registered with matching wallet key, returning existing api_key", body.user_id)
                return RegisterResponse(user_id=body.user_id, api_key=existing.api_key, message="Already registered.")
            raise HTTPException(
                status_code=403,
                detail=f"User '{body.user_id}' already exists with a different wallet key.",
            )

        # Generate credentials
        api_key = secrets.token_urlsafe(32)
        stream_id = secrets.token_hex(32)   # 64-char hex, same format as local .0g_secrets
        enc_key_hex = secrets.token_hex(32)  # 256-bit AES key

        secret_doc = UserSecret(
            user_id=body.user_id,
            api_key=api_key,
            zerog_stream_id=stream_id,
            zerog_encryption_key=enc_key_hex,
            zerog_wallet_key=body.zerog_wallet_key,
            created_at=datetime.utcnow(),
        )
        await secret_doc.insert()

        # Backup all users to local file after new registration
        try:
            from infra_layer.adapters.out.persistence.user_secret_backup import UserSecretBackup
            await UserSecretBackup.backup_all_users()
        except Exception as e:
            logger.warning("Failed to backup user secrets after registration: %s", e)
            # Don't fail registration if backup fails

        # Register stream_id in KV node config so it is synced on next restart
        try:
            from infra_layer.adapters.out.persistence.kv_storage.kv_node_config import (
                add_stream_id_to_kv_config,
            )
            add_stream_id_to_kv_config(stream_id)
        except Exception as e:
            logger.warning("Failed to update KV node config for user %s: %s", body.user_id, e)
            # Don't fail registration if config update fails

        logger.info("Registered new user: %s", body.user_id)
        return RegisterResponse(user_id=body.user_id, api_key=api_key)

    @get(
        "/me",
        response_model=UserMeResponse,
        summary="Get current user info",
    )
    async def get_me(self, request: FastAPIRequest) -> UserMeResponse:
        # user_id is set by MultiUserAuthMiddleware
        user_id = getattr(request.state, "user_id", None)
        if not user_id:
            raise HTTPException(status_code=401, detail="Not authenticated")

        from infra_layer.adapters.out.persistence.document.user.user_secret import (
            UserSecret,
        )

        secret = await UserSecret.find_one(UserSecret.user_id == user_id)
        if not secret:
            raise HTTPException(status_code=404, detail="User not found")

        return UserMeResponse(
            user_id=secret.user_id,
            zerog_stream_id=secret.zerog_stream_id,
            created_at=secret.created_at.isoformat(),
        )


__all__ = ["UserController"]
