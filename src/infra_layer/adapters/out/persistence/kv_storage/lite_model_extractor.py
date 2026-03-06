"""
Lite Model Field Extractor - dynamically extracts indexed fields at runtime

Automatically extracts all indexed and query fields from Document classes via Python reflection.
No manual maintenance of Lite class code required. Adapts automatically when third parties modify indexes.
"""

from typing import Type, Set, Any, Dict
from pydantic import BaseModel
from pydantic.fields import FieldInfo
from beanie import Indexed
import inspect

from core.observation.logger import get_logger

logger = get_logger(__name__)


class LiteModelExtractor:
    """
    Lite Model Field Extractor

    Dynamically extracts indexed and query fields from a Document at runtime to build Lite version data.

    Extraction rules:
    1. All fields marked with Indexed
    2. Indexed fields defined in Settings.indexes
    3. Query fields configured in Settings.query_fields (no index but used in queries)
    4. Audit fields: id, created_at, updated_at
    5. Soft-delete fields: deleted_at, deleted_by, deleted_id (if present)

    Note: query_fields is for fields that have no index but are used in queries
    """

    # System fields always included
    SYSTEM_FIELDS = {"id", "created_at", "updated_at", "revision_id"}

    # Soft-delete fields (if Document supports soft delete)
    SOFT_DELETE_FIELDS = {"deleted_at", "deleted_by", "deleted_id"}

    @classmethod
    def extract_indexed_fields(cls, document_class: Type[BaseModel]) -> Set[str]:
        """
        Extract all indexed and query fields from a Document class

        Args:
            document_class: Beanie Document class

        Returns:
            Set[str]: set of indexed field names + query field names
        """
        indexed_fields = set()

        # 1. Always include system fields
        indexed_fields.update(cls.SYSTEM_FIELDS)

        # 2. Check if soft delete is supported (has deleted_at field)
        if hasattr(document_class, "deleted_at"):
            indexed_fields.update(cls.SOFT_DELETE_FIELDS)

        # 3. Extract Indexed fields from field annotations
        for field_name, field_info in document_class.model_fields.items():
            # Check if this is an Indexed type
            if cls._is_indexed_field(field_info):
                indexed_fields.add(field_name)

        # 4. Extract indexed fields from Settings.indexes
        if hasattr(document_class, "Settings") and hasattr(document_class.Settings, "indexes"):
            for index_model in document_class.Settings.indexes:
                # The document attribute of IndexModel returns the full index spec (SON object)
                # Extract the actual field names from the 'key' entry
                if hasattr(index_model, "document"):
                    index_spec = index_model.document
                    # index_spec["key"] is a SON object containing (field_name, direction) pairs
                    if "key" in index_spec:
                        for field_name in index_spec["key"].keys():
                            indexed_fields.add(field_name)

        # 5. Extract query fields from Settings.query_fields (no index but used in queries)
        if hasattr(document_class, "Settings") and hasattr(document_class.Settings, "query_fields"):
            query_fields = document_class.Settings.query_fields
            if query_fields:
                indexed_fields.update(query_fields)
                logger.debug(f"📋 Added {len(query_fields)} query fields (no index): {sorted(query_fields)}")

        logger.debug(f"📋 Extracted {len(indexed_fields)} total fields for {document_class.__name__}: {sorted(indexed_fields)}")
        return indexed_fields

    @classmethod
    def _is_indexed_field(cls, field_info: FieldInfo) -> bool:
        """
        Check whether a field is of Indexed type

        Args:
            field_info: Pydantic FieldInfo

        Returns:
            bool: True if this is an indexed field
        """
        # Check whether the annotation contains Indexed
        annotation = field_info.annotation

        # Handle Optional[Indexed[...]] case
        if hasattr(annotation, "__origin__"):
            # Get generic arguments
            args = getattr(annotation, "__args__", ())
            for arg in args:
                if cls._is_indexed_type(arg):
                    return True

        # Directly check whether this is an Indexed type
        return cls._is_indexed_type(annotation)

    @classmethod
    def _is_indexed_type(cls, type_annotation: Any) -> bool:
        """
        Check whether a type is Indexed

        Args:
            type_annotation: type annotation

        Returns:
            bool: True if this is an Indexed type
        """
        # Check whether this is an Indexed generic
        if hasattr(type_annotation, "__origin__"):
            origin = type_annotation.__origin__
            # Indexed implementation in beanie
            if origin is not None and "Indexed" in str(origin):
                return True

        # Check the type name
        type_str = str(type_annotation)
        return "Indexed" in type_str

    @classmethod
    def extract_lite_data(cls, document: BaseModel, indexed_fields: Set[str]) -> Dict[str, Any]:
        """
        Extract Lite version data from a full Document (indexed fields only)

        Args:
            document: full Document instance
            indexed_fields: set of indexed fields

        Returns:
            Dict[str, Any]: dict containing only indexed fields
        """
        # Exclude Beanie internal fields that might be ExpressionField objects
        # These fields should not be serialized before the document is inserted
        exclude_fields = {'_id', 'id', 'revision_id'}

        try:
            full_data = document.model_dump(mode="python", exclude=exclude_fields)
        except Exception as e:
            # If model_dump fails, try to extract fields manually
            logger.warning(f"⚠️  model_dump failed, falling back to manual extraction: {e}")
            full_data = {}
            for field_name in document.model_fields.keys():
                if field_name not in exclude_fields:
                    try:
                        value = getattr(document, field_name, None)
                        # Skip ExpressionField objects
                        if value is not None and 'ExpressionField' not in str(type(value)):
                            full_data[field_name] = value
                    except Exception:
                        pass

        lite_data = {}

        for field_name in indexed_fields:
            if field_name in full_data:
                lite_data[field_name] = full_data[field_name]

        logger.debug(f"📦 Extracted lite data with {len(lite_data)} fields (from {len(full_data)} total fields)")
        return lite_data

    @classmethod
    def create_lite_document(cls, document: BaseModel, indexed_fields: Set[str]) -> BaseModel:
        """
        Create a Lite version Document instance (indexed fields only)

        Args:
            document: full Document instance
            indexed_fields: set of indexed fields

        Returns:
            BaseModel: Lite version Document instance
        """
        lite_data = cls.extract_lite_data(document, indexed_fields)

        # Use the same Document class to create an instance with only indexed fields
        # Pydantic will automatically handle missing optional fields
        lite_document = document.__class__.model_validate(lite_data)

        return lite_document


__all__ = ["LiteModelExtractor"]
