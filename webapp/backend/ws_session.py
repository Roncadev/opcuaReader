from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from routers.session_state import session_state

router = APIRouter()


@router.websocket('/ws/session')
async def ws_session(ws: WebSocket) -> None:
    await ws.accept()
    session_state.ws_clients.add(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        session_state.ws_clients.discard(ws)
