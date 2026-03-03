#!/bin/bash
# EverMemOS Service Starter
#
# Usage:
#   ./start_service.sh
#
# What this does:
#   1. Starts kv-server (zgs_kv) and Docker services in parallel
#   2. Waits for both to be ready
#   3. Starts EverMemOS backend
#
# Prerequisites: run ./install.sh first

set -e

# ── Resolve project root (works when called from any directory) ──────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Detect docker compose command ────────────────────────────────────────────
if command -v docker-compose &>/dev/null; then
    COMPOSE_CMD="docker-compose"
else
    COMPOSE_CMD="docker compose"
fi

echo ""
echo "============================================================"
echo "           EverMemOS Service Starter"
echo "============================================================"
echo ""

# ── Step 1a: Start kv-server in background ───────────────────────────────────
echo "▶  Checking kv-server (zgs_kv)..."
echo ""

KV_BIN="$SCRIPT_DIR/0g_kv_server/zgs_kv"
KV_RUN_DIR="$SCRIPT_DIR/0g_kv_server"
KV_LOG="$KV_RUN_DIR/kv.log"
KV_STARTED=false

if pgrep -f "zgs_kv" > /dev/null 2>&1; then
    echo "  ✅ kv-server already running, skipping"
elif [ ! -f "$KV_BIN" ]; then
    echo "  ⚠️  kv-server binary not found at $KV_BIN, skipping"
else
    echo "  🚀 Starting kv-server in background..."
    cd "$KV_RUN_DIR"
    nohup "$KV_BIN" --config config_testnet_turbo.toml >> kv.log 2>&1 &
    KV_PID=$!
    cd "$SCRIPT_DIR"
    echo "  ✅ kv-server started (PID: $KV_PID), logs: $KV_LOG"
    KV_STARTED=true
fi

# ── Step 1b: Start Docker services in background ─────────────────────────────
echo ""
echo "▶  Starting Docker services..."
echo ""

echo "  🚀 Running: $COMPOSE_CMD up -d"
$COMPOSE_CMD up -d
echo "  ✅ Docker containers started"

# ── Step 2a: Wait for kv-server ready ────────────────────────────────────────
if [ "$KV_STARTED" = true ]; then
    echo ""
    echo "  ⏳ Waiting for kv-server to sync blockchain data..."
    TIMEOUT=300  # 5 minutes max
    ELAPSED=0

    while [ $ELAPSED -lt $TIMEOUT ]; do
        if grep -q "log sync to block number" "$KV_LOG" 2>/dev/null; then
            echo "  ✅ kv-server synced and ready"
            break
        fi
        sleep 3
        ELAPSED=$((ELAPSED + 3))
    done

    if [ $ELAPSED -ge $TIMEOUT ]; then
        echo "  ⚠️  kv-server did not confirm ready within ${TIMEOUT}s, proceeding anyway"
        echo "     Check logs: $KV_LOG"
    fi
fi

# ── Step 2b: Wait for Docker services ready (MongoDB 27017 + Elasticsearch 9200) ─
echo ""
echo "  ⏳ Waiting for Docker services to be ready..."
TIMEOUT=180  # 3 minutes max (ES cold-start after volume wipe can be slow)
ELAPSED=0

while [ $ELAPSED -lt $TIMEOUT ]; do
    MONGO_OK=false
    ES_OK=false

    (echo > /dev/tcp/localhost/27017) 2>/dev/null && MONGO_OK=true
    (echo > /dev/tcp/localhost/19200) 2>/dev/null && ES_OK=true

    if [ "$MONGO_OK" = true ] && [ "$ES_OK" = true ]; then
        echo "  ✅ MongoDB ready (port 27017)"
        echo "  ✅ Elasticsearch ready (port 19200)"
        break
    fi

    [ "$MONGO_OK" = false ] && echo "  ⏳ Waiting for MongoDB (27017)..."    || true
    [ "$ES_OK"    = false ] && echo "  ⏳ Waiting for Elasticsearch (19200)..." || true

    sleep 3
    ELAPSED=$((ELAPSED + 3))
done

if [ $ELAPSED -ge $TIMEOUT ]; then
    echo "  ⚠️  Docker services did not become ready within ${TIMEOUT}s, proceeding anyway"
    echo "     Run: $COMPOSE_CMD ps"
fi

# ── Step 3: Start EverMemOS backend ──────────────────────────────────────────
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
