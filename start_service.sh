#!/bin/bash
# EverMemOS Service Starter
#
# Usage:
#   ./start_service.sh            # first-time start after install (fresh stream ID)
#   ./start_service.sh --restart  # subsequent starts (existing stream ID, must re-sync chain)
#
# What this does:
#   1. Starts kv-server (zgs_kv) and Docker services in parallel
#   2. Waits for both to be ready
#   3. Starts EverMemOS backend
#
# Prerequisites: run ./install.sh first

set -e

# ── Parse arguments ───────────────────────────────────────────────────────────
RESTART=false
for arg in "$@"; do
    [ "$arg" = "--restart" ] && RESTART=true
done

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

# ── Validate .env configuration ──────────────────────────────────────────────
ENV_FILE="$SCRIPT_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo "❌ .env file not found. Please create it from env.template.0g.example:"
    echo "   cp env.template.0g.example .env"
    echo "   Then edit .env and fill in your actual values."
    exit 1
fi

WALLET_KEY=$(grep '^ZEROG_WALLET_KEY=' "$ENV_FILE" | cut -d'=' -f2 | tr -d ' \r')
if [ -z "$WALLET_KEY" ] || ! echo "$WALLET_KEY" | grep -qE '^[0-9a-fA-F]{64}$'; then
    echo "❌ ZEROG_WALLET_KEY in .env is missing or invalid."
    echo "   Expected: 64-character hexadecimal string (without 0x prefix)."
    echo "   Please set your EVM wallet private key."
    echo "   See Appendix C in README.md for step-by-step instructions."
    exit 1
fi

# ── Step 1a: Start kv-server in background ───────────────────────────────────
echo "▶  Checking kv-server (zgs_kv)..."
echo ""

KV_BIN="$SCRIPT_DIR/0g_kv_server/zgs_kv"
KV_RUN_DIR="$SCRIPT_DIR/0g_kv_server"
KV_TS=$(date -u +"%Y%m%d_%H%M%S")
KV_LOG="$KV_RUN_DIR/kv_${KV_TS}.log"
KV_STARTED=false

if pgrep -f "zgs_kv" > /dev/null 2>&1; then
    echo "  ✅ kv-server already running, skipping"
elif [ ! -f "$KV_BIN" ]; then
    echo "  ⚠️  kv-server binary not found at $KV_BIN, skipping"
else
    echo "  🚀 Starting kv-server in background..."
    cd "$KV_RUN_DIR"
    nohup "$KV_BIN" --config config_testnet_turbo.toml >> "kv_${KV_TS}.log" 2>&1 &
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
    if [ "$RESTART" = false ]; then
        # First-time start: fresh stream ID, nothing to sync from chain.
        # Just confirm the process is alive.
        sleep 2
        if pgrep -f "zgs_kv" > /dev/null 2>&1; then
            echo "  ✅ kv-server running (fresh stream, no chain sync needed)"
        else
            echo "  ⚠️  kv-server process not found after start, check logs: $KV_LOG"
        fi
    else
        # Restart with existing stream ID: kv-server must re-sync data from chain.
        # Monitor only NEW log lines (skip pre-existing content).
        # Success = same sequence number appears 10 consecutive times and is not 0.
        # Pattern: "stream_replayer.*checking tx with sequence number <id>.."
        # No timeout — a large stream can take a long time to re-sync; wait as long as needed.
        echo "  ⏳ Waiting for kv-server to re-sync blockchain data (--restart mode)..."
        echo "     (success = same sequence number stable for 10 consecutive log lines)"
        echo "     Press Ctrl+C to abort."

        LOG_POS=$(wc -l < "$KV_LOG" 2>/dev/null || echo 0)
        LAST_ID=""
        CONSEC_COUNT=0
        SYNC_OK=false

        while true; do
            CURRENT_LINES=$(wc -l < "$KV_LOG" 2>/dev/null || echo 0)

            if [ "$CURRENT_LINES" -gt "$LOG_POS" ]; then
                while IFS= read -r line; do
                    if echo "$line" | grep -qE "stream_replayer.*checking tx with sequence number [0-9]+\.\."; then
                        ID=$(echo "$line" | grep -oE "sequence number [0-9]+" | grep -oE "[0-9]+$")
                        if [ "$ID" = "$LAST_ID" ]; then
                            CONSEC_COUNT=$((CONSEC_COUNT + 1))
                        else
                            LAST_ID="$ID"
                            CONSEC_COUNT=1
                        fi
                        if [ "$CONSEC_COUNT" -ge 10 ] && [ "$ID" != "0" ]; then
                            SYNC_OK=true
                            break
                        fi
                    fi
                done < <(sed -n "$((LOG_POS + 1)),${CURRENT_LINES}p" "$KV_LOG" 2>/dev/null)
                LOG_POS=$CURRENT_LINES
            fi

            [ "$SYNC_OK" = true ] && break
            sleep 3
        done

        echo "  ✅ kv-server re-synced (sequence number $LAST_ID stable)"
    fi
fi

# ── Step 2b: Wait for Docker services ready (MongoDB 27017 + Elasticsearch 19200) ─
echo ""
echo "  ⏳ Waiting for Docker services to be ready..."
TIMEOUT=300  # 5 minutes max (ES cold-start after volume wipe can be slow; macOS Docker VM adds latency)
ELAPSED=0

while [ $ELAPSED -lt $TIMEOUT ]; do
    MONGO_OK=false
    ES_OK=false

    nc -z localhost 27017 2>/dev/null && MONGO_OK=true || true
    # Use ES cluster health API instead of TCP check: port open ≠ ES ready.
    # wait_for_status=yellow ensures all primary shards are allocated before returning.
    # Must check "timed_out":false in the response body — ES always returns HTTP 200
    # even on timeout, so curl exit code alone is not sufficient.
    # || true on each line prevents set -e from killing the script when services aren't ready yet.
    ES_RESP=$(curl -sf "http://localhost:19200/_cluster/health?wait_for_status=yellow&timeout=3s" 2>/dev/null) || true
    echo "$ES_RESP" | grep -q '"timed_out":false' && ES_OK=true || true

    if [ "$MONGO_OK" = true ] && [ "$ES_OK" = true ]; then
        echo "  ✅ MongoDB ready (port 27017)"
        echo "  ✅ Elasticsearch ready (cluster health: yellow)"
        break
    fi

    [ "$MONGO_OK" = false ] && echo "  ⏳ Waiting for MongoDB (27017)..."           || true
    [ "$ES_OK"    = false ] && echo "  ⏳ Waiting for Elasticsearch (cluster health)..." || true

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
python3 scripts/service_manager.py start

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  ✅ EverMemOS is ready!"
echo ""
echo "  API:      http://localhost:1995"
echo "  Logs:     logs/evermemos_<timestamp>.log"
[ "$KV_STARTED" = true ] && echo "  KV logs:  0g_kv_server/kv_${KV_TS}.log"
echo "============================================================"
echo ""
