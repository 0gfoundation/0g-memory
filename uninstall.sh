#!/bin/bash
# EverMemOS Uninstaller
#
# Usage:
#   ./uninstall.sh
#
# What this does (reverse order of install.sh):
#   0. Stops EverMemOS backend and kv-server (if running)
#   0b. Removes Docker containers AND volumes (docker-compose down -v)
#   8. Deletes 0g_kv_server/config_testnet_turbo.toml
#   7. Deletes .0g_secrets
#   6b. Removes EverMemOS hooks and env vars from ~/.claude/settings.json
#   6a. Removes EverMemOS skills from ~/.claude/skills/
#   5b. Deletes runtime files in logs/ (evermemos_*.log, evermemos.pid)
#   5a. Deletes .env
#   3. Deletes .venv/

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
echo "           EverMemOS Uninstaller"
echo "============================================================"
echo ""

# ── Step 0: Stop all running services ────────────────────────────────────────
echo "▶  Stopping running services..."
echo ""

# Stop EverMemOS backend
python3 claude-skills/evermemos-start/scripts/service_manager.py stop 2>/dev/null || true
if pgrep -f "src/run.py" > /dev/null 2>&1; then
    pkill -TERM -f "src/run.py" 2>/dev/null || true
    sleep 2
    pkill -KILL -f "src/run.py" 2>/dev/null || true
    echo "  ✅ EverMemOS backend stopped"
else
    echo "  ℹ️  EverMemOS backend was not running"
fi

# Stop kv-server
if pgrep -f "zgs_kv" > /dev/null 2>&1; then
    pkill -f "zgs_kv" 2>/dev/null || true
    echo "  ✅ kv-server stopped"
else
    echo "  ℹ️  kv-server was not running"
fi

# ── Step 0b: Remove Docker containers and volumes ────────────────────────────
echo ""
echo "▶  Removing Docker containers and volumes..."
echo ""
if [ -n "$($COMPOSE_CMD ps -q 2>/dev/null)" ]; then
    echo "  🗑️  Running: $COMPOSE_CMD down -v"
    $COMPOSE_CMD down -v
    echo "  ✅ Containers and volumes removed"
else
    # Containers may not be listed by ps -q if already removed, but try anyway
    # to ensure volumes are cleaned up
    $COMPOSE_CMD down -v 2>/dev/null && echo "  ✅ Containers and volumes removed" || echo "  ℹ️  No containers found, skipping"
fi

# ── 0g_kv_server cleanup (binary + config + runtime data) ────────────────────
echo "▶  Removing 0g_kv_server files..."
KV_DIR="$SCRIPT_DIR/0g_kv_server"
for target in "$KV_DIR/zgs_kv" "$KV_DIR/config_testnet_turbo.toml" "$KV_DIR/db" "$KV_DIR/kv.DB"; do
    if [ -e "$target" ]; then
        rm -rf "$target"
        echo "  ✅ Deleted $target"
    else
        echo "  ℹ️  $target not found, skipping"
    fi
done

# ── Step 7 (reverse): Delete .0g_secrets ─────────────────────────────────────
echo ""
echo "▶  Removing .0g_secrets..."
if [ -f "$SCRIPT_DIR/.0g_secrets" ]; then
    rm "$SCRIPT_DIR/.0g_secrets"
    echo "  ✅ Deleted .0g_secrets"
else
    echo "  ℹ️  .0g_secrets not found, skipping"
fi

# ── Step 6b (reverse): Remove hooks and env vars from ~/.claude/settings.json ─
echo ""
echo "▶  Removing EverMemOS hooks from ~/.claude/settings.json..."
python3 - <<'EOF'
import json
from pathlib import Path

settings_path = Path.home() / ".claude" / "settings.json"
if not settings_path.exists():
    print("  ℹ️  ~/.claude/settings.json not found, skipping")
    exit(0)

with open(settings_path, "r", encoding="utf-8") as f:
    settings = json.load(f)

# Remove EverMemOS hooks
hook_scripts = {
    "hook_session_start.py",
    "hook_user_prompt.py",
    "hook_tool_use.py",
    "hook_stop.py",
    "hook_session_end.py",
}

removed_hooks = 0
hooks = settings.get("hooks", {})
for event in list(hooks.keys()):
    original_len = len(hooks[event])
    hooks[event] = [
        group for group in hooks[event]
        if not any(
            script in h.get("command", "")
            for h in group.get("hooks", [])
            for script in hook_scripts
        )
    ]
    removed = original_len - len(hooks[event])
    if removed:
        removed_hooks += removed
        print(f"  ✅ Removed hook: {event}")
    if not hooks[event]:
        del hooks[event]

# Remove EverMemOS env vars
evermemos_env_keys = {"EVERMEMOS_BASE_URL", "EVERMEMOS_USER_ID", "EVERMEMOS_GROUP_ID"}
env = settings.get("env", {})
removed_env = [k for k in evermemos_env_keys if k in env]
for k in removed_env:
    del env[k]
    print(f"  ✅ Removed env var: {k}")
if not env:
    settings.pop("env", None)

if removed_hooks == 0 and not removed_env:
    print("  ℹ️  No EverMemOS hooks or env vars found, skipping")
else:
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print("  ✅ Updated ~/.claude/settings.json")
EOF

# ── Step 6a (reverse): Remove EverMemOS skills from ~/.claude/skills/ ─────────
echo ""
echo "▶  Removing EverMemOS skills from ~/.claude/skills/..."
SKILLS_DIR="$HOME/.claude/skills"
found=false
for skill_dir in "$SKILLS_DIR"/evermemos*/; do
    if [ -d "$skill_dir" ]; then
        rm -rf "$skill_dir"
        echo "  ✅ Deleted $skill_dir"
        found=true
    fi
done
if [ "$found" = false ]; then
    echo "  ℹ️  No EverMemOS skills found in $SKILLS_DIR, skipping"
fi

# ── Step 5b (reverse): Delete runtime-generated files in logs/ ───────────────
echo ""
echo "▶  Removing runtime files in logs/..."
LOG_DIR="$SCRIPT_DIR/logs"
if [ -d "$LOG_DIR" ]; then
    # Remove all timestamped log files
    log_count=0
    for f in "$LOG_DIR"/evermemos_*.log; do
        [ -f "$f" ] || continue
        rm "$f"
        echo "  ✅ Deleted $f"
        log_count=$((log_count + 1))
    done
    [ "$log_count" -eq 0 ] && echo "  ℹ️  No log files found, skipping"
    # Remove PID file
    if [ -f "$LOG_DIR/evermemos.pid" ]; then
        rm "$LOG_DIR/evermemos.pid"
        echo "  ✅ Deleted $LOG_DIR/evermemos.pid"
    else
        echo "  ℹ️  evermemos.pid not found, skipping"
    fi
else
    echo "  ℹ️  logs/ directory not found, skipping"
fi

# ── Step 5a (reverse): Delete .env ───────────────────────────────────────────
echo ""
echo "▶  Removing .env..."
if [ -f "$SCRIPT_DIR/.env" ]; then
    rm "$SCRIPT_DIR/.env"
    echo "  ✅ Deleted .env"
else
    echo "  ℹ️  .env not found, skipping"
fi

# ── Step 3 (reverse): Delete .venv/ ──────────────────────────────────────────
echo ""
echo "▶  Removing .venv/..."
if [ -d "$SCRIPT_DIR/.venv" ]; then
    rm -rf "$SCRIPT_DIR/.venv"
    echo "  ✅ Deleted .venv/"
else
    echo "  ℹ️  .venv/ not found, skipping"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  ✅ Uninstall complete!"
echo ""
echo "  ⚠️  If Claude Code is running, restart it so the"
echo "     removed hooks take effect."
echo "============================================================"
echo ""
