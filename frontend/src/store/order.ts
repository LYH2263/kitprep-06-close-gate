import { computed, reactive, watch } from 'vue'
import { api } from '../api'

export interface OrderBrief {
  id: number
  code: string
  outlet: string
  status: string
}

const STORAGE_KEY = 'kitprep.selectedOrderId'

export const orderStore = reactive({
  orders: [] as OrderBrief[],
  selectedId: null as number | null,
  loaded: false,

  async load(force = false): Promise<void> {
    if (this.loaded && !force) return
    this.orders = await api('/orders')
    this.loaded = true
    if (this.orders.length && !this.orders.some((o) => o.id === this.selectedId)) {
      const saved = Number(localStorage.getItem(STORAGE_KEY))
      const initial = this.orders.find((o) => o.id === saved) ?? this.orders[0]
      this.selectedId = initial.id
    }
    if (!this.orders.length) this.selectedId = null
  },

  select(id: number): void {
    this.selectedId = id
  },
})

watch(
  () => orderStore.selectedId,
  (id) => {
    if (id == null) localStorage.removeItem(STORAGE_KEY)
    else localStorage.setItem(STORAGE_KEY, String(id))
  },
)

export const selectedOrder = computed<OrderBrief | null>(
  () => orderStore.orders.find((o) => o.id === orderStore.selectedId) ?? null,
)
export const isClosed = computed(() => selectedOrder.value?.status === 'closed')
export const statusLabel = (status: string) => (status === 'closed' ? '已截档' : '营业中')
