<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const orders = ref<any[]>([])
const lines = ref<any[]>([])
const selected = ref<any>(null)
const error = ref('')
async function load() {
  orders.value = await api('/orders')
  if (!selected.value && orders.value.length) selected.value = orders.value[0]
  if (selected.value) {
    selected.value = orders.value.find((o: any) => o.id === selected.value.id) || orders.value[0]
    if (selected.value) lines.value = await api('/orders/' + selected.value.id + '/lines')
  }
}
async function pick(o: any) {
  selected.value = o
  lines.value = await api('/orders/' + o.id + '/lines')
}
async function close(o: any) {
  error.value = ''
  try { await api('/orders/' + o.id + '/close', { method: 'POST' }); await load() }
  catch (e: any) { error.value = e.message }
}
async function reopen(o: any) {
  error.value = ''
  try { await api('/orders/' + o.id + '/reopen', { method: 'POST' }); await load() }
  catch (e: any) { error.value = e.message }
}
onMounted(load)
</script>
<template>
  <h1>订单芯片</h1>
  <p class="sub">门店要货 · 顶栏芯片对应订单 · 截单收档后钉死备料快照</p>
  <p v-if="error" class="badge badge-bad" style="margin-bottom:0.5rem">{{ error }}</p>
  <div class="kp-chips" style="margin-bottom:1rem">
    <span v-for="o in orders" :key="o.id" class="kp-chip" style="cursor:pointer"
          :style="selected?.id === o.id ? 'outline:2px solid currentColor' : ''"
          @click="pick(o)">
      {{ o.code }} · {{ o.outlet }} · {{ o.status === 'closed' ? '已截档' : 'open' }}
      <button v-if="o.status !== 'closed'" class="btn" style="margin-left:0.5rem" @click.stop="close(o)">截单收档</button>
      <button v-else class="btn" style="margin-left:0.5rem" @click.stop="reopen(o)">重新打开</button>
    </span>
  </div>
  <div class="kp-worksheet" v-if="selected">
    <h2>订单行 · {{ selected.code }}</h2>
    <table>
      <thead><tr><th>菜品</th><th>份数</th></tr></thead>
      <tbody>
        <tr v-for="l in lines" :key="l.id"><td>{{ l.dish_name }}</td><td>{{ l.portions }}</td></tr>
      </tbody>
    </table>
  </div>
</template>
