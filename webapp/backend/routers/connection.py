import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import asyncio
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


class OpcuaCfg(BaseModel):
    url: str
    anonymous: bool = True
    username: str = ''
    password: str = ''
    security_mode: str = 'None'
    security_policy: str = 'None'
    commessa: str = ''
    read_interval_seconds: int = 15
    read_records: int = 0
    run_mode: str = 'normal'
    deadband_global: float = 1.0
    subscription_publishing_interval_ms: int = 3000
    subscription_sampling_interval_ms: int = 3000


class DbCfg(BaseModel):
    dt_type: int = 2
    host: str = 'localhost'
    port: int = 3306
    database: str = ''
    user: str = ''
    password: str = ''


async def _opcua_connect(cfg: OpcuaCfg):
    from asyncua import Client
    client = Client(url=cfg.url, timeout=10)
    if not cfg.anonymous and cfg.username:
        client.set_user(cfg.username)
        client.set_password(cfg.password)
    return client


@router.post('/connection/test-opcua')
async def test_opcua(cfg: OpcuaCfg) -> dict:
    try:
        client = await _opcua_connect(cfg)
        async with client:
            node = client.get_node('i=2258')
            server_time = await node.read_value()
            return {'ok': True, 'message': f'Connesso — ora server: {server_time}'}
    except Exception as e:
        return {'ok': False, 'message': str(e)}


@router.post('/connection/endpoints')
async def get_endpoints(cfg: OpcuaCfg) -> dict:
    try:
        from asyncua import Client
        client = Client(url=cfg.url, timeout=10)
        client.application_uri = 'urn:AINIMA:OPCUA:VariablesReader'
        endpoints = await client.connect_and_get_server_endpoints()
        result = []
        for ep in endpoints:
            policy = str(getattr(ep, 'SecurityPolicyUri', '')).split('#')[-1]
            mode_val = getattr(ep, 'SecurityMode', None)
            mode = str(getattr(mode_val, 'name', mode_val)) if mode_val else 'Unknown'
            tokens = []
            for t in getattr(ep, 'UserIdentityTokens', None) or []:
                tt = getattr(t, 'TokenType', '')
                tokens.append(getattr(tt, 'name', None) or str(tt))
            result.append({
                'url': str(getattr(ep, 'EndpointUrl', '')),
                'security_mode': mode,
                'security_policy': policy,
                'login_types': tokens
            })
        return {'endpoints': result}
    except Exception as e:
        return {'endpoints': [], 'error': str(e)}


@router.post('/connection/test-db')
async def test_db(cfg: DbCfg) -> dict:
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _test_db_sync, cfg)
        return result
    except Exception as e:
        return {'ok': False, 'message': str(e)}


def _test_db_sync(cfg: DbCfg) -> dict:
    try:
        if cfg.dt_type == 1:  # MSSQL
            import pyodbc
            cs = (
                f'DRIVER={{ODBC Driver 17 for SQL Server}};'
                f'SERVER={cfg.host},{cfg.port};DATABASE={cfg.database};'
                f'UID={cfg.user};PWD={cfg.password};Connection Timeout=5'
            )
            conn = pyodbc.connect(cs, timeout=5)
            conn.close()
        elif cfg.dt_type in (2, 3):  # MariaDB / MySQL
            import pymysql
            conn = pymysql.connect(
                host=cfg.host, port=cfg.port, database=cfg.database,
                user=cfg.user, password=cfg.password, connect_timeout=5
            )
            conn.close()
        elif cfg.dt_type == 4:  # PostgreSQL
            import psycopg2  # type: ignore
            conn = psycopg2.connect(
                host=cfg.host, port=cfg.port, dbname=cfg.database,
                user=cfg.user, password=cfg.password, connect_timeout=5
            )
            conn.close()
        else:
            return {'ok': False, 'message': f'Tipo database non supportato: {cfg.dt_type}'}
        return {'ok': True, 'message': 'Connessione riuscita'}
    except Exception as e:
        return {'ok': False, 'message': str(e)}
