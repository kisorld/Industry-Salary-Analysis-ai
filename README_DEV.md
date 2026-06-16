# 行业薪酬洞察 AI 智能体：前后端拆分版

本版本实现：

- Vue3 + Vite 前端。
- Python FastAPI 后端。
- Qwen2.5-32B-Instruct API + Prompt + Tool Calling。
- pandas 批量清洗、统计和 CSV/Excel 导入。
- 更多薪资格式测试。
- 真实公开页面采集 PoC。

## 目录结构

```text
backend/
  app/
    main.py              FastAPI 接口
    ai_agent.py          Qwen Tool Calling 调用链
    salary_pandas.py     pandas 批量清洗与统计
    scraper.py           公开页面采集 PoC
    reporting.py         Word 报告生成
  tests/                 薪资解析测试
  requirements.txt       后端依赖
frontend/
  src/
    App.vue              Vue3 主页面
    services/api.js      后端接口封装
    components/          图表与表格组件
```

## 后端启动

```powershell
cd backend
pip install -r requirements.txt
copy .env.example .env
```

编辑 `.env`：

```text
QWEN_API_KEY=你的百炼或DashScope API Key
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen2.5-32b-instruct
BROWSER_HEADLESS=true
PLATFORM_SCRAPE_HEADLESS=true
AUTO_OPEN_LOGIN_PAGE=true
```

如果 BOSS/智联采集日志出现 `no_response`，可以临时改成可见浏览器调试：

```text
BROWSER_HEADLESS=false
```

改完 `.env` 后必须重启后端。可见模式下 DrissionPage 会打开浏览器窗口，方便判断页面实际进入的是岗位列表、登录页、验证码页、空页面还是平台限制页。

BOSS/智联专项采集默认使用后台浏览器：

```text
PLATFORM_SCRAPE_HEADLESS=true
AUTO_OPEN_LOGIN_PAGE=true
```

如果系统检测到未登录、登录页或验证页，会自动打开对应网站的可见登录界面，并返回 `login_required`。你在打开的浏览器里完成登录后，重新点击“脚本爬取并分析”即可。登录状态会保存在 `backend/.browser_profile`，后续已登录时采集和分析不会主动打开浏览器窗口。

启动：

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

接口文档：

```text
http://127.0.0.1:8000/docs
```

## 前端启动

```powershell
cd frontend
npm install
npm run dev
```

浏览器打开：

```text
http://127.0.0.1:5173
```

## Qwen Tool Calling 说明

后端 `app/ai_agent.py` 定义了两个工具：

- `analyze_salary`：返回系统已计算好的薪资统计结果。
- `generate_docx_report`：生成报告摘要数据。

模型不能直接编造数值，只能引用工具或程序统计结果。若没有配置 `QWEN_API_KEY` 或网络失败，系统会自动切换为 `local_fallback` 本地模板报告，保证演示不中断。

## 公开页面采集 PoC

接口：

```text
POST /api/scrape/poc
```

限制：

- 只抓取公开可访问页面。
- 不绕过登录、验证码、付费墙或访问限制。
- PoC 使用 HTML 文本和正则识别薪资表达，适合展示能力雏形，不等同于稳定生产采集器。

本轮增强后支持：

- 自动补全和校验 URL，例如 `example.com/jobs` 会转为 `https://example.com/jobs`。
- 多 URL 输入，每行一个或用逗号、分号分隔。
- JSON-LD、`article`/`li` 列表块、职位卡片 class/id 识别。
- 采集日志返回访问状态、页面大小、文本节点数、候选职位块数、命中岗位数。
- 失败时返回原因，不直接中断前端展示。
- 动态采集模式：安装 Playwright 后可选择 `auto` 或 `dynamic`，系统会使用 Chromium 渲染公开页面，再抽取岗位薪资。
- 静态采集模式：使用 urllib + BeautifulSoup/lxml 解析 HTML，适合静态公开页面。

## RAG 功能

知识库文件：

```text
docs/rag_knowledge_base.md
```

接口：

```text
GET /api/rag/search?q=薪资口径
```

AI 报告生成时会自动检索知识库，将薪资口径、样本量解释、数据合规、岗位归一和报告建议注入 Prompt。若 Qwen API 不可用，本地 fallback 报告也会显示命中的知识片段。

本轮升级后，RAG 优先使用 ChromaDB + sentence-transformers 向量检索；如果依赖或模型不可用，会自动回退到关键词检索。

初始化或重建向量索引：

```text
POST /api/rag/rebuild
```

默认 embedding 模型：

```text
BAAI/bge-small-zh-v1.5
```

可通过环境变量 `RAG_EMBED_MODEL` 修改。

## 一键启动

项目根目录提供：

```text
start_all.bat
```

运行后会检查 `backend\.venv` 和 `frontend\node_modules`，然后分别启动：

- 后端：`http://127.0.0.1:8000`
- 前端：`http://127.0.0.1:5173`

如果缺少软件，需要安装：

- Python 3.11，建议使用虚拟环境。
- Node.js LTS，用于 Vue3/Vite 前端。
- Playwright Chromium：执行 `python -m playwright install chromium`。

完整后端增强依赖：

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
```

## 输出文件管理

系统仍保留当前结果文件，供前端下载按钮使用：

```text
outputs/agent_cleaned_jobs.csv
outputs/platform_cleaned_preview.csv
reports/agent_salary_insight_report.docx
reports/platform_salary_report.docx
```

智能体任务和平台爬取分析会同时归档到最近任务目录：

```text
outputs/task_runs/YYYYMMDD_HHMMSS_任务名/
  rows_preview.csv
  partial_rows.csv
  cleaned_jobs.csv
  analysis.json
  ai_output.json
  scrape_logs.json
  agent_steps.json
  report.docx
  metadata.json
```

系统只保留最近 10 次任务输出，超过 10 个任务文件夹后会自动删除最旧的任务目录。可通过接口查看最近任务：

```text
http://127.0.0.1:8000/api/task-runs
```

## 测试

```powershell
cd backend
python tests/run_tests.py
python run_pipeline.py
```

`run_pipeline.py` 会读取样例数据，执行 pandas 清洗统计、AI 报告生成和 Word 导出
