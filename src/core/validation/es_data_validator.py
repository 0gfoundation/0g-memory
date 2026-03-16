"""
Elasticsearch data validator

Validates Elasticsearch data completeness against MongoDB and syncs missing documents.
"""

import time
import traceback
from datetime import timedelta
from typing import Set, Dict, Any

from core.observation.logger import get_logger
from core.di.utils import get_bean_by_type
from common_utils.datetime_utils import get_now_with_timezone
# Note: elasticsearch.helpers.async_bulk has a bug where it hangs after bulk operation completes
# We use the raw client API instead
from .data_sync_validator import DataSyncValidator, SyncResult

logger = get_logger(__name__)


async def validate_es_data(doc_type: str, days: int = 7) -> SyncResult:
    """
    Validate Elasticsearch data completeness for a document type

    Args:
        doc_type: Document type - "episodic_memory", "event_log", or "foresight"
        days: Check documents from last N days (0 = all documents)

    Returns:
        SyncResult with validation and sync statistics
    """
    start_time = time.time()

    try:
        # Route to specific validator based on doc_type
        if doc_type == "episodic_memory":
            result = await _validate_episodic_memory(days)
        elif doc_type == "event_log":
            result = await _validate_event_log(days)
        elif doc_type == "foresight":
            result = await _validate_foresight(days)
        else:
            raise ValueError(f"Unsupported document type: {doc_type}")

        # Update elapsed time
        result.elapsed_time = time.time() - start_time
        return result

    except Exception as e:
        logger.error(
            "Failed to validate ES data for %s: %s", doc_type, e, exc_info=True
        )
        # Return error result
        return SyncResult(
            doc_type=doc_type,
            target="elasticsearch",
            total_checked=0,
            missing_count=0,
            synced_count=0,
            error_count=1,
            elapsed_time=time.time() - start_time,
        )


async def _validate_episodic_memory(days: int) -> SyncResult:
    """Validate episodic memory documents"""
    from infra_layer.adapters.out.persistence.repository.episodic_memory_raw_repository import (
        EpisodicMemoryRawRepository,
    )
    from infra_layer.adapters.out.search.elasticsearch.converter.episodic_memory_converter import (
        EpisodicMemoryConverter,
    )
    from infra_layer.adapters.out.search.elasticsearch.memory.episodic_memory import (
        EpisodicMemoryDoc,
    )

    mongo_repo = get_bean_by_type(EpisodicMemoryRawRepository)
    es_client = EpisodicMemoryDoc.get_connection()
    index_name = EpisodicMemoryDoc.get_index_name()

    return await _validate_and_sync(
        doc_type="episodic_memory",
        mongo_repo=mongo_repo,
        es_client=es_client,
        index_name=index_name,
        converter_class=EpisodicMemoryConverter,
        days=days,
    )


async def _validate_event_log(days: int) -> SyncResult:
    """Validate event log documents"""
    from infra_layer.adapters.out.persistence.repository.event_log_record_raw_repository import (
        EventLogRecordRawRepository,
    )
    from infra_layer.adapters.out.search.elasticsearch.converter.event_log_converter import (
        EventLogConverter,
    )
    from infra_layer.adapters.out.search.elasticsearch.memory.event_log import (
        EventLogDoc,
    )

    mongo_repo = get_bean_by_type(EventLogRecordRawRepository)
    es_client = EventLogDoc.get_connection()
    index_name = EventLogDoc.get_index_name()

    return await _validate_and_sync(
        doc_type="event_log",
        mongo_repo=mongo_repo,
        es_client=es_client,
        index_name=index_name,
        converter_class=EventLogConverter,
        days=days,
    )


async def _validate_foresight(days: int) -> SyncResult:
    """Validate foresight documents"""
    from infra_layer.adapters.out.persistence.repository.foresight_record_repository import (
        ForesightRecordRawRepository,
    )
    from infra_layer.adapters.out.search.elasticsearch.converter.foresight_converter import (
        ForesightConverter,
    )
    from infra_layer.adapters.out.search.elasticsearch.memory.foresight import (
        ForesightDoc,
    )

    mongo_repo = get_bean_by_type(ForesightRecordRawRepository)
    es_client = ForesightDoc.get_connection()
    index_name = ForesightDoc.get_index_name()

    return await _validate_and_sync(
        doc_type="foresight",
        mongo_repo=mongo_repo,
        es_client=es_client,
        index_name=index_name,
        converter_class=ForesightConverter,
        days=days,
    )


async def _validate_and_sync(
    doc_type: str,
    mongo_repo: Any,
    es_client: Any,
    index_name: str,
    converter_class: Any,
    days: int,
) -> SyncResult:
    """
    Common validation and sync logic

    Args:
        doc_type: Document type name
        mongo_repo: MongoDB repository
        es_client: Elasticsearch async client
        index_name: ES index name
        converter_class: Converter class with from_mongo method
        days: Days to check (0 = all)

    Returns:
        SyncResult
    """
    try:
        # Step 1: Get MongoDB IDs
        mongo_ids = await _get_mongo_ids(mongo_repo, days)
        logger.info(
            "Found %d MongoDB documents for %s", len(mongo_ids), doc_type
        )

        # Step 2: Get ES IDs
        es_ids = await _get_es_ids(es_client, index_name, days)
        logger.info(
            "Found %d ES documents for %s", len(es_ids), doc_type
        )

        # Step 3: Find missing IDs
        missing_ids = DataSyncValidator.find_missing_ids(mongo_ids, es_ids)

        if not missing_ids:
            # No missing data - success
            return SyncResult(
                doc_type=doc_type,
                target="elasticsearch",
                total_checked=len(mongo_ids),
                missing_count=0,
                synced_count=0,
                error_count=0,
                elapsed_time=0.0,  # Will be updated by caller
            )

        # Step 4: Sync missing documents
        logger.warning(
            "Found %d missing documents for %s, starting sync...",
            len(missing_ids),
            doc_type,
        )

        synced_count, error_count = await _sync_missing_documents(
            mongo_repo=mongo_repo,
            es_client=es_client,
            index_name=index_name,
            converter_class=converter_class,
            missing_ids=missing_ids,
            doc_type=doc_type,
        )

        return SyncResult(
            doc_type=doc_type,
            target="elasticsearch",
            total_checked=len(mongo_ids),
            missing_count=len(missing_ids),
            synced_count=synced_count,
            error_count=error_count,
            elapsed_time=0.0,  # Will be updated by caller
        )

    except Exception as e:
        logger.error(
            "Error during validation and sync for %s: %s",
            doc_type,
            e,
            exc_info=True,
        )
        return SyncResult(
            doc_type=doc_type,
            target="elasticsearch",
            total_checked=0,
            missing_count=0,
            synced_count=0,
            error_count=1,
            elapsed_time=0.0,
        )


async def _get_mongo_ids(mongo_repo: Any, days: int) -> Set[str]:
    """
    Get MongoDB document IDs

    Args:
        mongo_repo: MongoDB repository
        days: Days to look back (0 = all documents)

    Returns:
        Set of document IDs as strings
    """
    # Build query filter
    query_filter: Dict[str, Any] = {}

    if days > 0:
        # Recent documents only
        now = get_now_with_timezone()
        start_time = now - timedelta(days=days)
        query_filter = {"created_at": {"$gte": start_time}}
        logger.info("Fetching MongoDB IDs from last %d days", days)
    else:
        # All documents (full database)
        logger.info("Fetching ALL MongoDB IDs (full database)")

    # Fetch only IDs (projection for efficiency)
    # Use get_pymongo_collection() to access raw MongoDB API
    collection = mongo_repo.model.get_pymongo_collection()
    cursor = collection.find(query_filter, {"_id": 1})
    docs = await cursor.to_list(length=None)

    return {str(doc["_id"]) for doc in docs}


async def _get_es_ids(es_client: Any, index_name: str, days: int) -> Set[str]:
    """
    Get Elasticsearch document IDs

    Args:
        es_client: ES async client
        index_name: Index name
        days: Days to look back (0 = all documents)

    Returns:
        Set of document IDs as strings
    """
    if days > 0:
        # Recent documents only - use time filter
        now = get_now_with_timezone()
        start_time = now - timedelta(days=days)

        query = {
            "query": {
                "range": {
                    "created_at": {
                        "gte": start_time.isoformat()
                    }
                }
            },
            "_source": False,  # Only fetch IDs
        }
        logger.info("Fetching ES IDs from last %d days", days)
    else:
        # All documents (full database)
        query = {
            "query": {
                "match_all": {}  # Match all documents
            },
            "_source": False,  # Only fetch IDs
        }
        logger.info("Fetching ALL ES IDs (full database)")

    # Use scroll API to fetch all IDs efficiently
    all_ids = set()

    try:
        # Initial search with scroll
        response = await es_client.search(
            index=index_name,
            body=query,
            scroll="2m",  # Keep scroll context for 2 minutes
            size=10000,  # Max batch size
        )

        scroll_id = response.get("_scroll_id")
        hits = response.get("hits", {}).get("hits", [])

        # Collect IDs from first batch
        all_ids.update(hit["_id"] for hit in hits)

        # Continue scrolling if there are more results
        while len(hits) > 0:
            response = await es_client.scroll(
                scroll_id=scroll_id,
                scroll="2m",
            )

            scroll_id = response.get("_scroll_id")
            hits = response.get("hits", {}).get("hits", [])

            all_ids.update(hit["_id"] for hit in hits)

        # Clear scroll context
        if scroll_id:
            try:
                await es_client.clear_scroll(scroll_id=scroll_id)
            except Exception as e:
                logger.warning("Failed to clear scroll context: %s", e)

    except Exception as e:
        logger.error("Error fetching ES IDs: %s", e)
        raise

    return all_ids


async def _sync_missing_documents(
    mongo_repo: Any,
    es_client: Any,
    index_name: str,
    converter_class: Any,
    missing_ids: Set[str],
    doc_type: str,
    batch_size: int = 500,
) -> tuple[int, int]:
    """
    Sync missing documents to Elasticsearch

    Args:
        mongo_repo: MongoDB repository
        es_client: Elasticsearch async client
        index_name: ES index name
        converter_class: Converter class
        missing_ids: Set of missing document IDs
        doc_type: Document type name
        batch_size: Batch size for sync operations

    Returns:
        Tuple of (synced_count, error_count)
    """
    synced_count = 0
    error_count = 0

    # Convert set to list for batch processing
    missing_ids_list = list(missing_ids)

    async def generate_actions():
        """Generate ES bulk actions for missing documents"""
        nonlocal error_count

        for i in range(0, len(missing_ids_list), batch_size):
            batch_ids = missing_ids_list[i : i + batch_size]

            try:
                # Fetch documents from MongoDB
                from bson import ObjectId

                object_ids = [ObjectId(id_str) for id_str in batch_ids]

                query = mongo_repo.model.find({"_id": {"$in": object_ids}})
                mongo_docs = await query.to_list(length=None)

                if not mongo_docs:
                    logger.warning(
                        "No documents found in MongoDB for batch %d-%d",
                        i,
                        i + len(batch_ids),
                    )
                    error_count += len(batch_ids)
                    continue

                # Convert and yield ES actions
                for mongo_doc in mongo_docs:
                    try:
                        # Convert to ES document
                        es_doc = converter_class.from_mongo(mongo_doc)
                        src = es_doc.to_dict()
                        doc_id = es_doc.meta.id

                        # Yield bulk action
                        yield {
                            "retry_on_conflict": 3,
                            "_op_type": "update",
                            "_index": index_name,
                            "doc_as_upsert": True,
                            "_id": doc_id,
                            "doc": src,
                        }

                    except Exception as e:
                        logger.error(
                            "Failed to convert document: id=%s, error=%s",
                            getattr(mongo_doc, "id", "unknown"),
                            e,
                        )
                        error_count += 1
                        continue

            except Exception as e:
                logger.error(
                    "Error processing batch %d-%d: %s", i, i + len(batch_ids), e, exc_info=True
                )
                error_count += len(batch_ids)

    # Use bulk API to sync documents
    # Initialize outside try so the except block can reference len(actions) for BUG-2 fix
    actions = []
    try:
        # Collect all actions from generator
        async for action in generate_actions():
            actions.append(action)

        if not actions:
            logger.warning("No actions generated for %s", doc_type)
            # BUG-1 fix: preserve error_count from generation phase instead of returning (0, 0)
            return 0, error_count

        # Workaround: elasticsearch helpers (async_bulk, async_streaming_bulk) hang after bulk completes
        # Use raw client API instead
        body = []
        for action in actions:
            # Build bulk request body
            action_line = {action["_op_type"]: {"_index": action["_index"], "_id": action["_id"]}}
            if "retry_on_conflict" in action:
                action_line[action["_op_type"]]["retry_on_conflict"] = action["retry_on_conflict"]

            body.append(action_line)

            if action["_op_type"] == "update" and "doc" in action:
                body.append({"doc": action["doc"], "doc_as_upsert": action.get("doc_as_upsert", False)})
            elif "doc" in action:
                body.append(action["doc"])

        response = await es_client.bulk(body=body)

        # Process response
        # BUG-1 fix: use separate bulk counters so generation-phase errors in error_count are preserved
        bulk_synced = 0
        bulk_errors = 0

        if response and "items" in response:
            for item in response["items"]:
                for op_type, result in item.items():
                    if result.get("status", 0) in (200, 201):
                        bulk_synced += 1
                    else:
                        bulk_errors += 1
                        if bulk_errors <= 5:  # Log first 5 errors
                            logger.error("Bulk error: %s", result.get("error", result))

        synced_count += bulk_synced
        error_count += bulk_errors
        logger.info("Batch sync completed: %d documents synced", synced_count)

    except Exception as e:
        logger.error("Error during bulk sync for %s: %s", doc_type, e, exc_info=True)
        # BUG-2 fix: count all actions that failed to reach ES as errors
        error_count += len(actions)
        # Don't return here, continue to try refresh

    # Refresh index to make documents searchable
    try:
        await es_client.indices.refresh(index=index_name)
        logger.info("ES index refresh completed for %s", doc_type)
    except Exception as e:
        logger.error("Error refreshing ES index for %s: %s", doc_type, e, exc_info=True)

    return synced_count, error_count
