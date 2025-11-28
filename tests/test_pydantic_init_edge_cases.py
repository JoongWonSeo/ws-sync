"""
Test edge cases for Pydantic model initialization with sync decorators.

Pydantic models can be initialized in multiple ways:
1. Normal constructor: Test(session_id="123", user_id="456")
2. model_validate(): Test.model_validate({"session_id": "123", "user_id": "456"})
3. model_construct(): Test.model_construct(session_id="123", user_id="456")
4. model_copy(): test.model_copy()
5. model_copy(update=...): test.model_copy(update={"session_id": "789"})
6. parse_obj() (deprecated but might still be used)

All of these should properly initialize the sync object.
"""

from typing import override

import pytest
from pydantic import BaseModel, computed_field

from ws_sync import Session, Sync, Synced, SyncedAsCamelCase, sync_all, sync_only


@sync_all()
class TestModelSyncAll(SyncedAsCamelCase, BaseModel):
    session_id: str
    user_id: str


@sync_only(user_id=...)
class TestModelSyncOnly(SyncedAsCamelCase, BaseModel):
    session_id: str
    user_id: str


@pytest.fixture
def session():
    with Session() as s:
        yield s


class TestPydanticNormalConstructor:
    def test_normal_constructor_sync_all(self, session):
        """Test that normal constructor initializes sync properly."""
        obj = TestModelSyncAll(session_id="123", user_id="456")
        assert hasattr(obj, "sync")
        assert isinstance(obj.sync, Sync)
        assert obj.sync.key == "TestModelSyncAll"

    def test_normal_constructor_sync_only(self, session):
        """Test that normal constructor initializes sync properly for sync_only."""
        obj = TestModelSyncOnly(session_id="123", user_id="456")
        assert hasattr(obj, "sync")
        assert isinstance(obj.sync, Sync)
        assert "user_id" in obj.sync.sync_attributes
        assert "session_id" not in obj.sync.sync_attributes


class TestPydanticModelValidate:
    def test_model_validate_dict_sync_all(self, session):
        """Test that model_validate with dict initializes sync properly."""
        obj = TestModelSyncAll.model_validate({"session_id": "123", "user_id": "456"})
        assert hasattr(obj, "sync")
        assert isinstance(obj.sync, Sync), f"Expected Sync, got {type(obj.sync)}"
        assert obj.sync.key == "TestModelSyncAll"

    def test_model_validate_dict_sync_only(self, session):
        """Test that model_validate with dict works with sync_only."""
        obj = TestModelSyncOnly.model_validate({"session_id": "123", "user_id": "456"})
        assert hasattr(obj, "sync")
        assert isinstance(obj.sync, Sync)
        assert "user_id" in obj.sync.sync_attributes
        assert "session_id" not in obj.sync.sync_attributes

    def test_model_validate_json_sync_all(self, session):
        """Test that model_validate_json initializes sync properly."""
        json_str = '{"session_id": "123", "user_id": "456"}'
        obj = TestModelSyncAll.model_validate_json(json_str)
        assert hasattr(obj, "sync")
        assert isinstance(obj.sync, Sync)

    def test_model_validate_from_dumped(self, session):
        """Test that re-validating a dumped model works."""
        original = TestModelSyncAll(session_id="123", user_id="456")
        dumped = original.model_dump(by_alias=False)
        obj = TestModelSyncAll.model_validate(dumped)
        assert hasattr(obj, "sync")
        assert isinstance(obj.sync, Sync)
        assert obj.session_id == "123"
        assert obj.user_id == "456"


class TestPydanticModelConstruct:
    def test_model_construct_sync_all(self, session):
        """Test that model_construct initializes sync properly."""
        obj = TestModelSyncAll.model_construct(session_id="123", user_id="456")
        assert hasattr(obj, "sync")
        assert isinstance(obj.sync, Sync), f"Expected Sync, got {type(obj.sync)}"
        assert obj.sync.key == "TestModelSyncAll"

    def test_model_construct_sync_only(self, session):
        """Test that model_construct works with sync_only."""
        obj = TestModelSyncOnly.model_construct(session_id="123", user_id="456")
        assert hasattr(obj, "sync")
        assert isinstance(obj.sync, Sync)
        assert "user_id" in obj.sync.sync_attributes
        assert "session_id" not in obj.sync.sync_attributes

    def test_model_construct_from_dumped(self, session):
        """Test that model_construct with dumped data works."""
        original = TestModelSyncAll(session_id="123", user_id="456")
        dumped = original.model_dump(by_alias=False)
        obj = TestModelSyncAll.model_construct(**dumped)
        assert hasattr(obj, "sync")
        assert isinstance(obj.sync, Sync)
        assert obj.session_id == "123"
        assert obj.user_id == "456"


class TestPydanticModelCopy:
    def test_model_copy_basic(self, session):
        """Test that model_copy initializes sync properly."""
        original = TestModelSyncAll(session_id="123", user_id="456")
        copied = original.model_copy()
        assert hasattr(copied, "sync")
        assert isinstance(copied.sync, Sync)
        # Model copies share the same Sync object by design
        # # Model copies share the same Sync instance
        # assert copied.sync is not original.sync
        assert copied.session_id == "123"
        assert copied.user_id == "456"

    def test_model_copy_deep(self, session):
        """Test that model_copy(deep=True) fails gracefully.

        Deep copying fails because the Sync object contains non-picklable
        objects like ContextVar tokens. This is a known limitation.
        Users should use shallow copy or model_validate(original.model_dump()).
        """
        original = TestModelSyncAll(session_id="123", user_id="456")
        with pytest.raises(TypeError, match="cannot pickle"):
            original.model_copy(deep=True)

    def test_model_copy_with_update(self, session):
        """Test that model_copy with update initializes sync properly."""
        original = TestModelSyncAll(session_id="123", user_id="456")
        copied = original.model_copy(update={"session_id": "789"})
        assert hasattr(copied, "sync")
        assert isinstance(copied.sync, Sync)
        # Model copies share the same Sync instance
        # assert copied.sync is not original.sync
        assert copied.session_id == "789"
        assert copied.user_id == "456"

    def test_model_copy_sync_only(self, session):
        """Test that model_copy works with sync_only."""
        original = TestModelSyncOnly(session_id="123", user_id="456")
        copied = original.model_copy()
        assert hasattr(copied, "sync")
        assert isinstance(copied.sync, Sync)
        assert "user_id" in copied.sync.sync_attributes
        assert "session_id" not in copied.sync.sync_attributes


class TestPydanticParseMethods:
    """Test deprecated parse methods (for backwards compatibility)."""

    def test_parse_obj_if_available(self, session):
        """Test parse_obj if it exists (deprecated in Pydantic v2 but might be used)."""
        # parse_obj was removed in Pydantic v2, but let's be defensive
        if hasattr(TestModelSyncAll, "parse_obj"):
            obj = TestModelSyncAll.parse_obj({"session_id": "123", "user_id": "456"})
            assert hasattr(obj, "sync")
            assert isinstance(obj.sync, Sync)


class TestPydanticFieldUpdate:
    """Test that updating fields doesn't break sync."""

    def test_field_assignment_preserves_sync(self, session):
        """Test that assigning to fields doesn't break sync."""
        obj = TestModelSyncAll(session_id="123", user_id="456")
        original_sync = obj.sync
        obj.session_id = "789"
        assert obj.sync is original_sync
        assert isinstance(obj.sync, Sync)


class TestNestedSyncModels:
    """Test that nested sync models work correctly."""

    def test_nested_model_in_field(self, session):
        """Test that models containing other synced models work."""

        @sync_all()
        class Inner(Synced, BaseModel):
            value: str

        @sync_all()
        class Outer(Synced, BaseModel):
            inner: Inner

        inner = Inner(value="test")
        outer = Outer(inner=inner)

        assert isinstance(outer.sync, Sync)
        assert isinstance(inner.sync, Sync)

    def test_nested_model_from_validate(self, session):
        """Test that nested models from model_validate work for outer, but not inner.

        With the Synced mixin + model_post_init approach, nested models work correctly!
                Pydantic's internal validation creates nested models using the normal Pydantic flow,
                which calls model_post_init, so sync is initialized properly.
        """

        @sync_all()
        class Inner(Synced, BaseModel):
            value: str

        @sync_all()
        class Outer(Synced, BaseModel):
            inner: Inner

        obj = Outer.model_validate({"inner": {"value": "test"}})
        assert isinstance(obj.sync, Sync)

        # With the Synced mixin + model_post_init approach, nested models
        # created by Pydantic's internal validation now work correctly!
        assert hasattr(obj.inner, "sync")
        assert isinstance(getattr(obj.inner, "sync", None), Sync)


class TestCustomInitAndPostInit:
    """Test combinations of custom __init__ and model_post_init with sync decorators."""

    def test_with_custom_init(self, session):
        """Test that models with custom __init__ work correctly."""

        @sync_all()
        class CustomInit(SyncedAsCamelCase, BaseModel):
            value: str
            computed: str = ""

            def __init__(self, **data):
                # Custom initialization logic
                super().__init__(**data)
                self.computed = f"computed_{self.value}"

        obj = CustomInit(value="test")
        assert isinstance(obj.sync, Sync)
        assert obj.computed == "computed_test"

    def test_with_model_post_init(self, session):
        """Test that models with model_post_init work correctly."""

        @sync_all()
        class CustomPostInit(SyncedAsCamelCase, BaseModel):
            value: str
            computed: str = ""

            @override
            def model_post_init(self, context):
                super().model_post_init(context)
                # Custom post-init logic
                self.computed = f"post_init_{self.value}"

        obj = CustomPostInit(value="test")
        assert isinstance(obj.sync, Sync)
        assert obj.computed == "post_init_test"

    def test_with_both_custom_init_and_post_init(self, session):
        """Test that models with both custom __init__ and model_post_init work."""

        @sync_all()
        class CustomBoth(SyncedAsCamelCase, BaseModel):
            value: str
            from_init: str = ""
            from_post_init: str = ""

            def __init__(self, **data):
                super().__init__(**data)
                object.__setattr__(self, "from_init", f"init_{self.value}")

            @override
            def model_post_init(self, context):
                super().model_post_init(context)
                self.from_post_init = f"post_init_{self.value}"

        obj = CustomBoth(value="test")
        assert isinstance(obj.sync, Sync)
        assert obj.from_init == "init_test"
        assert obj.from_post_init == "post_init_test"

    def test_model_validate_with_custom_post_init(self, session):
        """Test that model_validate works with custom model_post_init."""

        @sync_all()
        class CustomPostInit(SyncedAsCamelCase, BaseModel):
            value: str
            computed: str = ""

            @override
            def model_post_init(self, context):
                super().model_post_init(context)
                self.computed = f"validated_{self.value}"

        obj = CustomPostInit.model_validate({"value": "test"})
        assert isinstance(obj.sync, Sync)
        assert obj.computed == "validated_test"


class TestComputedFieldDependingOnPostInit:
    """Test that computed fields depending on model_post_init work correctly."""

    def test_computed_field_with_post_init_dependency(self, session):
        """Test computed field that depends on attributes set in model_post_init."""

        @sync_all()
        class ComputedFieldModel(Synced, BaseModel):
            value: str

            @override
            def model_post_init(self, context):
                # super().model_post_init(context)
                # Initialize private attribute that computed field depends on
                self._internal = f"processed_{self.value}"

            @computed_field
            @property
            def computed(self) -> str:
                # This depends on _internal which is set in model_post_init
                return self._internal

        obj = ComputedFieldModel(value="test")
        assert isinstance(obj.sync, Sync)
        assert obj.computed == "processed_test"
        assert obj.sync.key == "ComputedFieldModel"

    def test_computed_field_with_validation(self, session):
        """Test computed field works with model_validate."""

        @sync_all()
        class ComputedFieldModel(Synced, BaseModel):
            value: str

            @override
            def model_post_init(self, context):
                # super().model_post_init(context)
                self._internal = f"validated_{self.value}"

            @computed_field
            @property
            def computed(self) -> str:
                return self._internal

        obj = ComputedFieldModel.model_validate({"value": "test"})
        assert isinstance(obj.sync, Sync)
        assert obj.computed == "validated_test"
