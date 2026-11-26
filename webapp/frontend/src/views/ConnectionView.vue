<script setup lang="ts">
import { ref } from 'vue'
import { useMainStore } from '../stores/main'
import OpcuaPanel from '../components/OpcuaPanel.vue'
import DatabasePanel from '../components/DatabasePanel.vue'
import ReadParamsPanel from '../components/ReadParamsPanel.vue'

const store = useMainStore()
const saving = ref(false)
const saveOk = ref(false)
const saveErr = ref('')

async function handleSave() {
  saving.value = true
  saveOk.value = false
  saveErr.value = ''
  try {
    await store.persistConfig()
    saveOk.value = true
    setTimeout(() => { saveOk.value = false }, 3000)
  } catch (err) {
    saveErr.value = err instanceof Error ? err.message : String(err)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="space-y-5">
    <!-- Section: OPC UA + Database -->
    <section>
      <h2 class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
        </svg>
        Connessioni
      </h2>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <OpcuaPanel />
        <DatabasePanel />
      </div>
    </section>

    <!-- Section: Parametri di lettura -->
    <section>
      <h2 class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
        </svg>
        Parametri di lettura
      </h2>
      <ReadParamsPanel />
    </section>

    <!-- Save bar -->
    <div class="flex items-center gap-3">
      <button class="btn-primary" :disabled="saving" @click="handleSave">
        <svg v-if="saving" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
        <svg v-else class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" />
        </svg>
        Salva configurazione
      </button>
      <span v-if="saveOk" class="text-xs text-emerald-400 flex items-center gap-1">
        <svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
          <path fill-rule="evenodd"
            d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
            clip-rule="evenodd" />
        </svg>
        Salvato
      </span>
      <span v-if="saveErr" class="text-xs text-red-400">{{ saveErr }}</span>
    </div>
  </div>
</template>
