<script setup lang="ts">
import { ref } from 'vue'
import { useMainStore } from '../stores/main'

const store = useMainStore()
const testState = ref<'idle' | 'loading' | 'ok' | 'error'>('idle')
const testMsg = ref('')
const endpointsLoading = ref(false)
const endpointsList = ref<string[]>([])
const endpointsErr = ref('')
const showPassword = ref(false)

const securityModes = ['None', 'Sign', 'Sign & Encrypt']
const securityPolicies = ['None', 'Basic128RSA15', 'Basic256', 'Basic256SHA256']

async function handleTest() {
  testState.value = 'loading'
  testMsg.value = ''
  try {
    const res = await store.testOpcua(store.opcua)
    testState.value = res.ok ? 'ok' : 'error'
    testMsg.value = res.message
  } catch (err) {
    testState.value = 'error'
    testMsg.value = err instanceof Error ? err.message : String(err)
  }
}

async function handleEndpoints() {
  endpointsLoading.value = true
  endpointsErr.value = ''
  endpointsList.value = []
  try {
    const res = await store.getEndpoints(store.opcua)
    if (res.error) { endpointsErr.value = res.error; return }
    endpointsList.value = res.endpoints.map(e =>
      `${e.url} | ${e.security_mode} / ${e.security_policy} | ${e.login_types.join(', ')}`
    )
  } catch (err) {
    endpointsErr.value = err instanceof Error ? err.message : String(err)
  } finally {
    endpointsLoading.value = false
  }
}

function resetTest() { testState.value = 'idle'; testMsg.value = '' }
</script>

<template>
  <div class="card flex flex-col gap-3">
    <!-- Header -->
    <div class="flex items-center gap-2 pb-2 border-b border-slate-700">
      <svg class="w-4 h-4 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
          d="M13 10V3L4 14h7v7l9-11h-7z" />
      </svg>
      <span class="text-sm font-bold text-slate-200 uppercase tracking-wider">OPC UA</span>
    </div>

    <!-- URL -->
    <div>
      <label class="section-label">URL server</label>
      <input v-model="store.opcua.url" class="input" placeholder="opc.tcp://10.0.0.1:4840/" @input="resetTest" />
    </div>

    <!-- Autenticazione -->
    <div>
      <label class="flex items-center gap-2 text-sm cursor-pointer">
        <input type="checkbox" v-model="store.opcua.anonymous" class="w-4 h-4 accent-blue-500" @change="resetTest" />
        <span class="text-slate-200">Accesso anonimo</span>
      </label>
    </div>

    <template v-if="!store.opcua.anonymous">
      <div class="grid grid-cols-2 gap-2">
        <div>
          <label class="section-label">Utente</label>
          <input v-model="store.opcua.username" class="input" placeholder="Admin" @input="resetTest" />
        </div>
        <div>
          <label class="section-label">Password</label>
          <div class="relative">
            <input
              v-model="store.opcua.password"
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
    </template>

    <!-- Security -->
    <div class="grid grid-cols-2 gap-2">
      <div>
        <label class="section-label">Security mode</label>
        <select v-model="store.opcua.security_mode" class="select" @change="resetTest">
          <option v-for="m in securityModes" :key="m">{{ m }}</option>
        </select>
      </div>
      <div>
        <label class="section-label">Security policy</label>
        <select v-model="store.opcua.security_policy" class="select" @change="resetTest">
          <option v-for="p in securityPolicies" :key="p">{{ p }}</option>
        </select>
      </div>
    </div>

    <!-- Commessa -->
    <div>
      <label class="section-label">Commessa</label>
      <input v-model="store.opcua.commessa" class="input" placeholder="NOME_PROGETTO" />
    </div>

    <!-- Actions -->
    <div class="pt-1 border-t border-slate-700 flex flex-wrap items-center gap-2">
      <button class="btn-secondary" :disabled="testState === 'loading'" @click="handleTest">
        <svg v-if="testState === 'loading'" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
        <svg v-else class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        Test connessione
      </button>

      <button class="btn-secondary" :disabled="endpointsLoading" @click="handleEndpoints">
        <svg v-if="endpointsLoading" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
        <svg v-else class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M4 6h16M4 10h16M4 14h8" />
        </svg>
        Leggi endpoint
      </button>

      <span v-if="testState === 'ok'" class="text-xs text-emerald-400 flex items-center gap-1">
        <svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
          <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd" />
        </svg>
        {{ testMsg || 'OK' }}
      </span>
      <span v-else-if="testState === 'error'" class="text-xs text-red-400 max-w-xs break-words">{{ testMsg }}</span>
    </div>

    <!-- Endpoints list -->
    <div v-if="endpointsErr" class="text-xs text-red-400">{{ endpointsErr }}</div>
    <div v-if="endpointsList.length" class="space-y-1">
      <p class="section-label">Endpoint disponibili</p>
      <div
        v-for="(ep, i) in endpointsList"
        :key="i"
        class="text-xs font-mono text-slate-400 bg-slate-900/60 rounded px-2 py-1 break-all"
      >{{ ep }}</div>
    </div>
  </div>
</template>
