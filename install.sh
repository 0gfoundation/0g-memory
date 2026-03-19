#!/bin/bash
# EverMemOS One-Time Installer
#
# Usage:
#   ./install.sh              # interactive (recommended for first time)
#   ./install.sh --non-interactive  # fully automated (CI / headless)
#
# What this does:
#   1. Checks Python version (3.12 required)
#   2. Checks / auto-installs uv package manager
#   3. Installs Python dependencies (uv sync)
#   4. Verifies Docker is installed, creates .env from template
#   5. Copies EverMemOS skills to ~/.claude/skills/ and merges hooks into ~/.claude/settings.json
#   6. Fetches current block height and sets log_sync_start_block_number in kv-server config
#   7. Generates .0g_secrets (stream_id + encryption_key)
#   8. Writes stream_id + encryption_key into kv-server config
#   9. Downloads zgs_kv binary and places it in 0g_kv_server/
#
# To start services after installation, run: ./start_service.sh

set -e

# ── Resolve project root (works when called from any directory) ──────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Detect OS and CPU architecture ───────────────────────────────────────────
OS=$(uname -s)    # "Linux" or "Darwin"
ARCH=$(uname -m)  # "x86_64" or "arm64"

# Portable in-place sed: BSD sed (macOS) requires an explicit backup extension
# (we pass "" for no backup), while GNU sed (Linux) does not accept that form.
sed_inplace() {
    if [ "$OS" = "Darwin" ]; then
        sed -i "" "$@"
    else
        sed -i "$@"
    fi
}

echo ""
echo "============================================================"
echo "           EverMemOS Installer"
echo "============================================================"
echo ""

# ── Check Python 3 ──────────────────────────────────────────────────────────
# Only needs to be Python 3.8+ to run this installer script.
# The actual application requires Python 3.12, which uv manages automatically
# via pyproject.toml (requires-python = ">=3.12,<3.13").
if ! command -v python3 &>/dev/null; then
    echo "❌ python3 not found. Please install Python 3.8+ and retry."
    exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "✅ Python $PYTHON_VERSION (uv will manage Python 3.12 for the application)"

# ── Step 1-5: Setup (via setup.py) ──────────────────────────────────────────
#   1. Checks Python version (3.12 required)
#   2. Checks / auto-installs uv package manager
#   3. Installs Python dependencies (uv sync)
#   4. Verifies Docker is installed, creates .env from template
#   5. Copies EverMemOS skills to ~/.claude/skills/ and merges hooks into ~/.claude/settings.json
echo ""
echo "▶  Running setup..."
echo ""
python3 scripts/setup.py "$@"

# ── Step 6: Fetch block height → log_sync_start_block_number ─────────────────
echo ""
echo "▶  Fetching current block height from 0G testnet..."
echo ""
python3 scripts/update_start_block.py --copy-example

# ── Step 7: Generate .0g_secrets (stream_id + encryption_key) ───────────────
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

# ── Step 8: Write stream_id + encryption_key into kv-server config ───────────
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

    sed_inplace "s|stream_ids = \[\"[^\"]*\"\]|stream_ids = [\"$ZEROG_STREAM_ID\"]|" "$KV_CONFIG"
    sed_inplace "s|encryption_key = \"[^\"]*\"|encryption_key = \"$ZEROG_ENCRYPTION_KEY\"|" "$KV_CONFIG"

    echo "  ✅ stream_ids and encryption_key written to $KV_CONFIG"
fi

# ── Step 9: Download zgs_kv binary ───────────────────────────────────────────
echo ""
echo "▶  Downloading zgs_kv binary..."
echo ""

ZGS_KV_DIR="$SCRIPT_DIR/0g_kv_server"
ZGS_KV_BIN="$ZGS_KV_DIR/zgs_kv"
ZGS_KV_VERSION="v1.5.1"
ZGS_KV_BASE="https://github.com/0gfoundation/0g-storage-kv/releases/download/${ZGS_KV_VERSION}"

# Select the correct binary for the current OS
if [ "$OS" = "Darwin" ]; then
    ZGS_KV_ZIP_NAME="zgs_kv_mac.zip"
else
    # Default to Linux
    ZGS_KV_ZIP_NAME="zgs_kv_linux.zip"
fi

ZGS_KV_URL="${ZGS_KV_BASE}/${ZGS_KV_ZIP_NAME}"
ZGS_KV_ZIP="/tmp/${ZGS_KV_ZIP_NAME}"

mkdir -p "$ZGS_KV_DIR"

if [ -f "$ZGS_KV_BIN" ]; then
    echo "  ✅ zgs_kv already exists at $ZGS_KV_BIN, skipping download"
else
    echo "  ℹ️  Platform: $OS/$ARCH → downloading $ZGS_KV_ZIP_NAME"

    if ! command -v curl &>/dev/null && ! command -v wget &>/dev/null; then
        echo "  ❌ Neither curl nor wget found. Please install one and retry."
        exit 1
    fi

    if command -v curl &>/dev/null; then
        curl -L -o "$ZGS_KV_ZIP" "$ZGS_KV_URL"
    else
        wget -O "$ZGS_KV_ZIP" "$ZGS_KV_URL"
    fi

    if ! command -v unzip &>/dev/null; then
        echo "  ❌ unzip not found. Please install unzip and retry."
        exit 1
    fi

    unzip -o "$ZGS_KV_ZIP" zgs_kv -d "$ZGS_KV_DIR"
    rm -f "$ZGS_KV_ZIP"
    chmod +x "$ZGS_KV_BIN"
    echo "  ✅ zgs_kv downloaded and placed at $ZGS_KV_BIN"
fi

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  ✅ Installation complete!"
echo ""
echo "  Secrets:  .0g_secrets"
echo ""
echo "  ⚠️  ACTION REQUIRED: Edit .env and fill in your private keys:"
echo "       LLM_API_KEY        — your LLM provider API key"
echo "       VECTORIZE_API_KEY  — your embedding service API key"
echo "       RERANK_API_KEY     — your rerank service API key"
echo "       ZEROG_WALLET_KEY   — your 0G-funded EVM wallet private key"
echo "     Other variables have sensible defaults but can also be changed in .env."
echo ""
echo "  Next step: start services"
echo "    bash ./start_service.sh"
echo ""
echo "  ⚠️  If Claude Code is already running, restart it so the"
echo "     newly added hooks take effect in all projects."
echo "============================================================"
echo ""
