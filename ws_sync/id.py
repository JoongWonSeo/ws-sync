from starlette.websockets import WebSocket


async def get_user_session(ws: WebSocket):
    """
    A primitive WS user+session identification protocol.

    Args:
        ws: the websocket
        authorizer: a function that takes the user and session as arguments and returns whether the user is authorized
    """
    try:
        await ws.send_json({"type": "_REQUEST_USER_SESSION"})
        msg = await ws.receive_json()
        if msg["type"] != "_USER_SESSION":
            raise Exception("Client sent wrong message type")
        user = msg["data"]["user"]
        session = msg["data"]["session"]

        if not user or not session:
            raise Exception("Client sent invalid user or session")

        return user, session
    except:
        try:
            await ws.close()
        finally:
            return None, None
