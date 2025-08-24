import anyio
from starlette.applications import Starlette
from starlette.routing import WebSocketRoute
from starlette.testclient import TestClient

from ws_sync import Session, Sync

session = Session()


class Counter:
    def __init__(self):
        self.value = 0


counter = Counter()
with session:
    counter_sync = Sync.only(counter, "COUNTER", value="value")

app = Starlette(routes=[WebSocketRoute("/ws", session.handle_connection)])


def test_starlette_websocket_sync():
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        message = ws.receive_json()
        assert message == {"type": "_SET:COUNTER", "data": {"value": 0}}

        ws.send_json(
            {
                "type": "_PATCH:COUNTER",
                "data": [
                    {"op": "replace", "path": "/value", "value": 1},
                ],
            }
        )
        assert client.portal is not None
        portal = client.portal
        portal.call(anyio.sleep, 0)
        assert counter.value == 1

        counter.value = 2
        portal.call(counter_sync.sync)
        message2 = ws.receive_json()
        assert message2 == {
            "type": "_PATCH:COUNTER",
            "data": [{"op": "replace", "path": "/value", "value": 2}],
        }
