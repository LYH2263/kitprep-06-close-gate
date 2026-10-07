<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
const tree = ref<any[]>([])
const data = ref<any>(null)
const shortages = ref<any[]>([])
const orders = ref<any[]>([])
const selected = ref<any>(null)
const error = ref('')
const isClosed = computed(() => selected.value?.status === 'closed')
async function loadLatest() {
  if (!selected.value) return
  error.value = ''
  data.value = await api('/prep/latest?order_id=' + selected.value.id)
  const res = await api('/prep/shortages?order_id=' + selected.value.id)
  shortages.value = res.shortages || []
}
async function pick(o: any) {
  selected.value = o
  await loadLatest()
}
async function run() {
  if (!selected.value || isClosed.value) return
  error.value = ''
  try {
    data.value = await api('/prep/run?order_id=' + selected.value.id, { method: 'POST' })
    const res = await api('/prep/shortages?order_id=' + selected.value.id)
    shortages.value = res.shortages || []
  } catch (e: any) { error.value = e.message }
}
onMounted(async () => {
  tree.value = await api('/bom/tree')
  orders.value = await api('/orders')
  if (orders.value.length) {
    selected.value = orders.value[0]
    await loadLatest()
  }
})
</script>
<template>
  <h1>备料工作台</h1>
  <p class="sub">左 BOM 树 · 中备料表 · 右缺料便利贴 · 顶栏订单芯片</p>
  <div class="kp-chips" style="margin-bottom:0.75rem" v-if="orders.length">
    <span v-for="o in orders" :key="o.id" class="kp-chip" style="cursor:pointer"
          :style="selected?.id === o.id ? 'outline:2px solid currentColor' : ''"
          @click="pick(o)">
      {{ o.code }} · {{ o.outlet }} · {{ o.status === 'closed' ? '已截档' : 'open' }}
    </span>
  </div>
  <button class="btn" :disabled="isClosed || !selected" @click="run">生成备料单</button>
  <span v-if="isClosed" class="badge badge-bad" style="margin-left:0.5rem">已截单不能再生成</span>
  <p v-if="error" class="badge badge-bad" style="margin-top:0.5rem">{{ error }}</p>
  <div class="kp-workbench" style="margin-top:0.85rem">
    <aside class="kp-bom-tree">
      <h2>菜品 / BOM</h2>
      <div v-for="d in tree" :key="d.code" class="kp-dish-node">
        <strong>{{ d.dish }}</strong>
        <span style="font-size:0.7rem;color:#8a8078">{{ d.code }}</span>
        <ul>
          <li v-for="(c,i) in d.children" :key="i">{{ c.ingredient }} · {{ c.qty }} {{ c.unit }}</li>
        </ul>
      </div>
    </aside>
    <section class="kp-worksheet" v-if="data">
      <h2>
        备料单 · {{ data.order?.code }} · {{ data.order?.outlet }}
        <span v-if="data.closed" class="badge badge-bad">截档快照 · {{ data.closed_at }}</span>
      </h2>
      <table>
        <thead><tr><th>原料</th><th>需求</th><th>库存</th><th>单位</th></tr></thead>
        <tbody>
          <tr v-for="l in data.prep_lines" :key="l.ingredient_id">
            <td>{{ l.ingredient_name }}</td><td>{{ l.need_qty }}</td><td>{{ l.stock_qty }}</td><td>{{ l.unit }}</td>
          </tr>
        </tbody>
      </table>
    </section>
    <aside class="kp-shortage-sticky">
      <h2>⚠ 缺料便利贴</h2>
      <div v-for="r in shortages" :key="r.ingredient_id" class="kp-shortage-item">
        <span>{{ r.ingredient_name }}</span>
        <span class="kp-qty">−{{ r.shortage }} {{ r.unit }}</span>
      </div>
      <p v-if="!shortages.length" style="font-size:0.8rem;margin:0.5rem 0 0">暂无缺料</p>
    </aside>
  </div>
</template>
