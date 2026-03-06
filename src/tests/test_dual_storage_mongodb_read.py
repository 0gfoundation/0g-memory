#!/usr/bin/env python3
"""
Test data completeness when reading from MongoDB in dual storage mode

This test fully mimics the sync script's read approach to verify:
1. Whether data read via Repository.model.find().to_list() contains complete fields
2. 5 collections: episodic_memories, event_log_records, foresight_records, conversation_meta, memcells

Expected results:
- episodic_memories: should contain subject, summary, episode
- event_log_records: should contain atomic_fact
- foresight_records: should contain content/foresight
- conversation_meta: should contain complete data
- memcells: should contain summary, original_data

This verifies that DualStorageQueryProxy correctly loads complete data from KV-Storage
"""

import sys
import asyncio
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# IMPORTANT: Must setup environment and DI BEFORE importing repositories
from common_utils.load_env import setup_environment
setup_environment(load_env_file_name=".env", check_env_var="MONGODB_HOST")

# Setup all (DI container, etc.) - same as run.py
from application_startup import setup_all
setup_all(load_entrypoints=False)  # Don't load addons for testing

from core.di.utils import get_bean_by_type
from core.observation.logger import get_logger

logger = get_logger(__name__)


async def test_episodic_memory_read():
    """
    Test reading from the episodic_memories collection

    Fully mimics the read approach of milvus_sync_episodic_memory_docs.py
    """
    print("\n" + "="*80)
    print("Test 1: Episodic Memory Read")
    print("="*80)

    from infra_layer.adapters.out.persistence.repository.episodic_memory_raw_repository import (
        EpisodicMemoryRawRepository,
    )

    # Get Repository
    mongo_repo = get_bean_by_type(EpisodicMemoryRawRepository)

    # Use exactly the same read approach as the sync script
    # Note: sort by created_at descending to get the newest data first
    query = mongo_repo.model.find({}).sort("-created_at")  # Descending order to get newest
    mongo_docs = await query.limit(3).to_list()

    print(f"\n📊 Read {len(mongo_docs)} documents")

    if mongo_docs:
        print("\nChecking field completeness of the first document:")
        doc = mongo_docs[0]

        # Check key fields
        fields_to_check = {
            "id": getattr(doc, 'id', None),
            "subject": getattr(doc, 'subject', None),
            "summary": getattr(doc, 'summary', None),
            "episode": getattr(doc, 'episode', None),
            "user_id": getattr(doc, 'user_id', None),
            "group_id": getattr(doc, 'group_id', None),
            "timestamp": getattr(doc, 'timestamp', None),
            "vector": getattr(doc, 'vector', None),
        }

        for field_name, field_value in fields_to_check.items():
            has_value = field_value is not None
            value_preview = ""
            if has_value:
                if field_name == "vector":
                    value_preview = f"(vector length: {len(field_value)})" if field_value else ""
                elif isinstance(field_value, str) and len(field_value) > 50:
                    value_preview = f"'{field_value[:50]}...'"
                else:
                    value_preview = f"'{field_value}'"

            status = "✅" if has_value else "❌"
            print(f"  {status} {field_name:15s}: {'has value' if has_value else 'empty'} {value_preview}")

        # Key verification
        print("\n🎯 Key Verification:")
        if doc.subject and doc.summary and doc.episode:
            print("  ✅ PASS - contains complete content fields (subject, summary, episode)")
        else:
            print("  ❌ FAIL - missing content fields! This indicates Lite data was read")

    else:
        print("⚠️  Collection is empty, cannot test")


async def test_event_log_read():
    """
    Test reading from the event_log_records collection

    Fully mimics the sync script's read approach
    """
    print("\n" + "="*80)
    print("Test 2: Event Log Read")
    print("="*80)

    from infra_layer.adapters.out.persistence.repository.event_log_record_raw_repository import (
        EventLogRecordRawRepository,
    )

    # Get Repository
    mongo_repo = get_bean_by_type(EventLogRecordRawRepository)

    # Use exactly the same read approach as the sync script
    # Note: sort by created_at descending to get the newest data first
    query = mongo_repo.model.find({}).sort("-created_at")  # Descending order to get newest
    mongo_docs = await query.limit(3).to_list()

    print(f"\n📊 Read {len(mongo_docs)} documents")

    if mongo_docs:
        print("\nChecking field completeness of the first document:")
        doc = mongo_docs[0]

        # Check key fields
        fields_to_check = {
            "id": getattr(doc, 'id', None),
            "atomic_fact": getattr(doc, 'atomic_fact', None),
            "parent_type": getattr(doc, 'parent_type', None),
            "parent_id": getattr(doc, 'parent_id', None),
            "user_id": getattr(doc, 'user_id', None),
            "group_id": getattr(doc, 'group_id', None),
            "timestamp": getattr(doc, 'timestamp', None),
            "vector": getattr(doc, 'vector', None),
        }

        for field_name, field_value in fields_to_check.items():
            has_value = field_value is not None
            value_preview = ""
            if has_value:
                if field_name == "vector":
                    value_preview = f"(vector length: {len(field_value)})" if field_value else ""
                elif isinstance(field_value, str) and len(field_value) > 50:
                    value_preview = f"'{field_value[:50]}...'"
                else:
                    value_preview = f"'{field_value}'"

            status = "✅" if has_value else "❌"
            print(f"  {status} {field_name:15s}: {'has value' if has_value else 'empty'} {value_preview}")

        # Key verification
        print("\n🎯 Key Verification:")
        if doc.atomic_fact:
            print("  ✅ PASS - contains complete content field (atomic_fact)")
        else:
            print("  ❌ FAIL - missing atomic_fact field! This indicates Lite data was read")

    else:
        print("⚠️  Collection is empty, cannot test")


async def test_foresight_read():
    """
    Test reading from the foresight_records collection

    Fully mimics the sync script's read approach
    """
    print("\n" + "="*80)
    print("Test 3: Foresight Read")
    print("="*80)

    from infra_layer.adapters.out.persistence.repository.foresight_record_repository import (
        ForesightRecordRawRepository,
    )

    # Get Repository
    mongo_repo = get_bean_by_type(ForesightRecordRawRepository)

    # Use exactly the same read approach as the sync script
    # Note: sort by created_at descending to get the newest data first
    query = mongo_repo.model.find({}).sort("-created_at")  # Descending order to get newest
    mongo_docs = await query.limit(3).to_list()

    print(f"\n📊 Read {len(mongo_docs)} documents")

    if mongo_docs:
        print("\nChecking field completeness of the first document:")
        doc = mongo_docs[0]

        # Check key fields
        fields_to_check = {
            "id": getattr(doc, 'id', None),
            "content": getattr(doc, 'content', None),
            "evidence": getattr(doc, 'evidence', None),
            "parent_type": getattr(doc, 'parent_type', None),
            "parent_id": getattr(doc, 'parent_id', None),
            "user_id": getattr(doc, 'user_id', None),
            "group_id": getattr(doc, 'group_id', None),
            "start_time": getattr(doc, 'start_time', None),
            "vector": getattr(doc, 'vector', None),
        }

        for field_name, field_value in fields_to_check.items():
            has_value = field_value is not None
            value_preview = ""
            if has_value:
                if field_name == "vector":
                    value_preview = f"(vector length: {len(field_value)})" if field_value else ""
                elif isinstance(field_value, str) and len(field_value) > 50:
                    value_preview = f"'{field_value[:50]}...'"
                else:
                    value_preview = f"'{field_value}'"

            status = "✅" if has_value else "❌"
            print(f"  {status} {field_name:15s}: {'has value' if has_value else 'empty'} {value_preview}")

        # Key verification
        print("\n🎯 Key Verification:")
        if doc.content:
            print("  ✅ PASS - contains complete content field (content)")
        else:
            print("  ❌ FAIL - missing content field! This indicates Lite data was read")

    else:
        print("⚠️  Collection is empty, cannot test")


async def test_conversation_meta_read():
    """
    Test reading from the conversation_meta collection

    Fully mimics the sync script's read approach
    """
    print("\n" + "="*80)
    print("Test 4: Conversation Meta Read")
    print("="*80)

    from infra_layer.adapters.out.persistence.repository.conversation_meta_raw_repository import (
        ConversationMetaRawRepository,
    )

    # Get Repository
    mongo_repo = get_bean_by_type(ConversationMetaRawRepository)

    # Use exactly the same read approach as the sync script
    # Note: sort by created_at descending to get the newest data first
    query = mongo_repo.model.find({}).sort("-created_at")  # Descending order to get newest
    mongo_docs = await query.limit(3).to_list()

    print(f"\n📊 Read {len(mongo_docs)} documents")

    if mongo_docs:
        print("\nChecking field completeness of the first document:")
        doc = mongo_docs[0]

        # Check key fields
        fields_to_check = {
            "id": getattr(doc, 'id', None),
            "group_id": getattr(doc, 'group_id', None),
            "name": getattr(doc, 'name', None),
            "description": getattr(doc, 'description', None),
            "user_details": getattr(doc, 'user_details', None),
            "tags": getattr(doc, 'tags', None),
            "created_at": getattr(doc, 'created_at', None),
        }

        for field_name, field_value in fields_to_check.items():
            has_value = field_value is not None
            value_preview = ""
            if has_value:
                if field_name == "user_details":
                    value_preview = f"(dict length: {len(field_value)})" if isinstance(field_value, dict) else ""
                elif field_name == "tags":
                    value_preview = f"(list length: {len(field_value)})" if isinstance(field_value, list) else ""
                elif isinstance(field_value, str) and len(field_value) > 50:
                    value_preview = f"'{field_value[:50]}...'"
                else:
                    value_preview = f"'{field_value}'"

            status = "✅" if has_value else "❌"
            print(f"  {status} {field_name:20s}: {'has value' if has_value else 'empty'} {value_preview}")

        # Key verification
        print("\n🎯 Key Verification:")
        has_description = getattr(doc, 'description', None) is not None and doc.description
        has_user_details = getattr(doc, 'user_details', None) is not None and doc.user_details
        has_tags = getattr(doc, 'tags', None) is not None and doc.tags

        if has_description or has_user_details or has_tags:
            print(f"  ✅ PASS - contains complete data fields (description: {has_description}, user_details: {has_user_details}, tags: {has_tags})")
        else:
            print("  ❌ FAIL - missing data fields!")

    else:
        print("⚠️  Collection is empty, cannot test")


async def test_memcell_read():
    """
    Test reading from the memcells collection

    Fully mimics the sync script's read approach
    """
    print("\n" + "="*80)
    print("Test 5: MemCell Read")
    print("="*80)

    from infra_layer.adapters.out.persistence.repository.memcell_raw_repository import (
        MemCellRawRepository,
    )

    # Get Repository
    mongo_repo = get_bean_by_type(MemCellRawRepository)

    # Use exactly the same read approach as the sync script
    # Note: sort by created_at descending to get the newest data first
    query = mongo_repo.model.find({}).sort("-created_at")  # Descending order to get newest
    mongo_docs = await query.limit(3).to_list()

    print(f"\n📊 Read {len(mongo_docs)} documents")

    if mongo_docs:
        print("\nChecking field completeness of the first document:")
        doc = mongo_docs[0]

        # Check key fields
        fields_to_check = {
            "id": getattr(doc, 'id', None),
            "user_id": getattr(doc, 'user_id', None),
            "group_id": getattr(doc, 'group_id', None),
            "timestamp": getattr(doc, 'timestamp', None),
            "summary": getattr(doc, 'summary', None),
            "original_data": getattr(doc, 'original_data', None),
            "subject": getattr(doc, 'subject', None),
            "episode": getattr(doc, 'episode', None),
            "participants": getattr(doc, 'participants', None),
        }

        for field_name, field_value in fields_to_check.items():
            has_value = field_value is not None
            value_preview = ""
            if has_value:
                if field_name == "original_data":
                    value_preview = f"(list length: {len(field_value)})" if isinstance(field_value, list) else ""
                elif field_name == "participants":
                    value_preview = f"(list length: {len(field_value)})" if isinstance(field_value, list) else ""
                elif isinstance(field_value, str) and len(field_value) > 50:
                    value_preview = f"'{field_value[:50]}...'"
                else:
                    value_preview = f"'{field_value}'"

            status = "✅" if has_value else "❌"
            print(f"  {status} {field_name:20s}: {'has value' if has_value else 'empty'} {value_preview}")

        # Key verification
        print("\n🎯 Key Verification:")
        has_summary = getattr(doc, 'summary', None) is not None and doc.summary
        has_original_data = getattr(doc, 'original_data', None) is not None and doc.original_data

        if has_summary or has_original_data:
            print(f"  ✅ PASS - contains complete data fields (summary: {has_summary}, original_data: {has_original_data})")
        else:
            print("  ❌ FAIL - missing data fields!")

    else:
        print("⚠️  Collection is empty, cannot test")


async def main():
    """Main test function"""
    print("\n" + "🔬" * 40)
    print("Dual Storage Mode - MongoDB Read Completeness Test")
    print("Verifying data completeness by mimicking sync script read approach")
    print("🔬" * 40)

    try:
        # Test all collections
        await test_episodic_memory_read()
        await test_event_log_read()
        await test_foresight_read()
        await test_conversation_meta_read()
        await test_memcell_read()

        # Final summary
        print("\n" + "="*80)
        print("Test Summary")
        print("="*80)
        print("""
If all tests show ✅ PASS:
  → DualStorageQueryProxy is working correctly, loading full data from KV-Storage
  → Sync scripts can correctly read full data and sync to Milvus/ES

If any test shows ❌ FAIL:
  → DualStorageQueryProxy may have an issue
  → Or data was created before dual storage was enabled (only Lite data exists)
  → Suggestion: re-run the demo to create new data, then test again
        """)

    except Exception as e:
        logger.error(f"Error during testing: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    asyncio.run(main())
