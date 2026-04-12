#!/bin/bash
# clear_all_data_from_server_mode.sh
#
# Clears remaining server mode data that uninstall.sh does NOT remove.
# (MongoDB/Milvus/ES data is already deleted by `docker compose down -v` in uninstall.sh)
#
# What this clears:
#   - user_secrets_backup.json : local backup file (causes old users to reappear on reinstall)
#   - stream_ids in config_testnet_turbo.toml : per-user stream IDs added during registration
#
# Usage:
#   Run after ./uninstall.sh, before ./install.sh + ./start_service.sh
#   Users can then re-register with the same usernames and start fresh.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

BACKUP_FILE="${EVERMEMOS_USER_BACKUP_FILE:-$PROJECT_DIR/user_secrets_backup.json}"
KV_CONFIG="${KV_CONFIG_PATH:-$PROJECT_DIR/0g_kv_server/config_testnet_turbo.toml}"

# ── Step 1: Remove stream_ids from KV node config (read from backup BEFORE deleting it) ──
if [ -f "$BACKUP_FILE" ] && [ -f "$KV_CONFIG" ]; then
    # Extract all zerog_stream_id values from the backup JSON
    STREAM_IDS=$(python3 -c "
import json, sys
try:
    data = json.load(open('$BACKUP_FILE'))
    ids = [u['zerog_stream_id'] for u in data.get('users', []) if u.get('zerog_stream_id')]
    print('\n'.join(ids))
except Exception as e:
    print('ERROR:' + str(e), file=sys.stderr)
    sys.exit(1)
")

    if [ $? -ne 0 ]; then
        echo "❌ Failed to read stream_ids from backup, skipping KV config cleanup"
    elif [ -z "$STREAM_IDS" ]; then
        echo "ℹ️  No stream_ids found in backup, skipping KV config cleanup"
    else
        echo "🔧 Removing user stream_ids from $KV_CONFIG ..."
        python3 - "$KV_CONFIG" <<PYEOF
import re, sys, os

config_path = sys.argv[1]
stream_ids_to_remove = set("""$STREAM_IDS""".strip().splitlines())

text = open(config_path, encoding='utf-8').read()
match = re.search(r'^(stream_ids\s*=\s*\[)([^\]]*?)(\])', text, re.MULTILINE)
if not match:
    print("  ⚠️  stream_ids line not found in config, skipping")
    sys.exit(0)

prefix, ids_str, suffix = match.group(1), match.group(2), match.group(3)
existing_ids = [s.strip().strip('"') for s in ids_str.split(',') if s.strip().strip('"')]
kept_ids = [sid for sid in existing_ids if sid not in stream_ids_to_remove]
removed_ids = [sid for sid in existing_ids if sid in stream_ids_to_remove]

new_ids_str = ', '.join(f'"{sid}"' for sid in kept_ids)
new_line = f'{prefix}{new_ids_str}{suffix}'
new_text = text[:match.start()] + new_line + text[match.end():]

tmp_path = config_path + '.tmp'
open(tmp_path, 'w', encoding='utf-8').write(new_text)
os.replace(tmp_path, config_path)

for sid in removed_ids:
    print(f'  ✅ Removed stream_id: {sid}')
if not removed_ids:
    print('  ℹ️  No matching stream_ids found in config (already clean)')
PYEOF
    fi
elif [ ! -f "$KV_CONFIG" ]; then
    echo "ℹ️  KV config not found at $KV_CONFIG, skipping stream_id cleanup"
else
    echo "ℹ️  Backup file not found, skipping stream_id cleanup"
fi

# ── Step 2: Delete user_secrets_backup.json ───────────────────────────────────
if [ -f "$BACKUP_FILE" ]; then
    rm -f "$BACKUP_FILE"
    echo "✅ Deleted $BACKUP_FILE"
else
    echo "ℹ️  $BACKUP_FILE not found (already clean)"
fi

if [ -f "${BACKUP_FILE}.tmp" ]; then
    rm -f "${BACKUP_FILE}.tmp"
    echo "✅ Deleted ${BACKUP_FILE}.tmp"
fi
