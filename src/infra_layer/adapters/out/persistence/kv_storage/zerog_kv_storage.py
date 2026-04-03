"""
0G-Storage based KV-Storage implementation

Uses 0g-storage Python SDK (CachedKvClient) for storage operations.
All values are UTF-8 encoded as bytes.

Key Format: {collection_name}:{document_id}
Example: "episodic_memories:6979da5797f9041fc0aa063f"

Environment Variables Required:
- ZEROG_WALLET_KEY: Wallet private key (IMPORTANT: Keep secure!)

Auto-generated Secrets (.0g_secrets in project root):
- ZEROG_STREAM_ID: Unified stream ID, generated once on first startup
- ZEROG_ENCRYPTION_KEY: AES-256 encryption key, generated once on first startup

Concurrency Model:
- Single CachedKvClient shared across all coroutines/threads.
- SDK methods set(), get_bytes(), and commit() are all thread-safe.
- A dedicated background daemon thread (_commit_thread) wakes up every
  COMMIT_INTERVAL seconds. If _pending_count > 0, it calls cached.commit()
  (non-blocking: actual upload happens inside the SDK) and resets the counter;
  otherwise it skips the interval entirely.
- _pending_count is an _AtomicInt; increment() and get_and_reset() are each
  individually atomic, so there is no race between the writer and commit thread.
"""

import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Tuple, AsyncIterator

from core.observation.logger import get_logger
from core.di.decorators import component
from .kv_storage_interface import KVStorageInterface

from zg_storage import CachedKvClient, EvmClient, UploadOption

logger = get_logger(__name__)

COMMIT_INTERVAL = 20  # seconds between commit attempts
MAX_COMMIT_FAILURES = 3  # consecutive failures before attempting client reset

_SECRETS_FILE = ".0g_secrets"


def _load_or_generate_secrets() -> tuple[str, bytes]:
    """
    Load ZEROG_STREAM_ID and ZEROG_ENCRYPTION_KEY from .0g_secrets.
    Raises ValueError if the file or either key is missing — run install.sh first.
    Returns (stream_id: str, encryption_key: bytes).
    """
    secrets_path = Path.cwd() / _SECRETS_FILE

    if not secrets_path.exists():
        raise ValueError(
            f".0g_secrets not found at {secrets_path}. "
            f"Please run install.sh to generate it."
        )

    secrets: dict[str, str] = {}
    for line in secrets_path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line and '=' in line and not line.startswith('#'):
            k, v = line.split('=', 1)
            secrets[k.strip()] = v.strip()

    missing = [k for k in ('ZEROG_STREAM_ID', 'ZEROG_ENCRYPTION_KEY') if k not in secrets]
    if missing:
        raise ValueError(
            f"Missing keys in .0g_secrets: {', '.join(missing)}. "
            f"Please run install.sh to regenerate it."
        )

    stream_id = secrets['ZEROG_STREAM_ID']
    encryption_key = bytes.fromhex(secrets['ZEROG_ENCRYPTION_KEY'])
    return stream_id, encryption_key


class _AtomicInt:
    """Minimal thread-safe integer counter.

    increment() and get_and_reset() are each atomic operations.
    """

    __slots__ = ("_value", "_lock")

    def __init__(self) -> None:
        self._value: int = 0
        self._lock = threading.Lock()

    def increment(self) -> None:
        with self._lock:
            self._value += 1

    def get_and_reset(self) -> int:
        """Return current value and atomically reset to 0."""
        with self._lock:
            value, self._value = self._value, 0
            return value

    def __bool__(self) -> bool:
        return bool(self._value)


@component("zerog_kv_storage")
class ZeroGKVStorage(KVStorageInterface):
    """
    0G-Storage based KV-Storage implementation using CachedKvClient.

    put/delete: call cached.set() to stage the op (fast, in-memory).
    commit: a dedicated background thread wakes every COMMIT_INTERVAL seconds
            and calls cached.commit() only if there are pending staged ops.
    get: cached.get_bytes() reads from local cache or the KV node.
    """

    def __init__(
        self,
        kv_url: str,                    # KV node URL for reads/writes
        rpc_url: str,                   # "https://evmrpc-testnet.0g.ai"
        indexer_url: str,               # Indexer URL for uploads
        flow_address: str,              # Flow contract address
        max_queue_size: int = 100,      # Internal write queue size
        max_cache_entries: int = 10000, # Local read cache size
    ):
        # Load or generate stream_id and encryption_key from .0g_secrets
        stream_id, encryption_key = _load_or_generate_secrets()
        self.stream_id = stream_id

        wallet_private_key = os.getenv('ZEROG_WALLET_KEY')
        if not wallet_private_key:
            raise ValueError("ZEROG_WALLET_KEY environment variable is required")

        # Save params needed to recreate the client after failure
        self._kv_url = kv_url
        self._rpc_url = rpc_url
        self._indexer_url = indexer_url
        self._flow_address = flow_address
        self._max_queue_size = max_queue_size
        self._max_cache_entries = max_cache_entries
        self._wallet_private_key = wallet_private_key
        self._encryption_key = encryption_key

        evm = EvmClient(
            rpc_url=rpc_url,
            private_key=wallet_private_key,
        )

        self._cached = CachedKvClient(
            kv_url=kv_url,
            indexer_url=indexer_url,
            evm_client=evm,
            flow_address=flow_address,
            max_queue_size=max_queue_size,
            max_cache_entries=max_cache_entries,
            upload_option=UploadOption(skip_tx=False),
            encryption_key=encryption_key,
        )

        # Protects _cached during client recreation
        self._client_lock = threading.RLock()

        # Atomic counter: ops staged since the last commit.
        self._pending_count = _AtomicInt()

        # Background commit thread
        self._stop_event = threading.Event()
        self._commit_thread = threading.Thread(
            target=self._commit_loop,
            name="zerog_commit",
            daemon=True,
        )
        self._commit_thread.start()

        # Per-instance operation log file under /tmp
        dt_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._op_log_path = f"/tmp/log_EverMemOS_ZeroGKVStorage_{dt_str}.txt"
        self._op_log_lock = threading.Lock()
        self._op_log_file = open(self._op_log_path, 'w', encoding='utf-8')
        self._op_log_file.write(
            f"[{datetime.now().isoformat()}] ZeroGKVStorage initialized:"
            f" stream_id={stream_id}, kv_url={kv_url}\n"
        )
        self._op_log_file.flush()

        logger.info(
            f"✅ ZeroGKVStorage initialized: stream_id={stream_id}, "
            f"kv_url={kv_url}, indexer_url={indexer_url}, "
            f"commit_interval={COMMIT_INTERVAL}s"
        )
        logger.info(f"📄 ZeroGKVStorage op log: {self._op_log_path}")

    # -------------------------------------------------------------------------
    # Internal: time-based commit loop
    # -------------------------------------------------------------------------

    def _commit_loop(self) -> None:
        """
        Dedicated background thread.
        Wakes up every COMMIT_INTERVAL seconds.
        If _pending_count > 0, calls cached.commit() (non-blocking) and resets
        the counter. If _pending_count == 0, skips the interval silently.

        After MAX_COMMIT_FAILURES consecutive failures, reset() is called to
        clear the failed state while preserving the local cache.  This allows
        recovery from transient network errors (e.g. SSL failures) without
        losing cache data, which would cause KV misses on subsequent reads.
        """
        consecutive_failures = 0
        while not self._stop_event.wait(COMMIT_INTERVAL):
            pending = self._pending_count.get_and_reset()
            if not pending:
                # No writes to flush — do not reset consecutive_failures here.
                # A gap with no pending ops should not mask an ongoing failure streak.
                continue

            try:
                with self._client_lock:
                    self._cached.commit()
                consecutive_failures = 0
                logger.info(f"✅ Commit triggered ({pending} pending ops)")
                self._write_op_log(f"commit triggered ({pending} pending ops)")
            except Exception as e:
                consecutive_failures += 1
                logger.error(
                    f"❌ Commit failed ({consecutive_failures}/{MAX_COMMIT_FAILURES}): {e}",
                    exc_info=True,
                )
                if consecutive_failures >= MAX_COMMIT_FAILURES:
                    try:
                        with self._client_lock:
                            self._cached.reset()
                        logger.warning(
                            f"⚠️ CachedKvClient reset after {consecutive_failures} consecutive "
                            f"failures — local cache preserved, will retry on next interval"
                        )
                        self._write_op_log(f"client reset after {consecutive_failures} failures")
                    except Exception as reset_err:
                        logger.error(f"❌ Failed to reset CachedKvClient: {reset_err}", exc_info=True)
                    consecutive_failures = 0

    # -------------------------------------------------------------------------
    # Internal: write a line to the per-instance operation log file
    # -------------------------------------------------------------------------

    def _write_op_log(self, msg: str) -> None:
        with self._op_log_lock:
            try:
                self._op_log_file.write(f"[{datetime.now().isoformat()}] {msg}\n")
                self._op_log_file.flush()
            except Exception:
                pass

    # -------------------------------------------------------------------------
    # Internal: stage a set/delete operation
    # -------------------------------------------------------------------------

    def _stage_operation(self, key: str, value_bytes: bytes) -> bool:
        """
        Call cached.set() then increment _pending_count.
        The commit thread will flush to the chain on the next interval.
        """
        key_bytes = key.encode('utf-8')
        with self._client_lock:
            self._cached.set(self.stream_id, key_bytes, value_bytes)
        self._pending_count.increment()
        return True

    # -------------------------------------------------------------------------
    # KVStorageInterface implementation
    # -------------------------------------------------------------------------

    async def get(self, key: str) -> Optional[str]:
        logger.info(f"get key={key}")
        self._write_op_log(f"get key={key}")
        try:
            key_bytes = key.encode('utf-8')
            with self._client_lock:
                value_bytes = self._cached.get_bytes(self.stream_id, key_bytes)
            if not value_bytes:
                self._write_op_log(f"get value=None")
                return None
            value = value_bytes.decode('utf-8')
            self._write_op_log(f"get value={value}")
            return value
        except Exception as e:
            logger.error(f"❌ Failed to get key {key}: {e}")
            return None

    async def put(self, key: str, value: str) -> bool:
        """Stage a put operation. Commit happens in the background thread."""
        logger.info(f"put key={key}")
        self._write_op_log(f"put key={key}")
        self._write_op_log(f"put value={value}")
        try:
            return self._stage_operation(key, value.encode('utf-8'))
        except Exception as e:
            logger.error(f"❌ Failed to put key {key}: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Stage a delete operation (empty bytes). Commit happens in the background thread."""
        logger.info(f"delete key={key}")
        self._write_op_log(f"delete key={key}")
        try:
            return self._stage_operation(key, b'')
        except Exception as e:
            logger.error(f"❌ Failed to delete key {key}: {e}")
            return False

    async def batch_get(self, keys: List[str]) -> Dict[str, str]:
        logger.info(f"batch_get keys={keys}")
        self._write_op_log(f"batch_get keys={keys}")
        if not keys:
            return {}

        result = {}
        try:
            for key in keys:
                key_bytes = key.encode('utf-8')
                with self._client_lock:
                    value_bytes = self._cached.get_bytes(self.stream_id, key_bytes)
                if value_bytes:
                    result[key] = value_bytes.decode('utf-8')

            logger.info(f"✅ Batch get {len(result)}/{len(keys)} keys")
            return result

        except Exception as e:
            logger.error(f"❌ Failed to batch get {len(keys)} keys: {e}")
            return {}

    async def batch_delete(self, keys: List[str]) -> int:
        """Stage delete for each key. Commit happens in the background thread."""
        logger.info(f"batch_delete keys={keys}")
        self._write_op_log(f"batch_delete keys={keys}")
        if not keys:
            return 0

        deleted = 0
        for key in keys:
            try:
                if self._stage_operation(key, b''):
                    deleted += 1
            except Exception as e:
                logger.error(f"❌ Failed to stage delete for key {key}: {e}")

        return deleted

    async def iterate_all(self) -> AsyncIterator[Tuple[str, str]]:
        """
        Iterate all key-value pairs using CachedKvClient's iterator.
        Empty/deleted entries (empty bytes) are skipped.
        """
        logger.info("iterate_all")
        try:
            iterator = self._cached._kv_client.new_iterator(self.stream_id)
            iterator.seek_to_first()

            total_count = 0
            skipped_count = 0

            while iterator.valid():
                key_bytes = iterator.key
                data_bytes = iterator.data

                key = key_bytes.decode('utf-8')

                if data_bytes and len(data_bytes) > 0:
                    value = data_bytes.decode('utf-8')
                    total_count += 1
                    yield (key, value)
                else:
                    skipped_count += 1

                iterator.next()

                if (total_count + skipped_count) % 1000 == 0 and (total_count + skipped_count) > 0:
                    logger.info(
                        f"📊 ZeroG iterate progress: {total_count} yielded, "
                        f"{skipped_count} skipped (empty/deleted)"
                    )

            logger.info(
                f"✅ ZeroG iterate_all completed: {total_count} yielded, "
                f"{skipped_count} skipped"
            )

        except Exception as e:
            logger.error(f"❌ ZeroG iterate_all failed: {e}", exc_info=True)
            raise

    def close(self) -> None:
        """
        Stop the commit thread, flush any remaining pending ops, then
        release CachedKvClient resources.
        """
        self._stop_event.set()
        self._commit_thread.join(timeout=5)

        # CachedKvClient.close() will itself commit any remaining pending writes
        # and wait for all queued uploads to finish before shutting down the worker.
        try:
            with self._client_lock:
                self._cached.close()
            logger.info("✅ ZeroGKVStorage closed")
        except Exception as e:
            logger.error(f"❌ Failed to close CachedKvClient: {e}")

        with self._op_log_lock:
            try:
                self._op_log_file.write(
                    f"[{datetime.now().isoformat()}] ZeroGKVStorage closed\n"
                )
                self._op_log_file.close()
            except Exception:
                pass


__all__ = ["ZeroGKVStorage"]
