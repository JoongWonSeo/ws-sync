'''
This module defines a simple state syncing protocol between the frontend and the backend.

Concepts:
- Connection: A connection to the frontend. There should be one instance of this class per user session, even across reconnects of the websocket.
- Event: This is the primitive of the protocol. Every event is of type {type: str, data: any}.
    - Set Event: Overwrite the full value of the state
    - Get Event: Request the full value of the state
    - Patch Event: Apply a jsonpatch to the state, i.e. a list of operations
    - Action Event: Dispatch an action, can be handled however defined

The most convinient way to use this module is to create an object of Connection, passing all the attributes that should be synced with the frontend, while defining their sync config:
    self.connection = Connection(
        obj = self,
        state1 = sync(),
        state2 = sync(key="state2_key"),
        state3 = exposed(),
        state4 = remote(),
    )
Then, whenever you want to sync, simply call self.connection.sync().

For actions, you can subscribe to the action event by calling self.connection.subscribe(action_event(key), handler), and dispatch actions by calling self.connection.dispatch(action_event(key), action).
'''

import traceback
from typing import Callable
from starlette import WebSocket, WebSocketDisconnect
import jsonpatch

# global default connection, which can be temporarily overwritten by the context manager
_global_connection = None

class Connection:
    '''
    This is a counter-part to the ConnectionManager in the frontend.
    There should be one instance of this class per user session, even across reconnects of the websocket. This means the states that belong to the user session should be subscribed to the events of this class.
    It defines a simple state-syncing protocol between the frontend and the backend, every event being of type {type: str, data: any}.
    '''
    def __init__(self):
        self.ws = None
        self.event_handlers: dict[str, Callable] = {} # triggered on event
        self.init_handlers: list[Callable] = [] # triggered on connection init
    
    @property
    def is_connected(self):
        return self.ws is not None

    #===== Low-Level: Register Event Callbacks =====#
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
    
    #===== Low-Level: Networking =====#
    async def new_connection(self, ws: WebSocket):
        if self.ws is not None:
            print("Warning: Overwriting existing websocket.")
            await self.ws.close()
        self.ws = ws

        for handler in self.init_handlers:
            await nonblock_call(handler)
                
    async def send(self, event: str, data: any):
        if self.ws is None:
            return
        try:
            await self.ws.send_json({"type": event, "data": data})
        except Exception as e:
            print(f"Error sending event {event}: {e}")
    
    async def handle_connection(self):
        assert self.ws is not None
        try:
            while True:
                data = await self.ws.receive_json()
                event = data.get("type")
                if event in self.event_handlers:
                    # TODO: add support for task creation for long-running handlers
                    print(f"Received event {event}: {data.get('data')}")
                    handler = self.event_handlers[event]
                    await nonblock_call(handler, data.get("data"))
                else:
                    print(f"Received event {event} but no subscriber was found.")
        except WebSocketDisconnect:
            print("websocket disconnected")
        except Exception:
            print(f"Error while handling connection: {traceback.format_exc()}")
        finally:
            try:
                ws = self.ws
                self.ws = None
                await ws.close()
            except:
                pass
    
    #===== High-Level: Context Manager =====#
    def __enter__(self):
        global _global_connection
        self._prev_global_connection = _global_connection
        _global_connection = self
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        global _global_connection
        _global_connection = self._prev_global_connection
        self._prev_global_connection = None

