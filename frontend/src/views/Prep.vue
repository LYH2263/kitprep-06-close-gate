<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { api } from '../api'
import OrderChips from '../components/OrderChips.vue'
import { isClosed, orderStore } from '../store/order'

const tree = ref<any[]>([])
const data = ref<any>(null)
const shortages = ref<any[]>([])
const busy = ref(false)
const errorMsg = ref('')

async function refresh() {
  const id = orderStore.selectedId
  if (id == null) { data.value = null; shortages.value = []; return }
  data.value = await api('/prep/latest?order_id=' + id)
  try {
    const res = await api('/prep/shortages?order_id=' + id)
    shortages.value = res.shortages || []
  } catch { shortages.value = [] }
}

watch(() => orderStore.selectedId, async () => {
  errorMsg.value = ''
  await refresh()
})

async function run() {
  const id = orderStore.selectedId
  if (id == null || busy.value || isClosed.value) return
  busy.value = true; errorMsg.value = ''
  try {
    await api('/prep/run?order_id=' + id, { method: 'POST' })
    await refresh()
  } catch (e) {
    // 失败句只显示后端原样返回（已截单不能再生成）
    errorMsg.value = (e as Error).message
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  tree.value = await api('/bom/tree')
  await orderStore.load()
  await refresh()
})
</script>
<template>
  <h1>备料工作台</h1>
  <p class="sub">左 BOM 树 · 中备料表 · 右缺料便利贴 · 顶栏订单芯片</p>
  <OrderChips></OrderChips>
  <div style="display:flex;align-items:center;gap:0.6rem;margin:0.1rem 0 0.6rem;flex-wrap:wrap">
    <button class="btn" :disabled="busy || isClosed || orderStore.selectedId == null" @click="run">生成备料单</button>
    <span v-if="isClosed" class="badge badge-bad">已截档 · 备料单冻结中</span>
    <p v-if="errorMsg" class="inline-error" style="margin:0">{{ errorMsg }}</p>
  </div>
  <div class="kp-workbench">
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
        <span v-if="isClosed" class="badge badge-bad" style="margin-left:0.4rem">#{{ data.id }} 已钉死</span>
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
      <h2>⚠ 缺料便利贴<span v-if="isClosed" style="font-size:0.7rem"> · 已冻结</span></h2>
      <div v-for="r in shortages" :key="r.ingredient_id" class="kp-shortage-item">
        <span>{{ r.ingredient_name }}</span>
        <span class="kp-qty">−{{ r.shortage }} {{ r.unit }}</span>
      </div>
      <p v-if="!shortages.length" style="font-size:0.8rem;margin:0.5rem 0 0">暂无缺料</p>
    </aside>
  </div>
</template>
