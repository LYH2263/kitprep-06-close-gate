<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { api } from '../api'
const rows = ref<any[]>([])
const inputs = reactive<Record<number, string>>({})
const rowError = reactive<Record<number, string>>({})
const busy = reactive<Record<number, boolean>>({})

async function load() { rows.value = await api('/inventory') }

async function addStock(id: number) {
  rowError[id] = ''
  const raw = (inputs[id] ?? '').trim()
  const qty = Number(raw)
  if (raw === '' || !Number.isFinite(qty) || qty <= 0) {
    rowError[id] = '库存增加量必须大于0'
    return
  }
  busy[id] = true
  try {
    await api('/inventory/' + id + '/adjust', { method: 'POST', body: JSON.stringify({ add_qty: qty }) })
    inputs[id] = ''
    await load()
  } catch (e) {
    rowError[id] = (e as Error).message
  } finally {
    busy[id] = false
  }
}

onMounted(load)
</script>
<template>
  <h1>库存</h1>
  <p class="sub">中央厨房原料库存 · 只许加账面，不做出库扣减；加账面不影响已截订单的备料单与缺料贴</p>
  <div class="card">
    <table>
      <thead><tr><th>编码</th><th>名称</th><th>库存</th><th>单位</th><th>增加账面</th></tr></thead>
      <tbody>
        <tr v-for="r in rows" :key="r.id ?? JSON.stringify(r)">
          <td>{{ r.code }}</td>
          <td>{{ r.name }}</td>
          <td>{{ r.stock_qty }}</td>
          <td>{{ r.unit }}</td>
          <td>
            <input
              v-model="inputs[r.id]"
              type="number"
              min="0"
              step="0.01"
              style="width:6.5rem;padding:0.25rem 0.4rem"
              @keyup.enter="addStock(r.id)"
            >
            <button class="btn" style="margin-left:0.4rem" :disabled="busy[r.id]" @click="addStock(r.id)">加库存</button>
            <p v-if="rowError[r.id]" class="inline-error" style="margin:0.25rem 0 0">{{ rowError[r.id] }}</p>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
