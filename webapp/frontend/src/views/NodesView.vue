<script setup lang="ts">
import { ref } from 'vue'
import { useMainStore } from '../stores/main'
import NodeBrowser from '../components/NodeBrowser.vue'
import type { SavedNode } from '../types'

const store = useMainStore()
const saveOk = ref(false)
const saveErr = ref('')

async function handleSave() {
  saveOk.value = false
  saveErr.value = ''
  try {
    await store.persistSavedNodes()
    saveOk.value = true
    setTimeout(() => { saveOk.value = false }, 3000)
  } catch (err) {
    saveErr.value = err instanceof Error ? err.message : String(err)
  }
}

function handleAdd(node: SavedNode) {
  store.addNode(node)
}
</script>

<template>
  <div class="space-y-5">
    <section>
      <h2 class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
        </svg>
        Sfoglia nodi OPC UA
      </h2>
      <NodeBrowser @add="handleAdd" />
    </section>

    <!-- Nodi selezionati -->
    <section>
      <div class="flex items-center gap-3 mb-2">
        <h2 class="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
          </svg>
          Nodi selezionati
          <span class="text-blue-400 font-semibold ml-1">{{ store.savedNodes.length }}</span>
        </h2>
        <div class="ml-auto flex items-center gap-2">
          <button class="btn-primary text-xs" @click="handleSave">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" />
            </svg>
            Salva lista
          </button>
          <button class="btn-secondary text-xs" :disabled="store.nodesLoading" @click="store.fetchSavedNodes()">
            <svg class="w-3.5 h-3.5" :class="{ 'animate-spin': store.nodesLoading }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Ricarica
          </button>
          <span v-if="saveOk" class="text-xs text-emerald-400">Salvato</span>
          <span v-if="saveErr" class="text-xs text-red-400">{{ saveErr }}</span>
        </div>
      </div>

      <div class="card">
        <div v-if="store.savedNodes.length === 0" class="text-slate-500 text-sm text-center py-6 italic">
          Nessun nodo selezionato — sfoglia l'albero sopra e aggiungi variabili
        </div>
        <div v-else class="space-y-1.5">
          <div
            v-for="node in store.savedNodes"
            :key="node.node_id"
            class="flex items-center gap-3 px-3 py-2 bg-slate-700/40 rounded border border-slate-700 hover:border-slate-600 transition-colors"
          >
            <div class="flex-1 min-w-0">
              <div class="text-sm font-medium text-slate-200 truncate">{{ node.display_name }}</div>
              <div class="text-xs text-slate-500 font-mono truncate">{{ node.node_id }}</div>
            </div>
            <span class="text-xs px-1.5 py-0.5 rounded bg-slate-700 text-slate-400 shrink-0">{{ node.type || node.node_class }}</span>
            <button
              class="text-slate-500 hover:text-red-400 transition-colors shrink-0"
              title="Rimuovi"
              @click="store.removeNode(node.node_id)"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
