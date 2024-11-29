from __future__ import annotations
from abc import ABC, abstractmethod
from asyncio import Lock
from logging import Logger
import traceback
from typing import Any, Callable
from contextvars import ContextVar

from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketState

from .utils import nonblock_call

# session context
session_context: ContextVar[Session] = ContextVar("session_context")
"""Per-task session context. Within concurrent async tasks, this context variable can be used to access the current Session object."""


class Session:
    """
    This is a counter-part to the SessionManager in the frontend.
    There should be one instance of this class per user session, even across reconnects of the websocket. This means the states that belong to the user session should be subscribed to the events of this class.
    It defines a simple state-syncing protocol between the frontend and the backend, every event being of type {type: str, data: any}.
    """

    def __init__(self, logger: Logger | None = None):
        self.ws = None
        self.ws_lock = Lock()  # when multiple clients try to connect at the same time, we need to ensure that only one connection is established
        self.event_handlers: dict[str, Callable] = {}  # triggered on event
        self.init_handlers: list[Callable] = []  # triggered on connection init
        self.logger = logger
        self.state: SessionState | None = None
        """user-assigned state associated with the session"""

    @property
    def is_connected(self):
        return self.ws is not None

    # ===== Low-Level: Register Event Callbacks =====#
    def register_event(self, event: str, callback: Callable):
        if event in self.event_handlers:
            # raise Exception(f"Event {event} already has a subscriber.")
            if self.logger:
                self.logger.warning(f"Event {event} already has a subscriber.")
        self.event_handlers[event] = callback

    def deregister_event(self, event: str):
        if event not in self.event_handlers:
            raise Exception(f"Event {event} has no subscriber.")
        del self.event_handlers[event]

    def register_init(self, callback: Callable):
        self.init_handlers.append(callback)

    # ===== Low-Level: Networking =====#
    async def new_connection(self, ws: WebSocket):
        """
        Set the new ws connection while possibly gracefully disconnecting the old one.
        """
        async with self.ws_lock:
            if self.ws is not None:
                if self.logger:
                    self.logger.warning(
                        f"Overwriting existing websocket {self.ws.client} with {ws.client})"
                    )
                await self.disconnect()
            self.ws = ws

        if self.ws.application_state == WebSocketState.CONNECTING:
            await self.ws.accept()

        await self.init()

    async def disconnect(
        self,
        message="Seems like you're logged in somewhere else. If this is a mistake, please refresh the page.",
        ws: WebSocket | None = None,
    ):
        """
        Disconnect the websocket connection after sending a message.
        TODO: not sure why I made the ws argument, but I will keep it for now.
        """
        if ws:
            self.ws = ws
        if self.ws is None:
            return
        await self.send("_DISCONNECT", message)
        try:
            await self.ws.close()
        except Exception:
            pass
        self.ws = None

    async def init(self):
        for handler in self.init_handlers:
            await nonblock_call(handler)

    async def send(self, event: str, data: Any):
        if self.ws is None:
            return
        try:
            await self.ws.send_json({"type": event, "data": data})
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error sending event {event}: {e}")

    async def send_binary(self, event: str, metadata: dict[str, Any], data: bytes):
        if self.ws is None:
            return
        try:
            await self.ws.send_json(
                {"type": "_BIN_META", "data": {"type": event, "metadata": metadata}}
            )
            await self.ws.send_bytes(data)
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error sending binary event {event}: {e}")

    async def handle_connection(self, ws: WebSocket | None = None):
        """
        Handler that blocks until the websocket is disconnected. It takes care of accepting the websocket connection, and dispatching events to the appropriate handlers. If the ws argument is provided, it will be used as the websocket connection, otherwise it will use the existing connection.

        Args:
            ws: The websocket connection to use. If None, it will use the existing connection.
        """
        if ws:
            await self.new_connection(ws)

        assert self.ws is not None

        with self:  # provide the session context
            try:
                if self.state:
                    await self.state.on_connect()
            except Exception:
                if self.logger:
                    self.logger.error(
                        f"Error while calling state.on_connect: {traceback.format_exc()}"
                    )

            try:
                while self.ws.application_state == WebSocketState.CONNECTED:
                    full_data = await self.ws.receive_json()
                    event = full_data.get("type")
                    data = full_data.get("data")

                    if event == "_BIN_META":
                        # unwrap and construct the original event
                        event = data.get("type")
                        metadata = data.get("metadata")
                        bindata = await self.ws.receive_bytes()
                        data = {"data": bindata, **metadata}

                    if handler := self.event_handlers.get(event):
                        await nonblock_call(handler, data)
                    else:
                        if self.logger:
                            self.logger.warning(
                                f"Received event {event} but no subscriber was found."
                            )
            except WebSocketDisconnect:
                if self.logger:
                    self.logger.info("Websocket disconnected")
            except Exception:
                if self.logger:
                    self.logger.error(
                        f"Error while handling connection: {traceback.format_exc()}"
                    )
            finally:
                try:
                    if self.state:
                        await self.state.on_disconnect()
                except Exception:
                    if self.logger:
                        self.logger.error(
                            f"Error while calling state.on_disconnect: {traceback.format_exc()}"
                        )
                try:
                    ws = self.ws
                    self.ws = None
                    await ws.close()
                except Exception:
                    pass  # ignore errors during closing

    # ===== High-Level: Context Manager =====#
    def __enter__(self):
        self.token = session_context.set(self)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.token:
            session_context.reset(self.token)
        self.token = None


class SessionState(ABC):
    """
    Abstract base class for user-defined session state objects that can be associated with a Session object.
    """

    @abstractmethod
    async def on_connect(self):
        """Called after the websocket connection is established."""
        pass

    @abstractmethod
    async def on_disconnect(self):
        """Called after the websocket connection is closed."""
        pass
