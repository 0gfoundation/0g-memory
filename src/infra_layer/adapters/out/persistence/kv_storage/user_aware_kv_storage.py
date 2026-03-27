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
    ) -> None:
        self._kv_url = kv_url
        self._rpc_url = rpc_url
        self._indexer_url = indexer_url
        self._flow_address = flow_address
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
                encryption_key=bytes.fromhex(enc_key_hex),
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
        # In server mode each user has their own stream; a global scan without
        # a user context (e.g. startup data-sync) yields nothing.
        storage = _kv_user_context.get()
        if storage is None:
            return
        async for item in storage.iterate_all():
            yield item

    def close(self) -> None:
        for user_id, storage in self._cache.items():
            try:
                storage.close()
                logger.info("Closed ZeroGKVStorage for user=%s", user_id)
            except Exception as e:
                logger.error("Failed to close KV storage for user=%s: %s", user_id, e)
        self._cache.clear()


__all__ = ["UserAwareKVStorageProxy"]
