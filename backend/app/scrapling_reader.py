from __future__ import annotations

import re
import time
from typing import Any

from .browser_runtime import ensure_browser_event_loop_policy


def clean_text(text: str) -> str:
    return " ".join((text or "").split())


def html_to_visible_text(html: str) -> str:
    try:
        from bs4 import BeautifulSoup  # type: ignore
    except Exception:
        cleaned = re.sub(r"<(script|style|noscript|svg)[\s\S]*?</\1>", " ", html, flags=re.IGNORECASE)
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        return clean_text(cleaned)
    soup = BeautifulSoup(html or "", "lxml")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.extract()
    return clean_text(soup.get_text(" ", strip=True))


def page_to_text(page: Any) -> str:
    for attr in ["html", "body", "content"]:
        try:
            value = getattr(page, attr)
            if callable(value):
                value = value()
            text = html_to_visible_text(str(value))
            if looks_like_visible_text(text):
                return text
        except Exception:
            continue
    try:
        text = html_to_visible_text(str(page))
        if looks_like_visible_text(text):
            return text
    except Exception:
        pass
    for selector in ["body :not(script):not(style)::text", "body::text"]:
        try:
            values = page.css(selector).getall()
            text = clean_text(" ".join(str(item) for item in values if item))
            if looks_like_visible_text(text):
                return text
        except Exception:
            continue
    try:
        return clean_text(page.text)
    except Exception:
        return clean_text(str(page))


def looks_like_visible_text(text: str) -> bool:
    if len(text) < 80:
        return False
    script_markers = ["var staticPath", "_PAGE =", "function(", "window.", "captcha", "\\u003C", "webpack"]
    marker_hits = sum(1 for marker in script_markers if marker in text)
    job_markers = ["岗位", "职位", "招聘", "薪资", "工作地点", "任职要求", "岗位职责", "实习"]
    job_hits = sum(1 for marker in job_markers if marker in text)
    if marker_hits >= 2 and job_hits < 2:
        return False
    if text.count("\\u") > 30 and job_hits < 3:
        return False
    return True


def fetch_with_scrapling(url: str, timeout_ms: int = 30000) -> tuple[str, dict[str, object]]:
    ensure_browser_event_loop_policy()
    started = time.time()
    errors: list[str] = []
    try:
        from scrapling.fetchers import DynamicFetcher, StealthyFetcher  # type: ignore
    except Exception as exc:
        raise RuntimeError(f"Scrapling fetchers 不可用: {exc}") from exc

    attempts = [
        (
            "scrapling_dynamic_fetcher",
            DynamicFetcher,
            {
                "headless": True,
                "network_idle": True,
                "disable_resources": False,
                "timeout": timeout_ms,
            },
        ),
        (
            "scrapling_stealthy_fetcher",
            StealthyFetcher,
            {
                "headless": True,
                "network_idle": True,
                "timeout": timeout_ms,
            },
        ),
    ]
    for mode, fetcher, kwargs in attempts:
        try:
            page = fetcher.fetch(url, **kwargs)
            text = page_to_text(page)
            meta = {
                "url": url,
                "fetch_mode": mode,
                "elapsed_ms": round((time.time() - started) * 1000, 2),
                "reader_text_chars": len(text),
                "reader_text_preview": text[:300],
                "scrapling_errors": errors,
            }
            if looks_like_visible_text(text):
                return text, meta
            errors.append(f"{mode}: empty_or_script_like_text")
        except TypeError:
            safe_kwargs = {k: v for k, v in kwargs.items() if k in {"headless", "network_idle"}}
            try:
                page = fetcher.fetch(url, **safe_kwargs)
                text = page_to_text(page)
                meta = {
                    "url": url,
                    "fetch_mode": mode,
                    "elapsed_ms": round((time.time() - started) * 1000, 2),
                    "reader_text_chars": len(text),
                    "reader_text_preview": text[:300],
                    "scrapling_errors": errors,
                }
                if looks_like_visible_text(text):
                    return text, meta
                errors.append(f"{mode}: empty_or_script_like_text_after_safe_kwargs")
            except Exception as exc:
                errors.append(f"{mode}: {exc}")
        except Exception as exc:
            errors.append(f"{mode}: {exc}")
    raise RuntimeError("; ".join(errors) or "Scrapling 未抓取到可见文本")


def strip_noise(text: str) -> str:
    compact = clean_text(text)
    return re.sub(r"(隐私政策|用户协议|Cookie|版权所有){2,}", " ", compact)
