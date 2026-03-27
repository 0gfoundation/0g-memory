from typing import Optional, Dict, Any
from abc import ABC, abstractmethod
from fastapi import Request, HTTPException

from core.di.decorators import component
from core.observation.logger import get_logger

logger = get_logger(__name__)


class AuthProvider(ABC):
    """Authentication provider interface, responsible for handling authorization header and user context"""

    @abstractmethod
    async def get_optional_user_data_from_request(
        self, request: Request
    ) -> Optional[Dict[str, Any]]:
        """
        Extract full user data from the request (optional)

        Args:
            request: FastAPI request object

        Returns:
            Optional[Dict[str, Any]]: User data, including user_id, role, etc. Return None if not present or invalid
        """


@component(name="auth_provider")
class ApiKeyAuthProviderImpl(AuthProvider):
    """
    Production auth provider for server-side deployment.

    Validates Bearer <api_key> against the user_secrets MongoDB collection.
    Uses bcrypt to verify the stored hash. Returns user_id on success.
    """

    async def get_optional_user_data_by_key(
        self, api_key: str
    ) -> Optional[Dict[str, Any]]:
        """Validate a raw API key string and return user data, or None if invalid."""
        try:
            import asyncio
            from infra_layer.adapters.out.persistence.document.user.user_secret import (
                UserSecret,
            )
            import bcrypt as _bcrypt

            loop = asyncio.get_running_loop()

            # Scan user_secrets to find a matching api_key.
            # In practice the number of users is small; for scale add a lookup index
            # on a truncated key prefix.
            async for secret in UserSecret.find_all():
                # Run bcrypt in a thread pool to avoid blocking the event loop (~200ms).
                key_bytes = api_key.encode()
                hash_bytes = secret.api_key_hash.encode()
                match = await loop.run_in_executor(
                    None, _bcrypt.checkpw, key_bytes, hash_bytes
                )
                if match:
                    from core.authorize.enums import Role

                    return {
                        "user_id": secret.user_id,
                        "role": Role.USER.value,
                        "zerog_stream_id": secret.zerog_stream_id,
                        "zerog_encryption_key": secret.zerog_encryption_key,
                        "zerog_wallet_key": secret.zerog_wallet_key,
                    }
            return None
        except Exception as e:
            logger.error("ApiKeyAuthProviderImpl error: %s", e)
            return None

    async def get_optional_user_data_from_request(
        self, request: Request
    ) -> Optional[Dict[str, Any]]:
        auth_header = request.headers.get("authorization")
        if not auth_header:
            return None
        api_key = auth_header.replace("Bearer ", "").strip()
        if not api_key:
            return None
        return await self.get_optional_user_data_by_key(api_key)


# ---------------------------------------------------------------------------
# Legacy test provider — kept for local single-user mode (no auth required)
# ---------------------------------------------------------------------------


class TestAuthProviderImpl(AuthProvider):
    """Authentication provider implementation, responsible for handling authorization header and user context"""

    def __init__(self):
        """Initialize the authentication provider"""

    async def get_user_id_from_request(self, request: Request) -> int:
        """
        Extract user ID from the request

        Current implementation: directly obtain user ID from the authorization header (temporary solution)
        Future extension: can support JWT token parsing, etc.

        Args:
            request: FastAPI request object

        Returns:
            int: User ID

        Raises:
            HTTPException: When the authorization header is missing or invalid
        """
        # Get user ID from the authorization header
        auth_header = request.headers.get("authorization")

        if not auth_header:
            raise HTTPException(status_code=401, detail="Missing authorization header")

        # Remove possible "Bearer " prefix
        user_id_str = auth_header.replace("Bearer ", "").strip()

        try:
            user_id = int(user_id_str)
            if user_id <= 0:
                raise ValueError("User ID must be a positive integer")
            return user_id
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid user ID format in authorization header, should be a positive integer",
            )

    async def get_optional_user_data_from_request(
        self, request: Request
    ) -> Optional[Dict[str, Any]]:
        """
        Extract full user data from the request (optional)

        Args:
            request: FastAPI request object

        Returns:
            Optional[Dict[str, Any]]: User data, including user_id, role, etc. Return None if not present or invalid
        """
        try:
            user_id = await self.get_user_id_from_request(request)
            # Import Role enum
            from core.authorize.enums import Role

            return {"user_id": user_id, "role": Role.USER.value}
        except HTTPException:
            return None
