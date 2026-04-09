"""
UserAwareKVStorageProxy — per-user routing layer for 0G KV Storage.

In server-side deployment every user has their own 0G KV stream.
This proxy:
  1. Keeps a cache of ZeroGKVStorage instances, keyed by user_id.
  2. Uses a ContextVar to track which user's storage is active for the
     current async task / request.
  3. All KVStorageInterface calls are forwarded to the active user's storage.

Usage (called by MultiUserAuthMiddleware after authentication):
    proxy.set_user_context(user_id, stream_id, enc_key_hex, wallet_key)
    # ... handle request ...
    proxy.clear_user_context()
"""

from contextvars import ContextVar
from typing import Dict, List, Optional, Tuple, AsyncIterator

from core.observation.logger import get_logger
from .kv_storage_interface import KVStorageInterface

logger = get_logger(__name__)

# ContextVar holds the ZeroGKVStorage instance for the current request.
_kv_user_context: ContextVar[Optional[KVStorageInterface]] = ContextVar(
    "_kv_user_context", default=None
)


class UserAwareKVStorageProxy(KVStorageInterface):
    """
    Routes KV operations to the per-user ZeroGKVStorage instance.

    The proxy itself is a singleton registered in the DI container.
    Per-request routing is done via a ContextVar set by the auth middleware.
    """

    def __init__(
        self,
        kv_url: str,
        rpc_url: str,
        indexer_url: str,
        flow_address: str,
        encryption_key_hex: str = "",
    ) -> None:
        self._kv_url = kv_url
        self._rpc_url = rpc_url
        self._indexer_url = indexer_url
        self._flow_address = flow_address
        # Global encryption key shared by all users — must match the KV node's
        # encryption_key in config_testnet_turbo.toml so the node can replay txs.
        self._encryption_key: Optional[bytes] = bytes.fromhex(encryption_key_hex) if encryption_key_hex else None
        # user_id -> ZeroGKVStorage (lazy, created on first request per user)
        self._cache: Dict[str, KVStorageInterface] = {}

    # ------------------------------------------------------------------
    # Context management (called by MultiUserAuthMiddleware)
    # ------------------------------------------------------------------

    def set_user_context(
        self,
        user_id: str,
        stream_id: str,
        enc_key_hex: str,
        wallet_key: str,
    ) -> None:
        """Activate the per-user KV storage for the current async context."""
        storage = self._get_or_create(user_id, stream_id, enc_key_hex, wallet_key)
        _kv_user_context.set(storage)

    def clear_user_context(self) -> None:
        """Deactivate the per-user KV storage for the current async context."""
        _kv_user_context.set(None)

    def _get_or_create(
        self,
        user_id: str,
        stream_id: str,
        enc_key_hex: str,
        wallet_key: str,
    ) -> KVStorageInterface:
        if user_id not in self._cache:
            from .zerog_kv_storage import ZeroGKVStorage

            logger.info(
                "Creating ZeroGKVStorage for user=%s stream=%s", user_id, stream_id
            )
            self._cache[user_id] = ZeroGKVStorage(
                kv_url=self._kv_url,
                rpc_url=self._rpc_url,
                indexer_url=self._indexer_url,
                flow_address=self._flow_address,
                stream_id=stream_id,
                encryption_key=self._encryption_key,
                wallet_private_key=wallet_key,
            )
        return self._cache[user_id]

    # ------------------------------------------------------------------
    # Internal helper
    # ------------------------------------------------------------------

    def _current(self) -> KVStorageInterface:
        storage = _kv_user_context.get()
        if storage is None:
            raise RuntimeError(
                "No KV user context set for the current request. "
                "Ensure MultiUserAuthMiddleware ran successfully."
            )
        return storage

    # ------------------------------------------------------------------
    # KVStorageInterface delegation
    # ------------------------------------------------------------------

    async def get(self, key: str) -> Optional[str]:
        return await self._current().get(key)

    async def put(self, key: str, value: str) -> bool:
        return await self._current().put(key, value)

    async def delete(self, key: str) -> bool:
        return await self._current().delete(key)

    async def batch_get(self, keys: List[str]) -> Dict[str, str]:
        return await self._current().batch_get(keys)

    async def batch_delete(self, keys: List[str]) -> int:
        return await self._current().batch_delete(keys)

    async def iterate_all(self) -> AsyncIterator[Tuple[str, str]]:
        """Iterate all KV entries.

        - With user context: iterate current user's stream
        - Without user context (startup): iterate ALL users' streams for data recovery
        """
        storage = _kv_user_context.get()
        if storage is not None:
            # Normal request with user context: iterate current user's stream
            async for item in storage.iterate_all():
                yield item
        else:
            # No user context (startup data-sync): iterate ALL users' streams
            logger.info("🔄 Starting multi-user KV scan for startup data recovery...")
            async for item in self._iterate_all_users():
                yield item

    async def _iterate_all_users(self) -> AsyncIterator[Tuple[str, str]]:
        """Iterate through all users' streams for startup data recovery.

        This is called during startup when there's no user context.
        Reads all user credentials from MongoDB and scans each user's stream.
        """
        try:
            # Import here to avoid circular dependency
            from infra_layer.adapters.out.persistence.document.user.user_secret import UserSecret
            from infra_layer.adapters.out.persistence.kv_storage.zerog_kv_storage import ZeroGKVStorage

            # Get all users from MongoDB
            users = await UserSecret.find_all().to_list()

            if not users:
                logger.info("📭 No users found in database, skipping multi-user KV scan")
                return

            logger.info("📊 Found %d users, scanning their streams...", len(users))
            user_count = 0
            total_docs = 0
            failed_users: list = []

            for user in users:
                user_count += 1
                logger.info("[%d/%d] Scanning stream for user: %s",
                           user_count, len(users), user.user_id)

                user_storage = None
                try:
                    # Create temporary ZeroGKVStorage instance for this user
                    user_storage = ZeroGKVStorage(
                        kv_url=self._kv_url,
                        rpc_url=self._rpc_url,
                        indexer_url=self._indexer_url,
                        flow_address=self._flow_address,
                        stream_id=user.zerog_stream_id,
                        encryption_key=self._encryption_key,
                        wallet_private_key=user.zerog_wallet_key,
                    )

                    # Iterate this user's stream
                    user_docs = 0
                    async for key, value in user_storage.iterate_all():
                        user_docs += 1
                        total_docs += 1
                        yield key, value

                    if user_docs > 0:
                        logger.info("   ✓ Scanned %d documents for user %s",
                                   user_docs, user.user_id)
                    else:
                        logger.debug("   - No documents for user %s", user.user_id)

                except Exception as e:
                    logger.error("❌ Failed to scan stream for user %s: %s",
                                user.user_id, e)
                    failed_users.append(user.user_id)
                finally:
                    if user_storage is not None:
                        try:
                            user_storage.close()
                        except Exception as close_err:
                            logger.error("❌ Failed to close storage for user %s: %s",
                                        user.user_id, close_err)

            if failed_users:
                logger.warning(
                    "⚠️  Multi-user KV scan: %d/%d users failed — %s",
                    len(failed_users), len(users), failed_users,
                )
            logger.info("✅ Multi-user KV scan complete: %d users, %d total documents",
                       user_count, total_docs)

        except Exception as e:
            logger.error("❌ Multi-user KV scan failed: %s", e)
            # Don't raise - allow startup to continue even if scan fails

    def close(self) -> None:
        for user_id, storage in self._cache.items():
            try:
                storage.close()
                logger.info("Closed ZeroGKVStorage for user=%s", user_id)
            except Exception as e:
                logger.error("Failed to close KV storage for user=%s: %s", user_id, e)
        self._cache.clear()


__all__ = ["UserAwareKVStorageProxy"]
