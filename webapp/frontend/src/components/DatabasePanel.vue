<script setup lang="ts">
import { ref, watch } from 'vue'
import { useMainStore } from '../stores/main'

const store = useMainStore()
const testState = ref<'idle' | 'loading' | 'ok' | 'error'>('idle')
const testMsg = ref('')
const showPassword = ref(false)

const dtTypes = [
  { value: 1, label: 'MSSQL' },
  { value: 2, label: 'MariaDB' },
  { value: 3, label: 'MySQL' },
  { value: 4, label: 'PostgreSQL' }
]

const defaultPorts: Record<number, number> = { 1: 1433, 2: 3306, 3: 3306, 4: 5432 }

watch(() => store.db.dt_type, (newType, oldType) => {
  if (store.db.port === defaultPorts[oldType]) {
    store.db.port = defaultPorts[newType] ?? 3306
  }
  resetTest()
})

function resetTest() { testState.value = 'idle'; testMsg.value = '' }

async function handleTest() {
  testState.value = 'loading'
  testMsg.value = ''
  try {
    const res = await store.testDb(store.db)
    testState.value = res.ok ? 'ok' : 'error'
    testMsg.value = res.message
  } catch (err) {
    testState.value = 'error'
    testMsg.value = err instanceof Error ? err.message : String(err)
  }
}
</script>

<template>
  <div class="card flex flex-col gap-3">
    <!-- Header -->
    <div class="flex items-center gap-2 pb-2 border-b border-slate-700">
      <svg class="w-4 h-4 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
          d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4" />
      </svg>
      <span class="text-sm font-bold text-slate-200 uppercase tracking-wider">Database destinazione</span>
    </div>

    <!-- Tipo -->
    <div>
      <label class="section-label">Tipo</label>
      <select v-model="store.db.dt_type" class="select" @change="resetTest">
        <option v-for="t in dtTypes" :key="t.value" :value="t.value">{{ t.label }}</option>
      </select>
    </div>

    <!-- Host + Porta -->
    <div class="grid grid-cols-3 gap-2">
      <div class="col-span-2">
        <label class="section-label">Host</label>
        <input v-model="store.db.host" class="input" placeholder="localhost" @input="resetTest" />
      </div>
      <div>
        <label class="section-label">Porta</label>
        <input v-model.number="store.db.port" type="number" class="input" @input="resetTest" />
      </div>
    </div>

    <!-- Database -->
    <div>
      <label class="section-label">Database</label>
      <input v-model="store.db.database" class="input" placeholder="nome_database" @input="resetTest" />
    </div>

    <!-- User + Password -->
    <div class="grid grid-cols-2 gap-2">
      <div>
        <label class="section-label">Utente</label>
        <input v-model="store.db.user" class="input" placeholder="sa" @input="resetTest" />
      </div>
      <div>
        <label class="section-label">Password</label>
        <div class="relative">
          <input
            v-model="store.db.password"
            :type="showPassword ? 'text' : 'password'"
            class="input pr-9"
            placeholder="••••••••"
            @input="resetTest"
          />
          <button type="button" tabindex="-1"
            class="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200 transition-colors"
            @click="showPassword = !showPassword">
            <svg v-if="showPassword" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
            </svg>
            <svg v-else class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
            </svg>
          </button>
        </div>
      </div>
    </div>

    <!-- Test -->
    <div class="pt-1 border-t border-slate-700 flex flex-wrap items-center gap-2">
      <button class="btn-secondary" :disabled="testState === 'loading'" @click="handleTest">
        <svg v-if="testState === 'loading'" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
        <svg v-else class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        Test connessione DB
      </button>
      <span v-if="testState === 'ok'" class="text-xs text-emerald-400 flex items-center gap-1">
        <svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
          <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd" />
        </svg>
        {{ testMsg || 'OK' }}
      </span>
      <span v-else-if="testState === 'error'" class="text-xs text-red-400 max-w-xs break-words">{{ testMsg }}</span>
    </div>
  </div>
</template>
