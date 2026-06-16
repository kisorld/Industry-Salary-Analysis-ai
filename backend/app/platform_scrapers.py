from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .config import AUTO_OPEN_LOGIN_PAGE, LOGIN_BROWSER_USER_DATA_DIR, PLATFORM_SCRAPE_HEADLESS
from .drission_reader import fetch_with_drission, is_script_like, make_options
from .scraper import dedupe_jobs, fetch_dynamic_page, find_salary, guess_city, guess_education, guess_experience, make_job_row


BOSS_CITY_CODES = {
    "北京": "101010100",
    "上海": "101020100",
    "广州": "101280100",
    "深圳": "101280600",
    "杭州": "101210100",
    "成都": "101270100",
    "武汉": "101200100",
    "南京": "101190100",
    "苏州": "101190400",
    "西安": "101110100",
    "长沙": "101250100",
    "重庆": "101040100",
}

ZHAOPIN_CITY_CODES = {
    "北京": "530",
    "上海": "538",
    "广州": "763",
    "深圳": "765",
    "杭州": "653",
    "成都": "801",
    "武汉": "736",
    "南京": "635",
    "苏州": "639",
    "西安": "854",
    "长沙": "749",
    "重庆": "551",
}

OPEN_LOGIN_PAGES: list[Any] = []


@dataclass
class PlatformQuery:
    platform: str
    keyword: str
    city: str = ""
    position: str = ""
    industry: str = ""
    start_date: str = ""
    end_date: str = ""
    limit: int = 20
    pages: int = 20


def build_boss_url(keyword: str, city: str = "", position: str = "") -> str:
    city_code = BOSS_CITY_CODES.get(city, "100010000")
    parts = [f"query={quote(keyword)}", f"city={city_code}"]
    if position:
        parts.append(f"position={quote(position)}")
    return "https://www.zhipin.com/web/geek/jobs?" + "&".join(parts)


def build_zhaopin_url(keyword: str, city: str = "") -> str:
    city_code = ZHAOPIN_CITY_CODES.get(city, "")
    if city_code:
        return f"https://sou.zhaopin.com/?jl={city_code}&kw={quote(keyword)}"
    return f"https://sou.zhaopin.com/?kw={quote(keyword)}"


def login_url_for_platform(platform: str) -> str:
    if platform == "boss":
        return "https://www.zhipin.com/web/user/"
    if platform == "zhaopin":
        return "https://passport.zhaopin.com/login"
    return ""


def detect_login_required(page: Any, platform: str) -> tuple[bool, str]:
    text = ""
    current_url = ""
    try:
        current_url = str(getattr(page, "url", "") or "")
    except Exception:
        current_url = ""
    try:
        text = str(page.run_js("return document.body ? document.body.innerText : '';") or "")
    except Exception:
        try:
            text = str(page.html or "")
        except Exception:
            text = ""
    compact = " ".join(text.split())
    login_tokens = ["登录", "验证码", "扫码", "手机号码", "未登录", "请先登录", "安全验证", "验证"]
    if platform == "boss":
        url_hit = "login" in current_url or "/web/user" in current_url or "security-check" in current_url
        text_hit = any(token in compact for token in login_tokens) and not any(token in compact for token in ["岗位职责", "职位描述", "任职要求"])
        return url_hit or text_hit, current_url or compact[:120]
    if platform == "zhaopin":
        url_hit = "passport.zhaopin.com" in current_url or "login" in current_url
        text_hit = any(token in compact for token in login_tokens) and not any(token in compact for token in ["职位描述", "任职要求", "工作地点"])
        return url_hit or text_hit, current_url or compact[:120]
    return False, ""


def open_platform_login_page(platform: str) -> dict[str, Any]:
    login_url = login_url_for_platform(platform)
    if not login_url:
        return {"opened": False, "login_url": "", "error": "未知平台登录页"}
    if not AUTO_OPEN_LOGIN_PAGE:
        return {"opened": False, "login_url": login_url, "error": "AUTO_OPEN_LOGIN_PAGE=false"}
    try:
        from DrissionPage import ChromiumPage  # type: ignore
    except Exception as exc:
        return {"opened": False, "login_url": login_url, "error": f"DrissionPage不可用: {exc}"}
    page = ChromiumPage(make_options(headless=False, user_data_dir=LOGIN_BROWSER_USER_DATA_DIR))
    page.get(login_url)
    OPEN_LOGIN_PAGES.append(page)
    return {
        "opened": True,
        "login_url": login_url,
        "profile_dir": str(LOGIN_BROWSER_USER_DATA_DIR),
        "message": "已打开可见登录页。请在浏览器中完成登录，完成后重新点击采集。",
    }


def build_platform_urls(platforms: list[str], keywords: list[str], cities: list[str], limit: int = 20) -> list[dict[str, str]]:
    normalized_platforms = [p.lower().strip() for p in platforms if p.strip()] or ["boss", "zhaopin"]
    normalized_keywords = [k.strip() for k in keywords if k.strip()] or ["数据分析"]
    normalized_cities = [c.strip() for c in cities if c.strip()] or [""]
    urls: list[dict[str, str]] = []
    for platform in normalized_platforms:
        for keyword in normalized_keywords:
            for city in normalized_cities:
                if platform in {"boss", "boos", "zhipin", "boss直聘", "boos直聘"}:
                    urls.append({"platform": "boss", "keyword": keyword, "city": city, "url": build_boss_url(keyword, city)})
                elif platform in {"zhaopin", "zhilian", "智联", "智联招聘"}:
                    urls.append({"platform": "zhaopin", "keyword": keyword, "city": city, "url": build_zhaopin_url(keyword, city)})
                if len(urls) >= limit:
                    return urls
    return urls


def extract_rows_from_card_text(card: str, source: str, platform: str, keyword: str = "", city: str = "") -> dict[str, str]:
    salary = find_salary(card)
    row = make_job_row(card, source, salary)
    if row.get("job_title") == "公开页面岗位" and keyword:
        row["job_title"] = keyword
    if row.get("city") == "未识别" and city:
        row["city"] = city
    row["source"] = source
    row["platform"] = platform
    row["experience"] = row.get("experience") or guess_experience(card)
    row["education"] = row.get("education") or guess_education(card)
    row["city"] = row.get("city") if row.get("city") != "未识别" else guess_city(card)
    return row


def wait_listener_response(page: Any, timeout: int = 15) -> Any:
    try:
        return page.listen.wait(timeout=timeout)
    except TypeError:
        return page.listen.wait()


def response_body_or_none(resp: Any) -> Any | None:
    if not resp or resp is True:
        return None
    response = getattr(resp, "response", None)
    if response is None:
        return None
    return getattr(response, "body", None)


def parse_listener_logs(logs: list[str], platform: str) -> dict[str, Any]:
    page_details: list[dict[str, Any]] = []
    total_items = 0
    no_response_pages = 0
    empty_pages = 0
    login_required_pages = 0
    for raw in logs:
        parts = str(raw).split(":")
        if len(parts) < 3:
            continue
        try:
            page_no = int(parts[1])
        except ValueError:
            continue
        value = parts[2]
        if value == "login_required":
            count = None
            login_required_pages += 1
            status = "login_required"
        elif value == "no_response":
            count: int | None = None
            no_response_pages += 1
            status = "no_response"
        else:
            try:
                count = int(value)
            except ValueError:
                count = None
            status = "ok" if count and count > 0 else "empty"
            if count == 0:
                empty_pages += 1
            if count:
                total_items += count
        page_details.append({"page": page_no, "status": status, "items": count})
    attempted_pages = len(page_details)
    successful_pages = len([item for item in page_details if item["status"] == "ok"])
    if login_required_pages:
        reason = "检测到平台未登录或进入登录/验证页面，已打开对应网站登录页，请登录后重新发起采集。"
    elif not page_details:
        reason = "未进入监听循环，可能是浏览器启动失败、页面未打开或平台限制访问。"
    elif successful_pages:
        reason = "接口监听成功，但后续页可能受分页、游客态或平台公开访问范围影响。"
    elif no_response_pages:
        reason = "页面未触发目标岗位接口，可能需要更明确的关键词/城市，或当前访问状态受到平台限制。"
    else:
        reason = "接口返回为空，可能是关键词无结果、城市条件过窄或平台仅返回前端壳。"
    advice = [
        "优先使用带岗位关键词和城市参数的公开搜索URL。",
        "如果连续 no_response，建议切换平台、缩小页数或使用CSV/Excel导入补充。",
        "系统不绕过登录、验证码、付费墙或平台风控，受限页面只做失败诊断。",
    ]
    return {
        "platform": platform,
        "browser_headless": PLATFORM_SCRAPE_HEADLESS,
        "attempted_pages": attempted_pages,
        "successful_pages": successful_pages,
        "no_response_pages": no_response_pages,
        "empty_pages": empty_pages,
        "login_required": login_required_pages > 0,
        "login_required_pages": login_required_pages,
        "listener_total_items": total_items,
        "page_details": page_details,
        "diagnosis": reason,
        "advice": advice,
    }


def platform_status(rows: list[dict[str, str]], diagnostics: dict[str, Any]) -> str:
    if rows:
        return "success"
    if diagnostics.get("login_required"):
        return "login_required"
    if diagnostics.get("no_response_pages") or diagnostics.get("empty_pages") or diagnostics.get("attempted_pages"):
        return "failed"
    return "failed"


def scrape_boss_by_listener(url: str, limit: int = 400, pages: int = 20) -> dict[str, Any]:
    try:
        from DrissionPage import ChromiumPage  # type: ignore
    except Exception as exc:
        raise RuntimeError(f"DrissionPage 未安装或不可用: {exc}") from exc

    page = None
    rows: list[dict[str, str]] = []
    logs: list[str] = []
    try:
        page = ChromiumPage(make_options(headless=PLATFORM_SCRAPE_HEADLESS))
        page.listen.start("joblist")
        page.get(url)
        login_required, login_reason = detect_login_required(page, "boss")
        if login_required:
            return {
                "rows": [],
                "logs": ["boss_listener_page:1:login_required"],
                "login_required": True,
                "login_reason": login_reason,
            }
        for page_no in range(1, pages + 1):
            if len(rows) >= limit:
                break
            resp = wait_listener_response(page)
            json_data = response_body_or_none(resp)
            if not isinstance(json_data, dict):
                logs.append(f"boss_listener_page:{page_no}:no_response")
                break
            job_list = (((json_data or {}).get("zpData") or {}).get("jobList") or [])
            logs.append(f"boss_listener_page:{page_no}:{len(job_list)}")
            for job in job_list:
                row = {
                    "job_title": job.get("jobName", ""),
                    "job_category": "",
                    "company": job.get("brandName", ""),
                    "city": job.get("cityName", ""),
                    "salary_text": job.get("salaryDesc", ""),
                    "experience": job.get("jobExperience", ""),
                    "education": job.get("jobDegree", ""),
                    "publish_date": "",
                    "source": url,
                    "platform": "boss",
                    "industry": job.get("brandIndustry", ""),
                    "area": job.get("areaDistrict", ""),
                    "business_district": job.get("businessDistrict", ""),
                    "skills": " ".join(job.get("skills") or []),
                }
                rows.append(row)
                if len(rows) >= limit:
                    break
            try:
                page.scroll.to_bottom()
                time.sleep(0.8)
            except Exception:
                break
        return {"rows": rows[:limit], "logs": logs}
    finally:
        if page is not None:
            try:
                page.quit()
            except Exception:
                pass


def scrape_zhaopin_by_listener(url: str, limit: int = 400, pages: int = 20) -> dict[str, Any]:
    try:
        from DrissionPage import ChromiumPage  # type: ignore
    except Exception as exc:
        raise RuntimeError(f"DrissionPage 未安装或不可用: {exc}") from exc

    page = None
    rows: list[dict[str, str]] = []
    logs: list[str] = []
    try:
        page = ChromiumPage(make_options(headless=PLATFORM_SCRAPE_HEADLESS))
        page.listen.start("search/positions")
        page.get(url)
        login_required, login_reason = detect_login_required(page, "zhaopin")
        if login_required:
            return {
                "rows": [],
                "logs": ["zhaopin_listener_page:1:login_required"],
                "login_required": True,
                "login_reason": login_reason,
            }
        for page_no in range(1, pages + 1):
            if len(rows) >= limit:
                break
            resp = wait_listener_response(page)
            json_data = response_body_or_none(resp)
            if not isinstance(json_data, dict):
                logs.append(f"zhaopin_listener_page:{page_no}:no_response")
                break
            job_list = (((json_data or {}).get("data") or {}).get("list") or [])
            logs.append(f"zhaopin_listener_page:{page_no}:{len(job_list)}")
            for job in job_list:
                desc = (((job.get("jobDetailData") or {}).get("position") or {}).get("desc") or {})
                row = {
                    "job_title": job.get("name", ""),
                    "job_category": "",
                    "company": job.get("companyName", ""),
                    "city": job.get("workCity", ""),
                    "salary_text": job.get("salary60", "") or job.get("salary", ""),
                    "experience": job.get("workingExp", ""),
                    "education": job.get("education", ""),
                    "publish_date": job.get("updateDate", "") or job.get("publishTime", ""),
                    "source": job.get("positionURL", "") or url,
                    "platform": "zhaopin",
                    "industry": job.get("industryName", ""),
                    "area": job.get("cityDistrict", ""),
                    "company_size": job.get("companySize", ""),
                    "tags": " ".join(desc.get("labels") or []),
                }
                rows.append(row)
                if len(rows) >= limit:
                    break
            try:
                next_button = page.ele("text=下一页", timeout=1)
                if not next_button:
                    break
                next_button.click()
                time.sleep(0.8)
            except Exception:
                break
        return {"rows": rows[:limit], "logs": logs}
    finally:
        if page is not None:
            try:
                page.quit()
            except Exception:
                pass


def write_platform_csv(rows: list[dict[str, str]], output_dir: Path, platform: str, keyword: str, city: str) -> Path:
    import pandas as pd

    output_dir.mkdir(parents=True, exist_ok=True)
    safe_keyword = "".join(ch for ch in (keyword or "all") if ch.isalnum() or ch in {"_", "-", "中", "文"})[:30] or "all"
    safe_city = city or "all"
    path = output_dir / f"platform_scrape_{platform}_{safe_city}_{safe_keyword}.csv"
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")
    return path


def scrape_platform_to_csv(query: PlatformQuery, output_dir: Path) -> dict[str, Any]:
    errors: list[str] = []
    if query.platform == "boss":
        url = build_boss_url(query.keyword, query.city, query.position)
        try:
            result = scrape_boss_by_listener(url, query.limit, query.pages)
        except Exception as exc:
            result = {"rows": [], "logs": []}
            errors.append(str(exc))
    elif query.platform == "zhaopin":
        url = build_zhaopin_url(query.keyword, query.city)
        try:
            result = scrape_zhaopin_by_listener(url, query.limit, query.pages)
        except Exception as exc:
            result = {"rows": [], "logs": []}
            errors.append(str(exc))
    else:
        raise ValueError(f"暂不支持平台: {query.platform}")
    rows = result.get("rows", [])
    csv_path = write_platform_csv(rows, output_dir, query.platform, query.keyword, query.city)
    listener_logs = result.get("logs", [])
    diagnostics = parse_listener_logs(listener_logs, query.platform)
    if result.get("login_required"):
        diagnostics["login_required"] = True
        diagnostics["login_reason"] = result.get("login_reason", "")
        diagnostics["login_page"] = open_platform_login_page(query.platform)
        diagnostics["diagnosis"] = "检测到平台未登录或进入登录/验证页面，已打开登录界面，请登录后重新采集。"
    if errors:
        diagnostics["errors"] = errors
        diagnostics["diagnosis"] = "平台脚本执行失败：" + "；".join(errors)
    return {
        "platform": query.platform,
        "url": url,
        "status": platform_status(rows, diagnostics),
        "rows": rows,
        "csv_path": str(csv_path),
        "logs": listener_logs,
        "diagnostics": diagnostics,
        "pages": query.pages,
        "count": len(rows),
    }


def scrape_platform_jobs(query: PlatformQuery) -> dict[str, Any]:
    if query.platform == "boss":
        url = build_boss_url(query.keyword, query.city, query.position)
    elif query.platform == "zhaopin":
        url = build_zhaopin_url(query.keyword, query.city)
    else:
        raise ValueError(f"暂不支持平台: {query.platform}")

    started = time.time()
    try:
        errors: list[str] = []
        try:
            if query.platform == "boss":
                listener_result = scrape_boss_by_listener(url, query.limit, query.pages)
            else:
                listener_result = scrape_zhaopin_by_listener(url, query.limit, query.pages)
            listener_rows = listener_result["rows"]
            if not listener_rows:
                raise RuntimeError("DrissionPage 监听接口未返回岗位数据")
            rows = [row for row in listener_rows if row.get("salary_text")]
            partial_rows = []
            for row in listener_rows:
                if not row.get("salary_text"):
                    row["missing_reason"] = "接口岗位数据未提供薪资"
                    partial_rows.append(row)
            rows = dedupe_jobs(rows)[: query.limit]
            partial_rows = dedupe_jobs(partial_rows)[: query.limit]
            meta = {
                "fetch_mode": "drissionpage_api_listener",
                "platform_fetch_priority": "drissionpage_listener",
                "listener_logs": listener_result["logs"],
            }
            cards: list[str] = []
        except Exception as exc:
            errors.append(f"drission_listener_failed: {exc}")
            try:
                text, meta = fetch_with_drission(url, timeout=30, limit=query.limit)
                if is_script_like(text):
                    errors.append("drission_script_like_text")
                    raise RuntimeError("DrissionPage 返回脚本壳文本")
                cards = [line.split("] ", 1)[1] if "] " in line else line for line in text.splitlines() if line.strip()]
                meta["platform_fetch_priority"] = "drissionpage_dom"
            except Exception as inner_exc:
                errors.append(f"drission_dom_failed: {inner_exc}")
                _html, meta = fetch_dynamic_page(url, timeout_ms=30000)
                cards = [str(item) for item in meta.get("job_card_texts", []) if str(item).strip()]
                meta["platform_fetch_priority"] = "playwright_fallback"
            meta["platform_errors"] = errors
            rows = []
            partial_rows = []
            for card in cards[: query.limit]:
                row = extract_rows_from_card_text(card, url, query.platform, query.keyword, query.city)
                if row.get("salary_text"):
                    rows.append(row)
                else:
                    row["missing_reason"] = "公开列表卡片未提供薪资或未识别到薪资"
                    partial_rows.append(row)
            rows = dedupe_jobs(rows)[: query.limit]
            partial_rows = dedupe_jobs(partial_rows)[: query.limit]
        meta["platform_errors"] = errors
        return {
            "platform": query.platform,
            "url": url,
            "ok": bool(rows or partial_rows),
            "status": "success" if rows else "partial" if partial_rows else "failed",
            "rows": rows,
            "partial_rows": partial_rows,
            "diagnostics": {
                **{k: v for k, v in meta.items() if k not in {"visible_text", "job_card_texts"}},
                "platform_query": query.__dict__,
                "card_count": len(cards),
                "elapsed_total_ms": round((time.time() - started) * 1000, 2),
            },
            "error": "" if rows or partial_rows else "公开页面未返回可识别岗位卡片，可能需要登录、验证码、地区限制或平台风控",
        }
    except Exception as exc:
        return {
            "platform": query.platform,
            "url": url,
            "ok": False,
            "status": "failed",
            "rows": [],
            "partial_rows": [],
            "diagnostics": {"platform_query": query.__dict__},
            "error": str(exc),
        }


def scrape_many_platform_jobs(platforms: list[str], keywords: list[str], cities: list[str], limit: int = 40) -> dict[str, Any]:
    all_rows: list[dict[str, str]] = []
    all_partials: list[dict[str, str]] = []
    logs: list[dict[str, Any]] = []
    query_urls = build_platform_urls(platforms, keywords, cities, limit=20)
    per_query_limit = max(5, min(limit, 20))
    for item in query_urls:
        result = scrape_platform_jobs(
            PlatformQuery(
                platform=item["platform"],
                keyword=item["keyword"],
                city=item["city"],
                limit=per_query_limit,
            )
        )
        logs.append({k: v for k, v in result.items() if k not in {"rows", "partial_rows"}})
        all_rows.extend(result.get("rows", []))
        all_partials.extend(result.get("partial_rows", []))
        if len(all_rows) >= limit:
            break
    return {
        "rows": dedupe_jobs(all_rows)[:limit],
        "partial_rows": dedupe_jobs(all_partials)[:limit],
        "logs": logs,
        "query_urls": query_urls,
    }
