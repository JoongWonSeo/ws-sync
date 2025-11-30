"""
Tests for memory leak issues with Sync objects.

These tests verify that:
1. Event handlers are properly cleaned up when Sync objects are deleted
2. Init handlers don't accumulate indefinitely
3. Dynamic keys don't cause unbounded handler growth
4. Objects can be garbage collected when their Sync is no longer needed
"""

import gc
import weakref

import pytest

from ws_sync import sync_all
from ws_sync.session import Session, session_context
from ws_sync.sync import Sync


@pytest.fixture
def real_session():
    """Create a real Session (not mocked) for testing handler accumulation."""
    session = Session()
    token = session_context.set(session)
    yield session
    session_context.reset(token)


class TestEventHandlerAccumulation:
    """Tests for event handler accumulation in Session."""

    def test_dynamic_keys_accumulate_handlers(self, real_session: Session):
        """
        Test that creating Sync objects with dynamic keys accumulates event handlers,
        and that they are cleaned up when the Sync objects are garbage collected.
        """
        initial_handler_count = len(real_session.event_handlers)

        class DynamicObj:
            value: int = 0

        # Create multiple Sync objects with dynamic keys
        # NOTE: We append directly to avoid loop variables keeping the last object alive
        # (Python loop variables persist after the loop ends, preventing GC)
        syncs = []
        for i in range(10):
            syncs.append(Sync.all(DynamicObj(), f"DYNAMIC_KEY_{i}", send_on_init=False))  # noqa: PERF401

        # Each Sync registers 6 handlers: get, set, patch, action, task_start, task_cancel
        handlers_per_sync = 6
        expected_handlers = initial_handler_count + (10 * handlers_per_sync)
        assert len(real_session.event_handlers) == expected_handlers

        # Now delete the syncs - handlers should be cleaned up
        del syncs
        gc.collect()

        assert len(real_session.event_handlers) == initial_handler_count, (
            f"Expected handlers to be cleaned up after Sync deletion. "
            f"Initial: {initial_handler_count}, Current: {len(real_session.event_handlers)}"
        )

    def test_same_key_overrides_but_handlers_accumulate_for_different_keys(
        self, real_session: Session
    ):
        """
        Test that same key overrides handlers, but different keys accumulate.
        """
        initial_count = len(real_session.event_handlers)
        handlers_per_sync = 6  # get, set, patch, action, task_start, task_cancel

        class SimpleObj:
            value: int = 0

        # Create first Sync with key A
        obj1 = SimpleObj()
        sync1 = Sync.all(obj1, "KEY_A", send_on_init=False)
        count_after_first = len(real_session.event_handlers)
        assert count_after_first == initial_count + handlers_per_sync

        # Create second Sync with same key A - should override
        obj2 = SimpleObj()
        sync2 = Sync.all(obj2, "KEY_A", send_on_init=False)
        count_after_override = len(real_session.event_handlers)

        # Handler count should stay the same (overriding)
        assert count_after_override == count_after_first

        # Create third Sync with different key B - should add new handlers
        obj3 = SimpleObj()
        sync3 = Sync.all(obj3, "KEY_B", send_on_init=False)
        count_after_new_key = len(real_session.event_handlers)

        assert count_after_new_key == count_after_first + handlers_per_sync

        # Clean up - handlers should be removed
        del sync1, sync2, sync3
        gc.collect()

        assert len(real_session.event_handlers) == initial_count


class TestInitHandlerAccumulation:
    """Tests for init handler accumulation in Session."""

    def test_init_handlers_accumulate_with_dynamic_keys(self, real_session: Session):
        """
        Test that init handlers accumulate when creating Sync objects with dynamic keys,
        and that they are cleaned up when the Sync objects are garbage collected.
        """
        initial_init_handler_count = len(real_session.init_handlers)

        class DynamicObj:
            value: int = 0

        # Create multiple Sync objects with different keys, all with send_on_init=True
        # NOTE: We append directly to avoid loop variables keeping the last object alive
        # (Python loop variables persist after the loop ends, preventing GC)
        syncs = []
        for i in range(10):
            syncs.append(Sync.all(DynamicObj(), f"INIT_KEY_{i}", send_on_init=True))  # noqa: PERF401

        # Each Sync with send_on_init=True adds 1 init handler
        assert len(real_session.init_handlers) == initial_init_handler_count + 10

        # Delete the syncs
        del syncs
        gc.collect()

        assert len(real_session.init_handlers) == initial_init_handler_count, (
            f"Expected init handlers to be cleaned up. "
            f"Initial: {initial_init_handler_count}, Current: {len(real_session.init_handlers)}"
        )

    def test_same_key_with_send_on_init_accumulates_init_handlers(
        self, real_session: Session
    ):
        """
        Test that creating Sync with same key but send_on_init=True causes
        init handlers to accumulate (since it's a list, not a dict).
        """
        initial_count = len(real_session.init_handlers)

        class SimpleObj:
            value: int = 0

        # Create multiple Sync objects with the SAME key
        syncs = []
        for _i in range(5):
            obj = SimpleObj()
            sync = Sync.all(obj, "SAME_KEY", send_on_init=True)
            syncs.append(sync)

        # THIS EXPOSES A BUG - init handlers accumulate even with same key!
        # Because init_handlers is a list, not a dict
        assert len(real_session.init_handlers) == initial_count + 5, (
            "Init handlers should accumulate (this is a bug to fix)"
        )


class TestObjectGarbageCollection:
    """Tests for proper garbage collection of Sync-related objects."""

    def test_sync_object_prevents_gc_of_target_object(self, real_session: Session):
        """
        Test that the Session's reference to handlers prevents garbage collection
        of the underlying synced object.
        """

        class TrackedObj:
            value: int = 0

        obj = TrackedObj()
        obj_ref = weakref.ref(obj)

        sync = Sync.all(obj, "TRACKED", send_on_init=True)
        sync_ref = weakref.ref(sync)

        # Both should be alive
        assert obj_ref() is not None
        assert sync_ref() is not None

        # Delete direct references
        del obj
        del sync
        gc.collect()

        # THIS WILL FAIL - Session holds references to bound methods which hold self
        # The handlers like sync._send_state are bound methods that reference the Sync
        # object, which references the TrackedObj
        assert sync_ref() is None, (
            "Sync object should be garbage collected after deletion"
        )
        assert obj_ref() is None, (
            "TrackedObj should be garbage collected when Sync is deleted"
        )

    def test_decorator_created_sync_prevents_gc(self, real_session: Session):
        """
        Test that decorated objects cannot be garbage collected due to session references.
        """

        @sync_all("DECORATED_OBJ")
        class DecoratedClass:
            value: int = 0

        obj = DecoratedClass()
        obj_ref = weakref.ref(obj)
        sync_ref = weakref.ref(obj.sync)  # type: ignore

        del obj
        gc.collect()

        # THIS WILL FAIL - handlers in session prevent GC
        assert obj_ref() is None, (
            "Decorated object should be garbage collected after deletion"
        )
        assert sync_ref() is None, (
            "Sync attribute should be garbage collected with its parent"
        )


class TestCloseMethod:
    """Tests for the public close() method."""

    def test_close_immediately_removes_handlers(self, real_session: Session):
        """
        Test that calling close() immediately removes all handlers,
        without waiting for garbage collection.
        """
        initial_event_count = len(real_session.event_handlers)
        initial_init_count = len(real_session.init_handlers)
        handlers_per_sync = 6

        class SimpleObj:
            value: int = 0

        obj = SimpleObj()
        sync = Sync.all(obj, "CLOSE_TEST", send_on_init=True)

        # Verify handlers were added
        assert (
            len(real_session.event_handlers) == initial_event_count + handlers_per_sync
        )
        assert len(real_session.init_handlers) == initial_init_count + 1

        # Close should immediately remove handlers
        sync.close()

        assert len(real_session.event_handlers) == initial_event_count
        assert len(real_session.init_handlers) == initial_init_count

    def test_close_is_idempotent(self, real_session: Session):
        """
        Test that calling close() multiple times is safe.
        """
        initial_count = len(real_session.event_handlers)

        class SimpleObj:
            value: int = 0

        obj = SimpleObj()
        sync = Sync.all(obj, "IDEMPOTENT_TEST", send_on_init=False)

        # Close multiple times - should not raise
        sync.close()
        sync.close()
        sync.close()

        assert len(real_session.event_handlers) == initial_count


class TestDeregisterBehavior:
    """Tests for the _deregister method and cleanup patterns."""

    def test_explicit_deregister_cleans_up_handlers(self, real_session: Session):
        """
        Test that explicitly calling _deregister removes all handlers.
        This is the expected workaround until automatic cleanup is implemented.
        """
        initial_event_count = len(real_session.event_handlers)
        initial_init_count = len(real_session.init_handlers)
        handlers_per_sync = 6  # get, set, patch, action, task_start, task_cancel

        class SimpleObj:
            value: int = 0

        obj = SimpleObj()
        sync = Sync.all(obj, "DEREGISTER_TEST", send_on_init=True)

        # Verify handlers were added
        assert (
            len(real_session.event_handlers) == initial_event_count + handlers_per_sync
        )
        assert len(real_session.init_handlers) == initial_init_count + 1

        # Explicitly deregister
        sync._deregister()

        # Handlers should be removed
        assert len(real_session.event_handlers) == initial_event_count
        assert len(real_session.init_handlers) == initial_init_count

    def test_deregister_with_actions_and_tasks(self, real_session: Session):
        """
        Test that _deregister removes action and task handlers as well.
        """
        initial_count = len(real_session.event_handlers)

        class ObjWithActions:
            value: int = 0

            def do_action(self, x: int) -> None:
                self.value = x

            async def do_task(self) -> None:
                pass

        obj = ObjWithActions()
        sync = Sync.all(
            obj,
            "ACTION_TASK_TEST",
            send_on_init=False,
            actions={"do_action": obj.do_action},
            tasks={"do_task": obj.do_task},
        )

        # Should have: 3 base handlers + 1 action + 1 task_start + 1 task_cancel
        assert (
            len(real_session.event_handlers) >= initial_count + 3
        )  # At least base handlers

        # Deregister
        sync._deregister()

        # All handlers should be removed
        assert len(real_session.event_handlers) == initial_count


class TestLongLivedSessionWithDynamicSyncs:
    """
    Tests simulating a long-lived session with many sync objects being created and destroyed.
    This is the real-world scenario that would cause memory leaks.
    """

    def test_repeated_create_delete_with_unique_keys(self, real_session: Session):
        """
        Test simulating repeated creation and deletion of synced objects
        with unique keys (like user session IDs).
        """
        initial_event_count = len(real_session.event_handlers)
        initial_init_count = len(real_session.init_handlers)

        # Simulate 100 "sessions" being created and then "deleted"
        for i in range(100):

            class UserSession:
                data: str = ""

            session_obj = UserSession()
            sync = Sync.all(session_obj, f"SESSION_{i}", send_on_init=True)

            # "User disconnects" - in reality, these objects get deleted
            del sync
            del session_obj
            gc.collect()

        # After all sessions are "disconnected", handlers should be cleaned up
        # THIS WILL FAIL - we'll have 100 * 3 = 300 stale event handlers
        # and 100 stale init handlers
        current_event_count = len(real_session.event_handlers)
        current_init_count = len(real_session.init_handlers)

        assert current_event_count == initial_event_count, (
            f"Event handlers leaked: expected {initial_event_count}, got {current_event_count}. "
            f"Leaked {current_event_count - initial_event_count} handlers."
        )
        assert current_init_count == initial_init_count, (
            f"Init handlers leaked: expected {initial_init_count}, got {current_init_count}. "
            f"Leaked {current_init_count - initial_init_count} handlers."
        )

    def test_handler_count_stays_bounded_with_reused_keys(self, real_session: Session):
        """
        Test that with reused keys, event handlers stay bounded.
        Each Sync overwrites the previous one's handlers, and when collected,
        the cleanup removes handlers (since they match the registered ones).
        """
        initial_event_count = len(real_session.event_handlers)

        class SimpleObj:
            value: int = 0

        # Reuse the same key 100 times, explicitly deleting each time
        for _i in range(100):
            obj = SimpleObj()
            sync = Sync.all(obj, "REUSED_KEY", send_on_init=False)
            del sync
            del obj
            gc.collect()

        # Each iteration: create Sync -> delete -> gc collects and cleans up
        # The last cleanup removes the handlers since they match
        current_event_count = len(real_session.event_handlers)

        assert current_event_count == initial_event_count, (
            f"Event handlers should be cleaned up after each iteration. "
            f"Expected {initial_event_count}, got {current_event_count}"
        )


class TestSyncKeyPrefixWithCleanup:
    """Tests for sync key prefix interaction with cleanup."""

    def test_prefixed_sync_handlers_accumulate(self, real_session: Session):
        """
        Test that syncs created within key scopes accumulate handlers,
        and that they are cleaned up when the Sync objects are garbage collected.
        """
        from ws_sync.sync import sync_key_scope

        initial_count = len(real_session.event_handlers)
        handlers_per_sync = 6  # get, set, patch, action, task_start, task_cancel

        class SimpleObj:
            value: int = 0

        # Create syncs with different prefixes
        # NOTE: We append directly to avoid loop variables keeping the last object alive
        # (Python loop variables persist after the loop ends, preventing GC)
        syncs = []
        for prefix in ["user1", "user2", "user3"]:
            with sync_key_scope(prefix):
                syncs.append(Sync.all(SimpleObj(), "DATA", send_on_init=False))

        # Should have 3 * 6 = 18 new handlers (6 handlers per sync, 3 syncs)
        assert len(real_session.event_handlers) == initial_count + (
            3 * handlers_per_sync
        )

        # Cleanup
        del syncs
        gc.collect()

        assert len(real_session.event_handlers) == initial_count


class TestWeakRefSuggestion:
    """
    Tests that would pass if we used weakrefs for handler registration.
    These demonstrate the expected behavior after a fix.
    """

    def test_weakref_allows_gc_of_sync(self, real_session: Session):
        """
        If handlers were stored as weakrefs, this test would pass.
        Currently it will fail.
        """

        class SimpleObj:
            value: int = 0

        obj = SimpleObj()
        sync = Sync.all(obj, "WEAKREF_TEST", send_on_init=False)
        sync_ref = weakref.ref(sync)

        # Delete the sync
        del sync
        gc.collect()

        # With weakrefs, the sync should be collectable
        # Currently fails because session holds strong references
        assert sync_ref() is None, "Sync should be garbage collected"

    def test_weakref_cleanup_on_gc_removes_stale_handlers(self, real_session: Session):
        """
        If handlers used weakrefs with cleanup callbacks, stale handlers
        would be removed automatically.
        """
        initial_count = len(real_session.event_handlers)
        handlers_per_sync = 6  # get, set, patch, action, task_start, task_cancel

        class SimpleObj:
            value: int = 0

        obj = SimpleObj()
        sync = Sync.all(obj, "AUTO_CLEANUP_TEST", send_on_init=False)

        # Verify handlers were added
        assert len(real_session.event_handlers) == initial_count + handlers_per_sync

        # Delete and GC
        del sync
        del obj
        gc.collect()

        # With proper weakref cleanup, handlers would be removed
        # Currently fails
        assert len(real_session.event_handlers) == initial_count, (
            "Stale handlers should be automatically cleaned up"
        )
