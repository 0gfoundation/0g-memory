"""
Dual Storage Model Proxy - MongoDB call interception layer (Lite storage approach)

Dual storage implemented by intercepting all MongoDB calls on self.model. Zero Repository code changes.

How it works:
1. Indexed fields are extracted automatically from Document at runtime (no manual Lite class maintenance)
2. On write:
   - MongoDB stores only Lite version (indexed fields) - for queries
   - KV-Storage stores full data (encrypted) - for data reads
3. On query:
   - MongoDB query returns Lite data (with ID)
   - Full data is batch-loaded from KV-Storage by ID
4. Security: sensitive fields exist only in KV-Storage, not in MongoDB

Advantages:
- Zero changes needed to Repository code
- Indexed fields are extracted automatically; no code change when third parties modify indexes
- Sensitive data is stored only in KV-Storage (encrypted), improving security
"""

from typing import TYPE_CHECKING, Optional, Any, List, Set
from pymongo.asynchronous.client_session import AsyncClientSession
from pydantic import BaseModel, ConfigDict, Field
from beanie import PydanticObjectId

from core.observation.logger import get_logger
from infra_layer.adapters.out.persistence.kv_storage.lite_model_extractor import (
    LiteModelExtractor,
)

if TYPE_CHECKING:
    from infra_layer.adapters.out.persistence.kv_storage.kv_storage_interface import (
        KVStorageInterface,
    )

logger = get_logger(__name__)


class LiteStorageQueryError(Exception):
    """Exception raised when query uses fields not available in Lite storage"""
    pass


def get_kv_key(document_class_or_instance, doc_id: str) -> str:
    """
    Generate KV-Storage key with collection_name prefix

    Key Format: {collection_name}:{document_id}
    Example: "episodic_memories:6979da5797f9041fc0aa063f"

    Args:
        document_class_or_instance: Document class or instance (Beanie Document)
        doc_id: Document ID (ObjectId as string)

    Returns:
        Full key with collection prefix
    """
    try:
        # Check if it's a class or instance
        # NOTE: Can't use hasattr(..., '__class__') because classes also have __class__ (their metaclass)!
        import inspect
        if inspect.isclass(document_class_or_instance):
            # Already a class
            doc_class = document_class_or_instance
        else:
            # Instance: get class
            doc_class = document_class_or_instance.__class__

        # Get collection name from Settings
        collection_name = doc_class.Settings.name

        # Generate prefixed key
        kv_key = f"{collection_name}:{doc_id}"
        return kv_key
    except Exception as e:
        # Fallback: use doc_id only (backward compatible)
        logger.warning(f"Failed to get collection name, using doc_id only: {e}")
        return doc_id


# Minimal projection model for queries - only returns _id
class IdOnlyProjection(BaseModel):
    """Minimal projection to only retrieve document IDs from MongoDB"""
    # MongoDB uses _id, Beanie Documents map it to id
    # For projection models, we need to handle _id directly
    id: Optional[PydanticObjectId] = Field(None, alias="_id")

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class FindOneQueryProxy:
    """
    FindOne Query Proxy - supports find_one().delete() chaining and direct await

    Wraps DualStorageModelProxy's find_one logic, supporting:
    1. Direct await: await find_one(...) -> Document
    2. Chained delete: await find_one(...).delete() -> DeleteResult

    Ensures delete operations trigger DualStorageMixin's KV sync
    """

    def __init__(
        self,
        original_model,
        kv_storage: "KVStorageInterface",
        full_model_class,
        indexed_fields: Set[str],
        filter_args,
        filter_kwargs,
    ):
        """
        Initialize find_one query proxy

        Args:
            original_model: Original Beanie model class
            kv_storage: KV-Storage instance
            full_model_class: Full model class
            indexed_fields: Set of indexed field names
            filter_args: Positional arguments from find_one(*args)
            filter_kwargs: Keyword arguments from find_one(**kwargs)
        """
        self._original_model = original_model
        self._kv_storage = kv_storage
        self._full_model_class = full_model_class
        self._indexed_fields = indexed_fields
        self._filter_args = filter_args
        self._filter_kwargs = filter_kwargs

    def __await__(self):
        """
        Support direct await: doc = await find_one(...)

        Returns full document from KV-Storage
        """
        return self._execute_find_one().__await__()

    async def _execute_find_one(self):
        """
        Execute find_one query and return document from KV-Storage

        This is the core logic that both __await__ and delete() use
        """
        try:
            # Detect whether dict query syntax is used
            is_dict_syntax = self._filter_args and isinstance(self._filter_args[0], dict)

            if is_dict_syntax:
                # Dict syntax: validate query fields and use PyMongo
                filter_query = self._filter_args[0]
                self._validate_query_fields(filter_query)

                mongo_collection = self._original_model.get_pymongo_collection()
                session = self._filter_kwargs.get("session", None)
                lite_doc = await mongo_collection.find_one(filter_query, session=session)
            else:
                # Beanie operator syntax: use Beanie's native find_one
                lite_doc = await self._original_model.find_one(
                    *self._filter_args,
                    projection_model=IdOnlyProjection,
                    **self._filter_kwargs
                )

                # Convert IdOnlyProjection objects to dict format
                if lite_doc:
                    lite_doc = {"_id": lite_doc.id}

            if not lite_doc:
                return None

            # Load full data from KV-Storage
            doc_id = str(lite_doc["_id"])
            kv_key = get_kv_key(self._full_model_class, doc_id)
            kv_value = await self._kv_storage.get(key=kv_key)

            if kv_value:
                full_doc = self._full_model_class.model_validate_json(kv_value)
                logger.debug(f"✅ find_one loaded from KV: {doc_id}")
                return full_doc
            else:
                # KV miss - cannot recover full data
                logger.warning(f"⚠️  KV miss in find_one for {doc_id}")
                return None

        except LiteStorageQueryError:
            # Re-raise query field validation errors
            raise
        except Exception as e:
            logger.error(f"❌ Failed in find_one: {e}")
            return None

    def _extract_query_fields(self, filter_dict: Any) -> Set[str]:
        """Recursively extract all field names used in query conditions (same logic as DualStorageModelProxy)"""
        fields = set()
        if not isinstance(filter_dict, dict):
            return fields

        for key, value in filter_dict.items():
            if key.startswith("$"):
                if isinstance(value, list):
                    for sub_condition in value:
                        fields.update(self._extract_query_fields(sub_condition))
                elif isinstance(value, dict):
                    fields.update(self._extract_query_fields(value))
            else:
                fields.add(key)

        return fields

    def _validate_query_fields(self, filter_dict: Any) -> None:
        """Validate that query fields are available in Lite data (same logic as DualStorageModelProxy)"""
        if not filter_dict:
            return

        queried_fields = self._extract_query_fields(filter_dict)
        if not queried_fields:
            return

        # MongoDB field alias mapping: _id -> id
        normalized_queried_fields = set()
        for field in queried_fields:
            if field == "_id":
                normalized_queried_fields.add("id")
            else:
                normalized_queried_fields.add(field)

        # Check if any fields are not in indexed_fields
        missing_fields = normalized_queried_fields - self._indexed_fields

        if missing_fields:
            error_msg = (
                f"❌ Query uses fields not available in Lite storage: {sorted(missing_fields)}\n\n"
                f"These fields are not indexed and not in query_fields.\n"
                f"In Lite storage mode, MongoDB only stores indexed fields and query_fields.\n\n"
                f"To fix this issue, add these fields to Settings.query_fields in {self._full_model_class.__name__}:\n\n"
                f"  class Settings:\n"
                f"      query_fields = {sorted(list(missing_fields))}\n\n"
                f"Current indexed fields: {sorted(self._indexed_fields)}\n"
                f"Queried fields: {sorted(normalized_queried_fields)}\n"
            )
            raise LiteStorageQueryError(error_msg)

    async def delete(self, *args, **kwargs):
        """
        Execute find_one and delete the result

        Supports chaining: await find_one(...).delete()

        Returns:
            Delete result with deleted_count
        """
        try:
            # 1. Execute find_one to get document ID only
            is_dict_syntax = self._filter_args and isinstance(self._filter_args[0], dict)

            if is_dict_syntax:
                # Dict syntax
                filter_query = self._filter_args[0]
                self._validate_query_fields(filter_query)

                mongo_collection = self._original_model.get_pymongo_collection()
                session = self._filter_kwargs.get("session", None)
                lite_doc = await mongo_collection.find_one(filter_query, {"_id": 1}, session=session)
            else:
                # Beanie operator syntax
                lite_doc = await self._original_model.find_one(
                    *self._filter_args,
                    projection_model=IdOnlyProjection,
                    **self._filter_kwargs
                )
                if lite_doc:
                    lite_doc = {"_id": lite_doc.id}

            if not lite_doc:
                # No document found
                class DeleteResult:
                    deleted_count = 0
                return DeleteResult()

            doc_id = str(lite_doc["_id"])
            kv_key = get_kv_key(self._original_model, doc_id)

            # 2. Delete from MongoDB
            if is_dict_syntax:
                from bson import ObjectId
                delete_result = await mongo_collection.delete_one(
                    {"_id": ObjectId(doc_id)},
                    session=self._filter_kwargs.get("session", None)
                )
            else:
                # Use Beanie's find_one().delete()
                delete_query = self._original_model.find_one(*self._filter_args, **self._filter_kwargs)
                delete_result = await delete_query.delete(*args, **kwargs)

            # 3. Delete from KV-Storage
            if delete_result and hasattr(delete_result, 'deleted_count') and delete_result.deleted_count > 0:
                try:
                    await self._kv_storage.delete(key=kv_key)
                    logger.debug(f"✅ Deleted document {kv_key} from KV-Storage via find_one().delete()")
                except Exception as e:
                    logger.warning(f"⚠️  Failed to delete from KV-Storage: {e}")

            return delete_result

        except Exception as e:
            logger.error(f"❌ Failed to delete via find_one: {e}")
            raise


class DualStorageQueryProxy:
    """
    Query Cursor Proxy - intercepts MongoDB query cursor operations

    Intercepts the Cursor object returned by find(), automatically loading full data from KV-Storage.
    MongoDB returns only Lite data (ID + indexed fields); full data is loaded from KV.
    """

    def __init__(
        self,
        mongo_cursor,
        kv_storage: "KVStorageInterface",
        full_model_class,
    ):
        """
        Initialize query cursor proxy

        Args:
            mongo_cursor: MongoDB query cursor (from model.find())
            kv_storage: KV-Storage instance
            full_model_class: Full model class (e.g., EpisodicMemory)
        """
        self._mongo_cursor = mongo_cursor
        self._kv_storage = kv_storage
        self._full_model_class = full_model_class

    def sort(self, *args, **kwargs):
        """Proxy sort method"""
        self._mongo_cursor = self._mongo_cursor.sort(*args, **kwargs)
        return self

    def skip(self, *args, **kwargs):
        """Proxy skip method"""
        self._mongo_cursor = self._mongo_cursor.skip(*args, **kwargs)
        return self

    def limit(self, *args, **kwargs):
        """Proxy limit method"""
        self._mongo_cursor = self._mongo_cursor.limit(*args, **kwargs)
        return self

    async def to_list(self, *args, **kwargs) -> List[Any]:
        """
        Execute query and load full data from KV-Storage (Lite storage mode)

        Lite storage mode:
        1. Query MongoDB directly via PyMongo to get Lite data (raw dict, avoiding Beanie validation)
        2. Extract all IDs
        3. Batch-load full data from KV-Storage

        Returns:
            List of full model instances (from KV-Storage)
        """
        try:
            # 1. Use Beanie's project() to return only _id field
            # Use IdOnlyProjection model to avoid full Document validation

            # Add projection: return only _id field (using Pydantic model)
            projected_cursor = self._mongo_cursor.project(IdOnlyProjection)

            # Execute query to get IdOnlyProjection object list
            length = kwargs.get("length", None) or (args[0] if args else None)
            id_projections = await projected_cursor.to_list(length=length)

            if not id_projections:
                return []

            # 2. Extract all document IDs from projection objects
            try:
                doc_ids = [str(proj.id) for proj in id_projections if proj.id]
                logger.debug(f"📋 Query returned {len(doc_ids)} IDs from MongoDB")
            except Exception as e:
                logger.error(f"❌ Failed to extract IDs: {e}, projections type={type(id_projections)}, first item={id_projections[0] if id_projections else 'empty'}")
                return []

            # 3. Batch-load full data from KV-Storage
            full_docs = []
            for doc_id in doc_ids:
                try:
                    kv_key = get_kv_key(self._full_model_class, doc_id)
                    kv_value = await self._kv_storage.get(key=kv_key)
                    if kv_value:
                        # Deserialize full data from KV
                        full_doc = self._full_model_class.model_validate_json(kv_value)
                        full_docs.append(full_doc)
                    else:
                        # KV miss - cannot recover full data in Lite mode
                        logger.warning(f"⚠️  KV miss for {doc_id} - cannot return full document")
                        # Skip this document (cannot build full document from MongoDB Lite data)
                except Exception as e:
                    logger.error(f"❌ Failed to load from KV for {doc_id}: {e}")

            logger.debug(f"✅ Loaded {len(full_docs)}/{len(doc_ids)} full documents from KV-Storage")
            return full_docs

        except Exception as e:
            import traceback
            logger.error(f"❌ Failed in to_list: {e}\n{traceback.format_exc()}")
            return []

    async def delete(self, *args, **kwargs):
        """
        Delete documents matching query (Lite storage mode)

        Lite mode: use project() to get IDs, avoiding Beanie validation

        Also deletes from KV-Storage
        """
        try:
            # 1. Use project() to get IDs of documents to delete (avoiding Beanie validation)
            projected_cursor = self._mongo_cursor.project(IdOnlyProjection)
            id_projections = await projected_cursor.to_list(length=None)
            doc_ids = [str(proj.id) for proj in id_projections if proj.id]

            # 2. Delete from MongoDB
            result = await self._mongo_cursor.delete(*args, **kwargs)

            # 3. Batch-delete from KV-Storage
            if doc_ids:
                try:
                    kv_keys = [get_kv_key(self._full_model_class, doc_id) for doc_id in doc_ids]
                    await self._kv_storage.batch_delete(keys=kv_keys)
                    logger.debug(f"✅ Deleted {len(doc_ids)} documents from KV-Storage")
                except Exception as e:
                    logger.warning(f"⚠️  Failed to delete from KV-Storage: {e}")

            return result

        except Exception as e:
            logger.error(f"❌ Failed to delete with dual storage: {e}")
            raise

    async def count(self, *args, **kwargs):
        """Proxy count method to original cursor"""
        return await self._mongo_cursor.count(*args, **kwargs)

    async def update_many(self, update_data: dict, **kwargs):
        """
        Update documents matching query - batch update on Cursor with KV-Storage sync

        This is update_many() called on the Cursor returned by find(), distinct from model.update_many().
        Example: await model.find({"user_id": "123"}).update_many({"$set": {"field": "value"}})

        Args:
            update_data: Update operations (e.g., {"$set": {"field": value}})
            **kwargs: Additional options (e.g., session)

        Returns:
            Update result with modified_count
        """
        try:
            # 1. Get IDs of documents to update (using project to avoid Beanie validation)
            projected_cursor = self._mongo_cursor.project(IdOnlyProjection)
            id_projections = await projected_cursor.to_list(length=None)
            doc_ids = [str(proj.id) for proj in id_projections if proj.id]

            if not doc_ids:
                # No documents to update
                class UpdateResult:
                    modified_count = 0
                return UpdateResult()

            # 1.5. Auto-set updated_at if document has this field (AuditBase)
            from common_utils.datetime_utils import get_now_with_timezone
            if hasattr(self._full_model_class, 'model_fields') and 'updated_at' in self._full_model_class.model_fields:
                # Add updated_at to $set operator
                if "$set" not in update_data:
                    update_data = {"$set": {}}
                update_data["$set"]["updated_at"] = get_now_with_timezone()

            # 2. Execute MongoDB batch update
            result = await self._mongo_cursor.update_many(update_data, **kwargs)

            # 3. Sync to KV-Storage
            if result and result.modified_count > 0:
                import json
                from bson import ObjectId
                from datetime import datetime

                def json_serializer(obj):
                    """Custom JSON serializer for ObjectId and datetime"""
                    if isinstance(obj, ObjectId):
                        return str(obj)
                    elif isinstance(obj, datetime):
                        return obj.isoformat()
                    raise TypeError(f"Type {type(obj)} not serializable")

                # Extract update fields from $set operator
                update_fields = {}
                if "$set" in update_data:
                    update_fields = update_data["$set"]
                else:
                    logger.warning(f"⚠️  Cursor.update_many() only supports $set operator, got: {update_data.keys()}")

                # Update each document in KV-Storage
                for doc_id in doc_ids:
                    try:
                        # Generate KV key with collection prefix
                        kv_key = get_kv_key(self._full_model_class, doc_id)
                        # Load existing full data from KV
                        kv_value = await self._kv_storage.get(key=kv_key)
                        if kv_value:
                            # Parse existing data
                            full_data = json.loads(kv_value)
                            # Apply update fields
                            full_data.update(update_fields)
                            # Write back to KV
                            kv_value = json.dumps(full_data, default=json_serializer)
                            await self._kv_storage.put(key=kv_key, value=kv_value)
                        else:
                            logger.warning(f"⚠️  KV miss for {doc_id}, cannot update")
                    except Exception as e:
                        logger.warning(f"⚠️  Failed to sync to KV-Storage for {doc_id}: {e}")

                logger.debug(f"✅ Cursor.update_many() updated {result.modified_count} documents in MongoDB and KV-Storage")

            return result

        except Exception as e:
            logger.error(f"❌ Failed to update_many on cursor with dual storage: {e}")
            raise

    def __getattr__(self, name):
        """Proxy all other methods to original cursor"""
        return getattr(self._mongo_cursor, name)


class DualStorageModelProxy:
    """
    Model Proxy - intercepts MongoDB Model layer calls (Lite storage approach)

    Replaces Repository's self.model and intercepts all MongoDB operations:
    - Indexed fields extracted at runtime (auto-adapts to third-party changes)
    - find() -> returns QueryProxy (loads full data from KV)
    - get() -> reads full data from KV first
    - write -> MongoDB stores Lite only, KV stores full
    """

    def __init__(
        self,
        original_model,
        kv_storage: "KVStorageInterface",
        full_model_class,
    ):
        """
        Initialize model proxy and extract indexed fields

        Args:
            original_model: Original Beanie Document model class
            kv_storage: KV-Storage instance
            full_model_class: Full model class (same as original_model)
        """
        self._original_model = original_model
        self._kv_storage = kv_storage
        self._full_model_class = full_model_class

        # Automatically extract indexed fields at runtime (no manual Lite class maintenance)
        self._indexed_fields = LiteModelExtractor.extract_indexed_fields(full_model_class)
        logger.info(
            f"🔍 Auto-extracted {len(self._indexed_fields)} indexed fields for {full_model_class.__name__}"
        )

    def _extract_query_fields(self, filter_dict: Any) -> Set[str]:
        """
        Recursively extract all field names used in query conditions

        Supports:
        - Simple queries: {"user_id": "123"}
        - Operator queries: {"timestamp": {"$gt": date}}
        - Logical operators: {"$and": [...], "$or": [...]}
        - Array operators: {"keywords": {"$in": [...]}}

        Args:
            filter_dict: MongoDB filter query

        Returns:
            Set[str]: all field names used in the query
        """
        fields = set()

        if not isinstance(filter_dict, dict):
            return fields

        for key, value in filter_dict.items():
            # Skip MongoDB operators (prefixed with $)
            if key.startswith("$"):
                # For logical operators like $and, $or, recursively extract sub-conditions
                if isinstance(value, list):
                    for sub_condition in value:
                        fields.update(self._extract_query_fields(sub_condition))
                elif isinstance(value, dict):
                    fields.update(self._extract_query_fields(value))
            else:
                # This is an actual field name
                fields.add(key)

        return fields

    def _validate_query_fields(self, filter_dict: Any) -> None:
        """
        Validate that query fields are available in Lite data

        Raises a clear error if the query uses non-Lite fields

        Args:
            filter_dict: MongoDB filter query

        Raises:
            LiteStorageQueryError: if a query field is not in Lite storage
        """
        if not filter_dict:
            return

        # Extract all query fields
        queried_fields = self._extract_query_fields(filter_dict)

        if not queried_fields:
            return

        # MongoDB field alias mapping: _id -> id
        # MongoDB uses _id internally, but Beanie maps it to id
        normalized_queried_fields = set()
        for field in queried_fields:
            if field == "_id":
                # _id is an alias for id, always available
                normalized_queried_fields.add("id")
            else:
                normalized_queried_fields.add(field)

        # Check if any fields are not in indexed_fields
        missing_fields = normalized_queried_fields - self._indexed_fields

        if missing_fields:
            # Build a clear error message
            error_msg = (
                f"❌ Query uses fields not available in Lite storage: {sorted(missing_fields)}\n\n"
                f"These fields are not indexed and not in query_fields.\n"
                f"In Lite storage mode, MongoDB only stores indexed fields and query_fields.\n\n"
                f"To fix this issue, add these fields to Settings.query_fields in {self._full_model_class.__name__}:\n\n"
                f"  class Settings:\n"
                f"      query_fields = {sorted(list(missing_fields))}\n\n"
                f"Current indexed fields: {sorted(self._indexed_fields)}\n"
                f"Queried fields: {sorted(normalized_queried_fields)}\n"
            )
            raise LiteStorageQueryError(error_msg)

    def find(self, *args, **kwargs):
        """
        Intercept find() - returns QueryProxy for automatic dual storage handling

        Supports both:
        - Dict syntax: find({"user_id": "123"})
        - Beanie operator syntax: find(Model.user_id == "123")

        Returns:
            DualStorageQueryProxy
        """
        # Validate query fields only when dict syntax is used
        # Beanie operator syntax is passed through directly to underlying MongoDB
        if args and isinstance(args[0], dict):
            filter_query = args[0]
            self._validate_query_fields(filter_query)

        # Call the original model's find method
        mongo_cursor = self._original_model.find(*args, **kwargs)

        # Wrap in QueryProxy
        return DualStorageQueryProxy(
            mongo_cursor=mongo_cursor,
            kv_storage=self._kv_storage,
            full_model_class=self._full_model_class,
        )

    async def get(
        self, doc_id, session: Optional[AsyncClientSession] = None, **kwargs
    ):
        """
        Intercept get() - reads from KV-Storage first (Lite storage mode)

        In Lite storage mode:
        - MongoDB stores only Lite data (indexed fields)
        - KV-Storage stores full data
        - Must read from KV; MongoDB cannot provide a complete document

        Args:
            doc_id: Document ID (ObjectId or str)
            session: Optional MongoDB session

        Returns:
            Full document or None
        """
        try:
            # Must read full data from KV-Storage
            doc_id_str = str(doc_id)
            kv_key = get_kv_key(self._full_model_class, doc_id_str)
            kv_value = await self._kv_storage.get(key=kv_key)

            if kv_value:
                # KV hit - return full data
                document = self._full_model_class.model_validate_json(kv_value)
                logger.debug(f"✅ KV hit: {doc_id_str}")
                return document

            # KV miss - cannot recover full data from MongoDB in Lite mode
            # MongoDB only has indexed fields, which do not satisfy required fields
            logger.warning(f"⚠️  KV miss for {doc_id_str} - cannot recover full document from MongoDB Lite data")
            return None

        except Exception as e:
            logger.error(f"❌ Failed to get document: {e}")
            return None

    def find_one(self, *args, **kwargs):
        """
        Intercept find_one() - returns FindOneQueryProxy supporting chained calls

        Supports both:
        - Dict syntax: find_one({"user_id": "123", "group_id": "456"})
        - Beanie operator syntax: find_one(Model.user_id == "123", Model.group_id == "456")

        Returns FindOneQueryProxy that supports:
        1. Direct await: doc = await find_one(...)
        2. Chained delete: await find_one(...).delete()

        Args:
            *args: filter query (dict or Beanie operators)
            **kwargs: additional options

        Returns:
            FindOneQueryProxy (can be awaited or chained with .delete())

        Raises:
            LiteStorageQueryError: if a query field is not in Lite storage (dict syntax only)
        """
        return FindOneQueryProxy(
            original_model=self._original_model,
            kv_storage=self._kv_storage,
            full_model_class=self._full_model_class,
            indexed_fields=self._indexed_fields,
            filter_args=args,
            filter_kwargs=kwargs,
        )

    async def delete_many(self, *args, **kwargs):
        """
        Intercept delete_many() - batch soft delete in Lite storage mode

        Batch soft delete behavior in Lite storage mode:
        - MongoDB: mark deleted_at (batch update Lite data)
        - KV-Storage: retain full data (no delete)

        Reason: MongoDB only has indexed fields; deleting from KV would make recovery impossible

        Args:
            *args: filter query
            **kwargs: additional options

        Returns:
            Delete result
        """
        try:
            # Validate query fields
            filter_query = args[0] if args else {}
            self._validate_query_fields(filter_query)

            # Execute batch soft delete (mark deleted_at in MongoDB only)
            result = await self._original_model.delete_many(*args, **kwargs)

            # Lite mode: do not delete from KV, retain full data for recovery
            logger.debug(f"✅ Batch soft deleted in MongoDB (KV data preserved)")

            return result

        except Exception as e:
            logger.error(f"❌ Failed to delete_many with dual storage: {e}")
            raise

    async def update_many(self, filter_query: dict, update_data: dict, **kwargs):
        """
        Intercept update_many() - batch update with KV-Storage sync

        To ensure KV-Storage sync:
        1. Query all matching documents (get IDs)
        2. Execute MongoDB batch update
        3. Iterate documents, update corresponding fields in KV-Storage

        Args:
            filter_query: MongoDB filter query (dict)
            update_data: Update operations (e.g., {"$set": {"field": value}})
            **kwargs: Additional options (e.g., session)

        Returns:
            Update result with modified_count

        Example:
            await self.model.update_many(
                {"group_id": "123", "sync_status": -1},
                {"$set": {"sync_status": 0}}
            )
        """
        try:
            # 1. Validate query fields
            self._validate_query_fields(filter_query)

            # 2. Find all documents to update (get IDs before update)
            # Use self.find() which returns DualStorageQueryProxy
            session = kwargs.get("session", None)
            docs_to_update = await self.find(filter_query, session=session).to_list()

            if not docs_to_update:
                # No documents to update
                class UpdateResult:
                    modified_count = 0
                return UpdateResult()

            # 2.5. Auto-set updated_at if document has this field (AuditBase)
            from common_utils.datetime_utils import get_now_with_timezone
            if hasattr(self._full_model_class, 'model_fields') and 'updated_at' in self._full_model_class.model_fields:
                # Add updated_at to $set operator
                if "$set" not in update_data:
                    update_data = {"$set": {}}
                update_data["$set"]["updated_at"] = get_now_with_timezone()

            # 3. Execute MongoDB batch update using PyMongo
            collection = self._original_model.get_pymongo_collection()
            result = await collection.update_many(filter_query, update_data, **kwargs)

            # 4. Sync to KV-Storage
            if result and result.modified_count > 0:
                import json
                from bson import ObjectId
                from datetime import datetime

                def json_serializer(obj):
                    """Custom JSON serializer for ObjectId and datetime"""
                    if isinstance(obj, ObjectId):
                        return str(obj)
                    elif isinstance(obj, datetime):
                        return obj.isoformat()
                    raise TypeError(f"Type {type(obj)} not serializable")

                # Extract update fields from $set operator
                update_fields = {}
                if "$set" in update_data:
                    update_fields = update_data["$set"]
                else:
                    logger.warning(f"⚠️  update_many only supports $set operator, got: {update_data.keys()}")

                # Update each document in KV-Storage
                for doc in docs_to_update:
                    try:
                        doc_id = str(doc.id)
                        kv_key = get_kv_key(doc, doc_id)
                        # Load existing full data from KV
                        kv_value = await self._kv_storage.get(key=kv_key)
                        if kv_value:
                            # Parse existing data
                            full_data = json.loads(kv_value)
                            # Apply update fields
                            full_data.update(update_fields)
                            # Write back to KV
                            kv_value = json.dumps(full_data, default=json_serializer)
                            await self._kv_storage.put(key=kv_key, value=kv_value)
                        else:
                            logger.warning(f"⚠️  KV miss for {doc.id}, cannot update")
                    except Exception as e:
                        logger.warning(f"⚠️  Failed to sync to KV-Storage for {doc.id}: {e}")

                logger.debug(f"✅ update_many() updated {result.modified_count} documents in MongoDB and KV-Storage")

            return result

        except Exception as e:
            logger.error(f"❌ Failed to update_many with dual storage: {e}")
            raise

    async def delete_all(self, **kwargs):
        """
        Intercept delete_all() - delete all documents with KV-Storage sync

        To ensure KV-Storage sync:
        1. Get all documents
        2. Call delete() on each to trigger DualStorageMixin's wrap_delete
        3. Return delete count

        Returns:
            DeleteResult with deleted_count
        """
        try:
            # Get all documents first to ensure KV-Storage deletion via DualStorageMixin
            all_docs = await self.find({}).to_list()
            count = 0

            for doc in all_docs:
                try:
                    await doc.delete()
                    count += 1
                except Exception as e:
                    logger.error(f"❌ Failed to delete document {doc.id}: {e}")

            # Return a result object compatible with Beanie's DeleteResult
            class DeleteAllResult:
                def __init__(self, deleted_count):
                    self.deleted_count = deleted_count

            logger.debug(f"✅ delete_all() removed {count} documents from MongoDB and KV-Storage")
            return DeleteAllResult(deleted_count=count)

        except Exception as e:
            logger.error(f"❌ Failed to delete_all with dual storage: {e}")
            raise

    def hard_find_one(self, *args, **kwargs):
        """
        Intercept hard_find_one() - query including deleted documents, and backfill KV

        Args:
            *args: filter query
            **kwargs: additional options

        Returns:
            FindOne query object
        """
        # hard_find_one returns a query object, we need to wrap it
        # But since it's a class method returning a query object, we'll just pass through
        # and handle backfill in the wrapper if needed
        return self._original_model.hard_find_one(*args, **kwargs)

    async def hard_delete_many(self, *args, **kwargs):
        """
        Intercept hard_delete_many() - physical delete with KV-Storage sync (Lite storage mode)

        Lite mode: query IDs directly via PyMongo to avoid Beanie validation

        Args:
            *args: filter query
            **kwargs: additional options

        Returns:
            Delete result
        """
        try:
            # 1. Validate query fields
            filter_query = args[0] if args else {}
            self._validate_query_fields(filter_query)

            # 2. Query IDs of documents to delete directly via PyMongo (avoiding Beanie validation)
            mongo_collection = self._original_model.get_pymongo_collection()
            session = kwargs.get("session", None)

            # Query only _id field (including soft-deleted documents)
            lite_docs = await mongo_collection.find(filter_query, {"_id": 1}, session=session).to_list(length=None)
            doc_ids = [str(doc["_id"]) for doc in lite_docs]

            # 2. Execute physical delete
            result = await self._original_model.hard_delete_many(*args, **kwargs)

            # 3. Batch-delete from KV-Storage
            if doc_ids:
                try:
                    kv_keys = [get_kv_key(self._original_model, doc_id) for doc_id in doc_ids]
                    await self._kv_storage.batch_delete(keys=kv_keys)
                    logger.debug(f"✅ Hard deleted {len(doc_ids)} documents from KV-Storage")
                except Exception as e:
                    logger.warning(f"⚠️  Failed to delete from KV-Storage: {e}")

            return result

        except Exception as e:
            logger.error(f"❌ Failed to hard_delete_many with dual storage: {e}")
            raise

    async def restore_many(self, *args, **kwargs):
        """
        Intercept restore_many() - restore deleted documents with KV-Storage sync (Lite storage mode)

        Note: restore does not need to update KV because full data is already in KV.
        Only needs to update the deleted_at field in MongoDB (Lite data).

        Args:
            *args: filter query
            **kwargs: additional options

        Returns:
            Update result
        """
        try:
            # Validate query fields
            filter_query = args[0] if args else {}
            self._validate_query_fields(filter_query)

            # Execute restore (only update deleted_at field in MongoDB)
            result = await self._original_model.restore_many(*args, **kwargs)

            # In Lite mode, full data already exists in KV, no additional sync needed
            # restore only modifies the deleted_at field in MongoDB (an indexed field)

            logger.debug(f"✅ Restored documents in MongoDB (Lite data)")
            return result

        except Exception as e:
            logger.error(f"❌ Failed to restore_many with dual storage: {e}")
            raise

    async def insert_many(
        self,
        documents: List[Any],
        session: Optional[AsyncClientSession] = None,
        **kwargs
    ):
        """
        Intercept insert_many() - batch insert with KV-Storage sync (Lite storage mode)

        Batch insert in Lite mode:
        - MongoDB: store only Lite data (indexed fields)
        - KV-Storage: store full data (all fields)

        Args:
            documents: list of documents to insert
            session: Optional MongoDB session
            **kwargs: additional parameters

        Returns:
            InsertManyResult
        """
        try:
            from bson import ObjectId
            from datetime import datetime
            import json

            def json_serializer(obj):
                """Custom JSON serializer for ObjectId and datetime"""
                if isinstance(obj, ObjectId):
                    return str(obj)
                elif isinstance(obj, datetime):
                    return obj.isoformat()
                raise TypeError(f"Type {type(obj)} not serializable")

            # 1. Trigger before_event hooks (batch set audit fields)
            if hasattr(self._full_model_class, 'prepare_for_insert_many'):
                self._full_model_class.prepare_for_insert_many(documents)
            else:
                # Manually set audit fields
                from common_utils.datetime_utils import get_now_with_timezone
                now = get_now_with_timezone()
                for doc in documents:
                    if hasattr(doc, 'created_at') and doc.created_at is None:
                        doc.created_at = now
                    if hasattr(doc, 'updated_at') and doc.updated_at is None:
                        doc.updated_at = now

            # 2. Extract Lite data for all documents
            lite_data_list = []
            full_data_list = []

            for doc in documents:
                # Extract Lite data
                lite_data = LiteModelExtractor.extract_lite_data(doc, self._indexed_fields)
                lite_data_list.append(lite_data)

                # Save full data (for KV-Storage)
                full_data = doc.model_dump(mode="python", exclude={'_id', 'id', 'revision_id'})
                full_data_list.append(full_data)

            # 3. Batch-insert Lite data into MongoDB via PyMongo
            mongo_collection = self._original_model.get_pymongo_collection()
            insert_result = await mongo_collection.insert_many(lite_data_list, session=session)

            # 4. Assign generated IDs to document objects
            for doc, inserted_id in zip(documents, insert_result.inserted_ids):
                doc.id = inserted_id

            # 5. Batch-store full data to KV-Storage
            for doc, full_data in zip(documents, full_data_list):
                try:
                    doc_id = str(doc.id)
                    kv_key = get_kv_key(doc, doc_id)
                    full_data["id"] = doc.id  # Attach generated ID
                    kv_value = json.dumps(full_data, default=json_serializer)
                    await self._kv_storage.put(key=kv_key, value=kv_value)
                except Exception as e:
                    logger.warning(f"⚠️  Failed to sync to KV-Storage for {doc.id}: {e}")

            # 6. CRITICAL: ensure returned document objects contain full data
            # After PyMongo inserts lite_data directly, Beanie may have modified document objects
            # Re-set all full_data fields back onto doc objects
            for doc, full_data in zip(documents, full_data_list):
                for field_name, field_value in full_data.items():
                    # Set only non-special fields (excluding _id etc.)
                    if not field_name.startswith('_') and field_name != 'id':
                        try:
                            setattr(doc, field_name, field_value)
                        except Exception:
                            pass  # Ignore read-only fields

            logger.debug(
                f"💾 insert_many: MongoDB Lite ({len(lite_data_list)} docs), "
                f"KV Full ({len(full_data_list)} docs), restored full data to documents"
            )

            # IMPORTANT: Return InsertManyResult, NOT documents
            # BaseRepository.create_batch expects InsertManyResult and will handle assigning IDs
            return insert_result

        except Exception as e:
            logger.error(f"❌ Failed to insert_many with dual storage: {e}")
            raise

    def __getattr__(self, name):
        """Proxy all other methods to original model"""
        return getattr(self._original_model, name)


class DocumentInstanceWrapper:
    """
    Document Instance Wrapper - intercepts Document instance methods (Lite storage approach)

    Intercepts instance methods such as insert(), save(), delete():
    - MongoDB stores only Lite version (indexed fields)
    - KV-Storage stores full data (encrypted)
    """

    @staticmethod
    def wrap_insert(original_insert, kv_storage: "KVStorageInterface", indexed_fields: Set[str]):
        """
        Wrap document.insert() to implement Lite storage

        Use the underlying pymongo API to ensure MongoDB stores only Lite data

        MongoDB: Lite data (indexed fields only)
        KV-Storage: Full data (all fields, encrypted)
        """
        async def wrapped_insert(self, **kwargs):
            # Debug: Check self's fields
            logger.debug(f"🔍 Inserting {self.__class__.__name__}, fields: {self.model_fields.keys()}")

            # 0. Trigger Beanie's before_event hooks (e.g., AuditBase.set_created_at)
            # Since we're using PyMongo directly, we need to manually trigger these hooks
            if hasattr(self, 'set_created_at'):
                try:
                    await self.set_created_at()
                except Exception as e:
                    logger.warning(f"⚠️  Failed to call set_created_at hook: {e}")

            try:
                # 1. Extract Lite data (indexed fields only)
                lite_data = LiteModelExtractor.extract_lite_data(self, indexed_fields)
            except Exception as e:
                logger.error(f"❌ Failed to extract lite data: {e}")
                logger.error(f"Document type: {type(self)}")
                logger.error(f"Document __dict__: {self.__dict__.keys()}")

                # Check for ExpressionField in instance
                for key, value in self.__dict__.items():
                    logger.error(f"  {key}: {type(value)}")

                import traceback
                traceback.print_exc()
                raise

            try:
                # 2. Save full data to KV-Storage (before insert, to avoid ID issues)
                # Exclude Beanie internal fields
                full_data_for_kv = self.model_dump(mode="python", exclude={'_id', 'id', 'revision_id'})
            except Exception as e:
                logger.error(f"❌ Failed to dump full data: {e}")
                import traceback
                traceback.print_exc()
                raise

            # 3. Insert Lite data directly into MongoDB via the underlying pymongo API
            mongo_collection = self.get_pymongo_collection()

            # Get session parameter (if any)
            session = kwargs.get("session", None)

            # Insert Lite data directly
            insert_result = await mongo_collection.insert_one(lite_data, session=session)

            # 4. Assign the generated ID to the document object
            self.id = insert_result.inserted_id

            # 5. Store full data in KV-Storage
            try:
                doc_id = str(self.id)
                kv_key = get_kv_key(self, doc_id)

                # Update the ID in full_data
                full_data_for_kv["id"] = self.id

                # Serialize dict directly to JSON (avoid re-creating Document which causes ExpressionField issues)
                import json
                from bson import ObjectId
                from datetime import datetime

                def json_serializer(obj):
                    """Custom JSON serializer for ObjectId and datetime"""
                    if isinstance(obj, ObjectId):
                        return str(obj)
                    elif isinstance(obj, datetime):
                        return obj.isoformat()
                    raise TypeError(f"Type {type(obj)} not serializable")

                kv_value = json.dumps(full_data_for_kv, default=json_serializer)

                await kv_storage.put(key=kv_key, value=kv_value)
                logger.debug(f"💾 MongoDB: Lite ({len(lite_data)} fields), KV: Full ({len(full_data_for_kv)} fields) - {kv_key}")
            except Exception as e:
                # KV write failed — roll back the MongoDB insert to keep both sides consistent.
                # Without rollback, MongoDB has a lite doc but KV has nothing, causing every
                # subsequent find_one to KV-miss and every upsert to hit E11000 permanently.
                logger.error(f"❌ KV-Storage write failed, rolling back MongoDB insert for {doc_id}: {e}")
                try:
                    await mongo_collection.delete_one({"_id": insert_result.inserted_id}, session=session)
                    logger.info(f"↩️  MongoDB rollback succeeded for {doc_id}")
                except Exception as rollback_err:
                    logger.error(f"❌ MongoDB rollback also failed for {doc_id}: {rollback_err}")
                raise

            # 6. Return document object (Beanie's insert returns self)
            return self

        return wrapped_insert

    @staticmethod
    def wrap_save(original_save, kv_storage: "KVStorageInterface", indexed_fields: Set[str]):
        """
        Wrap document.save() to implement Lite storage

        Use the underlying pymongo API to ensure MongoDB stores only Lite data

        MongoDB: Lite data (indexed fields only)
        KV-Storage: Full data (all fields, encrypted)
        """
        async def wrapped_save(self, **kwargs):
            if not self.id:
                # If there is no ID, use insert instead of save
                logger.warning("save() called on document without ID, should use insert()")
                return await self.insert(**kwargs)

            # 0. Trigger Beanie's before_event hooks (e.g., AuditBase.set_updated_at)
            # Since we're using PyMongo directly, we need to manually trigger these hooks
            if hasattr(self, 'set_updated_at'):
                try:
                    await self.set_updated_at()
                except Exception as e:
                    logger.warning(f"⚠️  Failed to call set_updated_at hook: {e}")

            try:
                # 1. Extract Lite data
                lite_data = LiteModelExtractor.extract_lite_data(self, indexed_fields)

                # 2. Update MongoDB via the underlying pymongo API (Lite fields only)
                mongo_collection = self.get_pymongo_collection()
                session = kwargs.get("session", None)

                # Use replace_one to replace the entire document with Lite data
                from bson import ObjectId
                await mongo_collection.replace_one(
                    {"_id": ObjectId(self.id)},
                    lite_data,
                    session=session
                )

                # 3. Store full data in KV-Storage
                try:
                    doc_id = str(self.id)
                    kv_key = get_kv_key(self, doc_id)

                    # Use model_dump + json.dumps to avoid ExpressionField issues
                    # model_dump_json() may fail because objects restored from KV may have lazy_model ExpressionField
                    import json
                    from bson import ObjectId
                    from datetime import datetime

                    def json_serializer(obj):
                        """Custom JSON serializer for ObjectId and datetime"""
                        if isinstance(obj, ObjectId):
                            return str(obj)
                        elif isinstance(obj, datetime):
                            return obj.isoformat()
                        raise TypeError(f"Type {type(obj)} not serializable")

                    full_data = self.model_dump(mode="python", exclude={'_id', 'revision_id'})
                    kv_value = json.dumps(full_data, default=json_serializer)

                    await kv_storage.put(key=kv_key, value=kv_value)
                    logger.debug(f"💾 MongoDB: Lite ({len(lite_data)} fields), KV: Full - {kv_key}")
                except Exception as e:
                    logger.warning(f"⚠️  Failed to sync full data to KV-Storage: {e}")
                    import traceback
                    logger.error(traceback.format_exc())

                # 4. Return document object
                return self

            except Exception as e:
                logger.error(f"❌ Failed in wrapped_save: {e}")
                import traceback
                logger.error(traceback.format_exc())
                raise

        return wrapped_save

    @staticmethod
    def wrap_delete(original_delete, kv_storage: "KVStorageInterface"):
        """
        Wrap document.delete() - supports both soft and hard delete

        Behavior depends on whether the document has a hard_delete method:
        - Has hard_delete (soft-delete document):
          - MongoDB: mark deleted_at (update Lite data only)
          - KV-Storage: retain full data (no delete)
        - No hard_delete (regular document):
          - MongoDB: physical delete
          - KV-Storage: physical delete
        """
        async def wrapped_delete(self, **kwargs):
            doc_id = str(self.id) if self.id else None
            kv_key = get_kv_key(self, doc_id) if doc_id else None

            # Call original delete
            result = await original_delete(self, **kwargs)

            # Determine whether this is a soft or hard delete
            has_hard_delete = hasattr(self.__class__, "hard_delete")

            if has_hard_delete:
                # Soft-delete document: retain KV data
                logger.debug(f"✅ Soft deleted in MongoDB (KV data preserved): {self.id}")
            else:
                # Hard-delete document: remove KV data
                if kv_key:
                    try:
                        await kv_storage.delete(key=kv_key)
                        logger.debug(f"✅ Hard deleted from KV-Storage: {kv_key}")
                    except Exception as e:
                        logger.warning(f"⚠️  Failed to delete from KV-Storage: {e}")

            return result

        return wrapped_delete

    @staticmethod
    def wrap_restore(original_restore, kv_storage: "KVStorageInterface"):
        """
        Wrap document.restore() - restore in Lite storage mode

        Restore behavior in Lite mode:
        - MongoDB: clear deleted_at (update Lite data only)
        - KV-Storage: no action needed (data has always been there)

        Reason: KV data was not deleted on soft delete, so no sync needed on restore
        """
        async def wrapped_restore(self, **kwargs):
            # Call original restore (clears deleted_at in MongoDB only)
            result = await original_restore(self, **kwargs)

            # In Lite mode KV data was not deleted, no sync needed
            # Full data in KV has been there all along and can be used directly
            logger.debug(f"✅ Restored in MongoDB (KV data was preserved): {self.id}")

            return result

        return wrapped_restore

    @staticmethod
    def __original_wrap_restore_not_used(original_restore, kv_storage: "KVStorageInterface"):
        """DEPRECATED: original restore implementation (deprecated)"""
        async def wrapped_restore(self, **kwargs):
            # Call original restore (passing self)
            result = await original_restore(self, **kwargs)

            # Sync back to KV-Storage after restore
            if self.id:
                try:
                    doc_id = str(self.id)
                    kv_key = get_kv_key(self, doc_id)
                    kv_value = self.model_dump_json()
                    await kv_storage.put(key=kv_key, value=kv_value)
                    logger.debug(f"✅ Synced to KV-Storage after restore: {kv_key}")
                except Exception as e:
                    logger.warning(f"⚠️  Failed to sync to KV-Storage after restore: {e}")

            return result

        return wrapped_restore

    @staticmethod
    def wrap_hard_delete(original_hard_delete, kv_storage: "KVStorageInterface"):
        """Wrap document.hard_delete() to remove from KV-Storage"""
        async def wrapped_hard_delete(self, **kwargs):
            doc_id = str(self.id) if self.id else None
            kv_key = get_kv_key(self, doc_id) if doc_id else None

            # Call original hard_delete (passing self)
            result = await original_hard_delete(self, **kwargs)

            # Delete from KV-Storage
            if kv_key:
                try:
                    await kv_storage.delete(key=kv_key)
                    logger.debug(f"✅ Deleted from KV-Storage after hard_delete: {kv_key}")
                except Exception as e:
                    logger.warning(f"⚠️  Failed to delete from KV-Storage after hard_delete: {e}")

            return result

        return wrapped_hard_delete


__all__ = [
    "DualStorageModelProxy",
    "DualStorageQueryProxy",
    "FindOneQueryProxy",
    "DocumentInstanceWrapper",
    "LiteStorageQueryError",
]
