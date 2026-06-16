from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .ai_agent import generate_ai_report
from .config import DEFAULT_SAMPLE, OUTPUT_DIR, REPORT_DIR
from .models import AgentRequest
from .platform_scrapers import PlatformQuery, scrape_many_platform_jobs, scrape_platform_to_csv
from .reporting import build_report
from .run_outputs import archive_task_run
from .salary_pandas import analyze_dataframe, clean_dataframe, load_dataframe
from .scraper import scrape_many_public_jobs
from .url_reader import ai_read_job_url
from .url_tools import resolve_url_inputs


def add_step(steps: list[dict[str, Any]], name: str, status: str, detail: str, data: Any | None = None) -> None:
    item: dict[str, Any] = {"name": name, "status": status, "detail": detail}
    if data is not None:
        item["data"] = data
    steps.append(item)


def split_goal_terms(goal: str) -> list[str]:
    terms: list[str] = []
    for token in ["数据分析", "后端", "前端", "产品经理", "AI", "人工智能", "算法", "Java", "Python", "Vue", "React"]:
        if token.lower() in goal.lower():
            terms.append(token)
    return terms


def filter_dataframe(df: pd.DataFrame, payload: AgentRequest) -> pd.DataFrame:
    result = df.copy()
    keywords = payload.job_keywords or split_goal_terms(payload.goal)
    if keywords:
        pattern = "|".join(map(lambda x: str(x).strip(), keywords))
        result = result[result["job_title"].astype(str).str.contains(pattern, case=False, na=False) | result["job_category"].astype(str).str.contains(pattern, case=False, na=False)]
    if payload.cities:
        result = result[result["city"].astype(str).isin(payload.cities)]
    if payload.experience:
        result = result[result["experience"].astype(str).str.contains(payload.experience, case=False, na=False)]
    if payload.education:
        result = result[result["education"].astype(str).str.contains(payload.education, case=False, na=False)]
    if payload.start_date or payload.end_date:
        dates = pd.to_datetime(result["publish_date"], errors="coerce")
        if payload.start_date:
            result = result[dates >= pd.to_datetime(payload.start_date, errors="coerce")]
            dates = pd.to_datetime(result["publish_date"], errors="coerce")
        if payload.end_date:
            result = result[dates <= pd.to_datetime(payload.end_date, errors="coerce")]
    return result


def demand_trends(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df.empty or "publish_date" not in df.columns:
        return []
    parsed = pd.to_datetime(df["publish_date"], errors="coerce")
    work = df.copy()
    work["month"] = parsed.dt.strftime("%Y-%m")
    work = work[work["month"].notna() & work["month"].ne("NaT")]
    if work.empty:
        return []
    grouped = work.groupby(["month", "job_category"], dropna=False).size().reset_index(name="需求数量")
    grouped = grouped.rename(columns={"month": "月份", "job_category": "岗位类别"})
    return grouped.sort_values(["月份", "岗位类别"]).to_dict(orient="records")


def rows_from_ai_reader(ai_reader: dict[str, Any], source: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in ai_reader.get("items") or []:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "job_title": item.get("job_title", ""),
                "job_category": "",
                "company": item.get("company", ""),
                "city": item.get("city", ""),
                "salary_text": item.get("salary_text", ""),
                "experience": item.get("experience", ""),
                "education": item.get("education", ""),
                "publish_date": item.get("publish_date", ""),
                "source": source,
            }
        )
    return rows


def build_agent_reflection(
    rows: list[dict[str, Any]],
    partial_rows: list[dict[str, Any]],
    logs: list[dict[str, Any]],
    payload: AgentRequest,
) -> dict[str, Any]:
    total = len(rows) + len(partial_rows)
    salary_rows = len([row for row in rows if row.get("salary_text")])
    no_response = 0
    failed_platforms: list[str] = []
    advice: list[str] = []
    for log in logs:
        diagnostics = log.get("diagnostics") if isinstance(log, dict) else None
        if not isinstance(diagnostics, dict):
            continue
        no_response += int(diagnostics.get("no_response_pages") or 0)
        if log.get("status") == "failed" or diagnostics.get("no_response_pages"):
            platform = str(log.get("platform") or diagnostics.get("platform") or "")
            if platform:
                failed_platforms.append(platform)
    if total == 0:
        level = "failed"
        decision = "未获得可分析数据，建议改用CSV/Excel导入或更换公开URL。"
    elif salary_rows == 0:
        level = "partial"
        decision = "仅获得无薪资岗位信息，保留岗位核心信息，但不生成强薪资结论。"
    elif salary_rows < max(5, min(payload.limit, 10)):
        level = "warning"
        decision = "有效薪资样本偏少，AI结论需要降低置信度，并提示样本量风险。"
    else:
        level = "ok"
        decision = "有效薪资样本达到基础分析要求，可继续统计和生成报告。"
    if no_response:
        advice.append("平台接口存在无响应页，建议缩小页数、补充城市/岗位关键词，或换用CSV/Excel导入。")
    if partial_rows and salary_rows:
        advice.append("存在无薪资岗位，系统已保留为partial_rows，不纳入薪资分位值统计。")
    if payload.use_sample and salary_rows < 10:
        advice.append("已启用样例/本地数据作为兜底，避免平台采集失败导致分析链路中断。")
    if not advice:
        advice.append("继续使用当前数据进入结构化分析。")
    return {
        "level": level,
        "total_rows": total,
        "salary_rows": salary_rows,
        "partial_rows": len(partial_rows),
        "no_response_pages": no_response,
        "failed_platforms": sorted(set(failed_platforms)),
        "decision": decision,
        "advice": advice,
    }


def run_salary_agent(payload: AgentRequest) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    logs: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    partial_rows: list[dict[str, Any]] = []
    ai_readers: list[dict[str, Any]] = []
    generated_csvs: list[str] = []

    add_step(steps, "任务理解", "completed", f"目标：{payload.goal}")

    keywords = payload.job_keywords or split_goal_terms(payload.goal)
    if payload.platforms:
        platform_rows: list[dict[str, Any]] = []
        platform_logs: list[dict[str, Any]] = []
        query_urls: list[dict[str, Any]] = []
        for platform in payload.platforms:
            for keyword in (keywords or [""]):
                for city in (payload.cities or [""]):
                    result = scrape_platform_to_csv(
                        PlatformQuery(platform=platform, keyword=keyword, city=city, limit=max(payload.limit, 400), pages=payload.pages),
                        OUTPUT_DIR,
                    )
                    platform_rows.extend(result.get("rows", []))
                    generated_csvs.append(result.get("csv_path", ""))
                    platform_logs.append({k: v for k, v in result.items() if k != "rows"})
                    query_urls.append({"platform": platform, "keyword": keyword, "city": city, "url": result.get("url", "")})
        logs.extend(platform_logs)
        all_rows.extend([row for row in platform_rows if row.get("salary_text")])
        partial_rows.extend([row for row in platform_rows if not row.get("salary_text")])
        add_step(
            steps,
            "BOSS/智联平台专项采集",
            "completed" if platform_rows else "warning",
            f"生成 {len(query_urls)} 个公开搜索URL，按脚本监听接口爬取前 {payload.pages} 页，得到 {len(platform_rows)} 条岗位记录，CSV文件 {len(generated_csvs)} 个。",
            query_urls,
        )
    else:
        add_step(steps, "BOSS/智联平台专项采集", "skipped", "未选择平台，跳过平台专项采集。")

    urls = resolve_url_inputs(payload.url, payload.urls)
    if urls:
        scrape_result = scrape_many_public_jobs(urls, payload.limit, payload.mode)
        logs.extend(scrape_result.get("logs", []))
        all_rows.extend(scrape_result.get("rows", []))
        partial_rows.extend(scrape_result.get("partial_rows", []))
        add_step(steps, "平台公开URL采集", "completed", f"规则采集得到 {len(scrape_result.get('rows', []))} 条含薪资岗位，{len(scrape_result.get('partial_rows', []))} 条缺薪资岗位。")
        if len(all_rows) < max(1, min(payload.limit, 10)):
            for url in urls[:3]:
                reader = ai_read_job_url(url, logs, payload.mode)
                ai_readers.append({"url": url, "result": reader})
                reader_rows = rows_from_ai_reader(reader, url)
                all_rows.extend([row for row in reader_rows if row.get("salary_text")])
                partial_rows.extend([row for row in reader_rows if not row.get("salary_text")])
            add_step(steps, "AI阅读URL补充", "completed", f"AI阅读补充 {sum(len((x.get('result') or {}).get('items') or []) for x in ai_readers)} 条岗位核心信息。")
    else:
        add_step(steps, "平台公开URL采集", "skipped", "未输入公开URL，跳过平台抓取。")

    if payload.use_sample and DEFAULT_SAMPLE.exists():
        sample_df = load_dataframe(DEFAULT_SAMPLE)
        all_rows.extend(sample_df.to_dict(orient="records"))
        add_step(steps, "CSV/Excel导入", "completed", f"导入样例/本地数据 {len(sample_df)} 条。")
    else:
        add_step(steps, "CSV/Excel导入", "skipped", "未启用样例数据或样例文件不存在。")

    if not all_rows and not partial_rows:
        add_step(steps, "数据汇总", "failed", "未获得任何岗位数据。")
        return {"status": "failed", "steps": steps, "logs": logs, "rows": [], "partial_rows": [], "analysis": None, "ai": {"mode": "disabled", "text": ""}, "ai_readers": ai_readers}

    reflection = build_agent_reflection(all_rows, partial_rows, logs, payload)
    add_step(
        steps,
        "反思与补救决策",
        "completed" if reflection["level"] in {"ok", "warning"} else reflection["level"],
        f"{reflection['decision']} 建议：{'；'.join(reflection['advice'])}",
        reflection,
    )

    raw_df = pd.DataFrame(all_rows or partial_rows)
    filtered = filter_dataframe(raw_df, payload)
    if filtered.empty and not raw_df.empty:
        add_step(steps, "条件筛选", "warning", "筛选条件过窄，已回退使用全部可用数据。")
        filtered = raw_df
    else:
        add_step(steps, "条件筛选", "completed", f"按行业/地区/岗位/经验/学历/时间条件筛选后保留 {len(filtered)} 条。")

    cleaned = clean_dataframe(filtered)
    analysis = analyze_dataframe(cleaned)
    trends = demand_trends(cleaned)
    analysis["demand_trends"] = trends
    analysis["agent_reflection"] = reflection
    add_step(steps, "结构化与标准化", "completed", "已标准化岗位名称、薪资区间、经验、学历、地区、发布时间、公司等字段。")
    add_step(steps, "薪资统计", "completed", f"有效薪资样本 {analysis.get('valid', 0)} 条，已计算均值、中位数、P25/P75/P90。")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cleaned_path = OUTPUT_DIR / "agent_cleaned_jobs.csv"
    cleaned.to_csv(cleaned_path, index=False, encoding="utf-8-sig")

    ai = generate_ai_report(analysis, payload.goal) if payload.use_ai else {"mode": "disabled", "text": ""}
    add_step(steps, "RAG与AI建议", "completed" if payload.use_ai else "skipped", "已生成企业薪酬建议和风险提示。" if payload.use_ai else "未启用AI建议。")

    report_path = REPORT_DIR / "agent_salary_insight_report.docx"
    build_report(analysis, report_path, ai.get("text", ""), "行业薪酬洞察AI智能体报告")
    add_step(steps, "报告生成", "completed", f"已生成Word报告：{report_path}")
    task_archive = archive_task_run(
        payload.goal or "agent_task",
        query={
            "task_type": "智能体深度分析",
            "goal": payload.goal,
            "platforms": payload.platforms,
            "job_keywords": keywords,
            "cities": payload.cities,
            "urls": urls,
            "industry": payload.industry,
            "experience": payload.experience,
            "education": payload.education,
            "start_date": payload.start_date,
            "end_date": payload.end_date,
            "pages": payload.pages,
            "limit": payload.limit,
            "use_ai": payload.use_ai,
            "use_sample": payload.use_sample,
            "mode": payload.mode,
        },
        rows=cleaned.head(100).where(pd.notna(cleaned), "").to_dict(orient="records"),
        partial_rows=partial_rows[:100],
        analysis=analysis,
        ai=ai,
        logs=logs,
        steps=steps,
        report_path=report_path,
        cleaned_path=cleaned_path,
        source_csv_paths=generated_csvs,
    )
    add_step(steps, "任务输出归档", "completed", f"已保存到最近任务目录：{task_archive['run_dir']}")

    return {
        "status": "success" if analysis.get("valid", 0) else "partial",
        "steps": steps,
        "logs": logs,
        "rows": cleaned.head(100).where(pd.notna(cleaned), "").to_dict(orient="records"),
        "partial_rows": partial_rows[:100],
        "analysis": analysis,
        "ai": ai,
        "ai_readers": ai_readers,
        "report_path": str(report_path),
        "cleaned_path": str(cleaned_path),
        "generated_csvs": generated_csvs,
        "reflection": reflection,
        "task_archive": task_archive,
    }
