<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useMainStore } from './stores/main'
import ConnectionView from './views/ConnectionView.vue'
import NodesView from './views/NodesView.vue'
import SessionView from './views/SessionView.vue'

type Tab = 'connection' | 'nodes' | 'session'

const store = useMainStore()
const activeTab = ref<Tab>('connection')

const tabs: { key: Tab; label: string }[] = [
  { key: 'connection', label: 'Connessione' },
  { key: 'nodes',      label: 'Nodi' },
  { key: 'session',    label: 'Lettura' }
]

onMounted(async () => {
  await store.fetchConfig()
  await store.syncStatus()
  if (store.opcua.commessa) await store.fetchSavedNodes()
})
</script>

<template>
  <div class="min-h-screen bg-slate-900 flex flex-col">
    <!-- Navbar -->
    <header class="sticky top-0 z-30 bg-slate-900/95 backdrop-blur border-b border-slate-800">
      <div class="max-w-screen-xl mx-auto px-4 h-12 flex items-center gap-4">
        <!-- Logo / titolo -->
        <div class="flex items-center gap-2 shrink-0">
          <div class="w-7 h-7 rounded bg-blue-600 flex items-center justify-center">
            <svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18" />
            </svg>
          </div>
          <span class="text-sm font-bold text-slate-100 tracking-wide">OPC UA Reader</span>
        </div>

        <!-- Tabs -->
        <nav class="flex items-center gap-0.5 ml-2" role="tablist">
          <button
            v-for="tab in tabs"
            :key="tab.key"
            role="tab"
            :aria-selected="activeTab === tab.key"
            class="px-3 py-1.5 text-sm rounded transition-colors"
            :class="activeTab === tab.key
              ? 'bg-slate-700 text-slate-100 font-medium'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'"
            @click="activeTab = tab.key"
          >
            {{ tab.label }}
          </button>
        </nav>

        <!-- Status badge -->
        <div class="ml-auto flex items-center gap-2">
          <span
            class="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border"
            :class="store.isRunning
              ? 'border-emerald-700 bg-emerald-900/40 text-emerald-400'
              : 'border-slate-700 bg-slate-800 text-slate-500'"
          >
            <span
              class="w-1.5 h-1.5 rounded-full"
              :class="store.isRunning ? 'bg-emerald-400 animate-pulse' : 'bg-slate-600'"
            />
            {{ store.isRunning ? 'In lettura' : 'Fermo' }}
          </span>
          <span v-if="store.opcua.commessa" class="text-xs text-slate-500 font-mono">
            {{ store.opcua.commessa }}
          </span>
        </div>
      </div>
    </header>

    <!-- Main content -->
    <main class="flex-1 max-w-screen-xl mx-auto w-full px-4 py-5">
      <ConnectionView v-if="activeTab === 'connection'" />
      <NodesView v-else-if="activeTab === 'nodes'" />
      <SessionView v-else-if="activeTab === 'session'" />
    </main>

    <!-- Footer -->
    <footer class="border-t border-slate-800 py-2 px-4 text-center text-xs text-slate-600">
      OPC UA Reader — AINIMA
    </footer>
  </div>
</template>
