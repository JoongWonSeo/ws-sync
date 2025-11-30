from __future__ import annotations

from asyncio import Lock
from collections.abc import Callable
from contextlib import suppress
from contextvars import ContextVar, Token
from logging import Logger
from typing import Any, Self

from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketState

from .utils import nonblock_call

# session context
session_context: ContextVar[Session] = ContextVar("session_context")
"""Per-task session context. Within concurrent async tasks, this context variable can be used to access the current Session object."""


class Session:
    """
    A session is a persistent connection with the other.

    This is a counter-part to the SessionManager in the frontend.
    There should be one instance of this class per user session, even across reconnects of the websocket. This means the states that belong to the user session should be subscribed to the events of this class.
    It defines a simple state-syncing protocol between the frontend and the backend, every event being of type {type: str, data: any}.
    """

    def __init__(self, logger: Logger | None = None):
        self.ws = None
        self.ws_lock = Lock()  # when multiple clients try to connect at the same time, we need to ensure that only one connection is established
        self.event_handlers: dict[str, Callable[..., Any]] = {}  # triggered on event
        self.init_handlers: list[
            Callable[..., Any]
        ] = []  # triggered on connection init
        self.logger = logger
        self.state: SessionState | None = None
        """user-assigned state associated with the session"""
        self._tokens: list[Token[Session]] = []

    @property
    def is_connected(self) -> bool:
        return self.ws is not None

    # ===== Low-Level: Register Event Callbacks =====#
    def register_event(self, event: str, callback: Callable[..., Any]):
        if event in self.event_handlers and self.logger:
            self.logger.warning("Event %s already has a subscriber.", event)
        self.event_handlers[event] = callback

    def deregister_event(self, event: str):
        if event not in self.event_handlers:
            if self.logger:
                self.logger.warning("Event %s has no subscriber.", event)
            return
        del self.event_handlers[event]

    def register_init(self, callback: Callable[..., Any]):
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
                        "Overwriting existing websocket %s with %s",
                        self.ws.client,
                        ws.client,
                    )
                await self.disconnect()
            self.ws = ws

        if self.ws.application_state == WebSocketState.CONNECTING:
            await self.ws.accept()

        await self.init()

    async def disconnect(
        self,
        message: str = "Seems like you're logged in somewhere else. If this is a mistake, please refresh the page.",
        ws: WebSocket | None = None,
    ):
        """
        Disconnect the websocket connection after sending a message.
        """
        # TODO: not sure why I made the ws argument, but I will keep it for now.
        if ws:
            self.ws = ws
        if self.ws is None:
            return
        await self.send("_DISCONNECT", message)
        assert self.ws is not None
        with suppress(Exception):
            await self.ws.close()
        self.ws = None

    async def init(self):
        for handler in self.init_handlers:
            await nonblock_call(handler)

    async def send(self, event: str, data: Any):
        if self.ws is None:
            return
        try:
            await self.ws.send_json({"type": event, "data": data})
        except Exception:
            if self.logger:
                self.logger.exception("Error sending event %s", event)

    async def send_binary(self, event: str, metadata: dict[str, Any], data: bytes):
        if self.ws is None:
            return
        try:
            await self.ws.send_json(
                {"type": "_BIN_META", "data": {"type": event, "metadata": metadata}}
            )
            await self.ws.send_bytes(data)
        except Exception:
            if self.logger:
                self.logger.exception("Error sending binary event %s", event)

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
                    self.logger.exception("Error while calling state.on_connect")

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
                    elif self.logger:
                        self.logger.warning(
                            "Received event %s but no subscriber was found.", event
                        )
            except WebSocketDisconnect:
                if self.logger:
                    self.logger.info("Websocket disconnected")
            except Exception:
                if self.logger:
                    self.logger.exception("Error while handling connection")
            finally:
                try:
                    if self.state:
                        await self.state.on_disconnect()
                except Exception:
                    if self.logger:
                        self.logger.exception("Error while calling state.on_disconnect")
                with suppress(Exception):
                    ws = self.ws
                    self.ws = None
                    if ws is not None:
                        await ws.close()

    # ===== High-Level: Context Manager =====#
    def __enter__(self) -> Self:
        token = session_context.set(self)
        self._tokens.append(token)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ):
        if self._tokens:
            token = self._tokens.pop()
            session_context.reset(token)


class SessionState:
    """
    Abstract base class for user-defined session state objects that can be associated with a Session object.
    """

    async def on_connect(self):
        """Called after the websocket connection is established."""

    async def on_disconnect(self):
        """Called after the websocket connection is closed."""

    async def on_terminate(self):
        """Called when the session is forcefully terminated by the server."""
