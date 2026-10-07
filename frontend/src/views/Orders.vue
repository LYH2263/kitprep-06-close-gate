<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { api } from '../api'
import OrderChips from '../components/OrderChips.vue'
import { isClosed, orderStore, selectedOrder, statusLabel } from '../store/order'

const lines = ref<any[]>([])
const closures = ref<any[]>([])
const busy = ref(false)
const message = ref('')
const messageOk = ref(false)

async function loadDetail() {
  const o = selectedOrder.value
  if (!o) {
    lines.value = []
    closures.value = []
    return
  }
  lines.value = await api('/orders/' + o.id + '/lines')
  closures.value = await api('/orders/' + o.id + '/closures')
}

watch(() => orderStore.selectedId, loadDetail)

async function closeOrder() {
  const o = selectedOrder.value
  if (!o || busy.value) return
  if (!window.confirm('确认对该订单截单收档？截档后将不能再生成备料单。')) return
  busy.value = true; message.value = ''
  try {
    await api('/orders/' + o.id + '/close', { method: 'POST' })
    messageOk.value = true; message.value = '截单收档成功，备料单已钉死'
    await orderStore.load(true)
    await loadDetail()
  } catch (e) {
    messageOk.value = false; message.value = (e as Error).message
  } finally {
    busy.value = false
  }
}

async function reopenOrder() {
  const o = selectedOrder.value
  if (!o || busy.value) return
  busy.value = true; message.value = ''
  try {
    await api('/orders/' + o.id + '/reopen', { method: 'POST' })
    messageOk.value = true; message.value = '已重新打开，可重新生成备料单'
    await orderStore.load(true)
    await loadDetail()
  } catch (e) {
    messageOk.value = false; message.value = (e as Error).message
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  await orderStore.load()
  await loadDetail()
})
</script>
<template>
  <h1>订单芯片</h1>
  <p class="sub">门店要货 · 点芯片选订单 · 截单收档 / 重新打开</p>
  <OrderChips></OrderChips>
  <template v-if="selectedOrder">
    <div style="display:flex;align-items:center;gap:0.6rem;margin:0.2rem 0 0.9rem;flex-wrap:wrap">
      <strong style="color:#f0e6d8">{{ selectedOrder.code }} · {{ selectedOrder.outlet }}</strong>
      <span class="badge" :class="isClosed ? 'badge-bad' : 'badge-ok'">{{ statusLabel(selectedOrder.status) }}</span>
      <button class="btn" :disabled="busy || isClosed" @click="closeOrder">截单收档</button>
      <button class="btn" :disabled="busy || !isClosed" @click="reopenOrder">重新打开</button>
      <p v-if="message" class="inline-message" :class="messageOk ? 'inline-ok' : 'inline-error'">{{ message }}</p>
    </div>
    <div class="kp-worksheet" style="margin-bottom:0.85rem">
      <h2>订单行</h2>
      <table>
        <thead><tr><th>菜品</th><th>份数</th></tr></thead>
        <tbody>
          <tr v-for="l in lines" :key="l.id"><td>{{ l.dish_name }}</td><td>{{ l.portions }}</td></tr>
        </tbody>
      </table>
    </div>
    <div class="card">
      <h2 style="margin:0 0 0.5rem;font-size:0.95rem">截档记录（钉死的备料单与截住那一刻的结存）</h2>
      <p v-if="!closures.length" class="muted" style="margin:0;font-size:0.85rem">暂无截档记录</p>
      <table v-else>
        <thead>
          <tr><th>截档时间</th><th>重开时间</th><th>冻结备料单#</th><th>结存快照行数</th></tr>
        </thead>
        <tbody>
          <tr v-for="c in closures" :key="c.id">
            <td>{{ c.closed_at }}</td>
            <td>{{ c.reopened_at ?? '—' }}</td>
            <td>#{{ c.prep_run_id }}</td>
            <td>{{ c.stock_snapshot.length }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </template>
  <p v-else class="sub">暂无订单</p>
</template>
