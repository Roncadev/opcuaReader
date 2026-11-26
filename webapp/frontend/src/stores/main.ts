import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { AppConfig, OpcuaClientConfig, DbConfig, SavedNode, SessionStatus } from '../types'
import {
  getConfig, saveConfig,
  testOpcua, getEndpoints, testDb,
  browseNode, getSavedNodes, saveSavedNodes,
  getSessionStatus, startSession, stopSession,
  SessionWs
} from '../api'

function defaultOpcua(): OpcuaClientConfig {
  return {
    url: 'opc.tcp://10.0.0.1:4840/',
    anonymous: true,
    username: '',
    password: '',
    security_mode: 'None',
    security_policy: 'None',
    read_interval_seconds: 15,
    read_records: 0,
    run_mode: 'normal',
    deadband_global: 1.0,
    commessa: '',
    subscription_publishing_interval_ms: 3000,
    subscription_sampling_interval_ms: 3000
  }
}

function defaultDb(): DbConfig {
  return { dt_type: 2, host: 'localhost', port: 3306, database: '', user: '', password: '' }
}

export const useMainStore = defineStore('main', () => {
  // ─── Config ─────────────────────────────────────────────────────────────────
  const opcua = ref<OpcuaClientConfig>(defaultOpcua())
  const db = ref<DbConfig>(defaultDb())
  const configLoading = ref(false)
  const configSaving = ref(false)
  const configError = ref<string | null>(null)

  // ─── Nodes ──────────────────────────────────────────────────────────────────
  const savedNodes = ref<SavedNode[]>([])
  const nodesLoading = ref(false)

  // ─── Session ─────────────────────────────────────────────────────────────────
  const isRunning = ref(false)
  const readCount = ref(0)
  const nextReadIn = ref(0)
  const logs = ref<{ text: string; level: string }[]>([])
  let ws: SessionWs | null = null

  // ─── Computed ────────────────────────────────────────────────────────────────
  const dtTypeLabel = computed(() => {
    const labels: Record<number, string> = { 1: 'MSSQL', 2: 'MariaDB', 3: 'MySQL', 4: 'PostgreSQL' }
    return labels[db.value.dt_type] ?? 'MariaDB'
  })

  // ─── Config actions ──────────────────────────────────────────────────────────

  async function fetchConfig() {
    configLoading.value = true
    configError.value = null
    try {
      const cfg = await getConfig()
      opcua.value = { ...defaultOpcua(), ...cfg.opcua?.client }
      db.value = { ...defaultDb(), ...cfg.destination_database }
    } catch (err) {
      configError.value = err instanceof Error ? err.message : String(err)
    } finally {
      configLoading.value = false
    }
  }

  async function persistConfig() {
    configSaving.value = true
    configError.value = null
    try {
      const cfg: AppConfig = {
        opcua: { client: opcua.value },
        destination_database: db.value
      }
      await saveConfig(cfg)
    } catch (err) {
      configError.value = err instanceof Error ? err.message : String(err)
      throw err
    } finally {
      configSaving.value = false
    }
  }

  // ─── Nodes actions ───────────────────────────────────────────────────────────

  async function fetchSavedNodes() {
    nodesLoading.value = true
    try {
      const res = await getSavedNodes(opcua.value.commessa)
      savedNodes.value = res.nodes
    } catch (err) {
      console.error('fetchSavedNodes:', err)
    } finally {
      nodesLoading.value = false
    }
  }

  async function persistSavedNodes() {
    await saveSavedNodes(opcua.value.commessa, savedNodes.value)
  }

  function addNode(node: SavedNode) {
    if (!savedNodes.value.find(n => n.node_id === node.node_id)) {
      savedNodes.value.push(node)
    }
  }

  function removeNode(nodeId: string) {
    savedNodes.value = savedNodes.value.filter(n => n.node_id !== nodeId)
  }

  // ─── Session actions ─────────────────────────────────────────────────────────

  function addLog(text: string, level = 'info') {
    logs.value.push({ text, level })
    if (logs.value.length > 2000) logs.value.splice(0, logs.value.length - 2000)
  }

  function clearLogs() { logs.value = [] }

  async function startReading() {
    if (isRunning.value) return
    readCount.value = 0
    nextReadIn.value = 0
    addLog(`[${new Date().toLocaleTimeString()}] Avvio sessione di lettura...`)

    try {
      const res = await startSession()
      if (!res.ok) { addLog(`Errore avvio: ${res.message}`, 'error'); return }
    } catch (err) {
      addLog(`Errore avvio: ${err instanceof Error ? err.message : String(err)}`, 'error')
      return
    }

    isRunning.value = true
    ws = new SessionWs()

    ws.onLog = (text, level) => addLog(text, level)
    ws.onProgress = (rc, nri) => { readCount.value = rc; nextReadIn.value = nri }
    ws.onDone = (stats) => {
      isRunning.value = false
      addLog(`[${new Date().toLocaleTimeString()}] Sessione terminata — letture: ${stats.read_count ?? '?'}`)
    }
    ws.onError = (msg) => {
      isRunning.value = false
      addLog(`[${new Date().toLocaleTimeString()}] ERRORE: ${msg}`, 'error')
    }
    ws.onClose = () => {
      if (isRunning.value) {
        isRunning.value = false
        addLog(`[${new Date().toLocaleTimeString()}] Connessione WebSocket chiusa`)
      }
    }

    ws.connect()
  }

  async function stopReading() {
    try { await stopSession() } catch { /* ignora */ }
    ws?.close()
    ws = null
    isRunning.value = false
    addLog(`[${new Date().toLocaleTimeString()}] Fermato dall'utente`)
  }

  async function syncStatus() {
    try {
      const s: SessionStatus = await getSessionStatus()
      isRunning.value = s.running
      readCount.value = s.read_count
    } catch { /* ignora */ }
  }

  return {
    opcua, db, configLoading, configSaving, configError, dtTypeLabel,
    savedNodes, nodesLoading,
    isRunning, readCount, nextReadIn, logs,
    fetchConfig, persistConfig,
    fetchSavedNodes, persistSavedNodes, addNode, removeNode,
    startReading, stopReading, syncStatus,
    addLog, clearLogs,
    // expose per i componenti
    testOpcua: (cfg: OpcuaClientConfig) => testOpcua(cfg),
    getEndpoints: (cfg: OpcuaClientConfig) => getEndpoints(cfg),
    testDb: (cfg: DbConfig) => testDb(cfg),
    browseNode: (nodeId: string) => browseNode(opcua.value, nodeId)
  }
})
