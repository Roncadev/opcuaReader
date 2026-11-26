<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useMainStore } from '../stores/main'
import { NodeTreeItem, type TNode } from './NodeTreeItem'
import type { OpcuaNode, SavedNode } from '../types'

const emit = defineEmits<{ add: [node: SavedNode] }>()

const store = useMainStore()

interface TreeNode extends OpcuaNode {
  children: TreeNode[]
  expanded: boolean
  loading: boolean
  loaded: boolean
}

const roots = ref<TreeNode[]>([])
const loading = ref(false)
const error = ref('')
const toggleError = ref('')

const ROOT_NODE = 'i=84'

function makeTree(node: OpcuaNode): TreeNode {
  return { ...node, children: [], expanded: false, loading: false, loaded: false }
}

async function loadRoots() {
  loading.value = true
  error.value = ''
  roots.value = []
  try {
    const res = await store.browseNode(ROOT_NODE)
    if (res.error) { error.value = res.error; return }
    roots.value = res.nodes.map(makeTree)
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}

async function toggle(node: TNode) {
  const tnode = node as TreeNode
  if (!tnode.has_children) return
  if (tnode.expanded) { tnode.expanded = false; return }
  tnode.expanded = true
  if (tnode.loaded) return
  tnode.loading = true
  toggleError.value = ''
  try {
    const res = await store.browseNode(tnode.node_id)
    console.log('[toggle] browse result:', tnode.node_id, res)
    if (res.error) {
      toggleError.value = `Errore espansione: ${res.error}`
    } else {
      tnode.children = res.nodes.map(makeTree) as TreeNode[]
      console.log('[toggle] children set:', tnode.children.length)
    }
  } catch (err) {
    toggleError.value = `Eccezione espansione: ${err instanceof Error ? err.message : String(err)}`
    console.error('[toggle] exception:', err)
  } finally {
    tnode.loading = false
    tnode.loaded = true
  }
}

function handleAdd(node: TNode) {
  const saved: SavedNode = {
    node_id: node.node_id,
    display_name: node.display_name,
    browse_name: node.browse_name,
    node_class: node.node_class,
    type: node.data_type ?? node.node_class
  }
  emit('add', saved)
}

onMounted(loadRoots)
</script>

<template>
  <div class="card">
    <!-- Toolbar -->
    <div class="flex items-center gap-2 mb-3">
      <button class="btn-secondary text-xs" :disabled="loading" @click="loadRoots">
        <svg class="w-3.5 h-3.5" :class="{ 'animate-spin': loading }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
        Aggiorna albero
      </button>
      <span class="text-xs text-slate-500">Clicca ▶ per espandere, + per aggiungere ai nodi monitorati</span>
    </div>

    <!-- Error -->
    <div v-if="error || toggleError" class="mb-3 px-3 py-2 bg-red-900/30 border border-red-700 rounded text-red-400 text-xs font-mono">
      {{ error || toggleError }}
    </div>

    <!-- Loading -->
    <div v-if="loading && roots.length === 0" class="py-8 flex items-center justify-center gap-2 text-slate-400 text-sm">
      <svg class="w-5 h-5 animate-spin text-blue-400" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
      Connessione al server OPC UA...
    </div>

    <!-- Tree -->
    <div v-else-if="roots.length > 0" class="overflow-y-auto font-mono text-xs" style="max-height: 24rem;">
      <NodeTreeItem
        v-for="node in roots"
        :key="node.node_id"
        :node="(node as TNode)"
        :depth="0"
        @toggle="toggle"
        @add="handleAdd"
      />
    </div>

    <div v-else-if="!loading" class="py-6 text-center text-slate-500 text-sm italic">
      Nessun nodo — configura e testa la connessione OPC UA nella scheda "Connessione"
    </div>
  </div>
</template>
