import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import asyncio
import json
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from typing import Any, Optional

router = APIRouter()

NODES_DIR = os.path.join(PROJECT_ROOT, 'opcuaNodes')


def _nodes_path(commessa: str) -> str:
    os.makedirs(NODES_DIR, exist_ok=True)
    name = commessa.strip() or 'default'
    return os.path.join(NODES_DIR, f'{name}_variabili.json')


class OpcuaCfg(BaseModel):
    url: str
    anonymous: bool = True
    username: str = ''
    password: str = ''
    security_mode: str = 'None'
    security_policy: str = 'None'


class BrowseRequest(BaseModel):
    cfg: OpcuaCfg
    node_id: str = 'i=84'


class SaveNodesRequest(BaseModel):
    commessa: str
    nodes: list[dict[str, Any]]


class _BrowseManager:
    """Keeps one persistent OPC UA connection for tree browsing, reconnects when config changes."""

    def __init__(self):
        self._explorer = None
        self._lock: Optional[asyncio.Lock] = None
        self._cfg_key: str = ''

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    @staticmethod
    def _key(cfg: OpcuaCfg) -> str:
        return f"{cfg.url}|{cfg.anonymous}|{cfg.username}|{cfg.password}|{cfg.security_mode}|{cfg.security_policy}"

    async def get_client(self, cfg: OpcuaCfg):
        from app.utils.opcua_utils import OPCUAExplorer
        async with self._get_lock():
            key = self._key(cfg)
            if self._explorer is not None and self._explorer.connected and key == self._cfg_key:
                return self._explorer.client
            # Disconnect old connection if any
            if self._explorer is not None:
                try:
                    await self._explorer.disconnect()
                except Exception:
                    pass
                self._explorer = None
            # Connect fresh
            explorer = OPCUAExplorer(
                url=cfg.url,
                anonymous=cfg.anonymous,
                username=cfg.username,
                password=cfg.password,
                security_mode=cfg.security_mode,
                security_policy=cfg.security_policy,
            )
            await explorer.connect()
            self._explorer = explorer
            self._cfg_key = key
            return explorer.client

    async def disconnect(self):
        async with self._get_lock():
            if self._explorer is not None:
                try:
                    await self._explorer.disconnect()
                except Exception:
                    pass
                self._explorer = None
                self._cfg_key = ''


_browse_mgr = _BrowseManager()


@router.post('/nodes/browse')
async def browse_node(req: BrowseRequest) -> dict:
    try:
        from asyncua import ua
        client = await _browse_mgr.get_client(req.cfg)
        node = client.get_node(req.node_id)
        children = await node.get_children()
        result = []
        for child in children:
            try:
                attrs = await child.read_attributes([
                    ua.AttributeIds.NodeClass,
                    ua.AttributeIds.DisplayName,
                    ua.AttributeIds.BrowseName,
                ])
                node_class = attrs[0].Value.Value
                dn_val = attrs[1].Value.Value
                display_name = dn_val.Text if hasattr(dn_val, 'Text') else str(dn_val)
                bn_val = attrs[2].Value.Value
                browse_name = bn_val.Name if hasattr(bn_val, 'Name') else str(bn_val)

                sub_children = await child.get_children()
                has_children = len(sub_children) > 0

                data_type = None
                if node_class == ua.NodeClass.Variable:
                    try:
                        dt_node = await child.read_data_type()
                        data_type = str(dt_node)
                    except Exception:
                        data_type = 'Unknown'

                result.append({
                    'node_id': str(child.nodeid),
                    'display_name': display_name,
                    'browse_name': browse_name,
                    'node_class': node_class.name if hasattr(node_class, 'name') else ua.NodeClass(node_class).name if isinstance(node_class, int) else str(node_class),
                    'has_children': has_children,
                    'data_type': data_type
                })
            except Exception:
                pass
        return {'nodes': result}
    except Exception as e:
        # Connection might be broken — reset so next call reconnects
        try:
            await _browse_mgr.disconnect()
        except Exception:
            pass
        return {'nodes': [], 'error': str(e)}


@router.post('/nodes/browse/disconnect')
async def browse_disconnect() -> dict:
    await _browse_mgr.disconnect()
    return {'ok': True}


@router.get('/nodes/saved')
def get_saved_nodes(commessa: str = Query(default='')) -> dict:
    path = _nodes_path(commessa)
    if not os.path.exists(path):
        return {'nodes': []}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        nodes = data.get('rows', data) if isinstance(data, dict) else data
        return {'nodes': nodes}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/nodes/saved')
def save_saved_nodes(req: SaveNodesRequest) -> dict:
    path = _nodes_path(req.commessa)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({'rows': req.nodes}, f, ensure_ascii=False, indent=2)
        return {'ok': True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
