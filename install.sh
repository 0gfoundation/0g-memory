#!/bin/bash
# EverMemOS One-Time Installer
#
# Usage:
#   ./install.sh              # interactive (recommended for first time)
#   ./install.sh --non-interactive  # fully automated (CI / headless)
#
# What this does:
#   1. Installs uv + Python dependencies
#   2. Starts Docker services (MongoDB, Elasticsearch, Milvus, Redis)
#   3. Copies EverMemOS skills to ~/.claude/skills/
#   4. Merges hooks into ~/.claude/settings.json (global, all projects)
#   5. Installs 0G Storage SDK into uv venv
#   6. Generates .0g_secrets (stream_id + encryption_key)
#   7. Writes stream_id + encryption_key into kv-server config
#
# To start services after installation, run: ./start_service.sh

set -e

# ── Resolve project root (works when called from any directory) ──────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "============================================================"
echo "           EverMemOS Installer"
echo "============================================================"
echo ""

# ── Check Python 3 ──────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "❌ python3 not found. Please install Python 3.8+ and retry."
    exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "✅ Python $PYTHON_VERSION"

# ── Step 1-6: Setup (deps, Docker, skills, global hooks) ────────────────────
echo ""
echo "▶  Running setup..."
echo ""
python3 claude-skills/evermemos-setup/scripts/setup.py "$@"

# ── Step 7: Install 0G Storage SDK into uv venv ──────────────────────────────
echo ""
echo "▶  Installing 0G Storage SDK..."
echo ""

ZG_SDK_DIR="$SCRIPT_DIR/../0g-storage-sdk-python"

if [ ! -d "$ZG_SDK_DIR" ]; then
    echo "  ⚠️  0G Storage SDK not found at $ZG_SDK_DIR, skipping"
    echo "     Clone it first: git clone https://github.com/0glabs/0g-storage-sdk-python ../0g-storage-sdk-python"
else
    uv pip install -e "$ZG_SDK_DIR"
    echo "  ✅ 0G Storage SDK installed"
fi

# ── Step 8: Generate .0g_secrets (stream_id + encryption_key) ───────────────
echo ""
echo "▶  Generating 0G secrets (.0g_secrets)..."
echo ""
python3 - <<'EOF'
import os
from pathlib import Path

secrets_path = Path(".0g_secrets")
existing = {}
if secrets_path.exists():
    for line in secrets_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            existing[k.strip()] = v.strip()

changed = False
if "ZEROG_STREAM_ID" not in existing:
    existing["ZEROG_STREAM_ID"] = os.urandom(32).hex()
    changed = True
    print("  🔑 Generated ZEROG_STREAM_ID")
else:
    print("  ✅ ZEROG_STREAM_ID already exists, keeping")

if "ZEROG_ENCRYPTION_KEY" not in existing:
    existing["ZEROG_ENCRYPTION_KEY"] = os.urandom(32).hex()
    changed = True
    print("  🔑 Generated ZEROG_ENCRYPTION_KEY")
else:
    print("  ✅ ZEROG_ENCRYPTION_KEY already exists, keeping")

if changed:
    secrets_path.write_text(
        "\n".join(f"{k}={v}" for k, v in existing.items()) + "\n",
        encoding="utf-8",
    )
    print("  💾 Saved to .0g_secrets")
EOF

# ── Step 9: Write stream_id + encryption_key into kv-server config ───────────
echo ""
echo "▶  Updating kv-server config (config_testnet_turbo.toml)..."
echo ""

KV_CONFIG="$SCRIPT_DIR/0g_kv_server/config_testnet_turbo.toml"
KV_CONFIG_EXAMPLE="$SCRIPT_DIR/0g_kv_server/config_testnet_turbo.toml.example"

if [ ! -f "$KV_CONFIG" ]; then
    if [ ! -f "$KV_CONFIG_EXAMPLE" ]; then
        echo "  ⚠️  Neither config nor example found at $SCRIPT_DIR/0g_kv_server/, skipping"
    else
        cp "$KV_CONFIG_EXAMPLE" "$KV_CONFIG"
        echo "  📋 Copied config_testnet_turbo.toml.example → config_testnet_turbo.toml"
    fi
fi

if [ -f "$KV_CONFIG" ]; then
    ZEROG_STREAM_ID=$(grep '^ZEROG_STREAM_ID=' .0g_secrets | cut -d'=' -f2)
    ZEROG_ENCRYPTION_KEY=$(grep '^ZEROG_ENCRYPTION_KEY=' .0g_secrets | cut -d'=' -f2)

    sed -i "s|stream_ids = \[\"[^\"]*\"\]|stream_ids = [\"$ZEROG_STREAM_ID\"]|" "$KV_CONFIG"
    sed -i "s|encryption_key = \"[^\"]*\"|encryption_key = \"$ZEROG_ENCRYPTION_KEY\"|" "$KV_CONFIG"

    echo "  ✅ stream_ids and encryption_key written to $KV_CONFIG"
fi

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  ✅ Installation complete!"
echo ""
echo "  Secrets:  .0g_secrets"
echo ""
echo "  ⚠️  ACTION REQUIRED before starting services:"
echo "     Edit 0g_kv_server/config_testnet_turbo.toml"
echo "     Replace YOUR_API_KEY_HERE with your actual blockchain RPC API key:"
echo "       blockchain_rpc_endpoint = \"https://evmrpc-testnet.0g.ai/<YOUR_API_KEY>\""
echo ""
echo "  Next step: start services"
echo "    bash ./start_service.sh"
echo ""
echo "  ⚠️  If Claude Code is already running, restart it so the"
echo "     newly added hooks take effect in all projects."
echo "============================================================"
echo ""
