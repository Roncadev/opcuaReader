export interface OpcuaClientConfig {
  url: string
  anonymous: boolean
  username: string
  password: string
  security_mode: string
  security_policy: string
  read_interval_seconds: number
  read_records: number
  run_mode: string
  deadband_global: number
  commessa: string
  subscription_publishing_interval_ms: number
  subscription_sampling_interval_ms: number
}

export interface DbConfig {
  dt_type: number  // 1=MSSQL 2=MariaDB 3=MySQL 4=PostgreSQL
  host: string
  port: number
  database: string
  user: string
  password: string
}

export interface AppConfig {
  opcua: { client: OpcuaClientConfig }
  destination_database: DbConfig
}

export interface OpcuaEndpoint {
  url: string
  security_mode: string
  security_policy: string
  login_types: string[]
}

export interface OpcuaNode {
  node_id: string
  display_name: string
  browse_name: string
  node_class: string
  has_children: boolean
  value?: unknown
  data_type?: string
}

export interface SavedNode {
  node_id: string
  display_name: string
  browse_name: string
  node_class: string
  type: string
}

export interface SessionStatus {
  running: boolean
  read_count: number
  error: string | null
  started_at: string | null
}

export interface WsMessage {
  type: 'log' | 'progress' | 'done' | 'error'
  text?: string
  level?: string
  read_count?: number
  next_read_in?: number
  stats?: Record<string, unknown>
  message?: string
}
