from __future__ import annotations

import json
import re
from typing import Any

from .ai_agent import qwen_chat
from .drission_reader import fetch_with_drission, is_script_like
from .scraper import extract_tencent_job, extract_tencent_post_id, fetch_dynamic_page, fetch_public_page, fetch_tencent_post_detail, find_salary
from .scrapling_reader import fetch_with_scrapling, looks_like_visible_text, strip_noise


def visible_text_from_html(html: str) -> str:
    try:
        from bs4 import BeautifulSoup  # type: ignore
    except Exception:
        text = re.sub(r"<(script|style)[\s\S]*?</\1>", " ", html, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        return " ".join(text.split())
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.extract()
    return " ".join(soup.get_text(" ", strip=True).split())


def fetch_readable_page_text(url: str, mode: str = "auto") -> tuple[str, dict[str, object]]:
    errors: list[str] = []
    if extract_tencent_post_id(url):
        try:
            data, meta = fetch_tencent_post_detail(url)
            rows, partial_rows, diagnostics = extract_tencent_job(data, url)
            text = json.dumps(
                {
                    "source": "tencent_post_detail_api",
                    "rows": rows,
                    "partial_rows": partial_rows,
                    "raw_detail": data,
                },
                ensure_ascii=False,
            )
            meta["reader_mode"] = "tencent_post_detail_api_text"
            meta["reader_text_chars"] = len(text)
            meta["reader_text_preview"] = text[:300]
            return text, {**meta, **diagnostics, "reader_errors": errors}
        except Exception as exc:
            errors.append(f"tencent_detail_reader_failed: {exc}")
    if mode in {"auto", "dynamic"}:
        try:
            text, meta = fetch_with_scrapling(url, timeout_ms=30000)
            text = strip_noise(text)
            if len(text) >= 80 and looks_like_visible_text(text):
                meta["reader_mode"] = "scrapling_complex_url_reader"
                meta["reader_text_chars"] = len(text)
                meta["reader_text_preview"] = text[:300]
                return text, {**meta, "reader_errors": errors}
            errors.append("scrapling_reader_text_too_short_or_script_like")
        except Exception as exc:
            errors.append(f"scrapling_reader_failed: {exc}")
        try:
            text, meta = fetch_with_drission(url, timeout=30, limit=80)
            text = strip_noise(text)
            if len(text) >= 80 and not is_script_like(text):
                meta["reader_mode"] = "drissionpage_visible_text"
                meta["reader_text_chars"] = len(text)
                meta["reader_text_preview"] = text[:300]
                return text, {**meta, "reader_errors": errors}
            errors.append("drission_reader_text_too_short_or_script_like")
        except Exception as exc:
            errors.append(f"drission_reader_failed: {exc}")
        try:
            html, meta = fetch_dynamic_page(url, timeout_ms=25000)
            job_card_texts = [str(item) for item in meta.get("job_card_texts", []) if str(item).strip()]
            cards_text = build_job_cards_prompt(job_card_texts)
            text = cards_text or " ".join(str(meta.get("visible_text") or "").split()) or visible_text_from_html(html)
            meta["job_card_count"] = len(job_card_texts)
            meta.pop("visible_text", None)
            meta.pop("job_card_texts", None)
            if (len(text) >= 80 and looks_like_visible_text(text)) or mode == "dynamic":
                meta["reader_mode"] = "dynamic_playwright_visible_text"
                meta["reader_text_chars"] = len(text)
                meta["reader_text_preview"] = text[:300]
                return text, {**meta, "reader_errors": errors}
            errors.append("dynamic_reader_text_too_short_or_script_like")
        except Exception as exc:
            errors.append(f"dynamic_reader_failed: {exc}")
            if mode == "dynamic":
                return "", {"reader_errors": errors}
    try:
        html, meta = fetch_public_page(url)
        text = visible_text_from_html(html)
        meta["reader_mode"] = "static_urllib_visible_text"
        meta["reader_text_chars"] = len(text)
        meta["reader_text_preview"] = text[:300]
        return text, {**meta, "reader_errors": errors}
    except Exception as exc:
        errors.append(f"static_reader_failed: {exc}")
        return "", {"reader_errors": errors}


def parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if not match:
            raise
        data = json.loads(match.group(0))
    return data if isinstance(data, dict) else {"items": data}


def focus_job_text(text: str, max_chars: int = 6000) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= max_chars:
        return compact
    anchors = [
        "岗位职责",
        "工作职责",
        "职位描述",
        "职位信息",
        "任职要求",
        "岗位要求",
        "工作地点",
        "发布时间",
        "申请职位",
    ]
    positions = [compact.find(anchor) for anchor in anchors if compact.find(anchor) >= 0]
    if not positions:
        return compact[-max_chars:]
    start = max(0, min(positions) - 1200)
    end = min(len(compact), max(positions) + 4200)
    focused = compact[start:end]
    return focused[:max_chars]


def build_job_cards_prompt(cards: list[str], max_cards: int = 40, max_chars: int = 14000) -> str:
    chunks: list[str] = []
    used = 0
    for idx, card in enumerate(cards[:max_cards], start=1):
        cleaned = " ".join((card or "").split())[:1000]
        if not cleaned:
            continue
        item = f"[岗位卡片{idx}] {cleaned}"
        if used + len(item) > max_chars:
            break
        chunks.append(item)
        used += len(item)
    return "\n".join(chunks)


def validate_ai_reader_items(data: dict[str, Any], visible_text: str) -> dict[str, Any]:
    items = data.get("items")
    if not isinstance(items, list):
        data["items"] = []
        data["limits"] = f"{data.get('limits', '')}；模型未返回items数组。".strip("；")
        return data
    checked_items: list[dict[str, Any]] = []
    removed_count = 0
    compact_text = " ".join((visible_text or "").split())
    for raw in items:
        if not isinstance(raw, dict):
            removed_count += 1
            continue
        item = dict(raw)
        title = str(item.get("job_title") or "").strip()
        salary = str(item.get("salary_text") or "").strip()
        evidence = str(item.get("evidence") or "").strip()
        if title and title not in compact_text and title not in evidence:
            item["quality_warning"] = "岗位名称未能在网页可见文本中直接校验"
        if salary:
            normalized_salary = salary.replace(" ", "")
            if not find_salary(salary) or normalized_salary not in compact_text.replace(" ", ""):
                item["salary_text"] = ""
                item["quality_warning"] = "模型返回的薪资未在网页可见文本中校验，已清空"
        if title or evidence or item.get("responsibilities") or item.get("requirements"):
            checked_items.append(item)
        else:
            removed_count += 1
    data["items"] = checked_items
    data["salary_available"] = any(str(item.get("salary_text") or "").strip() for item in checked_items)
    if removed_count:
        data["limits"] = f"{data.get('limits', '')}；已移除{removed_count}条缺少证据的模型结果。".strip("；")
    return data


def ai_read_job_url(url: str, scrape_logs: list[dict[str, Any]] | None = None, mode: str = "auto") -> dict[str, Any]:
    text, reader_meta = fetch_readable_page_text(url, mode)
    if not text:
        return {
            "mode": "reader_failed",
            "items": [],
            "summary": "后端未能读取到动态渲染后的网页可见文本，无法交给大模型抽取。",
            "reader_meta": reader_meta,
        }
    if "tencent_post_detail_api" in text:
        clipped_text = text[:12000]
    elif "[岗位卡片" in text:
        clipped_text = text[:14000]
    else:
        clipped_text = focus_job_text(text, max_chars=6000)
    reader_meta["prompt_text_chars"] = len(clipped_text)
    reader_meta["prompt_text_preview"] = clipped_text[:300]
    system = (
        "你是招聘网页阅读助手。用户会提供URL、采集日志，以及后端通过Playwright动态渲染后提取的网页可见文本。"
        "你只能根据这些可见文本抽取岗位核心信息，严禁编造网页中没有出现的岗位、薪资、城市、学历、经验、公司、部门或日期。"
        "如果文本包含多个[岗位卡片N]，请尽量逐条抽取每个岗位卡片，最多返回40条items，不要只总结前几条。"
        "如果页面没有薪资，salary_text必须为空字符串，并将 salary_available 设为 false。"
        "如果可见文本无法确认某个字段，请将对应字段留空，并在limits中说明原因。"
        "请只输出JSON对象，不要输出Markdown。"
    )
    schema_hint = {
        "page_type": "招聘详情页/招聘列表页/非招聘页/无法判断",
        "summary": "一句话说明网页中真实可见的岗位信息",
        "salary_available": False,
        "items": [
            {
                "job_title": "",
                "company": "",
                "department": "",
                "city": "",
                "salary_text": "",
                "experience": "",
                "education": "",
                "publish_date": "",
                "responsibilities": "",
                "requirements": "",
                "evidence": "用于支撑抽取结果的短文本片段",
            }
        ],
        "limits": "说明缺失字段，例如未公开薪资",
    }
    user = {
        "url": url,
        "scrape_logs": scrape_logs or [],
        "reader_meta": reader_meta,
        "read_instruction": "请阅读后端动态渲染得到的网页可见文本，提取页面中真实存在的岗位核心信息；不要根据经验猜测薪资。",
        "output_schema": schema_hint,
        "visible_text": clipped_text,
    }
    try:
        response = qwen_chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            timeout=120,
        )
        content = response["choices"][0]["message"].get("content", "")
        data = parse_json_object(content)
        data = validate_ai_reader_items(data, clipped_text)
        data["mode"] = "qwen_dynamic_text_reader"
        data["reader_meta"] = reader_meta
        return data
    except Exception as exc:
        return {
            "mode": "qwen_dynamic_text_reader_failed",
            "items": [],
            "summary": "后端已读取网页可见文本，但大模型抽取失败。",
            "error": str(exc),
            "reader_meta": reader_meta,
        }
