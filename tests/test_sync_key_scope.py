"""Tests for sync key prefix scoping via sync_key_scope context manager."""

import asyncio

import pytest

from tests.utils import FakeWebSocket
from ws_sync import Session, get_current_sync_key_prefix, sync_key_scope
from ws_sync.decorators import sync_all, sync_only
from ws_sync.sync import Sync


@pytest.fixture
def session():
    """Create a session for testing."""
    return Session()


@pytest.fixture
def fake_ws():
    """Create a fake WebSocket for testing."""
    return FakeWebSocket()


class TestBasicPrefixing:
    """Test basic single-level prefix application."""

    def test_single_prefix_with_explicit_key(self, session, fake_ws):
        """Test that explicit keys get prefixed."""

        class MyObject:
            sync: Sync

            @sync_all("MY_KEY")
            def __init__(self):
                self.value = "test"

        with session:
            session.ws = fake_ws
            with sync_key_scope("abc"):
                obj = MyObject()

            assert obj.sync.key == "abc/MY_KEY"

    def test_single_prefix_with_default_key(self, session, fake_ws):
        """Test that default keys (class names) get prefixed."""

        class MyObject:
            sync: Sync

            @sync_all()
            def __init__(self):
                self.value = "test"

        with session:
            session.ws = fake_ws
            with sync_key_scope("abc"):
                obj = MyObject()

            assert obj.sync.key == "abc/MyObject"

    def test_single_prefix_with_sync_only(self, session, fake_ws):
        """Test prefix with @sync_only decorator."""

        class MyObject:
            sync: Sync

            @sync_only(_key="CUSTOM_KEY", value=...)
            def __init__(self):
                self.value = "test"

        with session:
            session.ws = fake_ws
            with sync_key_scope("abc"):
                obj = MyObject()

            assert obj.sync.key == "abc/CUSTOM_KEY"

    def test_single_prefix_with_sync_only_default(self, session, fake_ws):
        """Test prefix with @sync_only using default key."""

        class MyObject:
            sync: Sync

            @sync_only(value=...)
            def __init__(self):
                self.value = "test"

        with session:
            session.ws = fake_ws
            with sync_key_scope("abc"):
                obj = MyObject()

            assert obj.sync.key == "abc/MyObject"

    def test_single_prefix_with_direct_sync_all(self, session, fake_ws):
        """Test prefix with direct Sync.all() instantiation."""

        class MyObject:
            sync: Sync

            def __init__(self):
                self.value = "test"

        with session:
            session.ws = fake_ws
            with sync_key_scope("abc"):
                obj = MyObject()
                obj.sync = Sync.all(obj, "DIRECT_KEY")

            assert obj.sync.key == "abc/DIRECT_KEY"

    def test_single_prefix_with_direct_sync_only(self, session, fake_ws):
        """Test prefix with direct Sync.only() instantiation."""

        class MyObject:
            sync: Sync

            def __init__(self):
                self.value = "test"

        with session:
            session.ws = fake_ws
            with sync_key_scope("abc"):
                obj = MyObject()
                obj.sync = Sync.only(obj, "DIRECT_KEY", value=...)

            assert obj.sync.key == "abc/DIRECT_KEY"

    def test_single_prefix_with_direct_sync_init(self, session, fake_ws):
        """Test prefix with direct Sync() instantiation."""

        class MyObject:
            sync: Sync

            def __init__(self):
                self.value = "test"

        with session:
            session.ws = fake_ws
            with sync_key_scope("abc"):
                obj = MyObject()
                obj.sync = Sync(obj, "DIRECT_KEY", sync_all=True)

            assert obj.sync.key == "abc/DIRECT_KEY"


class TestNestedPrefixing:
    """Test nested prefix scopes."""

    def test_two_level_nesting(self, session, fake_ws):
        """Test two levels of nesting."""

        class MyObject:
            sync: Sync

            @sync_all("MY_KEY")
            def __init__(self):
                self.value = "test"

        with session:
            session.ws = fake_ws
            with sync_key_scope("abc"), sync_key_scope("nested"):
                obj = MyObject()

            assert obj.sync.key == "abc/nested/MY_KEY"

    def test_three_level_nesting(self, session, fake_ws):
        """Test three levels of nesting."""

        class MyObject:
            sync: Sync

            @sync_all("MY_KEY")
            def __init__(self):
                self.value = "test"

        with session:
            session.ws = fake_ws
            with (
                sync_key_scope("level1"),
                sync_key_scope("level2"),
                sync_key_scope("level3"),
            ):
                obj = MyObject()

            assert obj.sync.key == "level1/level2/level3/MY_KEY"

    def test_multiple_objects_at_different_nesting_levels(self, session, fake_ws):
        """Test creating objects at different nesting levels."""

        class MyObject:
            sync: Sync

            @sync_all("MY_KEY")
            def __init__(self):
                self.value = "test"

        with session:
            session.ws = fake_ws
            with sync_key_scope("level1"):
                obj1 = MyObject()
                with sync_key_scope("level2"):
                    obj2 = MyObject()
                    with sync_key_scope("level3"):
                        obj3 = MyObject()

            assert obj1.sync.key == "level1/MY_KEY"
            assert obj2.sync.key == "level1/level2/MY_KEY"
            assert obj3.sync.key == "level1/level2/level3/MY_KEY"


class TestEmptyPrefixHandling:
    """Test handling of empty and None prefixes."""

    def test_empty_string_prefix_is_skipped(self, session, fake_ws):
        """Test that empty string prefixes are skipped."""

        class MyObject:
            sync: Sync

            @sync_all("MY_KEY")
            def __init__(self):
                self.value = "test"

        with session:
            session.ws = fake_ws
            with sync_key_scope(""):
                obj = MyObject()

            assert obj.sync.key == "MY_KEY"

    def test_none_prefix_is_skipped(self, session, fake_ws):
        """Test that None prefixes are skipped."""

        class MyObject:
            sync: Sync

            @sync_all("MY_KEY")
            def __init__(self):
                self.value = "test"

        with session:
            session.ws = fake_ws
            with sync_key_scope(None):
                obj = MyObject()

            assert obj.sync.key == "MY_KEY"

    def test_mixed_empty_and_non_empty_prefixes(self, session, fake_ws):
        """Test mixing empty and non-empty prefixes."""

        class MyObject:
            sync: Sync

            @sync_all("MY_KEY")
            def __init__(self):
                self.value = "test"

        with session:
            session.ws = fake_ws
            with (
                sync_key_scope("abc"),
                sync_key_scope(""),
                sync_key_scope("nested"),
                sync_key_scope(None),
            ):
                obj = MyObject()

            # Empty and None should be filtered out
            assert obj.sync.key == "abc/nested/MY_KEY"

    def test_only_empty_prefixes(self, session, fake_ws):
        """Test when all prefixes are empty."""

        class MyObject:
            sync: Sync

            @sync_all("MY_KEY")
            def __init__(self):
                self.value = "test"

        with session:
            session.ws = fake_ws
            with sync_key_scope(""), sync_key_scope(None), sync_key_scope(""):
                obj = MyObject()

            assert obj.sync.key == "MY_KEY"


class TestGetCurrentPrefix:
    """Test the get_current_sync_key_prefix() function."""

    def test_get_prefix_with_no_scope(self):
        """Test getting prefix when no scope is active."""
        assert get_current_sync_key_prefix() is None

    def test_get_prefix_with_single_scope(self):
        """Test getting prefix with single scope."""
        with sync_key_scope("abc"):
            assert get_current_sync_key_prefix() == "abc"

    def test_get_prefix_with_nested_scopes(self):
        """Test getting prefix with nested scopes."""
        with sync_key_scope("abc"):
            assert get_current_sync_key_prefix() == "abc"
            with sync_key_scope("nested"):
                assert get_current_sync_key_prefix() == "abc/nested"
                with sync_key_scope("deep"):
                    assert get_current_sync_key_prefix() == "abc/nested/deep"

    def test_get_prefix_with_empty_scopes(self):
        """Test getting prefix with empty scopes (should be filtered)."""
        with (
            sync_key_scope("abc"),
            sync_key_scope(""),
            sync_key_scope(None),
            sync_key_scope("nested"),
        ):
            assert get_current_sync_key_prefix() == "abc/nested"

    def test_get_prefix_after_exiting_scope(self):
        """Test that prefix is cleared after exiting scope."""
        with sync_key_scope("abc"):
            assert get_current_sync_key_prefix() == "abc"

        assert get_current_sync_key_prefix() is None

    def test_get_prefix_partial_exit(self):
        """Test prefix after exiting inner scopes."""
        with sync_key_scope("level1"):
            with sync_key_scope("level2"):
                assert get_current_sync_key_prefix() == "level1/level2"

            # After exiting level2
            assert get_current_sync_key_prefix() == "level1"


class TestEventRegistration:
    """Test that prefixed keys are used in event registration."""

    def test_event_handlers_use_prefixed_key(self, session, fake_ws):
        """Test that event handlers are registered with prefixed keys."""

        class MyObject:
            sync: Sync

            @sync_all("MY_KEY")
            def __init__(self):
                self.value = "test"

        with session:
            session.ws = fake_ws
            with sync_key_scope("abc"):
                obj = MyObject()  # noqa: F841

            # Check that event handlers are registered with prefixed key
            assert "_GET:abc/MY_KEY" in session.event_handlers
            assert "_SET:abc/MY_KEY" in session.event_handlers
            assert "_PATCH:abc/MY_KEY" in session.event_handlers

    @pytest.mark.asyncio
    async def test_sync_sends_with_prefixed_key(self, session, fake_ws):
        """Test that sync operations send events with prefixed keys."""

        class MyObject:
            sync: Sync

            @sync_all("MY_KEY")
            def __init__(self):
                self.value = "initial"

        with session:
            session.ws = fake_ws
            with sync_key_scope("abc"):
                obj = MyObject()

            # Clear initial messages
            fake_ws.sent.clear()

            # Modify and sync
            obj.value = "updated"
            await obj.sync()

            # Check that patch event uses prefixed key
            assert len(fake_ws.sent) > 0
            _msg_type, patch_msg = fake_ws.sent[0]
            assert patch_msg["type"] == "_PATCH:abc/MY_KEY"


class TestConcurrentTasks:
    """Test that different async tasks can have different prefixes."""

    @pytest.mark.asyncio
    async def test_concurrent_tasks_with_different_prefixes(self):
        """Test concurrent tasks can have independent prefix contexts.

        This test verifies that ContextVar properly isolates prefix stacks
        across concurrent tasks.
        """
        from ws_sync.session import Session

        class MyObject:
            sync: Sync

            @sync_all("MY_KEY")
            def __init__(self):
                self.value = "test"

        objects = []

        async def create_with_prefix(prefix):
            # Each async task gets its own session and WebSocket
            local_session = Session()
            local_ws = FakeWebSocket()

            with local_session:
                local_session.ws = local_ws  # type: ignore[assignment]
                with sync_key_scope(prefix):
                    obj = MyObject()
                    objects.append(obj)
                    await asyncio.sleep(0.01)

        # Run concurrent tasks with different prefixes
        await asyncio.gather(
            create_with_prefix("prefix1"),
            create_with_prefix("prefix2"),
            create_with_prefix("prefix3"),
        )

        # Each should have its own prefix
        keys = {obj.sync.key for obj in objects}
        assert keys == {"prefix1/MY_KEY", "prefix2/MY_KEY", "prefix3/MY_KEY"}


class TestNoScopeUsage:
    """Test that objects created without scope work as before."""

    def test_no_scope_with_explicit_key(self, session, fake_ws):
        """Test object creation without scope using explicit key."""

        class MyObject:
            sync: Sync

            @sync_all("MY_KEY")
            def __init__(self):
                self.value = "test"

        with session:
            session.ws = fake_ws
            obj = MyObject()

        assert obj.sync.key == "MY_KEY"

    def test_no_scope_with_default_key(self, session, fake_ws):
        """Test object creation without scope using default key."""

        class MyObject:
            sync: Sync

            @sync_all()
            def __init__(self):
                self.value = "test"

        with session:
            session.ws = fake_ws
            obj = MyObject()

        assert obj.sync.key == "MyObject"


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_prefix_with_special_characters(self, session, fake_ws):
        """Test prefixes with special characters."""

        class MyObject:
            sync: Sync

            @sync_all("MY_KEY")
            def __init__(self):
                self.value = "test"

        with session:
            session.ws = fake_ws
            with sync_key_scope("user-123"), sync_key_scope("session_456"):
                obj = MyObject()

        assert obj.sync.key == "user-123/session_456/MY_KEY"

    def test_prefix_with_numbers(self, session, fake_ws):
        """Test prefixes that are numbers."""

        class MyObject:
            sync: Sync

            @sync_all("MY_KEY")
            def __init__(self):
                self.value = "test"

        with session:
            session.ws = fake_ws
            with sync_key_scope("123"), sync_key_scope("456"):
                obj = MyObject()

        assert obj.sync.key == "123/456/MY_KEY"

    def test_reusing_scope_context_manager(self, session, fake_ws):
        """Test entering and exiting scope multiple times."""

        class MyObject:
            sync: Sync

            @sync_all("MY_KEY")
            def __init__(self):
                self.value = "test"

        with session:
            session.ws = fake_ws

            with sync_key_scope("first"):
                obj1 = MyObject()

            # Outside scope now
            obj2 = MyObject()

            with sync_key_scope("second"):
                obj3 = MyObject()

        assert obj1.sync.key == "first/MY_KEY"
        assert obj2.sync.key == "MY_KEY"
        assert obj3.sync.key == "second/MY_KEY"

    def test_exception_in_scope_cleans_up(self, session, fake_ws):
        """Test that prefix is cleaned up even when exception occurs."""

        class MyObject:
            sync: Sync

            @sync_all("MY_KEY")
            def __init__(self):
                self.value = "test"

        with session:
            session.ws = fake_ws

            try:
                with sync_key_scope("abc"):
                    obj1 = MyObject()  # noqa: F841
                    raise ValueError("Test exception")  # noqa: TRY301
            except ValueError:
                pass

            # Prefix should be cleaned up
            assert get_current_sync_key_prefix() is None

            # New object should have no prefix
            obj2 = MyObject()
            assert obj2.sync.key == "MY_KEY"
