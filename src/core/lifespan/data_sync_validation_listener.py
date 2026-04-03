"""
Data sync validation listener

Automatically validates and syncs Milvus data on application startup.
"""

import os
import asyncio

from core.lifespan.lifespan_factory import AppReadyListener
from core.di.decorators import component
from core.observation.logger import get_logger
from core.validation.data_sync_validator import SyncResult

logger = get_logger(__name__)


@component("data_sync_validation_listener")
class DataSyncValidationListener(AppReadyListener):
    """Validates and syncs Milvus data on application startup"""

    def on_app_ready(self) -> None:
        """Called after all lifespan providers have started"""
        # Check if we're running via bootstrap.py (demo/test script) or run.py (backend)
        # Only run auto-sync when starting the actual backend, not for demo/test scripts
        is_bootstrap_mode = os.getenv("BOOTSTRAP_MODE", "false").lower() == "true"
        if is_bootstrap_mode:
            logger.info(
                "Skipping startup data sync (running via bootstrap.py, not backend startup)"
            )
            return

        # Check if startup sync is enabled
        enabled = os.getenv("STARTUP_SYNC_ENABLED", "true").lower() == "true"
        if not enabled:
            logger.info("Startup data sync is disabled (STARTUP_SYNC_ENABLED=false)")
            return

        # Get configuration
        days = int(os.getenv("STARTUP_SYNC_DAYS", "0"))
        check_mongodb = os.getenv("STARTUP_SYNC_MONGODB", "true").lower() == "true"
        check_milvus = os.getenv("STARTUP_SYNC_MILVUS", "true").lower() == "true"
        check_es = os.getenv("STARTUP_SYNC_ES", "true").lower() == "true"

        # Skip if all validations are disabled
        if not check_mongodb and not check_milvus and not check_es:
            logger.info(
                "All validations are disabled "
                "(STARTUP_SYNC_MONGODB=false, STARTUP_SYNC_MILVUS=false, STARTUP_SYNC_ES=false)"
            )
            return

        # Log appropriate message based on validation mode
        if days == 0:
            logger.warning(
                "🔥 Starting FULL DATABASE validation (all documents) - "
                "this may take several minutes. mongodb=%s, milvus=%s, es=%s",
                check_mongodb,
                check_milvus,
                check_es,
            )
        else:
            logger.info(
                "Starting data sync validation (last %d days, mongodb=%s, milvus=%s, es=%s)",
                days,
                check_mongodb,
                check_milvus,
                check_es,
            )

        # Block all API requests until recovery completes
        from core.startup.startup_state import mark_recovering
        mark_recovering()

        # Run validation asynchronously (non-blocking)
        asyncio.create_task(self._run_validation(days, check_mongodb, check_milvus, check_es))

    async def _run_validation(
        self, days: int, check_mongodb: bool, check_milvus: bool, check_es: bool
    ) -> None:
        """
        Run validation and sync process

        Args:
            days: Days to check (0 = all documents)
            check_mongodb: Whether to validate MongoDB (against KV Storage)
            check_milvus: Whether to validate Milvus
            check_es: Whether to validate Elasticsearch
        """
        from core.startup.startup_state import mark_ready
        from core.validation.milvus_data_validator import validate_milvus_data
        from core.validation.es_data_validator import validate_es_data
        from core.validation.mongodb_data_validator import validate_mongodb_data

        doc_types = ["episodic_memory", "event_log", "foresight"]
        all_results = []

        try:
            # STEP 0: Restore UserSecret table FIRST (prerequisite for everything else)
            # In server mode, UserSecret is needed to access any user's 0G stream
            await self._restore_user_secrets()

            # CRITICAL: Validate MongoDB FIRST (before Milvus and ES)
            # MongoDB is the source for Milvus/ES data recovery
            # If MongoDB is missing data, Milvus/ES recovery will fail
            kv_docs_by_collection: dict = {}
            if check_mongodb:
                logger.info("Validating MongoDB data against KV Storage...")
                try:
                    mongodb_results, kv_docs_by_collection = await validate_mongodb_data(days)
                    all_results.extend(mongodb_results)
                    for result in mongodb_results:
                        self._log_result(result, days)
                except Exception as e:
                    logger.error(f"Failed to validate MongoDB: {e}", exc_info=True)

            # Validate Milvus for each document type
            if check_milvus:
                logger.info("Validating Milvus data...")
                for doc_type in doc_types:
                    try:
                        result = await validate_milvus_data(doc_type, days, kv_docs_by_collection)
                        all_results.append(result)
                        self._log_result(result, days)
                    except Exception as e:
                        logger.error(
                            "Failed to validate %s (Milvus): %s", doc_type, e, exc_info=True
                        )

            # Validate Elasticsearch for each document type
            if check_es:
                logger.info("Validating Elasticsearch data...")
                for doc_type in doc_types:
                    try:
                        result = await validate_es_data(doc_type, days, kv_docs_by_collection)
                        all_results.append(result)
                        self._log_result(result, days)
                    except Exception as e:
                        logger.error(
                            "Failed to validate %s (ES): %s", doc_type, e, exc_info=True
                        )

            # Summary
            total_synced = sum(r.synced_count for r in all_results)
            total_errors = sum(r.error_count for r in all_results)
            total_checked = sum(r.total_checked for r in all_results)

            if total_synced > 0:
                if days == 0:
                    logger.warning(
                        "🔥 Full database sync completed: %d documents synced, %d errors "
                        "(scanned %d total documents)",
                        total_synced,
                        total_errors,
                        total_checked,
                    )
                else:
                    logger.warning(
                        "⚠️  Startup sync completed: %d documents synced, %d errors",
                        total_synced,
                        total_errors,
                    )
            else:
                if days == 0:
                    logger.info(
                        "✅ Full database sync completed: All data consistent "
                        "(scanned %d documents)",
                        total_checked,
                    )
                else:
                    logger.info("✅ Startup sync completed: All data consistent")

        except Exception as e:
            logger.error("❌ Startup sync validation failed: %s", e, exc_info=True)
        finally:
            mark_ready()
            logger.info("✅ Startup recovery complete, API gate opened")

    async def _restore_user_secrets(self) -> None:
        """
        Restore UserSecret table from local backup if needed.
        This must happen BEFORE any 0G stream access.
        """
        import os

        try:
            # Only do this in server mode
            server_mode = os.getenv("SERVER_MODE", "false").lower() == "true"
            if not server_mode:
                logger.debug("Local mode detected, skipping UserSecret restore")
                return

            logger.info("🔑 Checking UserSecret table for server mode...")

            from infra_layer.adapters.out.persistence.user_secret_backup import UserSecretBackup

            # Try to restore from backup.
            # Returns True if backup file was found (KV scan can proceed).
            # Returns False if backup file is missing (restore_to_mongodb already logged the reason).
            await UserSecretBackup.restore_to_mongodb()

        except Exception as e:
            logger.error("❌ Failed to restore UserSecret table: %s", e)
            # Don't crash startup if this fails - let the system try to continue

    def _log_result(self, result: SyncResult, days: int) -> None:
        """
        Log sync result

        Args:
            result: Sync result
            days: Days checked (for context in logging)
        """
        if result.synced_count > 0:
            logger.warning(
                "📊 %s (%s): Found %d missing docs, synced %d, errors %d (%.2fs)",
                result.doc_type,
                result.target,
                result.missing_count,
                result.synced_count,
                result.error_count,
                result.elapsed_time,
            )
        elif result.error_count > 0:
            logger.error(
                "❌ %s (%s): Validation failed with %d errors",
                result.doc_type,
                result.target,
                result.error_count,
            )
        else:
            if days == 0:
                logger.info(
                    "✅ %s (%s): All %d docs consistent (full database)",
                    result.doc_type,
                    result.target,
                    result.total_checked,
                )
            else:
                logger.info(
                    "✅ %s (%s): All %d docs consistent",
                    result.doc_type,
                    result.target,
                    result.total_checked,
                )
