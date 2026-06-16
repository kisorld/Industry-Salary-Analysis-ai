from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .ai_agent import generate_ai_report
from .agent import run_salary_agent
from .browser_runtime import ensure_browser_event_loop_policy
from .config import (
    DEFAULT_SAMPLE,
    OUTPUT_DIR,
    AUTO_OPEN_LOGIN_PAGE,
    PLATFORM_SCRAPE_HEADLESS,
    QWEN_API_KEY,
    QWEN_BASE_URL,
    QWEN_MODEL,
    REPORT_DIR,
    BROWSER_HEADLESS,
    ensure_dirs,
)
from .models import AgentRequest, ReportRequest, ScrapeRequest
from .platform_scrapers import PlatformQuery, open_platform_login_page, scrape_platform_to_csv
from .reporting import build_report
from .rag import rag_status, rebuild_vector_index, retrieve
from .run_outputs import archive_task_run, find_task_file, list_task_runs
from .salary_pandas import analyze_dataframe, analyze_file, clean_dataframe
from .scraper import scrape_many_public_jobs
from .url_reader import ai_read_job_url
from .url_tools import resolve_url_inputs


ensure_browser_event_loop_policy()
ensure_dirs()

app = FastAPI(title="行业薪酬洞察 AI 智能体 API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

LAST_ANALYSIS: dict[str, object] | None = None
LAST_AI: dict[str, object] | None = None
LAST_REPORT_PATH: Path | None = None
LAST_CLEANED_PATH: Path | None = None
LATEST_CLEANED_PATH = OUTPUT_DIR / "latest_cleaned_jobs.csv"


def publish_latest_cleaned(path: Path) -> Path:
    if not path.exists():
        return path
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if path.resolve() != LATEST_CLEANED_PATH.resolve():
        shutil.copy2(path, LATEST_CLEANED_PATH)
    return LATEST_CLEANED_PATH


@app.get("/api/health")
def health() -> dict[str, object]:
    return {"ok": True, "sample_exists": DEFAULT_SAMPLE.exists()}


@app.get("/api/config")
def config_status() -> dict[str, object]:
    return {
        "qwen_key_loaded": bool(QWEN_API_KEY),
        "qwen_key_prefix": QWEN_API_KEY[:6] + "***" if QWEN_API_KEY else "",
        "qwen_base_url": QWEN_BASE_URL,
        "qwen_model": QWEN_MODEL,
        "browser_headless": BROWSER_HEADLESS,
        "platform_scrape_headless": PLATFORM_SCRAPE_HEADLESS,
        "auto_open_login_page": AUTO_OPEN_LOGIN_PAGE,
    }


@app.get("/api/task-runs")
def task_runs() -> dict[str, object]:
    return {"runs": list_task_runs(), "limit": 10}


@app.get("/api/task-runs/download")
def download_task_file(run_dir: str, file_key: str) -> FileResponse:
    path = find_task_file(run_dir, file_key)
    if path is None:
        raise HTTPException(status_code=404, detail="历史文件不存在或不允许下载")
    return FileResponse(
        path,
        filename=path.name,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@app.get("/api/platform/open-login")
def platform_open_login(platform: str = "boss") -> dict[str, object]:
    normalized = platform.lower().strip()
    if normalized in {"boos", "boss直聘", "zhipin"}:
        normalized = "boss"
    if normalized in {"zhilian", "智联", "智联招聘"}:
        normalized = "zhaopin"
    if normalized not in {"boss", "zhaopin"}:
        raise HTTPException(status_code=422, detail="platform 只能是 boss 或 zhaopin")
    return open_platform_login_page(normalized)


@app.get("/api/sample/analyze")
def analyze_sample(use_ai: bool = True) -> dict[str, object]:
    global LAST_ANALYSIS, LAST_AI
    if not DEFAULT_SAMPLE.exists():
        raise HTTPException(status_code=404, detail="baseline sample csv not found")
    cleaned, analysis = analyze_file(DEFAULT_SAMPLE)
    cleaned_path = OUTPUT_DIR / "sample_cleaned_jobs.csv"
    cleaned.to_csv(cleaned_path, index=False, encoding="utf-8-sig")
    LAST_ANALYSIS = analysis
    LAST_AI = generate_ai_report(analysis) if use_ai else {"mode": "disabled", "text": ""}
    return {"analysis": analysis, "ai": LAST_AI}


@app.post("/api/upload/analyze")
def upload_analyze(file: UploadFile = File(...), use_ai: bool = True) -> dict[str, object]:
    global LAST_ANALYSIS, LAST_AI, LAST_CLEANED_PATH
    suffix = Path(file.filename or "upload.csv").suffix or ".csv"
    target = OUTPUT_DIR / f"upload{suffix}"
    with target.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    cleaned, analysis = analyze_file(target)
    cleaned_path = OUTPUT_DIR / "cleaned_jobs.csv"
    cleaned.to_csv(cleaned_path, index=False, encoding="utf-8-sig")
    LAST_CLEANED_PATH = publish_latest_cleaned(cleaned_path)
    LAST_ANALYSIS = analysis
    LAST_AI = generate_ai_report(analysis) if use_ai else {"mode": "disabled", "text": ""}
    return {"analysis": analysis, "ai": LAST_AI}


@app.post("/api/scrape/poc")
def scrape_poc(payload: ScrapeRequest) -> dict[str, object]:
    global LAST_ANALYSIS, LAST_AI, LAST_CLEANED_PATH
    try:
        urls = resolve_url_inputs(payload.url, payload.urls)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not urls:
        raise HTTPException(status_code=422, detail="请输入至少一个公开网页 URL")
    scrape_result = scrape_many_public_jobs(urls, payload.limit, payload.mode)
    rows = scrape_result["rows"]
    partial_rows = scrape_result.get("partial_rows", [])
    if not rows:
        status = "partial" if partial_rows else "failed"
        return {
            "status": status,
            "rows": [],
            "partial_rows": partial_rows,
            "logs": scrape_result["logs"],
            "analysis": None,
            "ai": {"mode": "disabled", "text": "", "error": "识别到岗位信息但缺少薪资，未进入薪资统计" if partial_rows else ""},
        }
    df = pd.DataFrame(rows)
    analysis = analyze_dataframe(df)
    cleaned_path = OUTPUT_DIR / "scraped_poc_jobs.csv"
    df.to_csv(cleaned_path, index=False, encoding="utf-8-sig")
    LAST_CLEANED_PATH = publish_latest_cleaned(cleaned_path)
    LAST_ANALYSIS = analysis
    LAST_AI = generate_ai_report(analysis) if payload.use_ai else {"mode": "disabled", "text": ""}
    return {
        "status": "success",
        "rows": rows,
        "partial_rows": partial_rows,
        "logs": scrape_result["logs"],
        "analysis": analysis,
        "ai": LAST_AI,
    }


@app.post("/api/url/read")
def read_url_with_ai(payload: ScrapeRequest) -> dict[str, object]:
    try:
        urls = resolve_url_inputs(payload.url, payload.urls)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not urls:
        raise HTTPException(status_code=422, detail="请输入至少一个公开网页 URL")
    scrape_result = scrape_many_public_jobs([urls[0]], payload.limit, payload.mode)
    ai_reader = ai_read_job_url(urls[0], scrape_result["logs"], payload.mode)
    return {"url": urls[0], "logs": scrape_result["logs"], "ai_reader": ai_reader}


@app.post("/api/agent/run")
def agent_run(payload: AgentRequest) -> dict[str, object]:
    global LAST_ANALYSIS, LAST_AI, LAST_REPORT_PATH, LAST_CLEANED_PATH
    result = run_salary_agent(payload)
    if result.get("analysis"):
        LAST_ANALYSIS = result["analysis"]
    if result.get("ai"):
        LAST_AI = result["ai"]
    if result.get("report_path"):
        LAST_REPORT_PATH = Path(str(result["report_path"]))
    if result.get("cleaned_path"):
        LAST_CLEANED_PATH = publish_latest_cleaned(Path(str(result["cleaned_path"])))
    return result


@app.post("/api/platform/crawl-analyze")
def platform_crawl_analyze(payload: AgentRequest) -> dict[str, object]:
    global LAST_ANALYSIS, LAST_AI, LAST_REPORT_PATH, LAST_CLEANED_PATH
    platforms = payload.platforms or ["boss"]
    keywords = payload.job_keywords or [payload.goal or "数据分析"]
    cities = payload.cities or [""]
    rows: list[dict[str, object]] = []
    logs: list[dict[str, object]] = []
    csv_paths: list[str] = []
    for platform in platforms:
        for keyword in keywords:
            for city in cities:
                result = scrape_platform_to_csv(
                    PlatformQuery(
                        platform=platform,
                        keyword=keyword,
                        city=city,
                        limit=max(payload.limit, 400),
                        pages=payload.pages,
                    ),
                    OUTPUT_DIR,
                )
                rows.extend(result.get("rows", []))
                csv_paths.append(result.get("csv_path", ""))
                logs.append({k: v for k, v in result.items() if k != "rows"})
    if not rows:
        diagnosis = []
        for log in logs:
            diagnostics = log.get("diagnostics") if isinstance(log, dict) else {}
            if isinstance(diagnostics, dict) and diagnostics.get("diagnosis"):
                diagnosis.append(str(diagnostics.get("diagnosis")))
        return {
            "status": "failed",
            "rows": [],
            "logs": logs,
            "csv_paths": csv_paths,
            "analysis": None,
            "ai": {
                "mode": "disabled",
                "text": "",
                "error": "未采集到公开岗位数据。" + ("；".join(diagnosis) if diagnosis else "请确认岗位关键词、城市和平台公开访问状态。"),
            },
        }
    df = pd.DataFrame(rows)
    analysis = analyze_dataframe(df)
    LAST_ANALYSIS = analysis
    LAST_AI = generate_ai_report(analysis, payload.goal) if payload.use_ai else {"mode": "disabled", "text": ""}
    path = build_report(analysis, REPORT_DIR / "platform_salary_report.docx", LAST_AI.get("text", ""), "平台岗位薪酬分析报告")
    LAST_REPORT_PATH = path
    cleaned = clean_dataframe(df)
    cleaned_path = OUTPUT_DIR / "platform_cleaned_jobs.csv"
    cleaned.to_csv(cleaned_path, index=False, encoding="utf-8-sig")
    LAST_CLEANED_PATH = publish_latest_cleaned(cleaned_path)
    archive = archive_task_run(
        payload.goal or "platform_crawl",
        query={
            "task_type": "平台采集分析",
            "goal": payload.goal,
            "platforms": platforms,
            "job_keywords": keywords,
            "cities": cities,
            "industry": payload.industry,
            "experience": payload.experience,
            "education": payload.education,
            "start_date": payload.start_date,
            "end_date": payload.end_date,
            "pages": payload.pages,
            "limit": payload.limit,
            "use_ai": payload.use_ai,
            "use_sample": payload.use_sample,
        },
        rows=rows[:100],
        analysis=analysis,
        ai=LAST_AI,
        logs=logs,
        report_path=path,
        cleaned_path=cleaned_path,
        source_csv_paths=csv_paths,
    )
    return {"status": "success", "rows": rows[:100], "logs": logs, "csv_paths": csv_paths, "analysis": analysis, "ai": LAST_AI, "report_path": str(path), "task_archive": archive}


@app.get("/api/rag/search")
def rag_search(q: str, top_k: int = 3) -> dict[str, object]:
    return {"query": q, "chunks": retrieve(q, top_k), "status": rag_status()}


@app.post("/api/rag/rebuild")
def rag_rebuild() -> dict[str, object]:
    return rebuild_vector_index()


@app.post("/api/report")
def report(payload: ReportRequest) -> dict[str, object]:
    global LAST_AI
    if LAST_ANALYSIS is None:
        analyze_sample(use_ai=payload.use_ai)
    ai = generate_ai_report(LAST_ANALYSIS or {}, payload.title) if payload.use_ai else {"text": ""}
    LAST_AI = ai
    path = build_report(LAST_ANALYSIS or {}, REPORT_DIR / "salary_insight_report.docx", ai.get("text", ""), payload.title)
    return {"path": str(path), "ai": ai}


@app.get("/api/download/report")
def download_report() -> FileResponse:
    path = LAST_REPORT_PATH or REPORT_DIR / "salary_insight_report.docx"
    if not path.exists():
        build_report(LAST_ANALYSIS or analyze_sample()["analysis"], path, (LAST_AI or {}).get("text", ""))
    return FileResponse(path, filename="salary_insight_report.docx")


@app.get("/api/download/cleaned")
def download_cleaned() -> FileResponse:
    candidates = [LATEST_CLEANED_PATH]
    if LAST_CLEANED_PATH is not None:
        candidates.append(LAST_CLEANED_PATH)
    for path in candidates:
        if path.exists():
            return FileResponse(
                path,
                filename="latest_cleaned_jobs.csv",
                headers={
                    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                    "Pragma": "no-cache",
                },
            )
    raise HTTPException(status_code=404, detail="暂无可下载清洗数据，请先完成一次采集或分析任务")
