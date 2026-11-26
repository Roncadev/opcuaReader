from fastapi import APIRouter
from .session_state import session_state

router = APIRouter()


@router.get('/session/status')
def get_status() -> dict:
    return {
        'running': session_state.running,
        'read_count': session_state.read_count,
        'error': session_state.last_error,
        'started_at': session_state.started_at
    }


@router.post('/session/start')
async def start_session() -> dict:
    if session_state.running:
        return {'ok': False, 'message': 'Sessione già in corso'}
    ok, msg = await session_state.start()
    return {'ok': ok, 'message': msg}


@router.post('/session/stop')
async def stop_session() -> dict:
    await session_state.stop()
    return {'ok': True}
