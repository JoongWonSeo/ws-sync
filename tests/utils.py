"""
Common test utilities and helper functions for ws-sync tests.
"""

import jsonpatch
from pydantic import BaseModel, computed_field
from starlette.websockets import WebSocketDisconnect, WebSocketState

from ws_sync.sync import Sync


def get_patch(sync: Sync):
    """Helper to get patch from sync object"""
    prev = sync.state_snapshot
    sync.state_snapshot = sync._snapshot()
    return jsonpatch.make_patch(prev, sync.state_snapshot).patch


class Duration:
    """
    Helper for asserting measured durations against an expected target with
    relative and absolute error margins.

    Usage:
        expected = Duration(0.01)
        assert expected.roughly_equal(actual_duration)

    Defaults:
        - error_margin: 0.1 -> ±10% relative margin
        - error_min_margin: 0.005 -> at least ±5ms absolute margin
    """

    def __init__(self, seconds: float):
        self.seconds = float(seconds)

    def bounds(
        self,
        error_margin: float = 0.01,  # 1%
        error_min_margin: float = 0.005,  # 5ms
    ) -> tuple[float, float]:
        slack = max(self.seconds * error_margin, error_min_margin)
        return self.seconds - slack, self.seconds + slack

    def roughly_equal(
        self,
        actual_seconds: float,
        *,
        error_margin: float = 0.01,  # 1%
        error_min_margin: float = 0.005,  # 5ms
    ) -> bool:
        low, high = self.bounds(
            error_margin=error_margin, error_min_margin=error_min_margin
        )
        return low <= actual_seconds <= high

    def confidently_exceeds(
        self,
        actual_seconds: float,
        *,
        error_margin: float = 0.01,  # 1%
        error_min_margin: float = 0.005,  # 5ms
    ) -> bool:
        low, high = self.bounds(
            error_margin=error_margin, error_min_margin=error_min_margin
        )
        return actual_seconds > high


# Test model classes used across multiple test files


class User(BaseModel):
    """Test Pydantic model"""

    name: str
    age: int
    email: str | None = None


class Team(BaseModel):
    """Test Pydantic model with nested structure"""

    name: str
    members: list[User]
    leader: User | None = None


class Company(BaseModel):
    """Test Pydantic model with complex nesting"""

    name: str
    teams: list[Team]
    employees: dict[str, User]


class UserWithComputedField(BaseModel):
    """Test Pydantic model with computed field"""

    name: str
    age: int

    @computed_field
    @property
    def display_name(self) -> str:
        return f"{self.name} (age {self.age})"


class UserWithWritableComputedField(BaseModel):
    """Test Pydantic model with writable computed field"""

    first_name: str
    last_name: str

    @computed_field
    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @full_name.setter
    def full_name(self, value: str) -> None:
        parts = value.split(" ", 1)
        self.first_name = parts[0]
        self.last_name = parts[1] if len(parts) > 1 else ""


class FakeWebSocket:
    """
    Minimal WebSocket test double for driving Session.handle_connection.
    Provides a client-side event queue to interleave events dynamically.
    """

    _DISCONNECT = object()

    def __init__(
        self, events: list[dict] | None = None, *, auto_disconnect: bool = True
    ):
        # events are dicts like {"type": str, "data": any}
        import asyncio as _asyncio

        self._in_q: _asyncio.Queue[object] = _asyncio.Queue()
        for ev in events or []:
            self._in_q.put_nowait(ev)
        if events and auto_disconnect:
            self._in_q.put_nowait(self._DISCONNECT)
        self.sent: list[tuple[str, object]] = []
        self.application_state = WebSocketState.CONNECTING
        self.client = ("test", 0)

    async def accept(self):
        self.application_state = WebSocketState.CONNECTED

    async def close(self):
        self.application_state = WebSocketState.DISCONNECTED

    async def send_json(self, data):
        self.sent.append(("json", data))

    async def send_bytes(self, data: bytes):
        self.sent.append(("bytes", data))

    async def receive_json(self):
        item = await self._in_q.get()
        if item is self._DISCONNECT:
            self.application_state = WebSocketState.DISCONNECTED
            raise WebSocketDisconnect(1000)
        return item  # type: ignore[return-value]

    async def receive_bytes(self) -> bytes:
        return b""

    def send_from_client(self, event: dict):
        self._in_q.put_nowait(event)

    def client_disconnect(self):
        self._in_q.put_nowait(self._DISCONNECT)
