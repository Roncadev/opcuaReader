import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from routers.config import router as config_router
from routers.connection import router as connection_router
from routers.nodes import router as nodes_router
from routers.session import router as session_router
from ws_session import router as ws_router

app = FastAPI(title='OPC UA Reader')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:5173', 'http://127.0.0.1:5173'],
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(config_router, prefix='/api')
app.include_router(connection_router, prefix='/api')
app.include_router(nodes_router, prefix='/api')
app.include_router(session_router, prefix='/api')
app.include_router(ws_router)

# Serve il frontend buildato (produzione)
frontend_dist = os.path.join(BACKEND_DIR, '..', 'frontend', 'dist')
if os.path.isdir(frontend_dist):
    app.mount('/', StaticFiles(directory=frontend_dist, html=True), name='frontend')

if __name__ == '__main__':
    import uvicorn
    uvicorn.run('main:app', host='0.0.0.0', port=8000, reload=True)
