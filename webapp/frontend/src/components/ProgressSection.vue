<script setup lang="ts">
import { computed } from 'vue'
import { useMainStore } from '../stores/main'

const store = useMainStore()

const statusText = computed(() => {
  if (store.isRunning) return 'In lettura'
  return 'Fermo'
})

const statusColor = computed(() => {
  if (store.isRunning) return 'text-emerald-400'
  return 'text-slate-500'
})
</script>

<template>
  <div class="card space-y-4">
    <!-- Status + contatori -->
    <div class="flex flex-wrap items-center gap-4">
      <div class="flex items-center gap-2">
        <span
          class="w-2 h-2 rounded-full"
          :class="store.isRunning ? 'bg-emerald-400 animate-pulse' : 'bg-slate-600'"
        />
        <span class="text-sm font-medium" :class="statusColor">{{ statusText }}</span>
      </div>

      <div v-if="store.isRunning || store.readCount > 0" class="flex items-center gap-4 text-sm">
        <span class="text-slate-400">
          Cicli completati:
          <span class="text-slate-100 font-semibold font-mono ml-1">{{ store.readCount }}</span>
        </span>
        <span v-if="store.isRunning && store.nextReadIn > 0" class="text-slate-400">
          Prossima lettura in:
          <span class="text-blue-400 font-semibold font-mono ml-1">{{ store.nextReadIn }}s</span>
        </span>
      </div>

      <!-- Nodi -->
      <span class="text-xs text-slate-500">
        <span class="text-slate-300 font-semibold">{{ store.savedNodes.length }}</span>
        variabili configurate
      </span>
    </div>

    <!-- Progress bar "next read" -->
    <div v-if="store.isRunning && store.opcua.read_interval_seconds > 0">
      <div class="flex justify-between items-center mb-1">
        <span class="text-xs text-slate-400">Intervallo {{ store.opcua.read_interval_seconds }}s</span>
        <span class="text-xs text-slate-500 font-mono">
          {{ store.nextReadIn > 0 ? store.nextReadIn + 's' : '—' }}
        </span>
      </div>
      <div class="progress-bar">
        <div
          class="progress-fill bg-emerald-500"
          :style="{
            width: store.nextReadIn > 0
              ? `${((store.opcua.read_interval_seconds - store.nextReadIn) / store.opcua.read_interval_seconds) * 100}%`
              : '100%'
          }"
        />
      </div>
    </div>

    <!-- Pulsanti azione -->
    <div class="flex flex-wrap gap-2 pt-1 border-t border-slate-700">
      <button
        class="btn-success"
        :disabled="store.isRunning || store.savedNodes.length === 0"
        @click="store.startReading()"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        Avvia lettura
      </button>

      <button
        v-if="store.isRunning"
        class="btn-danger"
        @click="store.stopReading()"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M9 10h6v4H9z" />
        </svg>
        Ferma
      </button>

      <div v-if="store.savedNodes.length === 0 && !store.isRunning" class="text-xs text-slate-500 self-center">
        Aggiungi nodi nella scheda "Nodi" prima di avviare
      </div>
    </div>
  </div>
</template>
