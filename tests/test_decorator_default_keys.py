"""
Tests for @sync_all and @sync_only decorators with default key behavior.
These tests should fail initially and pass after implementing the feature.
"""

from unittest.mock import Mock

from ws_sync import sync_all, sync_only
from ws_sync.sync import Sync


class TestDecoratorDefaultKeys:
    """Test suite for decorator default key functionality"""

    def test_sync_all_with_empty_parentheses(self, mock_session: Mock):
        """Test @sync_all() decorator with empty parentheses - should default to class name"""

        class AnotherTestClass:
            sync: Sync

            @sync_all()  # Empty parentheses, should default to "AnotherTestClass"
            def __init__(self):
                self.value = "test"

        obj = AnotherTestClass()

        # The sync key should default to the class name
        assert obj.sync.key == "AnotherTestClass"

    def test_sync_all_with_explicit_key(self, mock_session: Mock):
        """Test @sync_all("CUSTOM_KEY") - explicit key should take precedence"""

        class ExplicitKeyClass:
            sync: Sync

            @sync_all("CUSTOM_KEY")
            def __init__(self):
                self.value = "test"

        obj = ExplicitKeyClass()

        # The sync key should be the explicit key
        assert obj.sync.key == "CUSTOM_KEY"

    def test_sync_all_with_other_params(self, mock_session: Mock):
        """Test @sync_all() with other parameters but no key - should default to class name"""

        class ParamsTestClass:
            sync: Sync

            @sync_all(toCamelCase=True, send_on_init=False)
            def __init__(self):
                self.test_value = "test"

        obj = ParamsTestClass()

        # The sync key should default to the class name
        assert obj.sync.key == "ParamsTestClass"
        # Other parameters should work as expected
        assert (
            obj.sync.casing_func is not None
        )  # toCamelCase=True sets a casing function
        assert obj.sync.send_on_init is False

    def test_sync_only_without_key_param(self, mock_session: Mock):
        """Test @sync_only without _key parameter - should default to class name"""

        class SyncOnlyTestClass:
            sync: Sync

            @sync_only(
                value=...
            )  # No _key parameter, should default to "SyncOnlyTestClass"
            def __init__(self):
                self.value = "test"
                self.private_value = "private"

        obj = SyncOnlyTestClass()

        # The sync key should default to the class name
        assert obj.sync.key == "SyncOnlyTestClass"

    def test_sync_only_with_empty_key(self, mock_session: Mock):
        """Test @sync_only with _key=None - should default to class name"""

        class EmptyKeySyncOnlyClass:
            sync: Sync

            @sync_only(_key=None, value=...)
            def __init__(self):
                self.value = "test"

        obj = EmptyKeySyncOnlyClass()

        # The sync key should default to the class name
        assert obj.sync.key == "EmptyKeySyncOnlyClass"

    def test_sync_only_with_explicit_key(self, mock_session: Mock):
        """Test @sync_only with explicit _key - should use the explicit key"""

        class ExplicitSyncOnlyClass:
            sync: Sync

            @sync_only(_key="EXPLICIT_KEY", value=...)
            def __init__(self):
                self.value = "test"

        obj = ExplicitSyncOnlyClass()

        # The sync key should be the explicit key
        assert obj.sync.key == "EXPLICIT_KEY"

    def test_sync_only_with_other_params_no_key(self, mock_session: Mock):
        """Test @sync_only with other params but no key - should default to class name"""

        class SyncOnlyParamsClass:
            sync: Sync

            @sync_only(_toCamelCase=True, test_attr=...)
            def __init__(self):
                self.test_attr = "test"

        obj = SyncOnlyParamsClass()

        # The sync key should default to the class name
        assert obj.sync.key == "SyncOnlyParamsClass"
        # Other parameters should work as expected
        assert (
            obj.sync.casing_func is not None
        )  # _toCamelCase=True sets a casing function

    def test_nested_class_default_key(self, mock_session: Mock):
        """Test that nested classes use their simple name, not full qualified name"""

        class OuterClass:
            class InnerClass:
                sync: Sync

                @sync_all()
                def __init__(self):
                    self.value = "nested"

        obj = OuterClass.InnerClass()

        # Should use simple class name, not "OuterClass.InnerClass"
        assert obj.sync.key == "InnerClass"

    def test_class_with_special_characters_in_name(self, mock_session: Mock):
        """Test class names with special characters (if valid Python identifiers)"""

        class Class_With_Underscores:
            sync: Sync

            @sync_all()
            def __init__(self):
                self.value = "underscore"

        obj = Class_With_Underscores()

        # Should preserve the class name exactly as written
        assert obj.sync.key == "Class_With_Underscores"

    # ===== Additional @sync_all tests for complete coverage =====

    def test_sync_all_with_include_dict(self, mock_session: Mock):
        """Test @sync_all with include dict parameter"""

        class SyncAllIncludeClass:
            sync: Sync

            @sync_all(include={"value": "custom_name"})
            def __init__(self):
                self.value = "test"
                self.other = "also_synced"

        obj = SyncAllIncludeClass()

        # The sync key should default to the class name
        assert obj.sync.key == "SyncAllIncludeClass"

    def test_sync_all_with_exclude_list(self, mock_session: Mock):
        """Test @sync_all with exclude list parameter"""

        class SyncAllExcludeClass:
            sync: Sync

            @sync_all(exclude=["excluded_attr"])
            def __init__(self):
                self.value = "test"
                self.excluded_attr = "not_synced"

        obj = SyncAllExcludeClass()

        # The sync key should default to the class name
        assert obj.sync.key == "SyncAllExcludeClass"
        # excluded_attr should not be in sync_attributes
        assert "excluded_attr" not in obj.sync.sync_attributes

    def test_sync_all_full_explicit_args(self, mock_session: Mock):
        """Test @sync_all with all parameters explicit"""

        class SyncAllFullClass:
            sync: Sync

            @sync_all(
                key="FULL_SYNC_ALL_KEY",
                include=["specific_attr"],
                exclude=["excluded_attr"],
                toCamelCase=True,
                send_on_init=False,
                expose_running_tasks=True,
            )
            def __init__(self):
                self.specific_attr = "included"
                self.excluded_attr = "not_included"

        obj = SyncAllFullClass()

        # All explicit parameters should be respected
        assert obj.sync.key == "FULL_SYNC_ALL_KEY"
        assert obj.sync.send_on_init is False
        assert obj.sync.casing_func is not None
        assert obj.sync.task_exposure is not None

    # ===== Additional @sync_only tests for complete coverage =====

    def test_sync_only_with_camel_case(self, mock_session: Mock):
        """Test @sync_only with camelCase conversion"""

        class SyncOnlyCamelClass:
            sync: Sync

            @sync_only(_toCamelCase=True, test_attr=..., another_attr=...)
            def __init__(self):
                self.test_attr = "test"
                self.another_attr = "another"
                self.not_synced = "excluded"

        obj = SyncOnlyCamelClass()

        # The sync key should default to the class name
        assert obj.sync.key == "SyncOnlyCamelClass"
        # toCamelCase should be active
        assert obj.sync.casing_func is not None
        # Only specified attributes should be synced
        assert "test_attr" in obj.sync.sync_attributes
        assert "another_attr" in obj.sync.sync_attributes
        assert "not_synced" not in obj.sync.sync_attributes

    def test_sync_only_with_custom_sync_keys(self, mock_session: Mock):
        """Test @sync_only with custom sync keys for attributes"""

        class SyncOnlyCustomKeysClass:
            sync: Sync

            @sync_only(
                _key="CUSTOM_SYNC_ONLY_KEY",
                original_name="customSyncKey",
                another_attr=...,
            )
            def __init__(self):
                self.original_name = "value"
                self.another_attr = "another"

        obj = SyncOnlyCustomKeysClass()

        # The sync key should be the explicit key
        assert obj.sync.key == "CUSTOM_SYNC_ONLY_KEY"

    def test_sync_only_full_explicit_args(self, mock_session: Mock):
        """Test @sync_only with all parameters explicit"""

        class SyncOnlyFullClass:
            sync: Sync

            @sync_only(
                _key="FULL_SYNC_ONLY_KEY",
                _toCamelCase=True,
                _send_on_init=False,
                _expose_running_tasks=True,
                attr1=...,
                attr2="customKey",
            )
            def __init__(self):
                self.attr1 = "value1"
                self.attr2 = "value2"
                self.not_synced = "excluded"

        obj = SyncOnlyFullClass()

        # All explicit parameters should be respected
        assert obj.sync.key == "FULL_SYNC_ONLY_KEY"
        assert obj.sync.send_on_init is False
        assert obj.sync.casing_func is not None
        assert obj.sync.task_exposure is not None
        # Only specified attributes should be synced
        assert "attr1" in obj.sync.sync_attributes
        assert "attr2" in obj.sync.sync_attributes
        assert "not_synced" not in obj.sync.sync_attributes

    # ===== Edge cases and special scenarios =====

    def test_deeply_nested_class_default_key(self, mock_session: Mock):
        """Test deeply nested classes use their simple name"""

        class Outer:
            class Middle:
                class Inner:
                    sync: Sync

                    @sync_all()
                    def __init__(self):
                        self.value = "deeply_nested"

        obj = Outer.Middle.Inner()

        # Should use just the innermost class name
        assert obj.sync.key == "Inner"

    def test_class_with_numbers_in_name(self, mock_session: Mock):
        """Test class names with numbers"""

        class TestClass123:
            sync: Sync

            @sync_all()
            def __init__(self):
                self.value = "with_numbers"

        obj = TestClass123()

        # Should preserve numbers in the class name
        assert obj.sync.key == "TestClass123"

    def test_multiple_decorators_same_class(self, mock_session: Mock):
        """Test that each instance gets its own sync object"""

        class MultipleInstancesClass:
            sync: Sync

            @sync_all()
            def __init__(self):
                self.value = "instance"

        obj1 = MultipleInstancesClass()
        obj2 = MultipleInstancesClass()

        # Both should have the same key but different sync objects
        assert obj1.sync.key == "MultipleInstancesClass"
        assert obj2.sync.key == "MultipleInstancesClass"
        assert obj1.sync is not obj2.sync
