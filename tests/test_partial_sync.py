"""
Tests for partial sync functionality including include= and exclude= parameters
with both normal classes and Synced BaseModel patterns, including inheritance scenarios.
"""

from unittest.mock import Mock

import pytest
from pydantic import BaseModel

from ws_sync.sync import Sync
from ws_sync.synced_model import Synced, SyncedAsCamelCase

from .utils import get_patch

# Test classes for normal (non-Pydantic) objects


class SimpleClass:
    """Simple class for testing partial sync"""

    def __init__(self):
        self.field1 = "value1"
        self.field2 = "value2"
        self.field3 = "value3"
        self.private_field = "private"
        self._actual_private = "underscore_private"


class ParentClass:
    """Parent class for inheritance testing"""

    def __init__(self):
        self.parent_field = "parent_value"
        self.shared_field = "shared_parent"


class ChildClass(ParentClass):
    """Child class for inheritance testing"""

    def __init__(self):
        super().__init__()
        self.child_field = "child_value"
        self.shared_field = "shared_child"  # Override parent field


class ClassWithDependentProperty:
    """Class with a property that depends on other attributes"""

    def __init__(self):
        self.first_name = "John"
        self.last_name = "Doe"

    @property
    def full_name(self):
        """Property that depends on first_name and last_name"""
        return f"{self.first_name} {self.last_name}"


# Test classes for Synced BaseModel patterns


class SimpleModel(Synced, BaseModel):
    """Simple Pydantic model for testing partial sync"""

    field1: str
    field2: str
    field3: str
    private_field: str = "private"


class ParentModel(SyncedAsCamelCase, BaseModel):
    """Parent Pydantic model for inheritance testing"""

    parent_field: str
    shared_field: str


class ChildModel(ParentModel):
    """Child Pydantic model for inheritance testing"""

    child_field: str
    # shared_field inherited from parent


class CamelChildModel(ParentModel):
    """Child with camel case field"""

    camel_field: str
    snake_case_field: str


# Test classes use utilities from .utils module


class TestPartialSyncNormalClasses:
    """Test partial sync with normal (non-Pydantic) classes"""

    def test_include_specific_fields(self, mock_session: Mock):
        """Test including only specific fields"""
        obj = SimpleClass()
        sync = Sync(obj, key="TEST", include={"field1": ..., "field2": ...})

        snapshot = sync._snapshot()
        assert "field1" in snapshot
        assert "field2" in snapshot
        assert "field3" not in snapshot
        assert "private_field" not in snapshot

    def test_include_with_custom_keys(self, mock_session: Mock):
        """Test including fields with custom keys"""
        obj = SimpleClass()
        sync = Sync(obj, key="TEST", include={"field1": "custom_key", "field2": ...})

        snapshot = sync._snapshot()
        assert "custom_key" in snapshot
        assert "field2" in snapshot
        assert "field1" not in snapshot  # Should use custom key instead
        assert "field3" not in snapshot

    def test_sync_all_with_exclude(self, mock_session: Mock):
        """Test sync_all with exclude parameter"""
        obj = SimpleClass()
        sync = Sync.all(obj, key="TEST", exclude=["field3", "private_field"])

        snapshot = sync._snapshot()
        assert "field1" in snapshot
        assert "field2" in snapshot
        assert "field3" not in snapshot
        assert "private_field" not in snapshot

    def test_sync_all_excludes_private_by_default(self, mock_session: Mock):
        """Test that sync_all excludes private fields by default"""
        obj = SimpleClass()
        sync = Sync.all(obj, key="TEST")

        snapshot = sync._snapshot()
        assert "field1" in snapshot
        assert "field2" in snapshot
        assert "field3" in snapshot
        # Note: private_field doesn't start with underscore so it's included
        assert "private_field" in snapshot
        # Fields starting with underscore are excluded by default
        assert "_actual_private" not in snapshot

    def test_inheritance_include_parent_fields(self, mock_session: Mock):
        """Test including parent fields in child class"""
        obj = ChildClass()
        sync = Sync(obj, key="TEST", include={"parent_field": ..., "child_field": ...})

        snapshot = sync._snapshot()
        assert "parent_field" in snapshot
        assert "child_field" in snapshot
        assert "shared_field" not in snapshot

    def test_inheritance_include_overridden_fields(self, mock_session: Mock):
        """Test including overridden fields shows child value"""
        obj = ChildClass()
        sync = Sync(obj, key="TEST", include={"shared_field": ...})

        snapshot = sync._snapshot()
        assert snapshot["shared_field"] == "shared_child"

    def test_inheritance_sync_all_includes_all_fields(self, mock_session: Mock):
        """Test that sync_all includes both parent and child fields"""
        obj = ChildClass()
        sync = Sync.all(obj, key="TEST")

        snapshot = sync._snapshot()
        assert "parent_field" in snapshot
        assert "child_field" in snapshot
        assert "shared_field" in snapshot
        assert snapshot["shared_field"] == "shared_child"

    def test_inheritance_sync_all_with_exclude_parent(self, mock_session: Mock):
        """Test excluding parent fields from child class"""
        obj = ChildClass()
        sync = Sync.all(obj, key="TEST", exclude=["parent_field"])

        snapshot = sync._snapshot()
        assert "parent_field" not in snapshot
        assert "child_field" in snapshot
        assert "shared_field" in snapshot

    def test_inheritance_sync_all_with_exclude_child(self, mock_session: Mock):
        """Test excluding child fields"""
        obj = ChildClass()
        sync = Sync.all(obj, key="TEST", exclude=["child_field"])

        snapshot = sync._snapshot()
        assert "parent_field" in snapshot
        assert "child_field" not in snapshot
        assert "shared_field" in snapshot


class TestPartialSyncPydanticModels:
    """Test partial sync with Synced BaseModel patterns"""

    def test_include_specific_fields(self, mock_session: Mock):
        """Test including only specific fields with Pydantic models"""
        obj = SimpleModel(field1="val1", field2="val2", field3="val3")
        sync = Sync(obj, key="TEST", include={"field1": ..., "field2": ...})

        snapshot = sync._snapshot()
        assert "field1" in snapshot
        assert "field2" in snapshot
        assert "field3" not in snapshot
        assert "private_field" not in snapshot

    def test_include_with_custom_keys_pydantic(self, mock_session: Mock):
        """Test that custom keys are not allowed for Pydantic models"""
        obj = SimpleModel(field1="val1", field2="val2", field3="val3")

        # Should raise AssertionError when trying to use custom keys with Pydantic models
        with pytest.raises(
            AssertionError,
            match="Custom sync key 'custom_key' for attribute 'field1' is not allowed for Pydantic models",
        ):
            Sync(obj, key="TEST", include={"field1": "custom_key", "field2": ...})

    def test_sync_all_with_exclude_pydantic(self, mock_session: Mock):
        """Test sync_all with exclude parameter for Pydantic models"""
        obj = SimpleModel(field1="val1", field2="val2", field3="val3")
        sync = Sync.all(obj, key="TEST", exclude=["field3", "private_field"])

        snapshot = sync._snapshot()
        assert "field1" in snapshot
        assert "field2" in snapshot
        assert "field3" not in snapshot
        assert "private_field" not in snapshot

    def test_pydantic_inheritance_include_parent_fields(self, mock_session: Mock):
        """Test including parent fields in child Pydantic model"""
        obj = ChildModel(
            parent_field="parent", shared_field="shared", child_field="child"
        )
        sync = Sync(obj, key="TEST", include={"parent_field": ..., "child_field": ...})

        snapshot = sync._snapshot()
        assert "parentField" in snapshot  # Should be camelCase
        assert "childField" in snapshot
        assert "sharedField" not in snapshot

    def test_pydantic_inheritance_include_overridden_fields(self, mock_session: Mock):
        """Test including inherited fields in child Pydantic model"""
        obj = ChildModel(
            parent_field="parent", shared_field="child_shared", child_field="child"
        )
        sync = Sync(obj, key="TEST", include={"shared_field": ...})

        snapshot = sync._snapshot()
        assert snapshot["sharedField"] == "child_shared"

    def test_pydantic_inheritance_sync_all_includes_all_fields(
        self, mock_session: Mock
    ):
        """Test that sync_all includes both parent and child fields in Pydantic models"""
        obj = ChildModel(
            parent_field="parent", shared_field="shared", child_field="child"
        )
        sync = Sync.all(obj, key="TEST")

        snapshot = sync._snapshot()
        assert "parentField" in snapshot
        assert "childField" in snapshot
        assert "sharedField" in snapshot
        assert snapshot["sharedField"] == "shared"

    def test_pydantic_inheritance_sync_all_with_exclude_parent(
        self, mock_session: Mock
    ):
        """Test excluding parent fields from child Pydantic model"""
        obj = ChildModel(
            parent_field="parent", shared_field="shared", child_field="child"
        )
        sync = Sync.all(obj, key="TEST", exclude=["parent_field"])

        snapshot = sync._snapshot()
        assert "parentField" not in snapshot
        assert "childField" in snapshot
        assert "sharedField" in snapshot

    def test_pydantic_inheritance_sync_all_with_exclude_child(self, mock_session: Mock):
        """Test excluding child fields from Pydantic model"""
        obj = ChildModel(
            parent_field="parent", shared_field="shared", child_field="child"
        )
        sync = Sync.all(obj, key="TEST", exclude=["child_field"])

        snapshot = sync._snapshot()
        assert "parentField" in snapshot
        assert "childField" not in snapshot
        assert "sharedField" in snapshot

    def test_mixed_case_inheritance_with_include(self, mock_session: Mock):
        """Test inheritance with mixed camelCase and snake_case fields"""
        obj = CamelChildModel(
            parent_field="parent",
            shared_field="shared",
            camel_field="camel",
            snake_case_field="snake",
        )
        sync = Sync(
            obj, key="TEST", include={"camel_field": ..., "snake_case_field": ...}
        )

        snapshot = sync._snapshot()
        assert "camelField" in snapshot
        assert "snakeCaseField" in snapshot
        assert "parentField" not in snapshot
        assert "sharedField" not in snapshot

    def test_mixed_case_inheritance_exclude_snake_case(self, mock_session: Mock):
        """Test excluding snake_case fields while keeping camelCase"""
        obj = CamelChildModel(
            parent_field="parent",
            shared_field="shared",
            camel_field="camel",
            snake_case_field="snake",
        )
        sync = Sync.all(obj, key="TEST", exclude=["snake_case_field"])

        snapshot = sync._snapshot()
        assert "parentField" in snapshot
        assert "sharedField" in snapshot
        assert "camelField" in snapshot
        assert "snakeCaseField" not in snapshot


class TestPartialSyncListInclude:
    """Test partial sync with list[str] include parameter"""

    def test_include_list_normal_class(self, mock_session: Mock):
        """Test including fields using list[str] with normal classes"""
        obj = SimpleClass()
        sync = Sync(obj, key="TEST", include=["field1", "field2"])

        snapshot = sync._snapshot()
        assert "field1" in snapshot
        assert "field2" in snapshot
        assert "field3" not in snapshot
        assert "private_field" not in snapshot

    def test_include_list_pydantic_model(self, mock_session: Mock):
        """Test including fields using list[str] with Pydantic models"""
        obj = SimpleModel(field1="val1", field2="val2", field3="val3")
        sync = Sync(obj, key="TEST", include=["field1", "field2"])

        snapshot = sync._snapshot()
        assert "field1" in snapshot
        assert "field2" in snapshot
        assert "field3" not in snapshot
        assert "private_field" not in snapshot

    def test_include_list_with_camel_case(self, mock_session: Mock):
        """Test list[str] include with camelCase conversion"""
        obj = ChildModel(
            parent_field="parent", shared_field="shared", child_field="child"
        )
        sync = Sync(obj, key="TEST", include=["parent_field", "child_field"])

        snapshot = sync._snapshot()
        assert "parentField" in snapshot
        assert "childField" in snapshot
        assert "sharedField" not in snapshot

    def test_include_list_inheritance(self, mock_session: Mock):
        """Test list[str] include with inheritance"""
        obj = ChildClass()
        sync = Sync(obj, key="TEST", include=["parent_field", "child_field"])

        snapshot = sync._snapshot()
        assert "parent_field" in snapshot
        assert "child_field" in snapshot
        assert "shared_field" not in snapshot

    def test_sync_all_with_list_include(self, mock_session: Mock):
        """Test that Sync.all() works with list[str] include parameter"""
        obj = SimpleClass()
        sync = Sync.all(
            obj, key="TEST", include=["field1", "field2"], exclude=["field3"]
        )

        snapshot = sync._snapshot()
        assert "field1" in snapshot
        assert "field2" in snapshot
        assert "field3" not in snapshot
        assert "private_field" in snapshot  # Not in exclude list

    def test_decorators_with_list_include(self, mock_session: Mock):
        """Test that decorators work with list[str] include"""
        from ws_sync.decorators import sync

        # Use sync() instead of sync_all() to test include as restrictive
        class TestClass:
            @sync("TEST", include=["field1", "field2"])
            def __init__(self):
                self.field1 = "value1"
                self.field2 = "value2"
                self.field3 = "value3"

        obj = TestClass()
        snapshot = obj.sync._snapshot()  # type: ignore
        assert "field1" in snapshot
        assert "field2" in snapshot
        assert "field3" not in snapshot


class TestPartialSyncPatching:
    """Test partial sync behavior with patching"""

    def test_patch_only_included_fields_normal_class(self, mock_session: Mock):
        """Test that patches only affect included fields in normal classes"""
        obj = SimpleClass()
        sync = Sync(obj, key="TEST", include={"field1": ..., "field2": ...})

        # Change included field
        obj.field1 = "new_value1"
        patch = get_patch(sync)
        assert len(patch) == 1
        assert patch[0]["path"] == "/field1"
        assert patch[0]["value"] == "new_value1"

        # Change excluded field - should not generate patch
        obj.field3 = "new_value3"
        patch = get_patch(sync)
        assert len(patch) == 0

    def test_patch_only_included_fields_pydantic(self, mock_session: Mock):
        """Test that patches only affect included fields in Pydantic models"""
        obj = SimpleModel(field1="val1", field2="val2", field3="val3")
        sync = Sync(obj, key="TEST", include={"field1": ..., "field2": ...})

        # Change included field
        obj.field1 = "new_value1"
        patch = get_patch(sync)
        assert len(patch) == 1
        assert patch[0]["path"] == "/field1"
        assert patch[0]["value"] == "new_value1"

        # Change excluded field - should not generate patch
        obj.field3 = "new_value3"
        patch = get_patch(sync)
        assert len(patch) == 0

    def test_patch_excluded_fields_not_tracked(self, mock_session: Mock):
        """Test that excluded fields are not tracked in patches"""
        obj = SimpleClass()
        sync = Sync.all(obj, key="TEST", exclude=["field3"])

        # Change included field
        obj.field1 = "new_value1"
        patch = get_patch(sync)
        assert len(patch) == 1
        assert patch[0]["path"] == "/field1"

        # Change excluded field - should not generate patch
        obj.field3 = "new_value3"
        patch = get_patch(sync)
        assert len(patch) == 0

    def test_patch_inheritance_included_fields(self, mock_session: Mock):
        """Test patching inherited fields that are included"""
        obj = ChildClass()
        sync = Sync(obj, key="TEST", include={"parent_field": ..., "child_field": ...})

        # Change parent field
        obj.parent_field = "new_parent"
        patch = get_patch(sync)
        assert len(patch) == 1
        assert patch[0]["path"] == "/parent_field"
        assert patch[0]["value"] == "new_parent"

        # Change child field
        obj.child_field = "new_child"
        patch = get_patch(sync)
        assert len(patch) == 1
        assert patch[0]["path"] == "/child_field"
        assert patch[0]["value"] == "new_child"

    def test_patch_inheritance_excluded_parent_field(self, mock_session: Mock):
        """Test that excluded parent fields don't generate patches"""
        obj = ChildClass()
        sync = Sync.all(obj, key="TEST", exclude=["parent_field"])

        # Change excluded parent field
        obj.parent_field = "new_parent"
        patch = get_patch(sync)
        assert len(patch) == 0

        # Change included child field
        obj.child_field = "new_child"
        patch = get_patch(sync)
        assert len(patch) == 1
        assert patch[0]["path"] == "/child_field"
        assert patch[0]["value"] == "new_child"

    @pytest.mark.asyncio
    async def test_dependent_property_set_state_works_correctly(
        self, mock_session: Mock
    ):
        """Test that dependent properties work correctly with _set_state after fixing readonly assertion"""
        obj = ClassWithDependentProperty()
        sync = Sync.all(obj, key="TEST_DEPENDENT")

        # Check that full_name is included in sync attributes
        print(f"Sync attributes: {sync.sync_attributes}")
        print(f"Initial full_name: {obj.full_name}")

        # Initial state
        assert obj.first_name == "John"
        assert obj.last_name == "Doe"
        assert obj.full_name == "John Doe"

        # First, let's create a scenario that should trigger the readonly assertion
        # We need to modify the snapshot to include the full_name property
        snapshot = sync._snapshot()
        print(f"Snapshot: {snapshot}")

        # Now test with _set_state which should trigger the readonly assertion
        # When we set first_name to "Jane", the full_name property will automatically change to "Jane Doe"
        # But _set_state will also try to set full_name to its old snapshot value "John Doe"
        # This should trigger the readonly assertion because the property can't be set to "John Doe"
        # after first_name has been changed to "Jane"

        # The issue occurs when the dependent property is processed AFTER its dependencies
        # In Python 3.7+, dict maintains insertion order, so let's set first_name first
        # which will change full_name to "Jane Doe", then try to set full_name to "John Doe"
        new_state = {
            "first_name": "Jane",  # This changes full_name to "Jane Doe"
            "last_name": "Doe",  # This keeps full_name as "Jane Doe"
            "full_name": "John Doe",  # This tries to set full_name to "John Doe", but it's "Jane Doe"
        }

        # This should now work correctly after removing the problematic readonly assertion
        await sync._set_state(new_state)

        # Verify that the dependent property reflects the actual state based on its dependencies
        assert obj.first_name == "Jane"
        assert obj.last_name == "Doe"
        assert (
            obj.full_name == "Jane Doe"
        )  # Property calculated from first_name + last_name

    @pytest.mark.asyncio
    async def test_dependent_property_changes_with_dependency_update(
        self, mock_session: Mock
    ):
        """Test that dependent properties automatically update when dependencies change"""
        obj = ClassWithDependentProperty()
        # No sync needed for this test - just demonstrating property behavior

        # Initial state
        assert obj.first_name == "John"
        assert obj.last_name == "Doe"
        assert obj.full_name == "John Doe"

        # Change first_name directly (not via sync) to see property behavior
        obj.first_name = "Jane"
        assert obj.full_name == "Jane Doe"  # Property automatically updates

        # This demonstrates why the readonly assertion is problematic:
        # When we set first_name = "Jane", the full_name property changes from "John Doe" to "Jane Doe"
        # But the sync system expects full_name to remain "John Doe" (the old snapshot value)
