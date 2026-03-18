"""
Update log_sync_start_block_number in config_testnet_turbo.toml to the current
block height fetched from the 0G testnet RPC.

Usage:
    python3 scripts/update_start_block.py

Must be run from the project root directory.
"""

import json
import re
import shutil
import sys
import urllib.request
from pathlib import Path

RPC_URL = "https://evmrpc-testnet.0g.ai"
KV_CONFIG = Path("0g_kv_server/config_testnet_turbo.toml")
KV_CONFIG_EXAMPLE = Path("0g_kv_server/config_testnet_turbo.toml.example")


def fetch_block_height() -> int:
    data = json.dumps(
        {"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1}
    ).encode()
    req = urllib.request.Request(
        RPC_URL, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read())
    return int(result["result"], 16)


def update_start_block(copy_from_example: bool = False) -> None:
    """Fetch the current block height and write it to config_testnet_turbo.toml.

    Args:
        copy_from_example: If True, copy the .example file to create the config
                           when it does not yet exist (used by install.sh).
                           If False, skip silently when config is missing
                           (used by start_service.sh).
    """
    if not KV_CONFIG.exists():
        if copy_from_example and KV_CONFIG_EXAMPLE.exists():
            shutil.copy(KV_CONFIG_EXAMPLE, KV_CONFIG)
            print("  📋 Copied config_testnet_turbo.toml.example → config_testnet_turbo.toml")
        else:
            print("  ⚠️  config_testnet_turbo.toml not found, skipping")
            return

    try:
        block_height = fetch_block_height()
        print(f"  📦 Current block height: {block_height}")

        content = KV_CONFIG.read_text(encoding="utf-8")
        content = re.sub(
            r"^(log_sync_start_block_number\s*=\s*)\S+",
            lambda m: m.group(1) + str(block_height),
            content,
            flags=re.MULTILINE,
        )
        KV_CONFIG.write_text(content, encoding="utf-8")
        print(f"  ✅ log_sync_start_block_number set to {block_height}")
    except Exception as e:
        print(f"  ⚠️  Could not fetch block height: {e}")
        print("  ℹ️  log_sync_start_block_number not updated")


if __name__ == "__main__":
    copy = "--copy-example" in sys.argv
    update_start_block(copy_from_example=copy)
