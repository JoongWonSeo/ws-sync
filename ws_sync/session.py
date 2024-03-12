import traceback
from typing import Callable
from starlette.websockets import WebSocket, WebSocketDisconnect

from .utils import nonblock_call

# global default session, which can be temporarily overwritten by the context manager
_global_session = None


def get_global_session():
    global _global_session
    if _global_session is None:
        raise Exception(
            "No global session found. Please use the Session context manager."
        )
    return _global_session


class Session:
    """
    This is a counter-part to the SessionManager in the frontend.
    There should be one instance of this class per user session, even across reconnects of the websocket. This means the states that belong to the user session should be subscribed to the events of this class.
    It defines a simple state-syncing protocol between the frontend and the backend, every event being of type {type: str, data: any}.
    """

    def __init__(self):
        self.ws = None
        self.event_handlers: dict[str, Callable] = {}  # triggered on event
        self.init_handlers: list[Callable] = []  # triggered on connection init
        self.logger = None

    @property
    def is_connected(self):
        return self.ws is not None

    # ===== Low-Level: Register Event Callbacks =====#
    def register_event(self, event: str, callback: Callable):
        if event in self.event_handlers:
            raise Exception(f"Event {event} already has a subscriber.")
        self.event_handlers[event] = callback

    def deregister_event(self, event: str):
        if event not in self.event_handlers:
            raise Exception(f"Event {event} has no subscriber.")
        del self.event_handlers[event]

    def register_init(self, callback: Callable):
        self.init_handlers.append(callback)

    # ===== Low-Level: Networking =====#
    async def new_connection(self, ws: WebSocket):
        if self.ws is not None:
            if self.logger:
                self.logger.warning("Overwriting existing websocket.")
            await self.disconnect()
        self.ws = ws

        await self.init()

    async def disconnect(
        self,
        message="Seems like you're logged in somewhere else. If this is a mistake, please refresh the page.",
        ws: WebSocket = None,
    ):
        if ws:
            self.ws = ws
        await self.send("_DISCONNECT", message)
        await self.ws.close()
        self.ws = None

    async def init(self):
        for handler in self.init_handlers:
            await nonblock_call(handler)

    async def send(self, event: str, data: any):
        if self.ws is None:
            return
        try:
            await self.ws.send_json({"type": event, "data": data})
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error sending event {event}: {e}")

    async def handle_connection(self):
        assert self.ws is not None
        try:
            while True:
                data = await self.ws.receive_json()
                event = data.get("type")
                if event in self.event_handlers:
                    # TODO: add support for task creation for long-running handlers
                    if self.logger:
                        self.logger.debug(f"Received event {event}: {data.get('data')}")
                    handler = self.event_handlers[event]
                    await nonblock_call(handler, data.get("data"))
                else:
                    if self.logger:
                        self.logger.warning(
                            f"Received event {event} but no subscriber was found."
                        )
        except WebSocketDisconnect:
            if self.logger:
                self.logger.info("websocket disconnected")
        except Exception:
            if self.logger:
                self.logger.error(
                    f"Error while handling connection: {traceback.format_exc()}"
                )
        finally:
            try:
                ws = self.ws
                self.ws = None
                await ws.close()
            except:
                pass

    # ===== High-Level: Context Manager =====#
    def __enter__(self):
        global _global_session
        self._prev_global_connection = _global_session
        _global_session = self
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        global _global_session
        _global_session = self._prev_global_connection
        self._prev_global_connection = None
