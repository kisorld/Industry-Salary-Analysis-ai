from __future__ import annotations

import json
import random
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlparse

from .browser_runtime import ensure_browser_event_loop_policy
from .url_tools import normalize_url


SALARY_RE = re.compile(
    r"(\d+(?:\.\d+)?\s*(?:K|k|千|万|w|W|元)\s*[-~－—]\s*\d+(?:\.\d+)?\s*(?:K|k|千|万|w|W|元)?(?:[·xX*]\d+薪)?|"
    r"\d+(?:\.\d+)?\s*[-~－—]\s*\d+(?:\.\d+)?\s*(?:K|k|千|万|w|W|元)(?:[·xX*]\d+薪)?|"
    r"\d+(?:\.\d+)?\s*(?:K|k|千|万|w|W)(?:[·xX*]\d+薪)?|"
    r"\d+\s*[-~－—]\s*\d+\s*元/?(?:天|日|时)|"
    r"\d+\s*[-~－—]\s*\d+\s*万年薪)"
)

TITLE_TOKENS = [
    "数据分析师",
    "BI分析师",
    "商业分析师",
    "Java后端开发工程师",
    "Python后端工程师",
    "服务端开发工程师",
    "产品经理",
    "B端产品经理",
    "数据产品经理",
    "前端开发工程师",
]


@dataclass
class ExtractedBlock:
    text: str = ""
    attrs: dict[str, str] = field(default_factory=dict)


class JobHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.blocks: list[ExtractedBlock] = []
        self._stack: list[ExtractedBlock] = []
        self.json_ld: list[str] = []
        self._script_type = ""
        self._script_buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {k: v or "" for k, v in attrs}
        if tag == "script":
            self._script_type = attr_map.get("type", "")
            self._script_buffer = []
        if tag in {"article", "li", "section", "div"}:
            marker = " ".join([attr_map.get("class", ""), attr_map.get("id", "")]).lower()
            if tag in {"article", "li"} or any(token in marker for token in ["job", "position", "item", "card", "list"]):
                self._stack.append(ExtractedBlock(attrs=attr_map))

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            if "ld+json" in self._script_type:
                self.json_ld.append("".join(self._script_buffer))
            self._script_type = ""
            self._script_buffer = []
        if tag in {"article", "li", "section", "div"} and self._stack:
            block = self._stack.pop()
            if block.text.strip():
                self.blocks.append(block)

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if self._script_type:
            self._script_buffer.append(data)
            return
        if text:
            self.parts.append(text)
            for block in self._stack:
                block.text += " " + text


def fetch_public_page(url: str, timeout: int = 12) -> tuple[str, dict[str, object]]:
    normalized = normalize_url(url)
    started = time.time()
    req = urllib.request.Request(
        normalized,
        headers={
            "User-Agent": "Mozilla/5.0 SalaryInsightPoC/2.0",
            "Accept": "text/html,application/xhtml+xml,application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        body = resp.read().decode(charset, errors="ignore")
        return body, {
            "url": normalized,
            "status": getattr(resp, "status", 200),
            "content_type": resp.headers.get("content-type", ""),
            "elapsed_ms": round((time.time() - started) * 1000, 2),
            "bytes": len(body.encode("utf-8", errors="ignore")),
        }


def fetch_dynamic_page(url: str, timeout_ms: int = 15000) -> tuple[str, dict[str, object]]:
    ensure_browser_event_loop_policy()
    normalized = normalize_url(url)
    started = time.time()
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception as exc:
        raise RuntimeError(f"Playwright 未安装或不可用: {exc}") from exc
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            parsed = urlparse(normalized)
            origin = f"{parsed.scheme}://{parsed.netloc}"
            user_agent = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/115.0.0.0 Safari/537.36"
            )
            context = browser.new_context(
                user_agent=user_agent,
                locale="zh-CN",
                viewport={"width": 1366, "height": 900},
                extra_http_headers={
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    "Referer": origin + "/",
                },
            )
            page = context.new_page()
            response = page.goto(normalized, wait_until="domcontentloaded", timeout=timeout_ms, referer=origin + "/")
            wait_events: list[str] = ["domcontentloaded"]
            try:
                page.wait_for_load_state("networkidle", timeout=5000)
                wait_events.append("networkidle")
            except Exception:
                wait_events.append("networkidle_timeout")
            try:
                page.wait_for_selector("body", timeout=3000)
                wait_events.append("body_ready")
            except Exception:
                wait_events.append("body_timeout")
            if "careers.tencent.com" in parsed.netloc:
                for selector in ["text=岗位职责", "text=职位描述", "text=工作职责", "text=任职要求"]:
                    try:
                        page.wait_for_selector(selector, timeout=3000)
                        wait_events.append(f"selector:{selector}")
                        break
                    except Exception:
                        continue
            human_events = simulate_human_reading(page)
            wait_events.extend(human_events)
            settle_ms = random.randint(800, 1600)
            page.wait_for_timeout(settle_ms)
            visible_text = ""
            job_card_texts: list[str] = []
            try:
                visible_text = page.locator("body").inner_text(timeout=3000)
                wait_events.append("body_inner_text")
            except Exception:
                wait_events.append("body_inner_text_failed")
            try:
                job_card_texts, card_events = extract_visible_job_cards(page)
                wait_events.append(f"job_cards:{len(job_card_texts)}")
                wait_events.extend(card_events)
            except Exception:
                wait_events.append("job_cards_failed")
            html = page.content()
            return html, {
                "url": normalized,
                "status": response.status if response else 0,
                "content_type": response.headers.get("content-type", "") if response else "",
                "elapsed_ms": round((time.time() - started) * 1000, 2),
                "bytes": len(html.encode("utf-8", errors="ignore")),
                "fetch_mode": "dynamic_playwright",
                "user_agent": user_agent,
                "locale": "zh-CN",
                "wait_events": wait_events,
                "settle_ms": settle_ms,
                "visible_text": visible_text,
                "job_card_texts": job_card_texts,
            }
        finally:
            browser.close()


def simulate_human_reading(page: object) -> list[str]:
    events: list[str] = []
    expand_texts = [
        "展开",
        "展开更多",
        "查看更多",
        "查看全部",
        "显示更多",
        "更多",
        "阅读全文",
        "职位详情",
        "岗位详情",
    ]
    try:
        page.mouse.move(random.randint(260, 900), random.randint(180, 620))
        events.append("mouse_move")
    except Exception:
        events.append("mouse_move_failed")
    previous_height = 0
    stable_rounds = 0
    for idx in range(10):
        try:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(random.randint(900, 1600))
            current_height = int(page.evaluate("document.body.scrollHeight") or 0)
            events.append(f"scroll_down:{idx + 1}")
            if current_height <= previous_height:
                stable_rounds += 1
            else:
                stable_rounds = 0
            previous_height = current_height
            if stable_rounds >= 2:
                events.append("scroll_height_stable")
                break
        except Exception:
            events.append(f"scroll_down_failed:{idx + 1}")
            break
    for text in expand_texts:
        try:
            locator = page.get_by_text(text, exact=False).first
            if locator.count() > 0 and locator.is_visible(timeout=800):
                locator.click(timeout=1200)
                page.wait_for_timeout(random.randint(500, 1000))
                events.append(f"clicked:{text}")
        except Exception:
            continue
    try:
        page.mouse.wheel(0, -random.randint(300, 700))
        page.wait_for_timeout(random.randint(400, 800))
        events.append("scroll_up_review")
    except Exception:
        events.append("scroll_up_failed")
    try:
        page.wait_for_load_state("networkidle", timeout=3000)
        events.append("post_read_networkidle")
    except Exception:
        events.append("post_read_networkidle_timeout")
    return events


def extract_visible_job_cards(page: object, limit: int = 80) -> tuple[list[str], list[str]]:
    collect_events: list[str] = []
    selectors = [
        ".job-card-wrapper",
        ".job-card-body",
        ".job-card-left",
        ".job-card-box",
        ".job-list-box li",
        ".job-primary",
        ".job-card",
        ".job-item",
        ".job-list li",
        "[class*=job-card]",
        "[class*=job-name]",
        "[class*=salary]",
        "[class*=job] li",
        "[class*=position]",
        "article",
        "li",
    ]
    seen: set[str] = set()
    cards: list[str] = []
    def collect_once() -> None:
        for selector in selectors:
            try:
                locators = page.locator(selector)
                count = min(locators.count(), limit)
            except Exception:
                continue
            for idx in range(count):
                try:
                    text = " ".join(locators.nth(idx).inner_text(timeout=800).split())
                except Exception:
                    continue
                if not looks_like_job_text(text):
                    continue
                key = normalize_card_key(text)
                if key in seen:
                    continue
                seen.add(key)
                cards.append(text[:1200])
                if len(cards) >= limit:
                    return

    collect_once()
    collect_events.append(f"collect_initial:{len(cards)}")
    stable_rounds = 0
    for round_idx in range(12):
        before = len(cards)
        try:
            page.evaluate("window.scrollBy(0, Math.max(window.innerHeight * 0.9, 700))")
            page.wait_for_timeout(random.randint(700, 1300))
            collect_once()
            if len(cards) == before:
                stable_rounds += 1
            else:
                stable_rounds = 0
            collect_events.append(f"collect_round:{round_idx + 1}:{len(cards)}")
            if len(cards) >= limit or stable_rounds >= 3:
                break
        except Exception:
            collect_events.append(f"collect_round_failed:{round_idx + 1}")
            break
    return cards, collect_events


def normalize_card_key(text: str) -> str:
    compact = " ".join((text or "").split())
    return compact[:160]


def extract_tencent_post_id(url: str) -> str:
    parsed = urlparse(url)
    if "careers.tencent.com" not in parsed.netloc:
        return ""
    query = parse_qs(parsed.query)
    return (query.get("postId") or [""])[0].strip()


def fetch_tencent_post_detail(url: str, timeout: int = 12) -> tuple[dict[str, object], dict[str, object]]:
    normalized = normalize_url(url)
    post_id = extract_tencent_post_id(normalized)
    if not post_id:
        raise ValueError("不是腾讯招聘详情页或缺少 postId")
    started = time.time()
    api_url = (
        "https://careers.tencent.com/tencentcareer/api/post/ByPostId"
        f"?timestamp={int(time.time() * 1000)}&postId={post_id}&language=zh-cn"
    )
    req = urllib.request.Request(
        api_url,
        headers={
            "User-Agent": "Mozilla/5.0 SalaryInsightPoC/2.0",
            "Accept": "application/json,text/plain,*/*",
            "Referer": normalized,
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        raw = resp.read().decode(charset, errors="ignore")
    payload = json.loads(raw)
    data = payload.get("Data") or payload.get("data") or payload
    if isinstance(data, list):
        data = data[0] if data else {}
    if not isinstance(data, dict) or not data:
        raise ValueError("腾讯招聘接口未返回岗位详情")
    return data, {
        "url": normalized,
        "status": 200,
        "content_type": "application/json",
        "elapsed_ms": round((time.time() - started) * 1000, 2),
        "bytes": len(raw.encode("utf-8", errors="ignore")),
        "fetch_mode": "tencent_api_by_post_id",
        "post_id": post_id,
    }


def extract_tencent_job(data: dict[str, object], source: str) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, object]]:
    title = str(
        data.get("RecruitPostName")
        or data.get("PostName")
        or data.get("Title")
        or data.get("title")
        or ""
    )
    city = str(data.get("LocationName") or data.get("Location") or data.get("city") or "")
    publish_date = str(data.get("LastUpdateTime") or data.get("UpdateTime") or data.get("PublishTime") or "")
    text_parts = [title, city, publish_date]
    for key, value in data.items():
        if isinstance(value, (str, int, float)):
            text_parts.append(str(value))
    text = " ".join(part for part in text_parts if part)
    salary = find_explicit_salary_field(data)
    row = make_job_row(text, source, salary, title=title)
    if city:
        row["city"] = city
    if publish_date:
        row["publish_date"] = publish_date
    row["company"] = row.get("company") or "腾讯"
    diagnostics = {
        "strategy": "tencent_api_by_post_id",
        "matched_jobs": 1 if salary else 0,
        "partial_jobs": 0 if salary else 1,
    }
    if salary:
        return [row], [], diagnostics
    row["missing_reason"] = "腾讯招聘公开详情页未提供薪资字段"
    return [], [row], diagnostics


def find_explicit_salary_field(data: dict[str, object]) -> str:
    salary_keys = {
        "salary",
        "salarydesc",
        "salaryrange",
        "salarytext",
        "pay",
        "payrange",
        "compensation",
        "wage",
        "薪资",
        "薪酬",
        "薪资范围",
    }
    for key, value in data.items():
        normalized_key = str(key).replace("_", "").replace("-", "").lower()
        if normalized_key not in salary_keys and not any(token in str(key) for token in ["薪资", "薪酬"]):
            continue
        salary = find_salary(str(value))
        if salary:
            return salary
    return ""


def extract_jsonld_jobs(parser: JobHTMLParser, source: str, limit: int) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    jobs: list[dict[str, str]] = []
    partials: list[dict[str, str]] = []
    for raw in parser.json_ld:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack and len(jobs) < limit:
            item = stack.pop(0)
            if isinstance(item, list):
                stack.extend(item)
                continue
            if not isinstance(item, dict):
                continue
            stack.extend(v for v in item.values() if isinstance(v, (dict, list)))
            type_value = str(item.get("@type", "")).lower()
            text = json.dumps(item, ensure_ascii=False)
            salary = find_salary(text)
            looks_like_job = any(token in type_value for token in ["jobposting", "occupation"]) or "职位" in text or "岗位" in text
            if looks_like_job:
                row = make_job_row(text, source, salary, title=str(item.get("title") or item.get("name") or ""))
                if salary:
                    jobs.append(row)
                else:
                    row["missing_reason"] = "JSON-LD岗位信息未提供薪资"
                    partials.append(row)
    return jobs, partials


def extract_jobs_from_html(html: str, source: str, limit: int = 20) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, object]]:
    soup_rows, soup_diag = extract_jobs_with_bs4(html, source, limit)
    if soup_rows or soup_diag.get("partial_jobs"):
        return soup_rows, soup_diag.get("partial_rows", []), soup_diag
    parser = JobHTMLParser()
    parser.feed(html)
    jobs, partials = extract_jsonld_jobs(parser, source, limit)
    block_sources = [block.text for block in parser.blocks if find_salary(block.text)]
    partial_sources = [block.text for block in parser.blocks if not find_salary(block.text) and looks_like_job_text(block.text)]
    if not block_sources:
        lines = [line.strip() for line in parser.parts if line.strip()]
        block_sources = make_context_windows(lines)
    for text in block_sources:
        if len(jobs) >= limit:
            break
        salary = find_salary(text)
        if not salary:
            continue
        jobs.append(make_job_row(text, source, salary.replace(" ", "")))
    for text in partial_sources:
        if len(partials) >= limit:
            break
        row = make_job_row(text, source, "")
        row["missing_reason"] = "识别到岗位信息，但页面未提供薪资"
        partials.append(row)
    unique_jobs = dedupe_jobs(jobs)[:limit]
    unique_partials = dedupe_jobs(partials)[:limit]
    diagnostics = {
        "text_nodes": len(parser.parts),
        "job_like_blocks": len(parser.blocks),
        "json_ld_blocks": len(parser.json_ld),
        "matched_jobs": len(unique_jobs),
        "partial_jobs": len(unique_partials),
        "strategy": "jsonld+job_blocks+context_windows",
    }
    return unique_jobs, unique_partials, diagnostics


def extract_jobs_with_bs4(html: str, source: str, limit: int = 20) -> tuple[list[dict[str, str]], dict[str, object]]:
    try:
        from bs4 import BeautifulSoup  # type: ignore
    except Exception:
        return [], {"strategy": "htmlparser_fallback", "bs4_available": False}
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        if tag.name == "script" and tag.get("type") == "application/ld+json":
            continue
        tag.extract()
    selectors = [
        "[class*=job]",
        "[class*=position]",
        "[class*=card]",
        "[class*=item]",
        "article",
        "li",
    ]
    candidates = []
    weak_candidates = []
    partial_candidates = []
    seen_text: set[str] = set()
    for selector in selectors:
        for node in soup.select(selector):
            text = " ".join(node.get_text(" ", strip=True).split())
            binding = salary_binding_level(text)
            if text and binding == "strong" and text not in seen_text:
                seen_text.add(text)
                candidates.append(text)
            elif text and binding == "weak" and text not in seen_text:
                seen_text.add(text)
                weak_candidates.append(text)
            elif text and looks_like_job_text(text) and text not in seen_text:
                seen_text.add(text)
                partial_candidates.append(text)
    if not candidates:
        text = " ".join(soup.get_text(" ", strip=True).split())
        candidates = make_context_windows([part.strip() for part in re.split(r"(?<=[。；;])|\s{2,}", text) if part.strip()])
    rows = []
    for text in candidates:
        if len(rows) >= limit:
            break
        salary = find_salary(text)
        if not salary:
            continue
        rows.append(make_job_row(text, source, salary))
    rows = dedupe_jobs(rows)[:limit]
    partial_rows = []
    for text in weak_candidates[:limit]:
        salary = find_salary(text)
        row = make_job_row(text, source, "")
        row["salary_text_candidate"] = salary
        row["salary_confidence"] = "weak"
        row["missing_reason"] = "识别到疑似薪资，但薪资与岗位文本绑定较弱，未纳入薪资统计"
        partial_rows.append(row)
    for text in partial_candidates[:limit]:
        row = make_job_row(text, source, "")
        row["missing_reason"] = "识别到岗位信息，但页面未提供薪资"
        partial_rows.append(row)
    partial_rows = dedupe_jobs(partial_rows)[:limit]
    return rows, {
        "strategy": "bs4_css_selectors+context_windows",
        "bs4_available": True,
        "candidate_blocks": len(candidates),
        "weak_candidate_blocks": len(weak_candidates),
        "partial_candidate_blocks": len(partial_candidates),
        "matched_jobs": len(rows),
        "partial_jobs": len(partial_rows),
        "partial_rows": partial_rows,
    }


def make_context_windows(lines: list[str]) -> list[str]:
    windows: list[str] = []
    for idx, line in enumerate(lines):
        if find_salary(line):
            window = " ".join(lines[max(0, idx - 4): idx + 5])
            if salary_binding_level(window) in {"strong", "weak"}:
                windows.append(window)
    return windows


def find_salary(text: str) -> str:
    match = SALARY_RE.search(text.replace("－", "-").replace("—", "-").replace("~", "-"))
    return match.group(1).replace(" ", "") if match else ""


def salary_bound_to_job(text: str) -> bool:
    return salary_binding_level(text) == "strong"


def salary_binding_level(text: str) -> str:
    compact = " ".join((text or "").split())
    if not find_salary(compact):
        return "none"
    salary_match = SALARY_RE.search(compact.replace("－", "-").replace("—", "-").replace("~", "-"))
    if not salary_match:
        return "none"
    title_hit = guess_title(compact) != "公开页面岗位"
    job_word_hit = any(token in compact for token in ["岗位", "职位", "招聘", "任职要求", "岗位职责", "工程师", "分析师", "产品经理", "开发", "运营", "策划", "顾问"])
    company_hit = bool(guess_company(compact))
    city_hit = guess_city(compact) != "未识别"
    edu_or_exp_hit = guess_education(compact) != "未识别" or guess_experience(compact) != "未识别"
    if title_hit and (city_hit or edu_or_exp_hit or company_hit):
        return "strong"
    if looks_like_job_text(compact) or job_word_hit:
        return "weak"
    salary_match = SALARY_RE.search(compact.replace("－", "-").replace("—", "-").replace("~", "-"))
    if not salary_match:
        return "none"
    start = max(0, salary_match.start() - 80)
    end = min(len(compact), salary_match.end() + 120)
    return "weak" if looks_like_job_text(compact[start:end]) else "none"


def looks_like_job_text(text: str) -> bool:
    compact = " ".join((text or "").split())
    if len(compact) < 4:
        return False
    title_hit = any(token.lower() in compact.lower() for token in TITLE_TOKENS)
    job_word_hit = any(token in compact for token in ["岗位", "职位", "招聘", "任职要求", "岗位职责", "工程师", "分析师", "产品经理"])
    city_hit = guess_city(compact) != "未识别"
    edu_or_exp_hit = guess_education(compact) != "未识别" or guess_experience(compact) != "未识别"
    return title_hit or (job_word_hit and (city_hit or edu_or_exp_hit))


def make_job_row(text: str, source: str, salary: str, title: str = "") -> dict[str, str]:
    return {
        "job_title": title or guess_title(text),
        "job_category": "",
        "company": guess_company(text),
        "city": guess_city(text),
        "salary_text": salary,
        "experience": guess_experience(text),
        "education": guess_education(text),
        "publish_date": guess_date(text),
        "source": source,
    }


def guess_title(text: str) -> str:
    low = text.lower()
    for token in TITLE_TOKENS:
        if token.lower() in low:
            return token
    title_match = re.search(r"([\u4e00-\u9fffA-Za-z]{2,20}(?:工程师|分析师|产品经理|开发|运营|专家))", text)
    return title_match.group(1) if title_match else "公开页面岗位"


def guess_company(text: str) -> str:
    match = re.search(r"([\u4e00-\u9fffA-Za-z0-9]{2,30}(?:公司|科技|集团|网络|信息|智能|软件))", text)
    return match.group(1) if match else ""


def guess_city(text: str) -> str:
    for city in ["北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "南京", "苏州", "西安", "长沙", "重庆"]:
        if city in text:
            return city
    return "未识别"


def guess_experience(text: str) -> str:
    for pattern in [r"\d+\s*[-~]\s*\d+\s*年", r"\d+年以上", r"经验不限", r"应届"]:
        match = re.search(pattern, text)
        if match:
            return match.group(0).replace(" ", "")
    return "未识别"


def guess_education(text: str) -> str:
    for edu in ["大专", "本科", "硕士", "博士", "学历不限", "不限"]:
        if edu in text:
            return edu
    return "未识别"


def guess_date(text: str) -> str:
    match = re.search(r"20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}", text)
    return match.group(0) if match else ""


def dedupe_jobs(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str, str, str]] = set()
    result: list[dict[str, str]] = []
    for row in rows:
        key = (row.get("job_title", ""), row.get("city", ""), row.get("salary_text", ""), row.get("source", ""))
        if key not in seen:
            seen.add(key)
            result.append(row)
    return result


def scrape_public_jobs(url: str, limit: int = 20, mode: str = "auto") -> dict[str, object]:
    normalized = normalize_url(url)
    errors: list[str] = []
    try:
        if extract_tencent_post_id(normalized):
            try:
                data, fetch_meta = fetch_tencent_post_detail(normalized)
                rows, partial_rows, diagnostics = extract_tencent_job(data, normalized)
                return {
                    "url": normalized,
                    "ok": bool(rows or partial_rows),
                    "status": "success" if rows else "partial" if partial_rows else "failed",
                    "rows": rows[:limit],
                    "partial_rows": partial_rows[:limit],
                    "diagnostics": {**fetch_meta, **diagnostics, "errors": errors},
                    "error": "" if rows else "页面已访问，识别到腾讯岗位详情但公开数据未提供薪资",
                }
            except Exception as exc:
                errors.append(f"tencent_api_failed: {exc}")
        if mode in {"auto", "dynamic"}:
            try:
                html, fetch_meta = fetch_dynamic_page(normalized)
            except Exception as exc:
                errors.append(f"dynamic_failed: {exc}")
                if mode == "dynamic":
                    raise
                html, fetch_meta = fetch_public_page(normalized)
                fetch_meta["fetch_mode"] = "static_urllib_fallback"
        else:
            html, fetch_meta = fetch_public_page(normalized)
            fetch_meta["fetch_mode"] = "static_urllib"
        rows, partial_rows, diagnostics = extract_jobs_from_html(html, normalized, limit)
        dynamic_cards = [str(item) for item in fetch_meta.get("job_card_texts", []) if str(item).strip()]
        if dynamic_cards and not rows:
            for card in dynamic_cards[:limit]:
                salary = find_salary(card)
                binding = salary_binding_level(card)
                row = make_job_row(card, normalized, salary if binding == "strong" else "")
                if row.get("salary_text"):
                    rows.append(row)
                elif salary and binding == "weak":
                    row["salary_text_candidate"] = salary
                    row["salary_confidence"] = "weak"
                    row["missing_reason"] = "识别到疑似薪资，但薪资与岗位文本绑定较弱，未纳入薪资统计"
                    partial_rows.append(row)
                elif looks_like_job_text(card):
                    row["missing_reason"] = "公开列表卡片未提供薪资或未识别到薪资"
                    partial_rows.append(row)
            rows = dedupe_jobs(rows)[:limit]
            partial_rows = dedupe_jobs(partial_rows)[:limit]
            diagnostics["strategy"] = f"{diagnostics.get('strategy', '')}+dynamic_job_cards"
            diagnostics["dynamic_card_count"] = len(dynamic_cards)
        return {
            "url": normalized,
            "ok": bool(rows or partial_rows),
            "status": "success" if rows else "partial" if partial_rows else "failed",
            "rows": rows,
            "partial_rows": partial_rows,
            "diagnostics": {**fetch_meta, **diagnostics, "errors": errors},
            "error": "" if rows else "页面已访问，识别到岗位但未识别到薪资" if partial_rows else "页面已访问，但未识别到岗位内容；可能是动态渲染、接口加密、登录校验或反爬限制",
        }
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        return {"url": normalized, "ok": False, "status": "failed", "rows": [], "partial_rows": [], "diagnostics": {}, "error": str(exc)}


def scrape_many_public_jobs(urls: list[str], limit: int = 20, mode: str = "auto") -> dict[str, object]:
    all_rows: list[dict[str, str]] = []
    all_partials: list[dict[str, str]] = []
    logs: list[dict[str, object]] = []
    per_url_limit = max(1, limit)
    for url in urls:
        result = scrape_public_jobs(url, per_url_limit, mode)
        logs.append({k: v for k, v in result.items() if k not in {"rows", "partial_rows"}})
        all_rows.extend(result.get("rows", []))
        all_partials.extend(result.get("partial_rows", []))
        if len(all_rows) >= limit:
            break
    return {"rows": dedupe_jobs(all_rows)[:limit], "partial_rows": dedupe_jobs(all_partials)[:limit], "logs": logs}
