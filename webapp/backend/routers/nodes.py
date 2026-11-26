import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import json
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from typing import Any

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


@router.post('/nodes/browse')
async def browse_node(req: BrowseRequest) -> dict:
    try:
        from asyncua import Client, ua
        client = Client(url=req.cfg.url, timeout=10)
        if not req.cfg.anonymous and req.cfg.username:
            client.set_user(req.cfg.username)
            client.set_password(req.cfg.password)

        async with client:
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
                    display_name = str(attrs[1].Value.Value)
                    browse_name = str(attrs[2].Value.Value)

                    # Conta i figli per sapere se è espandibile
                    sub_children = await child.get_children()
                    has_children = len(sub_children) > 0

                    # Tipo dato (solo per Variable)
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
                        'node_class': getattr(node_class, 'name', str(node_class)),
                        'has_children': has_children,
                        'data_type': data_type
                    })
                except Exception:
                    pass
            return {'nodes': result}
    except Exception as e:
        return {'nodes': [], 'error': str(e)}


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
