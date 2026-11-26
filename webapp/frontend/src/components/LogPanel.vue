<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'

const props = defineProps<{
  logs: string[]
}>()

const emit = defineEmits<{
  clear: []
}>()

const container = ref<HTMLElement | null>(null)
const autoScroll = ref(true)

watch(
  () => props.logs.length,
  async () => {
    if (!autoScroll.value) return
    await nextTick()
    if (container.value) {
      container.value.scrollTop = container.value.scrollHeight
    }
  }
)

function onScroll() {
  if (!container.value) return
  const { scrollTop, scrollHeight, clientHeight } = container.value
  autoScroll.value = scrollHeight - scrollTop - clientHeight < 60
}

function scrollToBottom() {
  if (container.value) {
    container.value.scrollTop = container.value.scrollHeight
    autoScroll.value = true
  }
}

function colorLine(line: string): string {
  if (/ERROR|ERRORE|error/i.test(line)) return 'text-red-400'
  if (/WARN|warning/i.test(line)) return 'text-amber-400'
  if (/OK|success|completat|✓/i.test(line)) return 'text-emerald-400'
  if (/^\[/.test(line)) return 'text-slate-300'
  return 'text-emerald-300'
}
</script>

<template>
  <div class="flex flex-col bg-zinc-950 border border-slate-700 rounded-lg overflow-hidden">
    <!-- Header bar -->
    <div class="flex items-center justify-between px-3 py-1.5 bg-slate-800 border-b border-slate-700">
      <div class="flex items-center gap-1.5 text-xs text-slate-400">
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
        </svg>
        Log
        <span class="text-slate-600 font-mono">({{ logs.length }})</span>
      </div>
      <div class="flex items-center gap-1.5">
        <button
          v-if="!autoScroll"
          class="text-xs text-blue-400 hover:text-blue-300 transition-colors px-1.5 py-0.5 rounded hover:bg-slate-700"
          @click="scrollToBottom"
        >
          ↓ Scorri
        </button>
        <button
          class="text-xs text-slate-400 hover:text-slate-200 transition-colors px-1.5 py-0.5 rounded hover:bg-slate-700"
          @click="$emit('clear')"
        >
          Pulisci
        </button>
      </div>
    </div>

    <!-- Log content -->
    <div
      ref="container"
      class="overflow-y-auto font-mono text-xs leading-5 p-3 space-y-0.5 h-48"
      style="min-height: 10rem; max-height: 20rem;"
      @scroll="onScroll"
    >
      <div v-if="logs.length === 0" class="text-slate-600 italic">
        In attesa di avviare la sessione di lettura...
      </div>
      <div
        v-for="(line, idx) in logs"
        :key="idx"
        :class="colorLine(line)"
        class="whitespace-pre-wrap break-all"
      >{{ line }}</div>
    </div>
  </div>
</template>
