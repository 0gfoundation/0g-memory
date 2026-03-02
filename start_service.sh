#!/bin/bash
# EverMemOS Service Starter
#
# Usage:
#   ./start_service.sh
#
# What this does:
#   1. Starts kv-server (zgs_kv) if not already running
#   2. Starts EverMemOS backend if not already running
#
# Prerequisites: run ./install.sh first

set -e

# ── Resolve project root (works when called from any directory) ──────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "============================================================"
echo "           EverMemOS Service Starter"
echo "============================================================"
echo ""

# ── Step 1: Start kv-server if not already running ───────────────────────────
echo "▶  Checking kv-server (zgs_kv)..."
echo ""

KV_BIN="$SCRIPT_DIR/0g_kv_server/zgs_kv"
KV_RUN_DIR="$SCRIPT_DIR/0g_kv_server"

if pgrep -f "zgs_kv" > /dev/null 2>&1; then
    echo "  ✅ kv-server already running, skipping"
elif [ ! -f "$KV_BIN" ]; then
    echo "  ⚠️  kv-server binary not found at $KV_BIN, skipping"
else
    echo "  🚀 Starting kv-server in background..."
    cd "$KV_RUN_DIR"
    nohup "$KV_BIN" --config config_testnet_turbo.toml > kv.log 2>&1 &
    KV_PID=$!
    cd "$SCRIPT_DIR"
    echo "  ✅ kv-server started (PID: $KV_PID), logs: $KV_RUN_DIR/kv.log"
    sleep 2
fi

# ── Step 2: Start EverMemOS backend ──────────────────────────────────────────
echo ""
echo "▶  Starting EverMemOS backend..."
echo ""
python3 claude-skills/evermemos-start/scripts/service_manager.py start

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  ✅ EverMemOS is ready!"
echo ""
echo "  API:      http://localhost:1995"
echo "  Logs:     data/evermemos.log"
echo "  KV logs:  0g_kv_server/kv.log"
echo "============================================================"
echo ""
