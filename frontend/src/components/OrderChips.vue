<script setup lang="ts">
import { orderStore } from '../store/order'
</script>
<template>
  <div class="kp-chips" style="margin-bottom:0.75rem">
    <button
      v-for="o in orderStore.orders"
      :key="o.id"
      type="button"
      class="kp-chip kp-chip-btn"
      :class="{ 'kp-chip-active': o.id === orderStore.selectedId }"
      :aria-pressed="o.id === orderStore.selectedId"
      @click="orderStore.select(o.id)"
    >
      <span class="kp-dot" :class="o.status === 'closed' ? 'kp-dot-closed' : 'kp-dot-open'"></span>
      {{ o.code }} · {{ o.outlet }}
    </button>
  </div>
</template>
