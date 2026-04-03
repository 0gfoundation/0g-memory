"""
KV node config updater — append a new stream_id to config_testnet_turbo.toml.

Called on user registration (SERVER_MODE=true) so that the next KV node restart
(via stop_service.sh + start_service.sh) will pick up and sync the new stream.

The config file lives at:  <project_root>/0g_kv_server/config_testnet_turbo.toml

stream_ids format in the TOML file:
    stream_ids = ["id1"]
    stream_ids = ["id1", "id2", "id3"]
"""

import os
import re
import threading
from pathlib import Path

from core.observation.logger import get_logger

logger = get_logger(__name__)

# File-level lock: concurrent registrations are rare but possible.
_config_lock = threading.Lock()

# Path can be overridden via env var; default is relative to this file's project root.
_DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[6] / "0g_kv_server" / "config_testnet_turbo.toml"
)


def add_stream_id_to_kv_config(stream_id: str) -> bool:
    """
    Append stream_id to the stream_ids list in config_testnet_turbo.toml.

    No-op if:
    - SERVER_MODE is not true (Scenario A — single stream already in config)
    - Config file does not exist
    - stream_id is already present

    Returns True if the file was modified, False otherwise.
    """
    if os.getenv("SERVER_MODE", "false").lower() != "true":
        return False

    config_path = Path(os.getenv("KV_CONFIG_PATH", str(_DEFAULT_CONFIG_PATH)))

    if not config_path.exists():
        logger.warning(
            "KV node config not found at %s, skipping stream_id registration", config_path
        )
        return False

    with _config_lock:
        text = config_path.read_text(encoding="utf-8")

        # Find the stream_ids line: stream_ids = ["id1", "id2", ...]
        match = re.search(r'^(stream_ids\s*=\s*\[)([^\]]*?)(\])', text, re.MULTILINE)
        if not match:
            logger.warning("stream_ids line not found in %s", config_path)
            return False

        prefix, ids_str, suffix = match.group(1), match.group(2), match.group(3)

        # Parse existing ids
        existing_ids = [s.strip().strip('"') for s in ids_str.split(",") if s.strip().strip('"')]

        if stream_id in existing_ids:
            logger.debug("stream_id %s already in KV config, skipping", stream_id)
            return False

        existing_ids.append(stream_id)
        new_ids_str = ", ".join(f'"{sid}"' for sid in existing_ids)
        new_line = f"{prefix}{new_ids_str}{suffix}"
        new_text = text[: match.start()] + new_line + text[match.end() :]

        # Write atomically via temp file
        tmp_path = config_path.with_suffix(".toml.tmp")
        tmp_path.write_text(new_text, encoding="utf-8")
        tmp_path.replace(config_path)

        logger.info(
            "Added stream_id %s to KV config (%s). "
            "Will be active after next KV node restart.",
            stream_id,
            config_path,
        )
        return True


__all__ = ["add_stream_id_to_kv_config"]
