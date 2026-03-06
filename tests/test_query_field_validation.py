"""
Test automatic query field validation

Verify that the system correctly detects and reports when a query uses fields not in Lite storage.
"""

import pytest
import pytest_asyncio
import uuid
from datetime import datetime

from infra_layer.adapters.out.persistence.kv_storage.dual_storage_model_proxy import (
    LiteStorageQueryError,
)

# Mark all test functions in this module as asyncio tests
pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def memcell_repository():
    """Get MemCell repository instance"""
    from core.di import get_bean_by_type
    from infra_layer.adapters.out.persistence.repository.memcell_raw_repository import (
        MemCellRawRepository,
    )
    return get_bean_by_type(MemCellRawRepository)


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


@pytest.mark.asyncio
class TestQueryFieldValidation:
    """Test query field validation functionality"""

    async def test_query_with_valid_fields(self, memcell_repository, test_user_id):
        """
        Test: query with a valid field - should succeed

        user_id is an indexed field and should be queryable normally
        """
        # Should not raise an exception
        result = await memcell_repository.model.find_one({"user_id": test_user_id})
        # Result may be None (no data), but should not raise an exception
        assert True  # If we reach here without exception, the test passes

    async def test_query_with_invalid_field_raises_error(
        self, memcell_repository, test_user_id
    ):
        """
        Test: query with an invalid field - should raise LiteStorageQueryError

        Assumes 'invalid_field' is not in indexed_fields
        """
        with pytest.raises(LiteStorageQueryError) as exc_info:
            await memcell_repository.model.find_one({"invalid_field": "some_value"})

        # Verify error message contains key information
        error_msg = str(exc_info.value)
        assert "invalid_field" in error_msg
        assert "query_fields" in error_msg
        assert "Settings" in error_msg

    async def test_query_with_keywords_succeeds(self, memcell_repository, test_user_id):
        """
        Test: query with keywords field - should succeed

        keywords is in query_fields; though not indexed, it should be queryable
        """
        # Should not raise an exception (keywords is in query_fields)
        result = await memcell_repository.model.find_one(
            {"keywords": {"$in": ["test"]}}
        )
        # Result may be None (no data), but should not raise an exception
        assert True  # If we reach here without exception, the test passes

    async def test_error_message_provides_fix_instructions(
        self, memcell_repository, test_user_id
    ):
        """
        Test: error message provides clear fix guidance

        Verify error message contains:
        1. List of missing fields
        2. Instructions for how to fix
        3. Current indexed_fields
        """
        with pytest.raises(LiteStorageQueryError) as exc_info:
            await memcell_repository.model.find_one(
                {"unknown_field_1": "value1", "unknown_field_2": "value2"}
            )

        error_msg = str(exc_info.value)

        # Verify contains missing fields
        assert "unknown_field_1" in error_msg
        assert "unknown_field_2" in error_msg

        # Verify contains fix instructions
        assert "Settings" in error_msg
        assert "query_fields" in error_msg

        # Verify contains current indexed_fields information
        assert "Current indexed fields" in error_msg

    async def test_complex_query_validation(self, memcell_repository, test_user_id):
        """
        Test: field validation for complex query conditions

        Test queries containing logical operators such as $and, $or
        """
        # Valid complex query - should succeed
        try:
            await memcell_repository.model.find_one(
                {
                    "$and": [
                        {"user_id": test_user_id},
                        {"timestamp": {"$gt": datetime.now()}},
                    ]
                }
            )
            assert True  # No exception means success
        except LiteStorageQueryError:
            pytest.fail("Valid complex query should not raise error")

        # Complex query with invalid fields - should raise an exception
        with pytest.raises(LiteStorageQueryError) as exc_info:
            await memcell_repository.model.find_one(
                {
                    "$or": [
                        {"user_id": test_user_id},
                        {"invalid_field": "value"},
                    ]
                }
            )

        error_msg = str(exc_info.value)
        assert "invalid_field" in error_msg

    async def test_find_method_validation(self, memcell_repository, test_user_id):
        """
        Test: find() method also performs field validation
        """
        # Valid query - should succeed
        cursor = memcell_repository.model.find({"user_id": test_user_id})
        assert cursor is not None

        # Invalid query - should raise an exception
        with pytest.raises(LiteStorageQueryError):
            memcell_repository.model.find({"invalid_field": "value"})

    async def test_delete_many_validation(self, memcell_repository, test_user_id):
        """
        Test: delete_many() method also performs field validation
        """
        # Valid query - should succeed
        try:
            await memcell_repository.model.delete_many({"user_id": test_user_id})
            assert True
        except LiteStorageQueryError:
            pytest.fail("Valid delete_many should not raise error")

        # Invalid query - should raise an exception
        with pytest.raises(LiteStorageQueryError):
            await memcell_repository.model.delete_many({"invalid_field": "value"})
