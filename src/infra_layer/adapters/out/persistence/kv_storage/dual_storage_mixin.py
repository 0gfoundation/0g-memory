"""
Dual Storage Mixin - Model layer interception approach

Minimal-intrusion approach: dual storage via intercepting MongoDB calls on self.model
- Zero changes to Repository code (no need to change append/get_by_id or any other methods)
- No sync needed when main branch updates CRUD
- Dual storage is completely transparent

How it works:
1. Replace self.model with DualStorageModelProxy in __init__
2. Proxy intercepts all MongoDB calls (find, get, etc.)
3. Monkey patch document class instance methods (insert, save, delete)
4. Dual storage sync is handled automatically

Usage example:
    class EpisodicMemoryRawRepository(
        DualStorageMixin,  # Just add the Mixin
        BaseRepository[EpisodicMemory]
    ):
        # All other code remains unchanged
        pass
"""

from typing import TypeVar, Generic, Type, Optional

from core.observation.logger import get_logger
from infra_layer.adapters.out.persistence.kv_storage.kv_storage_interface import (
    KVStorageInterface,
)
from infra_layer.adapters.out.persistence.kv_storage.dual_storage_model_proxy import (
    DualStorageModelProxy,
    DocumentInstanceWrapper,
)

logger = get_logger(__name__)

TDocument = TypeVar("TDocument")


class DualStorageMixin(Generic[TDocument]):
    """
    Dual Storage Mixin - Model layer interception implementation

    Automatically enables dual storage by intercepting self.model. Zero Repository code changes required.

    Workflow:
    1. Replace self.model with ModelProxy in __init__
    2. Proxy intercepts find(), get(), etc.
    3. Monkey patch Document class insert(), save(), delete()
    4. All MongoDB operations are automatically synced to KV-Storage

    Advantages:
    - No changes needed to any Repository code
    - No sync needed when main branch is updated
    - Dual storage logic is completely transparent
    """

    def __init__(self, *args, **kwargs):
        """
        Initialize mixin and setup dual storage interception

        Automatically:
        1. Get KV-Storage instance
        2. Replace self.model with ModelProxy
        3. Monkey patch Document instance methods
        """
        super().__init__(*args, **kwargs)

        # Initialize dual storage immediately (no lazy init)
        self._kv_storage: Optional[KVStorageInterface] = None
        self._setup_dual_storage()

    def _setup_dual_storage(self):
        """
        Setup dual storage interception immediately

        Set up interception immediately in __init__
        """
        try:
            # 1. Get KV-Storage instance
            self._kv_storage = self._get_kv_storage()

            # 2. Replace self.model with ModelProxy
            original_model = self.model
            self.model = DualStorageModelProxy(
                original_model=original_model,
                kv_storage=self._kv_storage,
                full_model_class=original_model,
            )

            # 3. Monkey patch Document class instance methods
            # Pass indexed_fields to the wrapper
            self._patch_document_methods(original_model, self.model._indexed_fields)

            logger.debug(
                f"✅ Dual storage initialized for {original_model.__name__}"
            )

        except Exception as e:
            logger.error(f"❌ Failed to initialize dual storage: {e}")
            raise

    def _get_kv_storage(self) -> KVStorageInterface:
        """Lazy load KV-Storage instance from DI container"""
        if self._kv_storage is None:
            from core.di import get_bean_by_type

            self._kv_storage = get_bean_by_type(KVStorageInterface)
        return self._kv_storage

    def _patch_document_methods(self, document_class, indexed_fields):
        """
        Monkey patch Document class instance methods

        Wrap insert(), create(), save(), delete() to enable Lite storage:
        - MongoDB stores only indexed fields (Lite)
        - KV-Storage stores full data (Full)

        Args:
            document_class: Document model class (e.g., EpisodicMemory)
            indexed_fields: set of indexed fields (extracted automatically at runtime)
        """
        kv_storage = self._kv_storage

        # Save original methods
        if not hasattr(document_class, "_original_insert"):
            document_class._original_insert = document_class.insert
            document_class._original_save = document_class.save
            document_class._original_delete = document_class.delete

            # Wrap instance methods - pass indexed_fields
            document_class.insert = DocumentInstanceWrapper.wrap_insert(
                document_class._original_insert, kv_storage, indexed_fields
            )
            document_class.save = DocumentInstanceWrapper.wrap_save(
                document_class._original_save, kv_storage, indexed_fields
            )
            document_class.delete = DocumentInstanceWrapper.wrap_delete(
                document_class._original_delete, kv_storage
            )

            # Wrap create() method if it exists (Beanie's alias for insert)
            if hasattr(document_class, "create"):
                document_class._original_create = document_class.create
                document_class.create = DocumentInstanceWrapper.wrap_insert(
                    document_class._original_create, kv_storage, indexed_fields
                )

            # Wrap restore() and hard_delete() if they exist (for soft-delete documents)
            if hasattr(document_class, "restore"):
                document_class._original_restore = document_class.restore
                document_class.restore = DocumentInstanceWrapper.wrap_restore(
                    document_class._original_restore, kv_storage
                )

            if hasattr(document_class, "hard_delete"):
                document_class._original_hard_delete = document_class.hard_delete
                document_class.hard_delete = DocumentInstanceWrapper.wrap_hard_delete(
                    document_class._original_hard_delete, kv_storage
                )

            # Count intercepted methods
            patched_methods = ["insert", "save", "delete"]
            if hasattr(document_class, "_original_create"):
                patched_methods.append("create")
            if hasattr(document_class, "_original_restore"):
                patched_methods.append("restore")
            if hasattr(document_class, "_original_hard_delete"):
                patched_methods.append("hard_delete")

            logger.debug(
                f"✅ Patched {len(patched_methods)} instance methods for {document_class.__name__}: "
                f"{', '.join(patched_methods)} (Lite: {len(indexed_fields)} fields)"
            )


__all__ = ["DualStorageMixin"]
