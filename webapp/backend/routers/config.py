import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any
import yaml

router = APIRouter()

CONFIG_PATH = os.path.join(PROJECT_ROOT, 'config', 'config.yaml')


def _load_raw() -> dict:
    if not os.path.exists(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def _save_raw(data: dict) -> None:
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)


@router.get('/config')
def get_config() -> dict:
    return _load_raw()


@router.post('/config')
def save_config(body: dict[str, Any]) -> dict:
    try:
        _save_raw(body)
        return {'ok': True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
