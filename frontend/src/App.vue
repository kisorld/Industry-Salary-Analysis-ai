<template>
  <main>
    <header class="topbar">
      <div>
        <h1>行业薪酬洞察 AI 智能体</h1>
        <p>按岗位和地区获取招聘样本，形成薪资分析和企业建议。</p>
      </div>
      <div class="downloads">
        <a :href="reportUrl">下载分析报告</a>
        <a :href="cleanedDownloadUrl">下载清洗数据</a>
      </div>
    </header>

    <section class="user-flow">
      <nav class="mode-tabs">
        <button :class="{ active: activeMode === 'crawler' }" @click="switchMode('crawler')">平台采集分析</button>
        <button :class="{ active: activeMode === 'urlCsv' }" @click="switchMode('urlCsv')">URL / 文件分析</button>
      </nav>

      <section class="panel task-card">
        <template v-if="activeMode === 'crawler'">
          <div class="task-title">
            <span>推荐流程</span>
            <h2>先登录平台，再采集岗位数据</h2>
            <p>登录完成后，系统会根据你的岗位条件采集公开招聘样本，并输出薪资分析反馈。</p>
          </div>

          <div class="step-row">
            <div class="step-index">1</div>
            <div class="step-body">
              <strong>登录招聘平台</strong>
              <p>每次打开本系统页面后，每个平台通常只需登录一次。登录完成后回到本页面继续采集。</p>
              <div class="button-row">
                <button class="secondary" @click="openLogin('boss')" :disabled="loading">登录 BOSS</button>
                <button class="secondary" @click="openLogin('zhaopin')" :disabled="loading">登录智联</button>
              </div>
            </div>
          </div>

          <div class="step-row">
            <div class="step-index">2</div>
            <div class="step-body">
              <strong>填写采集条件</strong>
              <div class="form-grid">
                <label class="field-label">
                  <span>岗位关键词</span>
                  <input v-model="agentKeywords" placeholder="填写岗位名称，如 算法工程师、C++、数据分析师" />
                </label>
                <label class="field-label">
                  <span>采集地区</span>
                  <input v-model="agentCities" placeholder="填写城市名称，如 广州、深圳、北京；可用逗号分隔多个城市" />
                </label>
                <label class="field-label">
                  <span>采集页数</span>
                  <input v-model.number="agentPages" type="number" min="1" max="20" placeholder="填写 1-20，建议先填 1 测试" />
                </label>
              </div>
              <div class="platform-choice">
                <label><input v-model="agentPlatforms" type="checkbox" value="boss" /> BOSS直聘</label>
                <label><input v-model="agentPlatforms" type="checkbox" value="zhaopin" /> 智联招聘</label>
              </div>
            </div>
          </div>

          <div class="step-row">
            <div class="step-index">3</div>
            <div class="step-body">
              <strong>开始分析</strong>
              <textarea v-model="agentGoal" placeholder="你希望系统重点分析什么？例如：评估广州算法工程师薪资水平，并给出招聘预算建议。"></textarea>
              <details class="advanced">
                <summary>可选筛选条件</summary>
                <div class="form-grid">
                  <input v-model="agentIndustry" placeholder="行业" />
                  <input v-model="agentExperience" placeholder="经验" />
                  <input v-model="agentEducation" placeholder="学历" />
                  <input v-model="agentStartDate" placeholder="开始日期 YYYY-MM-DD" />
                  <input v-model="agentEndDate" placeholder="结束日期 YYYY-MM-DD" />
                  <label class="check"><input v-model="agentUseSample" type="checkbox" /> 样本不足时合并本地样例数据</label>
                </div>
              </details>
              <div class="button-row">
                <button @click="runPlatformCrawler" :disabled="loading">采集并分析</button>
                <button class="secondary" @click="runAgentTask" :disabled="loading">智能体深度分析</button>
                <button class="ghost" @click="clearResults" :disabled="loading">清除反馈</button>
              </div>
            </div>
          </div>
        </template>

        <template v-else>
          <div class="task-title">
            <span>快速分析</span>
            <h2>使用 URL 或 CSV / Excel 文件分析</h2>
            <p>适合已有数据文件，或只想分析少量公开招聘页面的场景。</p>
          </div>

          <textarea v-model="scrapeUrl" placeholder="输入公开招聘 URL，每行一个；如果只上传文件，这里可以留空。"></textarea>
          <div class="button-row">
            <label class="file">
              <input type="file" accept=".csv,.xlsx,.xls" @change="onFileChange" />
              上传文件并分析
            </label>
            <button @click="runScrape" :disabled="loading || !scrapeUrl">分析 URL</button>
            <button class="secondary" @click="runAiReadUrl" :disabled="loading || !scrapeUrl">提取页面岗位信息</button>
            <button class="ghost" @click="clearResults" :disabled="loading">清除反馈</button>
          </div>
        </template>
      </section>
    </section>

    <section v-if="loading || message || feedbackCards.length || aiText" class="panel feedback-panel">
      <div class="feedback-header">
        <div>
          <span>系统反馈</span>
          <h2>{{ loading ? '正在处理，请稍候' : feedbackTitle }}</h2>
        </div>
        <label class="toggle">
          <input v-model="useAi" type="checkbox" />
          启用 AI 分析
        </label>
      </div>

      <div v-if="loading" class="progress-line">
        <div></div>
      </div>

      <p v-if="message" class="message">{{ message }}</p>

      <div v-if="feedbackCards.length" class="feedback-grid">
        <div v-for="card in feedbackCards" :key="card.label" class="feedback-card">
          <span>{{ card.label }}</span>
          <strong>{{ card.value }}</strong>
        </div>
      </div>

      <div v-if="nextAdvice" class="advice-box">
        <strong>下一步建议</strong>
        <p>{{ nextAdvice }}</p>
      </div>

      <div v-if="aiText" class="ai-summary">
        <h3>分析反馈</h3>
        <p>{{ aiText }}</p>
      </div>

      <div v-if="analysis" class="download-strip">
        <a :href="reportUrl">下载完整报告</a>
        <a :href="cleanedDownloadUrl">下载清洗数据</a>
      </div>
    </section>

    <section class="panel history-panel">
      <div class="history-head">
        <div>
          <span>历史记录</span>
          <h2>最近任务输出（{{ historyRuns.length }} 条）</h2>
          <p>系统最多保留最近 10 次采集、分析和报告输出。</p>
        </div>
        <div class="history-actions">
          <button class="ghost" @click="historyExpanded = !historyExpanded">
            {{ historyExpanded ? '收起历史记录' : '展开历史记录' }}
          </button>
          <button class="ghost" @click="loadHistory" :disabled="historyLoading">
            {{ historyLoading ? '刷新中' : '刷新记录' }}
          </button>
        </div>
      </div>
      <div v-if="historyExpanded && historyError" class="message">{{ historyError }}</div>
      <div v-else-if="historyExpanded && !historyRuns.length" class="empty-history">暂无历史记录，完成一次采集或分析后会显示在这里。</div>
      <div v-else-if="historyExpanded" class="history-list">
        <article v-for="run in historyRuns" :key="run.run_dir" class="history-item">
          <div class="history-main">
            <strong>{{ run.label || '未命名任务' }}</strong>
            <p>{{ formatRunTime(run.created_at) }}</p>
            <dl class="history-query">
              <template v-for="item in historyQueryItems(run)" :key="item.label">
                <dt>{{ item.label }}</dt>
                <dd>{{ item.value }}</dd>
              </template>
            </dl>
          </div>
          <div class="history-files">
            <a v-if="run.files?.cleaned_jobs_csv" :href="historyFileUrl(run, 'cleaned_jobs_csv')">下载清洗数据</a>
            <a v-if="run.files?.report_docx" :href="historyFileUrl(run, 'report_docx')">下载报告</a>
            <a v-if="run.files?.rows_preview_csv" :href="historyFileUrl(run, 'rows_preview_csv')">下载岗位预览</a>
            <a v-if="run.files?.analysis_json" :href="historyFileUrl(run, 'analysis_json')">下载统计结果</a>
            <a v-if="run.files?.scrape_logs_json" :href="historyFileUrl(run, 'scrape_logs_json')">下载采集日志</a>
          </div>
        </article>
      </div>
    </section>

    <section v-if="analysis && appMode === 'user'" class="panel visual-panel">
      <div class="visual-head">
        <div>
          <span>数据可视化</span>
          <h2>薪资分布概览</h2>
        </div>
        <button class="ghost" @click="showJobDetails = !showJobDetails">
          {{ showJobDetails ? '隐藏岗位具体信息' : '查看岗位具体信息' }}
        </button>
      </div>
      <div class="chart-grid">
        <SalaryChart title="岗位类别中位薪资" :rows="analysis.by_category || []" />
        <SalaryChart title="城市中位薪资" :rows="analysis.by_city || []" />
      </div>
      <div v-if="analysis.demand_trends?.length" class="chart-single">
        <SalaryChart title="岗位需求数量变化" :rows="analysis.demand_trends" value-key="需求数量" name-key="月份" y-name="数量" />
      </div>
      <div v-if="showJobDetails" class="job-details">
        <h3>岗位具体信息</h3>
        <div class="job-list">
          <div v-for="(row, index) in jobDetailRows" :key="index" class="job-item">
            <div>
              <strong>{{ row.岗位 || '未识别岗位' }}</strong>
              <p>{{ row.公司 || '未知公司' }} · {{ row.城市 || '未知城市' }} · {{ row.经验 || '经验不限' }} · {{ row.学历 || '学历不限' }}</p>
            </div>
            <div class="job-side">
              <span>{{ row.薪资 || '薪资待确认' }}</span>
              <a v-if="row.链接" :href="row.链接" target="_blank" rel="noreferrer">查看岗位</a>
              <span v-else class="no-link">无链接</span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section v-if="appMode === 'admin'" class="admin-mode">
      <section v-if="adminSteps.length" class="panel">
        <h2>智能体执行过程</h2>
        <div v-for="(step, index) in adminSteps" :key="index" class="step">
          <strong>{{ step.name }}</strong>
          <span>{{ step.status }}</span>
          <p>{{ step.detail }}</p>
        </div>
      </section>

      <section v-if="generatedUrls.length" class="panel">
        <h2>已生成公开采集 URL</h2>
        <StatsTable :rows="generatedUrls" />
      </section>

      <section v-if="adminLogs.length" class="panel">
        <h2>采集日志</h2>
        <StatsTable :rows="adminLogs" />
      </section>

      <section v-if="adminRows.length" class="panel">
        <h2>岗位样本</h2>
        <StatsTable :rows="adminRows" />
      </section>

      <section v-if="partialRows.length" class="panel">
        <h2>待确认样本</h2>
        <StatsTable :rows="partialRows" />
      </section>

      <section v-if="analysis" class="chart-grid">
        <div class="panel">
          <SalaryChart title="岗位类别中位薪资" :rows="analysis.by_category || []" />
        </div>
        <div class="panel">
          <SalaryChart title="城市中位薪资" :rows="analysis.by_city || []" />
        </div>
      </section>

      <section v-if="analysis" class="panel">
        <h2>岗位类别统计</h2>
        <StatsTable :rows="analysis.by_category || []" />
      </section>
      <section v-if="analysis" class="panel">
        <h2>城市统计</h2>
        <StatsTable :rows="analysis.by_city || []" />
      </section>
      <section v-if="analysis" class="panel">
        <h2>经验统计</h2>
        <StatsTable :rows="analysis.by_experience || []" />
      </section>
    </section>

    <footer class="mode-switch">
      <button class="ghost" @click="toggleAppMode">
        {{ appMode === 'user' ? '切换为管理员模式' : '返回用户模式' }}
      </button>
    </footer>
  </main>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import SalaryChart from './components/SalaryChart.vue'
import StatsTable from './components/StatsTable.vue'
import { cleanedUrl, crawlAnalyzePlatform, listTaskRuns, openPlatformLogin, readUrlWithAi, reportUrl, runAgent, scrapePoc, taskRunDownloadUrl, uploadAnalyze } from './services/api'

const appMode = ref('user')
const activeMode = ref('crawler')
const loading = ref(false)
const useAi = ref(true)
const analysis = ref(null)
const ai = ref(null)
const message = ref('')
const nextAdvice = ref('')
const showJobDetails = ref(false)
const adminSteps = ref([])
const adminLogs = ref([])
const adminRows = ref([])
const partialRows = ref([])
const generatedUrls = ref([])
const scrapeUrl = ref('')
const scrapeMode = ref('auto')
const agentGoal = ref('分析目标岗位的行业薪酬水平，输出地区差异、经验/学历溢价和企业薪酬建议')
const agentPlatforms = ref(['boss'])
const agentIndustry = ref('')
const agentCities = ref('')
const agentKeywords = ref('')
const agentExperience = ref('')
const agentEducation = ref('')
const agentStartDate = ref('')
const agentEndDate = ref('')
const agentPages = ref(1)
const agentUseSample = ref(false)
const downloadVersion = ref(Date.now())
const cleanedDownloadUrl = computed(() => `${cleanedUrl()}&v=${downloadVersion.value}`)
const historyRuns = ref([])
const historyLoading = ref(false)
const historyError = ref('')
const historyExpanded = ref(false)

const feedbackTitle = computed(() => {
  if (!analysis.value && !ai.value) return '等待任务开始'
  if (analysis.value?.valid > 0) return '分析完成'
  return '已完成处理，但样本不足'
})

const feedbackCards = computed(() => {
  if (!analysis.value) return []
  return [
    { label: '总样本数', value: analysis.value.total ?? 0 },
    { label: '有效薪资样本', value: analysis.value.valid ?? 0 },
    { label: '解析成功率', value: `${analysis.value.parse_accuracy ?? 0}%` },
    { label: '中位薪资', value: `${analysis.value.overall?.['中位数K月'] ?? 0}K` },
  ]
})

const aiText = computed(() => {
  const raw = ai.value?.text || ''
  if (!raw) return ''
  return raw.length > 420 ? `${raw.slice(0, 420)}...` : raw
})

const jobDetailRows = computed(() => {
  const rows = adminRows.value.length ? adminRows.value : analysis.value?.cleaned_preview || []
  return rows.slice(0, 20).map((row) => ({
    岗位: row.job_title || row.岗位名称 || '',
    公司: row.company || row.公司 || '',
    城市: row.city || row.城市 || '',
    薪资: row.salary_text || row.薪资 || row.salary_text_candidate || '',
    经验: row.experience || row.经验 || '',
    学历: row.education || row.学历 || '',
    链接: row.source || row.url || row.来源 || '',
  }))
})

function switchMode(mode) {
  activeMode.value = mode
  clearResults()
}

function splitInput(value) {
  return String(value || '')
    .split(/\n|,|，|;|；/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function applyResult(data, okMessage) {
  downloadVersion.value = Date.now()
  analysis.value = data.analysis
  ai.value = data.ai
  adminSteps.value = data.steps || []
  adminLogs.value = data.logs || []
  adminRows.value = data.rows || []
  partialRows.value = data.partial_rows || []
  generatedUrls.value = extractGeneratedUrls(data)
  message.value = okMessage
  nextAdvice.value = buildAdvice(data)
  loadHistory()
}

function buildAdvice(data) {
  if (data?.analysis?.valid > 0) return '可以下载完整报告，或调整岗位、地区、页数后再次分析。'
  const logs = data?.logs || []
  const hasLoginRequired = logs.some((log) => log?.diagnostics?.login_required)
  if (hasLoginRequired) return '系统检测到平台需要登录。请点击登录按钮完成登录，然后重新采集。'
  if (data?.partial_rows?.length) return '已识别到部分岗位信息，但薪资不足。建议补充CSV文件或换用更明确的岗位详情页。'
  return '建议先确认平台已登录，并将页数设为1进行测试；成功后再增加页数。'
}

function clearResults() {
  analysis.value = null
  ai.value = null
  message.value = ''
  nextAdvice.value = ''
  adminSteps.value = []
  adminLogs.value = []
  adminRows.value = []
  partialRows.value = []
  generatedUrls.value = []
  showJobDetails.value = false
}

function toggleAppMode() {
  appMode.value = appMode.value === 'user' ? 'admin' : 'user'
}

async function loadHistory() {
  historyLoading.value = true
  historyError.value = ''
  try {
    const data = await listTaskRuns()
    historyRuns.value = data.runs || []
  } catch (err) {
    historyError.value = err?.response?.data?.detail || err.message || '历史记录读取失败'
  } finally {
    historyLoading.value = false
  }
}

function formatRunTime(value) {
  if (!value) return '时间未知'
  return String(value).replace('T', ' ')
}

function joinValue(value) {
  if (Array.isArray(value)) return value.filter(Boolean).join('、') || '未填写'
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (value === undefined || value === null || value === '') return '未填写'
  return String(value)
}

function historyQueryItems(run) {
  const query = run.query || {}
  return [
    { label: '任务类型', value: joinValue(query.task_type) },
    { label: '平台', value: joinValue(query.platforms) },
    { label: '岗位关键词', value: joinValue(query.job_keywords) },
    { label: '地区', value: joinValue(query.cities) },
    { label: '采集页数', value: joinValue(query.pages) },
    { label: '行业', value: joinValue(query.industry) },
    { label: '经验', value: joinValue(query.experience) },
    { label: '学历', value: joinValue(query.education) },
    { label: '时间范围', value: query.start_date || query.end_date ? `${joinValue(query.start_date)} 至 ${joinValue(query.end_date)}` : '未填写' },
    { label: '目标', value: joinValue(query.goal || run.label) },
  ].filter((item) => item.value !== '未填写' || ['岗位关键词', '地区', '平台', '采集页数'].includes(item.label))
}

function historyFileUrl(run, fileKey) {
  return taskRunDownloadUrl(run.run_dir || '', fileKey)
}

onMounted(() => {
  loadHistory()
})

async function onFileChange(event) {
  const file = event.target.files?.[0]
  if (!file) return
  loading.value = true
  try {
    applyResult(await uploadAnalyze(file, useAi.value), '文件分析完成。')
  } catch (err) {
    message.value = err?.response?.data?.detail || err.message
  } finally {
    loading.value = false
    event.target.value = ''
  }
}

async function runScrape() {
  loading.value = true
  try {
    const data = await scrapePoc(scrapeUrl.value, 30, useAi.value, scrapeMode.value)
    applyResult(data, data.status === 'success' ? 'URL 分析完成。' : 'URL 已处理，但可统计样本不足。')
  } catch (err) {
    message.value = err?.response?.data?.detail || err.message
  } finally {
    loading.value = false
  }
}

async function runAgentTask() {
  loading.value = true
  try {
    const result = await runAgent(buildAgentPayload(true))
    applyResult(result, result.status === 'success' ? '智能体深度分析完成。' : '智能体已完成处理，但样本不足。')
  } catch (err) {
    message.value = err?.response?.data?.detail || err.message
  } finally {
    loading.value = false
  }
}

async function runPlatformCrawler() {
  loading.value = true
  try {
    const result = await crawlAnalyzePlatform(buildAgentPayload(false))
    applyResult(result, result.status === 'success' ? '采集和分析完成。' : '采集未获得可分析数据。')
  } catch (err) {
    message.value = err?.response?.data?.detail || err.message
  } finally {
    loading.value = false
  }
}

function buildAgentPayload(useSample) {
  return {
    goal: agentGoal.value,
    platforms: agentPlatforms.value.length ? agentPlatforms.value : ['boss'],
    cities: splitInput(agentCities.value),
    job_keywords: splitInput(agentKeywords.value),
    industry: agentIndustry.value,
    experience: agentExperience.value,
    education: agentEducation.value,
    start_date: agentStartDate.value,
    end_date: agentEndDate.value,
    limit: 400,
    pages: agentPages.value || 1,
    use_ai: useAi.value,
    use_sample: useSample && agentUseSample.value,
    mode: scrapeMode.value,
  }
}

async function openLogin(platform) {
  loading.value = true
  try {
    const result = await openPlatformLogin(platform)
    message.value = result.opened
      ? `${platform === 'boss' ? 'BOSS' : '智联'} 登录页已打开。登录完成后，请回到本页面继续采集。`
      : result.error || '登录页未能打开。'
    nextAdvice.value = '登录成功后，建议先用1页数据测试采集是否正常。'
  } catch (err) {
    message.value = err?.response?.data?.detail || err.message
  } finally {
    loading.value = false
  }
}

async function runAiReadUrl() {
  loading.value = true
  try {
    const data = await readUrlWithAi(scrapeUrl.value, 30, scrapeMode.value)
    const items = data.ai_reader?.items || []
    message.value = items.length ? `已提取 ${items.length} 条岗位信息。` : '页面已读取，但没有提取到明确岗位信息。'
    nextAdvice.value = items.length ? '如需薪资统计，请使用包含薪资的URL或上传CSV文件。' : '建议换用岗位详情页，或上传CSV文件进行分析。'
    analysis.value = null
    ai.value = { text: data.ai_reader?.summary || data.ai_reader?.limits || '' }
    adminLogs.value = data.logs || []
    adminRows.value = items
    partialRows.value = []
  } catch (err) {
    message.value = err?.response?.data?.detail || err.message
  } finally {
    loading.value = false
  }
}

function extractGeneratedUrls(result) {
  const urls = []
  for (const step of result.steps || []) {
    if (Array.isArray(step.data)) {
      for (const item of step.data) {
        if (item?.url) urls.push(item)
      }
    }
  }
  for (const log of result.logs || []) {
    if (log?.url) {
      urls.push({
        platform: log.platform || log.diagnostics?.platform_query?.platform || '',
        keyword: log.diagnostics?.platform_query?.keyword || '',
        city: log.diagnostics?.platform_query?.city || '',
        url: log.url,
      })
    }
  }
  const seen = new Set()
  return urls.filter((item) => {
    if (!item.url || seen.has(item.url)) return false
    seen.add(item.url)
    return true
  })
}
</script>
