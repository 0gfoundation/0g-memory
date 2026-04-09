"""
MongoDB data validator for Dual Storage

Validates MongoDB data completeness against KV Storage and syncs missing documents.
Only syncs Lite data (indexed fields + query fields) to MongoDB.

This ensures that MongoDB has index data for all documents stored in KV Storage,
enabling queries and data recovery for Milvus/ES.
"""

import time
import json
from typing import Set, Dict, Any, List, Tuple
from collections import defaultdict
from bson import ObjectId

from core.observation.logger import get_logger
from core.di.utils import get_bean_by_type
from infra_layer.adapters.out.persistence.kv_storage.kv_storage_interface import KVStorageInterface
from infra_layer.adapters.out.persistence.kv_storage.lite_model_extractor import LiteModelExtractor
from .data_sync_validator import SyncResult

logger = get_logger(__name__)


async def validate_mongodb_data(days: int = 7) -> Tuple[List[SyncResult], Dict[str, Dict[str, str]]]:
    """
    Validate MongoDB data completeness against KV Storage

    Iterates KV Storage and ensures MongoDB has Lite data for all documents.

    Args:
        days: Check documents from last N days (0 = all documents)
              Note: Currently checks ALL documents from KV Storage regardless of days parameter

    Returns:
        Tuple of (List[SyncResult], kv_docs_by_collection).
        kv_docs_by_collection is Dict[collection_name, Dict[doc_id, json_value]] —
        passed to Milvus/ES validators so they can load full docs without KV user context.
    """
    start_time = time.time()
    results = []

    try:
        # Get KV Storage instance
        kv_storage = get_bean_by_type(KVStorageInterface)

        # Group documents by collection
        logger.info("📦 Scanning KV Storage for all documents...")
        kv_docs_by_collection = await _scan_kv_storage(kv_storage)

        logger.info(f"✅ Found documents in {len(kv_docs_by_collection)} collections")

        # Validate each collection
        for collection_name, kv_docs in kv_docs_by_collection.items():
            try:
                result = await _validate_collection(
                    collection_name=collection_name,
                    kv_docs=kv_docs
                )
                results.append(result)
            except Exception as e:
                logger.error(f"❌ Failed to validate collection {collection_name}: {e}", exc_info=True)
                results.append(SyncResult(
                    doc_type=collection_name,
                    target="mongodb",
                    total_checked=0,
                    missing_count=0,
                    synced_count=0,
                    error_count=1,
                    elapsed_time=0.0
                ))

        # Update elapsed time
        elapsed = time.time() - start_time
        for result in results:
            result.elapsed_time = elapsed

        return results, kv_docs_by_collection

    except Exception as e:
        logger.error(f"❌ MongoDB validation failed: {e}", exc_info=True)
        return [SyncResult(
            doc_type="all",
            target="mongodb",
            total_checked=0,
            missing_count=0,
            synced_count=0,
            error_count=1,
            elapsed_time=time.time() - start_time
        )], {}


async def _scan_kv_storage(kv_storage: KVStorageInterface) -> Dict[str, Dict[str, str]]:
    """
    Scan KV Storage and group documents by collection

    Args:
        kv_storage: KV Storage instance

    Returns:
        Dict[collection_name, Dict[doc_id, json_value]]
    """
    docs_by_collection = defaultdict(dict)
    count = 0

    async for key, value in kv_storage.iterate_all():
        count += 1

        # Parse key format: "{collection_name}:{document_id}"
        if ':' in key:
            collection_name, doc_id = key.split(':', 1)
            docs_by_collection[collection_name][doc_id] = value
        else:
            logger.warning(f"⚠️  Invalid key format (no collection prefix): {key}")

        # Log progress every 1000 documents
        if count % 1000 == 0:
            logger.info(f"📊 Scanned {count} documents from KV Storage...")

    logger.info(f"✅ Scanned {count} total documents from KV Storage")
    return dict(docs_by_collection)


async def _validate_collection(
    collection_name: str,
    kv_docs: Dict[str, str]
) -> SyncResult:
    """
    Validate a single collection

    Args:
        collection_name: MongoDB collection name
        kv_docs: Dict[doc_id, json_value] from KV Storage

    Returns:
        SyncResult
    """
    try:
        # Get repository and model class for this collection
        repo_info = _get_repository_for_collection(collection_name)
        if not repo_info:
            logger.warning(f"⚠️  No repository found for collection: {collection_name}, skipping")
            return SyncResult(
                doc_type=collection_name,
                target="mongodb",
                total_checked=len(kv_docs),
                missing_count=0,
                synced_count=0,
                error_count=0,  # Not an error, just skipped
                elapsed_time=0.0
            )

        mongo_repo, model_class = repo_info

        # Get existing MongoDB IDs
        mongo_ids = await _get_mongodb_ids(mongo_repo, collection_name)
        kv_ids = set(kv_docs.keys())

        # Find missing IDs
        missing_ids = kv_ids - mongo_ids

        if not missing_ids:
            logger.info(f"✅ Collection {collection_name}: All {len(kv_ids)} docs present in MongoDB")
            return SyncResult(
                doc_type=collection_name,
                target="mongodb",
                total_checked=len(kv_ids),
                missing_count=0,
                synced_count=0,
                error_count=0,
                elapsed_time=0.0
            )

        # Sync missing documents
        logger.warning(f"⚠️  Collection {collection_name}: Found {len(missing_ids)} missing docs, syncing...")

        synced_count, error_count = await _sync_missing_to_mongodb(
            mongo_repo=mongo_repo,
            model_class=model_class,
            collection_name=collection_name,
            missing_ids=missing_ids,
            kv_docs=kv_docs
        )

        return SyncResult(
            doc_type=collection_name,
            target="mongodb",
            total_checked=len(kv_ids),
            missing_count=len(missing_ids),
            synced_count=synced_count,
            error_count=error_count,
            elapsed_time=0.0
        )

    except Exception as e:
        logger.error(f"❌ Failed to validate collection {collection_name}: {e}", exc_info=True)
        return SyncResult(
            doc_type=collection_name,
            target="mongodb",
            total_checked=len(kv_docs),
            missing_count=0,
            synced_count=0,
            error_count=1,
            elapsed_time=0.0
        )


def _get_repository_for_collection(collection_name: str):
    """
    Get repository and model class for a collection name

    Args:
        collection_name: MongoDB collection name (e.g., "episodic_memories")

    Returns:
        Tuple[repository, model_class] or None if not found
    """
    # Map collection names to repository class names
    # This mapping is based on Document Settings.name
    collection_mapping = {
        "episodic_memories": "EpisodicMemoryRawRepository",
        "event_log_records": "EventLogRecordRawRepository",
        "foresight_records": "ForesightRecordRawRepository",
        "core_memories": "CoreMemoryRawRepository",
        "conversation_metas": "ConversationMetaRawRepository",
        # conversation_status is excluded: it is operational metadata (processing cursor),
        # not stored in 0G KV (no DualStorageMixin on ConversationStatusRawRepository).
        "user_profiles": "UserProfileRawRepository",
        "group_profiles": "GroupProfileRawRepository",
        "group_user_profile_memories": "GroupUserProfileMemoryRawRepository",
        "entities": "EntityRawRepository",
        "relationships": "RelationshipRawRepository",
        "behavior_histories": "BehaviorHistoryRawRepository",
        "memcells": "MemCellRawRepository",
        "cluster_states": "ClusterStateRawRepository",
        "memory_request_logs": "MemoryRequestLogRepository",
    }

    if collection_name not in collection_mapping:
        # Collection not in mapping - might be a non-dual-storage collection
        return None

    try:
        repo_class_name = collection_mapping[collection_name]

        # Dynamically get repository from DI container
        from core.di.utils import get_beans_by_type
        from core.oxm.mongo.base_repository import BaseRepository

        # Find repository by class name
        all_repos = get_beans_by_type(BaseRepository)
        repo = next((r for r in all_repos if r.__class__.__name__ == repo_class_name), None)

        if not repo:
            logger.warning(f"⚠️  Repository not found in DI container: {repo_class_name}")
            return None

        # Get model class from repository
        model_class = repo.model

        return (repo, model_class)

    except Exception as e:
        logger.error(f"❌ Failed to get repository for {collection_name}: {e}")
        return None


async def _get_mongodb_ids(mongo_repo: Any, collection_name: str) -> Set[str]:
    """
    Get all document IDs from MongoDB

    Args:
        mongo_repo: MongoDB repository
        collection_name: Collection name (for logging)

    Returns:
        Set of document IDs as strings
    """
    try:
        collection = mongo_repo.model.get_pymongo_collection()
        cursor = collection.find({}, {"_id": 1})
        docs = await cursor.to_list(length=None)
        return {str(doc["_id"]) for doc in docs}
    except Exception as e:
        logger.error(f"❌ Failed to get MongoDB IDs for {collection_name}: {e}")
        return set()


async def _sync_missing_to_mongodb(
    mongo_repo: Any,
    model_class: Any,
    collection_name: str,
    missing_ids: Set[str],
    kv_docs: Dict[str, str],
    batch_size: int = 500
) -> tuple[int, int]:
    """
    Sync missing documents to MongoDB (Lite data only)

    Args:
        mongo_repo: MongoDB repository
        model_class: Document model class
        collection_name: Collection name
        missing_ids: Set of missing document IDs
        kv_docs: Dict[doc_id, json_value] from KV Storage
        batch_size: Batch size for inserts

    Returns:
        Tuple[synced_count, error_count]
    """
    synced_count = 0
    error_count = 0

    # Get indexed fields for this model
    indexed_fields = LiteModelExtractor.extract_indexed_fields(model_class)
    logger.info(f"📋 Model {model_class.__name__} has {len(indexed_fields)} indexed fields: {sorted(indexed_fields)}")

    # Process in batches
    missing_list = list(missing_ids)
    for i in range(0, len(missing_list), batch_size):
        batch_ids = missing_list[i:i + batch_size]
        lite_docs = []

        for doc_id in batch_ids:
            try:
                # Get full document from KV Storage
                json_value = kv_docs.get(doc_id)
                if not json_value:
                    logger.warning(f"⚠️  Document {doc_id} not found in KV docs")
                    error_count += 1
                    continue

                # Parse JSON
                full_data = json.loads(json_value)

                # Extract Lite data (only indexed fields)
                lite_data = {}
                for field in indexed_fields:
                    # Special handling for 'id' field
                    # KV Storage stores 'id' as string, but MongoDB uses '_id' as ObjectId
                    # Skip 'id' field here - we'll set '_id' separately below
                    if field == 'id':
                        continue

                    if field in full_data:
                        value = full_data[field]

                        # Convert string timestamps back to datetime if needed
                        # (KV Storage stores datetime as ISO string)
                        if field in ('created_at', 'updated_at', 'deleted_at') and isinstance(value, str):
                            from datetime import datetime
                            try:
                                value = datetime.fromisoformat(value)
                            except Exception:
                                pass  # Keep as string if conversion fails

                        lite_data[field] = value

                # CRITICAL: Add _id field (MongoDB requires it)
                # This ensures the document has the same ID in both MongoDB and KV Storage
                try:
                    lite_data["_id"] = ObjectId(doc_id)
                except Exception as e:
                    logger.error(f"❌ Invalid ObjectId {doc_id}: {e}")
                    error_count += 1
                    continue

                lite_docs.append(lite_data)

            except json.JSONDecodeError as e:
                logger.error(f"❌ Failed to parse JSON for doc {doc_id}: {e}")
                error_count += 1
            except Exception as e:
                logger.error(f"❌ Failed to prepare doc {doc_id}: {e}")
                error_count += 1

        # Batch insert to MongoDB
        if lite_docs:
            try:
                collection = mongo_repo.model.get_pymongo_collection()
                # Use ordered=False to continue on duplicate key errors
                result = await collection.insert_many(lite_docs, ordered=False)
                inserted = len(result.inserted_ids)
                synced_count += inserted
                logger.info(f"✅ Batch {i//batch_size + 1}: Inserted {inserted}/{len(lite_docs)} Lite docs to {collection_name}")
            except Exception as e:
                # Handle bulk write errors (e.g., duplicate keys)
                error_msg = str(e)
                if "duplicate key" in error_msg.lower():
                    # Some documents already exist - this is OK
                    logger.warning(f"⚠️  Some documents already exist in {collection_name}: {error_msg}")
                    # Count successful inserts from error details if available
                    if hasattr(e, 'details') and 'nInserted' in e.details:
                        inserted = e.details['nInserted']
                        synced_count += inserted
                        error_count += len(lite_docs) - inserted
                    else:
                        error_count += len(lite_docs)
                else:
                    logger.error(f"❌ Batch insert failed for {collection_name}: {e}")
                    error_count += len(lite_docs)

    return synced_count, error_count
