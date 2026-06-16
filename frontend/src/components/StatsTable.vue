<template>
  <div class="table-wrap">
    <table v-if="rows && rows.length">
      <thead>
        <tr>
          <th v-for="key in keys" :key="key">{{ key }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, index) in rows" :key="index">
          <td v-for="key in keys" :key="key">{{ row[key] }}</td>
        </tr>
      </tbody>
    </table>
    <p v-else class="empty">暂无数据</p>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  rows: {
    type: Array,
    default: () => [],
  },
})

const keys = computed(() => (props.rows.length ? Object.keys(props.rows[0]) : []))
</script>

