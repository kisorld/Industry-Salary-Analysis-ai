# 行业薪酬洞察 AI 智能体

本项目是一个面向招聘岗位数据的薪酬分析系统。系统支持从 BOSS 直聘、智联招聘采集公开岗位数据，也支持通过 URL、CSV、Excel 文件导入数据；后端完成字段清洗、薪资标准化、统计分析、AI 总结和 Word 报告生成；前端提供用户模式和管理员模式，便于演示、测试和查看任务过程。

## 核心功能

- 平台采集分析：按平台、岗位关键词、地区、页数采集招聘岗位数据。
- URL / 文件分析：支持公开招聘 URL、CSV、Excel 文件分析。
- 数据清洗：结构化岗位名称、公司、城市、薪资、经验、学历、来源链接等字段。
- 薪资统计：计算均值、中位数、P25、P75、P90、年薪区间等指标。
- 可视化展示：展示岗位类别、城市、需求变化等图表。
- AI 分析：调用千问大模型生成薪酬洞察、风险提示和企业建议。
- RAG 增强：支持本地知识库检索，为 AI 分析补充规则和项目背景。
- 报告导出：生成 Word 格式分析报告。
- 历史记录：保留最近 10 次任务输出，可下载清洗数据、报告、岗位预览、统计结果和采集日志。

## 技术栈

- 前端：Vue 3、Vite、Axios、ECharts
- 后端：Python、FastAPI、Uvicorn、Pandas
- 数据处理：Pandas、NumPy、OpenPyXL
- 报告生成：python-docx
- 网页采集：DrissionPage、Playwright、Scrapling
- AI 调用：DashScope 兼容 OpenAI 接口的 Qwen 模型
- RAG：sentence-transformers、ChromaDB、本地 Markdown 知识库

## 目录结构

```text
行业薪酬洞察AI智能体/
├─ backend/                 后端 FastAPI 服务
│  ├─ app/                  后端核心代码
│  ├─ requirements.txt      Python 依赖
│  └─ .env                  后端环境变量配置
├─ frontend/                Vue3 前端
│  ├─ src/                  前端源码
│  └─ package.json          前端依赖和脚本
├─ data/                    样例数据
├─ docs/                    RAG 知识库文档
├─ outputs/                 清洗数据、采集结果、历史任务输出
├─ reports/                 Word 报告输出
├─ install_all.bat          一键安装依赖
├─ start_all.bat            一键启动前后端
└─ README.md                项目说明文档
```

## 环境要求

建议使用：

- Windows 10 / 11
- Python 3.11
- Node.js LTS
- Chrome 或 Edge 浏览器

不建议使用 Python 3.14。部分依赖如 Pandas、Playwright、DrissionPage 在 Python 3.14 上可能安装或运行不稳定。

## 安装依赖

推荐在项目根目录直接执行：

```powershell
.\install_all.bat
```

该脚本会自动完成：

- 检查 Python 3.11
- 创建或复用 `backend/.venv`
- 安装后端 Python 依赖
- 安装 Playwright Chromium 浏览器内核
- 安装前端 Node 依赖

如果你希望手动安装，可以按下面步骤执行。

### 1. 后端依赖

进入后端目录：

```powershell
cd backend
```

创建虚拟环境：

```powershell
py -3.11 -m venv .venv
```

安装依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

如果使用 Playwright，需要安装浏览器内核：

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
```

### 2. 前端依赖

进入前端目录：

```powershell
cd frontend
```

安装依赖：

```powershell
npm install
```

## 配置大模型 API

在 `backend/.env` 中配置：

```env
QWEN_API_KEY=你的千问或DashScope API Key
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen2.5-32b-instruct
```

如果你使用其他兼容 OpenAI Chat Completions 的模型服务，可以修改：

- `QWEN_BASE_URL`：模型服务地址
- `QWEN_MODEL`：模型名称
- `QWEN_API_KEY`：对应平台的 API Key

无 API Key 时，系统仍可进行采集、清洗、统计和图表展示，但 AI 总结会受限。

## RAG 配置

RAG 知识库文件位于：

```text
docs/rag_knowledge_base.md
```

如果已下载本地向量模型，可在 `backend/.env` 中配置：

```env
RAG_EMBED_MODEL=paraphrase-multilingual-MiniLM-L12-v2
RAG_LOCAL_FILES_ONLY=1
```

重建向量索引：

```powershell
cd backend
.\.venv\Scripts\python.exe check_enhanced_deps.py
```

## 启动项目

推荐在项目根目录执行：

```powershell
.\start_all.bat
```

脚本会自动启动：

- 后端：http://127.0.0.1:8000
- 前端：http://127.0.0.1:5173

如果启动后页面没有变化，请在浏览器中按 `Ctrl + F5` 强制刷新。

## 手动启动

后端：

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

前端：

```powershell
cd frontend
npm run dev
```

## 使用流程

### 平台采集分析

1. 打开前端页面。
2. 点击“登录 BOSS”或“登录智联”。
3. 每次打开系统页面后，每个平台通常只需登录一次。
4. 输入采集条件：
   - 岗位关键词：如 `算法工程师`、`C++`、`数据分析师`
   - 采集地区：如 `广州`、`深圳`、`北京`
   - 采集页数：建议先填 `1` 测试，稳定后再增加
5. 点击“采集并分析”。
6. 查看系统反馈、图表、岗位具体信息和 AI 分析结果。
7. 可下载清洗数据和分析报告。

### URL / 文件分析

1. 切换到“URL / 文件分析”。
2. 输入公开招聘 URL，或上传 CSV / Excel 文件。
3. 点击“分析 URL”或“上传文件并分析”。
4. 查看统计结果、图表和输出文件。

### 历史记录

历史记录默认折叠。展开后可以查看最近 10 次任务：

- 任务类型
- 平台
- 岗位关键词
- 地区
- 采集页数
- 行业、经验、学历、时间范围
- 下载清洗数据、报告、岗位预览、统计结果、采集日志

历史文件保存在：

```text
outputs/task_runs/
```

## 输出文件说明

常用输出位置：

```text
outputs/latest_cleaned_jobs.csv       最近一次真实清洗数据
outputs/platform_cleaned_jobs.csv     平台采集后的清洗数据
outputs/agent_cleaned_jobs.csv        智能体分析后的清洗数据
outputs/task_runs/                    最近 10 次任务归档
reports/platform_salary_report.docx   平台采集分析报告
reports/agent_salary_insight_report.docx 智能体分析报告
```

说明：系统不会无限保留历史任务，默认只保留最近 10 次任务输出。

## 注意事项

- 本系统只处理用户可访问的公开页面或用户自行导入的数据。
- 系统不会绕过登录、验证码、付费墙或平台风控。
- 若平台提示登录，请先点击页面中的登录按钮完成登录，再重新采集。
- 招聘网站页面结构和接口可能变化，采集结果可能受网络、登录状态、平台限制影响。
- 如果平台采集不稳定，建议使用 CSV / Excel 导入作为补充数据来源。

## 常见问题

### 1. 执行 `start_all.bat` 后页面没变化

先确认前端地址是否为：

```text
http://127.0.0.1:5173
```

然后按 `Ctrl + F5` 强制刷新。

### 2. 下载清洗数据还是旧文件

重新执行：

```powershell
.\start_all.bat
```

然后刷新页面。当前下载接口使用 `outputs/latest_cleaned_jobs.csv`，只对应最近一次真实分析结果。

### 3. 报错 `No module named uvicorn`

说明后端依赖没有安装到当前虚拟环境。执行：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 4. 报错无法激活虚拟环境

可以不执行 `activate`，直接使用：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

### 5. AI 调用超时或模型不存在

检查 `backend/.env`：

```env
QWEN_API_KEY=是否填写正确
QWEN_BASE_URL=是否为正确服务地址
QWEN_MODEL=是否为账号可用模型
```

如果模型名写错或账号无权限，接口会返回 `model_not_found`。

## 开发检查

前端构建：

```powershell
cd frontend
npm run build
```

后端接口文档：

```text
http://127.0.0.1:8000/docs
```

## 项目定位

本项目适合作为“行业薪酬分析智能体”课程设计或实训项目，重点展示：

- 招聘岗位数据采集
- 薪资字段结构化处理
- Pandas 批量统计分析
- AI 报告生成
- RAG 增强分析
- Vue3 + FastAPI 前后端分离
- 历史任务归档和报告导出
