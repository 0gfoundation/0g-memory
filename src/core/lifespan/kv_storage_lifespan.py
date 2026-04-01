"""
KV-Storage Lifespan Provider

Initializes and manages KV-Storage lifecycle based on environment configuration.
Supports InMemoryKVStorage (development) and ZeroGKVStorage (production).
"""

import os
from core.observation.logger import get_logger
from core.di.decorators import component
from core.lifespan.lifespan_interface import LifespanProvider
from core.di.utils import register_primary
from infra_layer.adapters.out.persistence.kv_storage.kv_storage_interface import (
    KVStorageInterface,
)

logger = get_logger(__name__)


@component("kv_storage_lifespan", primary=True)
class KVStorageLifespan(LifespanProvider):
    """
    KV-Storage lifecycle management

    Reads KV_STORAGE_TYPE environment variable to determine implementation:
    - "inmemory": InMemoryKVStorage (default, for development/testing)
    - "redis": RedisKVStorage (for production with Redis backend)
    - "zerog": ZeroGKVStorage (for production with 0G-Storage backend)
    """

    def __init__(self):
        super().__init__(name="kv_storage_lifespan", order=5)
        self.kv_storage = None

    async def startup(self, app) -> None:
        """
        Initialize KV-Storage based on environment configuration

        Environment Variables:
            KV_STORAGE_TYPE: "inmemory", "redis", or "zerog" (default: "inmemory")

        For ZeroG Storage, also requires:
            ZEROG_READ_NODE: KV node URL for reads/writes
            ZEROG_RPC_URL: RPC endpoint URL
            ZEROG_WALLET_KEY: Wallet private key
            ZEROG_INDEXER_URL: Indexer service URL
            ZEROG_FLOW_ADDRESS: Flow contract address
            (ZEROG_STREAM_ID and ZEROG_ENCRYPTION_KEY are auto-managed in .0g_secrets)
        """
        kv_type = os.getenv("KV_STORAGE_TYPE", "inmemory").lower()

        try:
            if kv_type == "zerog":
                # Read configuration from environment variables
                kv_url = os.getenv("ZEROG_READ_NODE")
                rpc_url = os.getenv("ZEROG_RPC_URL")
                indexer_url = os.getenv("ZEROG_INDEXER_URL")
                flow_address = os.getenv("ZEROG_FLOW_ADDRESS")

                # Validate required configuration
                missing_vars = []
                if not kv_url:
                    missing_vars.append("ZEROG_READ_NODE")
                if not rpc_url:
                    missing_vars.append("ZEROG_RPC_URL")
                if not indexer_url:
                    missing_vars.append("ZEROG_INDEXER_URL")
                if not flow_address:
                    missing_vars.append("ZEROG_FLOW_ADDRESS")

                if missing_vars:
                    raise ValueError(
                        f"Missing required 0G-Storage configuration: {', '.join(missing_vars)}. "
                        f"Please set these environment variables or check .env file."
                    )

                # Server mode: multi-user, use UserAwareKVStorageProxy.
                # Local mode: single user, use ZeroGKVStorage directly (loads .0g_secrets).
                server_mode = os.getenv("SERVER_MODE", "false").lower() == "true"

                if server_mode:
                    logger.info("🚀 Initializing 0G-Storage KV-Storage (server/multi-user mode)...")
                    from infra_layer.adapters.out.persistence.kv_storage.user_aware_kv_storage import (
                        UserAwareKVStorageProxy,
                    )

                    kv_storage = UserAwareKVStorageProxy(
                        kv_url=kv_url,
                        rpc_url=rpc_url,
                        indexer_url=indexer_url,
                        flow_address=flow_address,
                    )
                    logger.info(
                        f"✅ UserAwareKVStorageProxy initialized\n"
                        f"   KV URL: {kv_url}\n"
                        f"   Indexer URL: {indexer_url}"
                    )
                else:
                    logger.info("🚀 Initializing 0G-Storage KV-Storage (local/single-user mode)...")
                    from infra_layer.adapters.out.persistence.kv_storage.zerog_kv_storage import (
                        ZeroGKVStorage,
                    )

                    # ZEROG_WALLET_KEY, ZEROG_STREAM_ID, ZEROG_ENCRYPTION_KEY
                    # are read/generated inside ZeroGKVStorage.__init__ from .0g_secrets
                    kv_storage = ZeroGKVStorage(
                        kv_url=kv_url,
                        rpc_url=rpc_url,
                        indexer_url=indexer_url,
                        flow_address=flow_address,
                    )
                    logger.info(
                        f"✅ 0G-Storage KV-Storage initialized successfully\n"
                        f"   KV URL: {kv_url}\n"
                        f"   Indexer URL: {indexer_url}"
                    )

            elif kv_type == "redis":
                logger.info("🚀 Initializing Redis KV-Storage...")

                # Import here to avoid circular dependency
                from infra_layer.adapters.out.persistence.kv_storage.redis_kv_storage import (
                    RedisKVStorage,
                )

                # RedisKVStorage uses RedisProvider from DI container
                # No additional configuration needed here
                kv_storage = RedisKVStorage()

                logger.info(
                    "✅ Redis KV-Storage initialized successfully\n"
                    "   (Using RedisProvider from DI container)"
                )

            else:
                # Default: InMemoryKVStorage
                if kv_type != "inmemory":
                    logger.warning(
                        f"⚠️  Unknown KV_STORAGE_TYPE '{kv_type}', falling back to 'inmemory'"
                    )

                logger.info("🚀 Initializing In-Memory KV-Storage...")

                from infra_layer.adapters.out.persistence.kv_storage.in_memory_kv_storage import (
                    InMemoryKVStorage,
                )

                kv_storage = InMemoryKVStorage()
                logger.info(
                    "✅ In-Memory KV-Storage initialized (data will be lost on restart)"
                )

            # Register to DI container as primary KVStorageInterface implementation
            register_primary(KVStorageInterface, kv_storage)
            self.kv_storage = kv_storage
            logger.info(
                f"✅ KV-Storage registered to DI container: {type(kv_storage).__name__}"
            )

        except Exception as e:
            logger.error(f"❌ Failed to initialize KV-Storage: {e}")
            raise

    async def shutdown(self, app) -> None:
        """Cleanup KV-Storage resources"""
        if self.kv_storage:
            logger.info(f"🔄 Shutting down KV-Storage: {type(self.kv_storage).__name__}")
            if hasattr(self.kv_storage, 'close'):
                self.kv_storage.close()


__all__ = ["KVStorageLifespan"]
