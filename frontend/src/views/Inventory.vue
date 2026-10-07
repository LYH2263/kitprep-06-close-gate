<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const rows = ref<any[]>([])
const addQty = ref<Record<number, number>>({})
const error = ref('')
async function load() { rows.value = await api('/inventory') }
async function adjust(r: any) {
  error.value = ''
  const qty = Number(addQty.value[r.id] || 0)
  if (!(qty > 0)) { error.value = '只许加账面，数量必须为正'; return }
  try {
    await api('/inventory/adjust', { method: 'POST', body: JSON.stringify({ ingredient_id: r.id, qty }) })
    addQty.value[r.id] = 0
    await load()
  } catch (e: any) { error.value = e.message }
}
onMounted(load)
</script>
<template>
  <h1>库存</h1>
  <p class="sub">中央厨房原料库存 · 改结存只加账面，不带动已截订单与缺料贴</p>
  <p v-if="error" class="badge badge-bad" style="margin-bottom:0.5rem">{{ error }}</p>
  <div class="card">
    <table>
      <thead><tr><th>编码</th><th>名称</th><th>库存</th><th>单位</th><th>加账面</th></tr></thead>
      <tbody>
        <tr v-for="r in rows" :key="r.id ?? JSON.stringify(r)">
          <td>{{ r.code }}</td><td>{{ r.name }}</td><td>{{ r.stock_qty }}</td><td>{{ r.unit }}</td>
          <td>
            <input type="number" min="0" step="0.001" style="width:6rem" v-model="addQty[r.id]" />
            <button class="btn" style="margin-left:0.4rem" @click="adjust(r)">加账面</button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
