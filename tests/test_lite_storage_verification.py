#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Lite Storage Verification

Verify that MongoDB stores only Lite data (indexed fields) and full data is stored in KV-Storage
"""

import asyncio
import pytest
import pytest_asyncio
import uuid
from typing import TYPE_CHECKING

# Mark all test functions in this module as asyncio tests
pytestmark = pytest.mark.asyncio

if TYPE_CHECKING:
    from infra_layer.adapters.out.persistence.repository.episodic_memory_raw_repository import (
        EpisodicMemoryRawRepository,
    )


@pytest_asyncio.fixture
async def repository():
    """Get repository instance"""
    from core.di import get_bean_by_type
    from infra_layer.adapters.out.persistence.repository.episodic_memory_raw_repository import (
        EpisodicMemoryRawRepository,
    )
    return get_bean_by_type(EpisodicMemoryRawRepository)


@pytest_asyncio.fixture
async def kv_storage():
    """Get KV-Storage instance"""
    from core.di import get_bean_by_type
    from infra_layer.adapters.out.persistence.kv_storage.kv_storage_interface import (
        KVStorageInterface,
    )
    return get_bean_by_type(KVStorageInterface)


@pytest.fixture
def test_user_id():
    """Generate unique test user ID"""
    return f"test_user_{uuid.uuid4().hex[:8]}"


def create_test_episodic_memory(user_id: str):
    """Helper to create test EpisodicMemory with sensitive data"""
    from common_utils.datetime_utils import get_now_with_timezone
    from infra_layer.adapters.out.persistence.document.memory.episodic_memory import (
        EpisodicMemory,
    )

    return EpisodicMemory(
        user_id=user_id,
        timestamp=get_now_with_timezone(),
        summary="🔒 This is SENSITIVE summary data - should ONLY be in KV!",
        episode="🔒 This is SENSITIVE episode content - should ONLY be in KV!",
        user_name=f"TestUser_{user_id[-8:]}",
        group_id=f"group_{user_id}",
        group_name="TestGroup",
        participants=[user_id, "Alice", "Bob"],
        type="Conversation",
        subject="Secret Meeting Discussion",
        keywords=["security", "confidential"],  # Indexed field, should be in MongoDB
        linked_entities=[f"entity_{uuid.uuid4().hex[:8]}"],  # Indexed field
        extend={"secret_key": "sensitive_value"},  # Should exist only in KV
    )


def get_logger():
    """Helper to get logger"""
    from core.observation.logger import get_logger as _get_logger
    return _get_logger(__name__)


class TestLiteStorageVerification:
    """Verify Lite storage approach: MongoDB stores only indexed fields, KV stores full data"""

    async def test_mongodb_only_stores_lite_data(self, repository, kv_storage, test_user_id):
        """
        Core verification: MongoDB stores only Lite data (indexed fields), sensitive fields only in KV

        Verification points:
        1. Create a document containing sensitive fields
        2. Query MongoDB raw data directly
        3. Confirm sensitive fields are None in MongoDB
        4. Confirm KV-Storage has full data
        """
        logger = get_logger()
        logger.info("=" * 80)
        logger.info("🔍 CRITICAL TEST: Verify MongoDB ONLY stores Lite data")

        # 1. Create a document containing sensitive data
        test_data = create_test_episodic_memory(user_id=test_user_id)
        logger.info(f"📝 Creating document with SENSITIVE data...")
        logger.info(f"   - summary: {test_data.summary}")
        logger.info(f"   - episode: {test_data.episode}")
        logger.info(f"   - extend: {test_data.extend}")

        # 2. Save the document (should trigger Lite storage)
        created = await repository.append_episodic_memory(test_data)
        assert created is not None
        doc_id = str(created.id)
        logger.info(f"✅ Document created: {doc_id}")

        # 3. Query directly from MongoDB raw collection (bypassing Proxy)
        from infra_layer.adapters.out.persistence.document.memory.episodic_memory import (
            EpisodicMemory,
        )
        from bson import ObjectId

        mongo_collection = EpisodicMemory.get_pymongo_collection()
        raw_mongo_doc = await mongo_collection.find_one({"_id": ObjectId(doc_id)})

        assert raw_mongo_doc is not None, "Document should exist in MongoDB"
        logger.info(f"📋 Raw MongoDB document fields: {list(raw_mongo_doc.keys())}")

        # 4. Verify that sensitive fields are None or absent in MongoDB
        sensitive_fields = ["summary", "episode", "user_name", "group_name", "participants", "type", "subject", "extend"]

        logger.info(f"\n🔍 Checking SENSITIVE fields in MongoDB:")
        for field_name in sensitive_fields:
            mongo_value = raw_mongo_doc.get(field_name)
            if field_name in ["keywords", "linked_entities"]:
                # These are indexed fields, should be present in MongoDB
                assert mongo_value is not None, f"Indexed field '{field_name}' should be in MongoDB"
                logger.info(f"   ✅ {field_name}: {mongo_value} (indexed field, OK in MongoDB)")
            else:
                # Sensitive fields should be None or absent
                assert mongo_value is None or mongo_value == {}, f"❌ SECURITY RISK: '{field_name}' should NOT be in MongoDB! Got: {mongo_value}"
                logger.info(f"   ✅ {field_name}: None (SECURE - not in MongoDB)")

        # 5. Verify KV-Storage has full data
        kv_value = await kv_storage.get(doc_id)
        assert kv_value is not None, "KV-Storage should have full data"

        kv_doc = EpisodicMemory.model_validate_json(kv_value)
        logger.info(f"\n🔐 Checking FULL data in KV-Storage:")

        # Verify sensitive data is in KV
        assert kv_doc.summary == test_data.summary, "Summary should be in KV"
        assert kv_doc.episode == test_data.episode, "Episode should be in KV"
        assert kv_doc.extend == test_data.extend, "Extend should be in KV"
        logger.info(f"   ✅ summary: {kv_doc.summary}")
        logger.info(f"   ✅ episode: {kv_doc.episode[:50]}...")
        logger.info(f"   ✅ extend: {kv_doc.extend}")

        # 6. Verify indexed fields are present in both MongoDB and KV
        assert raw_mongo_doc.get("keywords") == test_data.keywords, "Keywords should be in MongoDB"
        assert kv_doc.keywords == test_data.keywords, "Keywords should also be in KV"
        logger.info(f"\n✅ Indexed fields present in BOTH MongoDB and KV:")
        logger.info(f"   - keywords: {test_data.keywords}")

        logger.info(f"\n" + "=" * 80)
        logger.info(f"✅ ✅ ✅ SECURITY VERIFIED ✅ ✅ ✅")
        logger.info(f"   MongoDB: ONLY indexed fields (Lite data)")
        logger.info(f"   KV-Storage: FULL data including sensitive fields")
        logger.info(f"=" * 80)

        # Cleanup
        await repository.delete_by_event_id(doc_id, test_user_id)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
