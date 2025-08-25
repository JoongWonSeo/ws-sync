from contextlib import suppress

from starlette.websockets import WebSocket


class InvalidUserSessionMessageError(Exception):
    def __init__(self, wrong_message: dict):
        super().__init__(f"Client sent wrong message type: {wrong_message}")


class InvalidUserSessionError(Exception):
    def __init__(self, wrong_message: dict):
        super().__init__(f"Client sent invalid user or session: {wrong_message}")


async def get_user_session(ws: WebSocket) -> tuple[str, str] | tuple[None, None]:
    """
    A primitive WS user+session identification protocol.

    So that the `Session` state can persist across reconnections/tabs/etc., the client sends their user_id and session_id to the server.

    Args:
        ws: the websocket

    Returns:
        the user_id and session_id or None, None if the client sent invalid data
    """
    try:
        await ws.send_json({"type": "_REQUEST_USER_SESSION"})
        msg = await ws.receive_json()
        if msg["type"] != "_USER_SESSION":
            raise InvalidUserSessionMessageError(msg)  # noqa: TRY301
        user = msg["data"]["user"]
        session = msg["data"]["session"]

        if not user or not session:
            raise InvalidUserSessionError(msg)  # noqa: TRY301

    except (InvalidUserSessionMessageError, InvalidUserSessionError):
        with suppress(Exception):
            await ws.close()
        return None, None
    else:
        return user, session
