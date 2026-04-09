"""
UserSecret backup manager — simple plaintext local file backup for disaster recovery.

In server mode, user credentials are critical for accessing 0G streams.
This module provides simple backup/restore to/from local JSON file.
"""

import json
import os
import asyncio
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime

from core.observation.logger import get_logger

logger = get_logger(__name__)

# Backup file location with environment variable override
BACKUP_FILE = os.getenv(
    "EVERMEMOS_USER_BACKUP_FILE",
    "./user_secrets_backup.json"  # Default to current directory
)
BACKUP_DIR = Path(BACKUP_FILE).parent

# Global lock to prevent concurrent backup operations
_backup_lock = asyncio.Lock()


class UserSecretBackup:
    """Simple file-based backup for UserSecret data."""

    @staticmethod
    def ensure_backup_dir():
        """Ensure backup directory exists."""
        try:
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Backup directory ensured: {BACKUP_DIR}")
        except Exception as e:
            logger.error(f"Failed to create backup directory: {e}")
            raise

    @staticmethod
    def save_to_file(user_secrets: List[Dict[str, Any]]) -> bool:
        """
        Save user secrets to local file (plaintext JSON).

        Args:
            user_secrets: List of UserSecret documents as dicts

        Returns:
            bool: True if saved successfully
        """
        try:
            UserSecretBackup.ensure_backup_dir()

            backup_data = {
                "version": "1.0",
                "backup_time": datetime.utcnow().isoformat(),
                "user_count": len(user_secrets),
                "users": user_secrets
            }

            # Write to temp file first, then atomic rename
            temp_file = f"{BACKUP_FILE}.tmp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, indent=2, default=str)

            # Atomic rename
            os.rename(temp_file, BACKUP_FILE)

            logger.info(f"✅ Saved {len(user_secrets)} user secrets to {BACKUP_FILE}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to save user secrets backup: {e}")
            return False

    @staticmethod
    def load_from_file() -> List[Dict[str, Any]]:
        """
        Load user secrets from local file.

        Returns:
            List of UserSecret documents as dicts, empty if file not found or invalid
        """
        try:
            if not os.path.exists(BACKUP_FILE):
                logger.debug(f"Backup file not found: {BACKUP_FILE}")
                return []

            with open(BACKUP_FILE, 'r', encoding='utf-8') as f:
                backup_data = json.load(f)

            # Validate backup format
            if not isinstance(backup_data, dict) or "users" not in backup_data:
                logger.warning(f"⚠️  Invalid backup file format: {BACKUP_FILE}")
                return []

            users = backup_data["users"]
            backup_time = backup_data.get("backup_time", "unknown")

            logger.info(f"✅ Loaded {len(users)} user secrets from backup (created: {backup_time})")
            return users

        except Exception as e:
            logger.error(f"❌ Failed to load user secrets backup: {e}")
            return []

    @staticmethod
    def backup_exists() -> bool:
        """Check if backup file exists."""
        return os.path.exists(BACKUP_FILE)

    @staticmethod
    async def backup_all_users():
        """
        Backup all users from MongoDB to local file.
        Called when users are registered/updated.
        Uses async lock to prevent concurrent backup operations.
        """
        async with _backup_lock:
            try:
                from infra_layer.adapters.out.persistence.document.user.user_secret import UserSecret

                logger.debug("🔒 Acquired backup lock, starting user backup...")

                # Get all users from MongoDB
                users = await UserSecret.find_all().to_list()

                if not users:
                    logger.info("📭 No users found in MongoDB, skipping backup")
                    return

                # Convert to dict format
                user_dicts = []
                for user in users:
                    user_dict = {
                        "user_id": user.user_id,
                        "api_key": user.api_key,
                        "zerog_stream_id": user.zerog_stream_id,
                        "zerog_encryption_key": user.zerog_encryption_key,
                        "zerog_wallet_key": user.zerog_wallet_key,
                        "created_at": user.created_at.isoformat() if user.created_at else None,
                    }
                    user_dicts.append(user_dict)

                # Save to file
                UserSecretBackup.save_to_file(user_dicts)
                logger.debug("🔓 User backup completed, releasing lock")

            except Exception as e:
                logger.error(f"❌ Failed to backup all users: {e}")
                # Lock is automatically released by 'async with'

    @staticmethod
    async def restore_to_mongodb() -> bool:
        """
        Restore users from local backup file to MongoDB (Scenario B / server mode).

        - Backup not found + MongoDB empty   → WARNING (likely first startup)
        - Backup not found + MongoDB has data → ERROR (backup lost, KV sync impossible)
        - Backup found → restore missing users to MongoDB (skip existing ones), return True
          so the caller proceeds with the 0G KV → MongoDB data sync.

        Returns:
            True if backup file was found (caller should proceed with KV scan).
            False if backup file is missing (KV scan cannot be performed safely).
        """
        try:
            from infra_layer.adapters.out.persistence.document.user.user_secret import UserSecret
            from datetime import datetime

            # ── 1. Backup file missing ────────────────────────────────────────────
            if not UserSecretBackup.backup_exists():
                existing_count = await UserSecret.count()
                if existing_count == 0:
                    logger.warning(
                        "⚠️  Backup file not found (%s) and MongoDB has no users. "
                        "This is expected on first startup. "
                        "If this is a restart after data loss, the backup file is missing "
                        "and users cannot be recovered.",
                        BACKUP_FILE,
                    )
                else:
                    logger.error(
                        "❌ Backup file not found (%s) but MongoDB has %d user(s). "
                        "Cannot sync from 0G KV storage — backup file is required for stream credentials. "
                        "Restore the backup file to enable full data recovery.",
                        BACKUP_FILE,
                        existing_count,
                    )
                return False

            # ── 2. Backup file found — load it ───────────────────────────────────
            user_dicts = UserSecretBackup.load_from_file()
            if not user_dicts:
                logger.warning("⚠️  Backup file exists but contains no users (%s).", BACKUP_FILE)
                return False

            # ── 3. Restore missing users to MongoDB (skip already-existing ones) ─
            restored_count = 0
            skipped_count = 0
            for user_dict in user_dicts:
                try:
                    existing = await UserSecret.find_one(
                        UserSecret.user_id == user_dict["user_id"]
                    )
                    if existing:
                        skipped_count += 1
                        continue

                    created_at = None
                    if user_dict.get("created_at"):
                        created_at = UserSecretBackup._parse_datetime_safe(user_dict["created_at"])

                    user_secret = UserSecret(
                        user_id=user_dict["user_id"],
                        api_key=user_dict["api_key"],
                        zerog_stream_id=user_dict["zerog_stream_id"],
                        zerog_encryption_key=user_dict["zerog_encryption_key"],
                        zerog_wallet_key=user_dict["zerog_wallet_key"],
                        created_at=created_at or datetime.utcnow(),
                    )
                    await user_secret.insert()
                    restored_count += 1

                except Exception as e:
                    logger.error(
                        "❌ Failed to restore user %s: %s",
                        user_dict.get("user_id", "unknown"),
                        e,
                    )

            logger.info(
                "✅ UserSecret restore complete: %d restored, %d already existed (skipped)",
                restored_count,
                skipped_count,
            )
            # Return True regardless — backup was found, caller should proceed with KV scan
            return True

        except Exception as e:
            logger.error("❌ Failed to restore users to MongoDB: %s", e)
            return False

    @staticmethod
    def _parse_datetime_safe(date_str: str):
        """
        Safely parse datetime string with multiple format support.

        Args:
            date_str: Datetime string in various formats

        Returns:
            datetime object or None if parsing fails
        """
        if not date_str or not isinstance(date_str, str):
            return None

        # Common datetime formats to try
        formats_to_try = [
            "%Y-%m-%dT%H:%M:%S.%fZ",      # 2024-01-15T08:30:00.123456Z
            "%Y-%m-%dT%H:%M:%SZ",         # 2024-01-15T08:30:00Z
            "%Y-%m-%dT%H:%M:%S.%f%z",     # 2024-01-15T08:30:00.123456+00:00
            "%Y-%m-%dT%H:%M:%S%z",        # 2024-01-15T08:30:00+00:00
            "%Y-%m-%dT%H:%M:%S.%f",       # 2024-01-15T08:30:00.123456 (no timezone)
            "%Y-%m-%dT%H:%M:%S",          # 2024-01-15T08:30:00 (no timezone)
        ]

        # Try each format
        for fmt in formats_to_try:
            try:
                parsed = datetime.strptime(date_str, fmt)
                # If no timezone info, assume UTC
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=None)  # Keep as naive datetime for MongoDB
                else:
                    parsed = parsed.replace(tzinfo=None)  # Remove timezone for MongoDB compatibility
                return parsed
            except ValueError:
                continue

        # Fallback: try fromisoformat with Z replacement
        try:
            # Handle 'Z' suffix (UTC indicator)
            normalized = date_str.replace('Z', '+00:00')
            parsed = datetime.fromisoformat(normalized)
            # Remove timezone info for MongoDB compatibility
            return parsed.replace(tzinfo=None)
        except ValueError:
            pass

        # Last resort: try to extract just the date part
        try:
            # Extract date and time, ignore timezone
            import re
            # Match YYYY-MM-DDTHH:MM:SS (ignore everything after)
            match = re.match(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})', date_str)
            if match:
                return datetime.strptime(match.group(1), "%Y-%m-%dT%H:%M:%S")
        except (ValueError, AttributeError):
            pass

        logger.warning(f"⚠️  Failed to parse datetime '{date_str}', keeping as None for safety")
        return None


__all__ = ["UserSecretBackup"]