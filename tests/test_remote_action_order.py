"""Tests ensuring remote actions maintain declaration order."""

from ws_sync import remote_action
from ws_sync.decorators import find_remote_actions


def test_find_remote_actions_preserves_definition_order():
    class Example:
        @remote_action
        async def third(self):  # pragma: no cover - executed via decorator
            ...

        @remote_action
        async def first(self):  # pragma: no cover - executed via decorator
            ...

        @remote_action
        async def second(self):  # pragma: no cover - executed via decorator
            ...

    actions = find_remote_actions(Example)

    assert list(actions) == ["third", "first", "second"]
