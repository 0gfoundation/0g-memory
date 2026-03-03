#!/bin/bash
# EverMemOS Service Stopper
#
# Usage:
#   ./stop_service.sh
#
# What this does:
#   1. Stops EverMemOS backend
#   2. Stops Docker services (MongoDB, Elasticsearch, Milvus, Redis)
#   3. Stops kv-server (zgs_kv)
#   4. Verifies all services are stopped and reports results

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
echo "           EverMemOS Service Stopper"
echo "============================================================"
echo ""

# ── Step 1: Stop EverMemOS backend ───────────────────────────────────────────
echo "▶  Stopping EverMemOS backend..."
echo ""
python3 claude-skills/evermemos-start/scripts/service_manager.py stop

# Fallback: service_manager relies on PID file; if it's missing but the process
# is still running (e.g. started outside of service_manager), kill it directly.
if pgrep -f "src/run.py" > /dev/null 2>&1; then
    echo "  ⚠️  Process still found via pgrep, killing directly..."
    pkill -TERM -f "src/run.py"
    sleep 2
    if pgrep -f "src/run.py" > /dev/null 2>&1; then
        pkill -KILL -f "src/run.py"
        sleep 1
    fi
    echo "  ✅ EverMemOS backend killed"
fi

# ── Step 2: Stop Docker services ─────────────────────────────────────────────
echo ""
echo "▶  Stopping Docker services..."
echo ""
echo "  🛑 Running: $COMPOSE_CMD down"
$COMPOSE_CMD down

# ── Step 3: Stop kv-server ───────────────────────────────────────────────────
echo ""
echo "▶  Stopping kv-server (zgs_kv)..."
echo ""
if pgrep -f "zgs_kv" > /dev/null 2>&1; then
    pkill -f "zgs_kv"
    echo "  ✅ kv-server stopped"
else
    echo "  ℹ️  kv-server was not running, skipping"
fi

# ── Step 4: Verify ───────────────────────────────────────────────────────────
echo ""
echo "▶  Verifying services are stopped..."
echo ""

ALL_OK=true

# Check EverMemOS backend
if pgrep -f "src/run.py" > /dev/null 2>&1; then
    echo "  ❌ EverMemOS backend: still running"
    ALL_OK=false
else
    echo "  ✅ EverMemOS backend: stopped"
fi

# Check Docker containers
RUNNING_CONTAINERS=$($COMPOSE_CMD ps -q 2>/dev/null | wc -l | tr -d ' ')
if [ "$RUNNING_CONTAINERS" -gt 0 ]; then
    echo "  ❌ Docker containers: $RUNNING_CONTAINERS still running"
    ALL_OK=false
else
    echo "  ✅ Docker containers: all stopped"
fi

# Check kv-server
if pgrep -f "zgs_kv" > /dev/null 2>&1; then
    echo "  ❌ kv-server (zgs_kv): still running"
    ALL_OK=false
else
    echo "  ✅ kv-server (zgs_kv): stopped"
fi

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo "============================================================"
if [ "$ALL_OK" = true ]; then
    echo "  ✅ All services stopped successfully."
else
    echo "  ⚠️  Some services may still be running. Check above."
fi
echo "============================================================"
echo ""
