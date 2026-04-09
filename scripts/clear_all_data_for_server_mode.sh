#!/bin/bash
# clear_all_data_from_server_mode.sh
#
# Clears remaining server mode data that uninstall.sh does NOT remove.
# (MongoDB/Milvus/ES data is already deleted by `docker compose down -v` in uninstall.sh)
#
# What this clears:
#   - user_secrets_backup.json : local backup file (causes old users to reappear on reinstall)
#
# Usage:
#   Run after ./uninstall.sh, before ./install.sh + ./start_service.sh
#   Users can then re-register with the same usernames and start fresh.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

BACKUP_FILE="${EVERMEMOS_USER_BACKUP_FILE:-$PROJECT_DIR/user_secrets_backup.json}"

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
