import axios from 'axios'

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000',
  timeout: 120000,
})

export async function analyzeSample(useAi = true) {
  const { data } = await api.get('/api/sample/analyze', { params: { use_ai: useAi } })
  return data
}

export async function uploadAnalyze(file, useAi = true) {
  const form = new FormData()
  form.append('file', file)
  const { data } = await api.post('/api/upload/analyze', form, {
    params: { use_ai: useAi },
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function scrapePoc(url, limit = 20, useAi = true, mode = 'auto') {
  const urls = String(url)
    .split(/\n|,|，|;|；/)
    .map((item) => item.trim())
    .filter(Boolean)
  const { data } = await api.post('/api/scrape/poc', { url, urls, limit, use_ai: useAi, mode })
  return data
}

export async function readUrlWithAi(url, limit = 20, mode = 'auto') {
  const urls = String(url)
    .split(/\n|,|，|;|；/)
    .map((item) => item.trim())
    .filter(Boolean)
  const { data } = await api.post('/api/url/read', { url, urls, limit, use_ai: true, mode })
  return data
}

export async function runAgent(payload) {
  const { data } = await api.post('/api/agent/run', payload)
  return data
}

export async function crawlAnalyzePlatform(payload) {
  const { data } = await api.post('/api/platform/crawl-analyze', payload)
  return data
}

export async function openPlatformLogin(platform) {
  const { data } = await api.get('/api/platform/open-login', { params: { platform } })
  return data
}

export async function searchRag(q, topK = 3) {
  const { data } = await api.get('/api/rag/search', { params: { q, top_k: topK } })
  return data
}

export async function generateReport(title = '行业薪酬洞察报告', useAi = true) {
  const { data } = await api.post('/api/report', { title, use_ai: useAi })
  return data
}

export async function listTaskRuns() {
  const { data } = await api.get('/api/task-runs')
  return data
}

export function taskRunDownloadUrl(runDir, fileKey) {
  const params = new URLSearchParams({
    run_dir: runDir,
    file_key: fileKey,
    t: String(Date.now()),
  })
  return `${api.defaults.baseURL}/api/task-runs/download?${params.toString()}`
}

export const reportUrl = `${api.defaults.baseURL}/api/download/report`
export function cleanedUrl() {
  return `${api.defaults.baseURL}/api/download/cleaned?t=${Date.now()}`
}
