import type {
  AppConfig,
  OpcuaClientConfig,
  DbConfig,
  OpcuaEndpoint,
  OpcuaNode,
  SavedNode,
  SessionStatus,
  WsMessage
} from './types'

const BASE = '/api'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`HTTP ${res.status}: ${text}`)
  }
  return res.json() as Promise<T>
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`HTTP ${res.status}: ${text}`)
  }
  return res.json() as Promise<T>
}

// ─── Config ───────────────────────────────────────────────────────────────────

export async function getConfig(): Promise<AppConfig> {
  return get<AppConfig>('/config')
}

export async function saveConfig(config: AppConfig): Promise<{ ok: boolean }> {
  return post<{ ok: boolean }>('/config', config)
}

// ─── Connection ───────────────────────────────────────────────────────────────

export async function testOpcua(cfg: OpcuaClientConfig): Promise<{ ok: boolean; message: string }> {
  return post<{ ok: boolean; message: string }>('/connection/test-opcua', cfg)
}

export async function getEndpoints(cfg: OpcuaClientConfig): Promise<{ endpoints: OpcuaEndpoint[]; error?: string }> {
  return post<{ endpoints: OpcuaEndpoint[]; error?: string }>('/connection/endpoints', cfg)
}

export async function testDb(cfg: DbConfig): Promise<{ ok: boolean; message: string }> {
  return post<{ ok: boolean; message: string }>('/connection/test-db', cfg)
}

// ─── Nodes ───────────────────────────────────────────────────────────────────

export async function browseNode(cfg: OpcuaClientConfig, nodeId: string): Promise<{ nodes: OpcuaNode[]; error?: string }> {
  return post<{ nodes: OpcuaNode[]; error?: string }>('/nodes/browse', { cfg, node_id: nodeId })
}

export async function getSavedNodes(commessa: string): Promise<{ nodes: SavedNode[] }> {
  return get<{ nodes: SavedNode[] }>(`/nodes/saved?commessa=${encodeURIComponent(commessa)}`)
}

export async function saveSavedNodes(commessa: string, nodes: SavedNode[]): Promise<{ ok: boolean }> {
  return post<{ ok: boolean }>('/nodes/saved', { commessa, nodes })
}

// ─── Session ─────────────────────────────────────────────────────────────────

export async function getSessionStatus(): Promise<SessionStatus> {
  return get<SessionStatus>('/session/status')
}

export async function startSession(): Promise<{ ok: boolean; message: string }> {
  return post<{ ok: boolean; message: string }>('/session/start', {})
}

export async function stopSession(): Promise<{ ok: boolean }> {
  return post<{ ok: boolean }>('/session/stop', {})
}

// ─── WebSocket session ────────────────────────────────────────────────────────

type LogCb = (text: string, level: string) => void
type ProgressCb = (readCount: number, nextReadIn: number) => void
type DoneCb = (stats: Record<string, unknown>) => void
type ErrorCb = (message: string) => void

export class SessionWs {
  private ws: WebSocket | null = null

  public onLog: LogCb = () => {}
  public onProgress: ProgressCb = () => {}
  public onDone: DoneCb = () => {}
  public onError: ErrorCb = () => {}
  public onClose: () => void = () => {}

  connect(): void {
    const wsUrl = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/session`
    this.ws = new WebSocket(wsUrl)

    this.ws.onmessage = (event: MessageEvent) => {
      let msg: WsMessage
      try { msg = JSON.parse(event.data as string) as WsMessage } catch { return }
      switch (msg.type) {
        case 'log':
          this.onLog(msg.text ?? '', msg.level ?? 'info')
          break
        case 'progress':
          this.onProgress(msg.read_count ?? 0, msg.next_read_in ?? 0)
          break
        case 'done':
          this.onDone(msg.stats ?? {})
          break
        case 'error':
          this.onError(msg.message ?? 'Errore sconosciuto')
          break
      }
    }

    this.ws.onerror = () => { this.onError('Errore connessione WebSocket') }
    this.ws.onclose = () => { this.onClose() }
  }

  close(): void {
    this.ws?.close()
    this.ws = null
  }
}
