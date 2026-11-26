import sys
import os
import asyncio
import json
import time
from datetime import datetime
from typing import Optional, Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fastapi import WebSocket

CONFIG_PATH = os.path.join(PROJECT_ROOT, 'config', 'config.yaml')
NODES_DIR = os.path.join(PROJECT_ROOT, 'opcuaNodes')


def _load_config() -> dict:
    import yaml
    if not os.path.exists(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def _load_nodes(commessa: str) -> list[dict]:
    name = commessa.strip() or 'default'
    path = os.path.join(NODES_DIR, f'{name}_variabili.json')
    if not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get('rows', data) if isinstance(data, dict) else data


class SessionState:
    def __init__(self):
        self.running = False
        self.read_count = 0
        self.last_error: Optional[str] = None
        self.started_at: Optional[str] = None
        self._task: Optional[asyncio.Task] = None
        self._stop_event: Optional[asyncio.Event] = None
        self.ws_clients: set[WebSocket] = set()

    async def broadcast(self, msg: dict) -> None:
        dead = set()
        for ws in list(self.ws_clients):
            try:
                await ws.send_json(msg)
            except Exception:
                dead.add(ws)
        self.ws_clients -= dead

    async def start(self) -> tuple[bool, str]:
        cfg = _load_config()
        client_cfg = cfg.get('opcua', {}).get('client', {})
        db_cfg = cfg.get('destination_database', {})
        commessa = client_cfg.get('commessa', '')
        nodes = _load_nodes(commessa)

        if not nodes:
            return False, f'Nessun nodo configurato per la commessa "{commessa}" — aggiungi nodi nella scheda Nodi'

        url = client_cfg.get('url', '')
        if not url:
            return False, 'URL OPC UA non configurato'

        self._stop_event = asyncio.Event()
        self.running = True
        self.read_count = 0
        self.last_error = None
        self.started_at = datetime.now().isoformat()

        self._task = asyncio.create_task(
            self._reading_loop(client_cfg, db_cfg, nodes, self._stop_event)
        )
        return True, 'Sessione avviata'

    async def stop(self) -> None:
        if self._stop_event:
            self._stop_event.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
        self.running = False

    async def _reading_loop(self, client_cfg: dict, db_cfg: dict, nodes: list[dict], stop: asyncio.Event) -> None:
        interval = float(client_cfg.get('read_interval_seconds', 15))
        max_reads = int(client_cfg.get('read_records', 0))
        url = client_cfg.get('url', '')
        anonymous = client_cfg.get('anonymous', True)
        username = client_cfg.get('username', '')
        password = client_cfg.get('password', '')
        commessa = client_cfg.get('commessa', '')

        await self.broadcast({'type': 'log', 'text': f'[{_ts()}] Connessione a {url}...', 'level': 'info'})

        try:
            from asyncua import Client
            client = Client(url=url, timeout=15)
            if not anonymous and username:
                client.set_user(username)
                client.set_password(password)

            async with client:
                await self.broadcast({'type': 'log', 'text': f'[{_ts()}] Connesso — {len(nodes)} variabili', 'level': 'info'})

                while not stop.is_set():
                    if max_reads > 0 and self.read_count >= max_reads:
                        await self.broadcast({'type': 'log', 'text': f'[{_ts()}] Raggiunto il limite di {max_reads} letture', 'level': 'info'})
                        break

                    t0 = time.monotonic()
                    values = await _read_nodes(client, nodes)
                    self.read_count += 1

                    await self.broadcast({
                        'type': 'log',
                        'text': f'[{_ts()}] Ciclo #{self.read_count} — {len(values)} valori letti',
                        'level': 'info'
                    })

                    # Scrivi su DB (non-blocking)
                    if db_cfg.get('host') and db_cfg.get('database'):
                        try:
                            loop = asyncio.get_event_loop()
                            await loop.run_in_executor(None, _write_to_db, db_cfg, commessa, values, nodes)
                            await self.broadcast({'type': 'log', 'text': f'[{_ts()}] Scritto su DB', 'level': 'info'})
                        except Exception as e:
                            await self.broadcast({'type': 'log', 'text': f'[{_ts()}] Errore DB: {e}', 'level': 'error'})

                    elapsed = time.monotonic() - t0
                    wait = max(0.0, interval - elapsed)

                    # Countdown con progress
                    countdown = int(wait)
                    while countdown > 0 and not stop.is_set():
                        await self.broadcast({'type': 'progress', 'read_count': self.read_count, 'next_read_in': countdown})
                        await asyncio.sleep(min(1.0, countdown))
                        countdown -= 1

                    await self.broadcast({'type': 'progress', 'read_count': self.read_count, 'next_read_in': 0})

        except Exception as e:
            self.last_error = str(e)
            await self.broadcast({'type': 'log', 'text': f'[{_ts()}] ERRORE: {e}', 'level': 'error'})
        finally:
            self.running = False
            await self.broadcast({
                'type': 'done',
                'stats': {'read_count': self.read_count, 'error': self.last_error}
            })


def _ts() -> str:
    return datetime.now().strftime('%H:%M:%S')


async def _read_nodes(client: Any, nodes: list[dict]) -> list[dict]:
    from asyncua import ua
    results = []
    for node_info in nodes:
        nid = node_info.get('node_id', '')
        if not nid:
            continue
        try:
            node = client.get_node(nid)
            dv = await node.read_data_value()
            value = dv.Value.Value if dv.Value else None
            results.append({
                'node_id': nid,
                'display_name': node_info.get('display_name', ''),
                'value': value,
                'timestamp': datetime.now().isoformat()
            })
        except Exception as e:
            results.append({
                'node_id': nid,
                'display_name': node_info.get('display_name', ''),
                'value': None,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            })
    return results


def _write_to_db(db_cfg: dict, commessa: str, values: list[dict], node_defs: list[dict]) -> None:
    dt = db_cfg.get('dt_type', 2)
    host = db_cfg.get('host', '')
    port = int(db_cfg.get('port', 3306))
    database = db_cfg.get('database', '')
    user = db_cfg.get('user', '')
    password = db_cfg.get('password', '')
    table = f'{commessa}_OPCUA_Nodes' if commessa else 'OPCUA_Nodes'
    now = datetime.now()

    rows = []
    for v in values:
        rows.append((
            now,
            v.get('node_id', ''),
            v.get('display_name', ''),
            str(v.get('value', '')),
            v.get('error', '')
        ))

    if not rows:
        return

    sql = f'INSERT INTO {table} (timestamp, node_id, display_name, value, error) VALUES (%s,%s,%s,%s,%s)'

    if dt == 1:  # MSSQL
        import pyodbc
        cs = (
            f'DRIVER={{ODBC Driver 17 for SQL Server}};'
            f'SERVER={host},{port};DATABASE={database};UID={user};PWD={password}'
        )
        conn = pyodbc.connect(cs)
        cur = conn.cursor()
        cur.executemany(sql.replace('%s', '?'), rows)
        conn.commit()
        conn.close()
    elif dt in (2, 3):  # MariaDB / MySQL
        import pymysql
        conn = pymysql.connect(host=host, port=port, database=database, user=user, password=password)
        cur = conn.cursor()
        cur.executemany(sql, rows)
        conn.commit()
        conn.close()
    elif dt == 4:  # PostgreSQL
        import psycopg2  # type: ignore
        conn = psycopg2.connect(host=host, port=port, dbname=database, user=user, password=password)
        cur = conn.cursor()
        cur.executemany(sql, rows)
        conn.commit()
        conn.close()


session_state = SessionState()
