<script setup lang="ts">
import { useMainStore } from '../stores/main'
import LogPanel from '../components/LogPanel.vue'
import ProgressSection from '../components/ProgressSection.vue'

const store = useMainStore()
</script>

<template>
  <div class="space-y-5">
    <!-- Section: Avanzamento -->
    <section>
      <h2 class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
        </svg>
        Avanzamento e Azioni
      </h2>
      <ProgressSection />
    </section>

    <!-- Section: Log -->
    <section>
      <h2 class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
        </svg>
        Log
      </h2>
      <LogPanel
        :logs="store.logs.map(l => l.text)"
        @clear="store.clearLogs()"
      />
    </section>

    <!-- Nodi monitorati (riepilogo) -->
    <section v-if="store.savedNodes.length > 0">
      <h2 class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M4 6h16M4 10h16M4 14h16M4 18h16" />
        </svg>
        Variabili monitorate
        <span class="text-blue-400 font-semibold ml-1">{{ store.savedNodes.length }}</span>
      </h2>
      <div class="card">
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
          <div
            v-for="node in store.savedNodes"
            :key="node.node_id"
            class="flex items-center gap-2 px-2.5 py-1.5 bg-slate-700/40 rounded border border-slate-700/60 text-xs"
          >
            <span
              class="w-1.5 h-1.5 rounded-full shrink-0"
              :class="store.isRunning ? 'bg-emerald-400 animate-pulse' : 'bg-slate-600'"
            />
            <span class="text-slate-300 truncate">{{ node.display_name }}</span>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
