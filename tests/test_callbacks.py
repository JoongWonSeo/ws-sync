import asyncio
from unittest.mock import Mock

import pytest

from ws_sync.sync import Sync


class Dummy:
    def __init__(self) -> None:
        self.value = 0


@pytest.mark.asyncio
async def test_on_snapshot_callback_called(mock_session: Mock):
    obj = Dummy()
    called = asyncio.Event()

    async def cb(snapshot):
        assert snapshot["value"] == obj.value
        called.set()

    sync = Sync(obj, key="TEST", include={"value": ...}, on_snapshot=cb)
    obj.value = 1
    await sync.sync()
    assert called.is_set()
