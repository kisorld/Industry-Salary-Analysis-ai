<template>
  <div ref="el" class="chart"></div>
</template>

<script setup>
import * as echarts from 'echarts'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  rows: {
    type: Array,
    default: () => [],
  },
  title: {
    type: String,
    default: '薪资统计',
  },
  nameKey: {
    type: String,
    default: '维度',
  },
  valueKey: {
    type: String,
    default: '中位数',
  },
  yName: {
    type: String,
    default: 'K/月',
  },
})

const el = ref(null)
let chart

function render() {
  if (!el.value) return
  if (!chart) chart = echarts.init(el.value)
  const names = props.rows.map((row) => row[props.nameKey])
  const values = props.rows.map((row) => row[props.valueKey])
  chart.setOption({
    title: { text: props.title, left: 0, textStyle: { fontSize: 15 } },
    grid: { left: 36, right: 16, top: 48, bottom: 32 },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: names, axisLabel: { interval: 0 } },
    yAxis: { type: 'value', name: props.yName },
    series: [{ type: 'bar', data: values, itemStyle: { color: '#1f7a8c' }, barMaxWidth: 44 }],
  })
}

onMounted(render)
watch(() => props.rows, render, { deep: true })
window.addEventListener('resize', () => chart?.resize())
onBeforeUnmount(() => chart?.dispose())
</script>
