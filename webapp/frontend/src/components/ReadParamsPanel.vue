<script setup lang="ts">
import { useMainStore } from '../stores/main'

const store = useMainStore()

const runModes = [
  { value: 'normal', label: 'Polling (lettura ciclica)' },
  { value: 'subscription', label: 'Sottoscrizione OPC UA' }
]
</script>

<template>
  <div class="card">
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <!-- Modalità -->
      <div>
        <p class="section-label mb-2">Modalità</p>
        <div class="space-y-1.5">
          <label
            v-for="m in runModes"
            :key="m.value"
            class="flex items-center gap-2 text-sm cursor-pointer"
          >
            <input type="radio" :value="m.value" v-model="store.opcua.run_mode" class="accent-blue-500" />
            <span class="text-slate-200">{{ m.label }}</span>
          </label>
        </div>
      </div>

      <!-- Intervallo -->
      <div>
        <label class="section-label">Intervallo lettura (s)</label>
        <input
          v-model.number="store.opcua.read_interval_seconds"
          type="number"
          min="1"
          class="input"
        />
      </div>

      <!-- Numero record -->
      <div>
        <label class="section-label">Max record (0 = infinito)</label>
        <input
          v-model.number="store.opcua.read_records"
          type="number"
          min="0"
          class="input"
        />
      </div>

      <!-- Deadband -->
      <div>
        <label class="section-label">Deadband globale</label>
        <input
          v-model.number="store.opcua.deadband_global"
          type="number"
          min="0"
          step="0.1"
          class="input"
        />
      </div>
    </div>
  </div>
</template>
