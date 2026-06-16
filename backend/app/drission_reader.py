from __future__ import annotations

import re
import time
from typing import Any

from pathlib import Path

from .config import BROWSER_HEADLESS, BROWSER_USER_DATA_DIR


JOB_SELECTORS = [
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
    "[class*=position]",
    "article",
    "li",
]


def clean_text(text: object) -> str:
    return " ".join(str(text or "").split())


def looks_like_job_text(text: str) -> bool:
    compact = clean_text(text)
    if len(compact) < 4:
        return False
    return any(token in compact for token in ["岗位", "职位", "招聘", "工程师", "分析师", "产品经理", "实习", "经验", "学历", "K", "薪"])


def make_options(headless: bool = True, user_data_dir: str | Path | None = None) -> Any:
    try:
        from DrissionPage import ChromiumOptions  # type: ignore
    except Exception as exc:
        raise RuntimeError(f"DrissionPage 未安装或不可用: {exc}") from exc
    options = ChromiumOptions()
    profile_dir = Path(user_data_dir) if user_data_dir else BROWSER_USER_DATA_DIR
    profile_dir.mkdir(parents=True, exist_ok=True)
    for method_name in ["set_user_data_path", "set_user_data_dir"]:
        try:
            getattr(options, method_name)(str(profile_dir))
            break
        except Exception:
            continue
    else:
        try:
            options.set_argument(f"--user-data-dir={profile_dir}")
        except Exception:
            pass
    if headless:
        try:
            options.headless(True)
        except Exception:
            options.set_argument("--headless=new")
    for arg in [
        "--disable-gpu",
        "--no-first-run",
        "--disable-dev-shm-usage",
        "--lang=zh-CN",
        "--window-size=1366,900",
    ]:
        try:
            options.set_argument(arg)
        except Exception:
            pass
    try:
        options.set_user_agent(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/115.0.0.0 Safari/537.36"
        )
    except Exception:
        pass
    return options


def page_text(page: Any) -> str:
    for expr in [
        "return document.body ? document.body.innerText : '';",
        "return document.documentElement ? document.documentElement.innerText : '';",
    ]:
        try:
            text = clean_text(page.run_js(expr))
            if text:
                return text
        except Exception:
            continue
    try:
        return clean_text(page.html)
    except Exception:
        return ""


def collect_cards(page: Any, limit: int = 80) -> tuple[list[str], list[str]]:
    events: list[str] = []
    cards: list[str] = []
    seen: set[str] = set()

    def collect_once() -> None:
        for selector in JOB_SELECTORS:
            try:
                elements = page.eles(f"css:{selector}")
            except Exception:
                continue
            for ele in elements[:limit]:
                try:
                    text = clean_text(ele.text)
                except Exception:
                    continue
                if not looks_like_job_text(text):
                    continue
                key = text[:160]
                if key in seen:
                    continue
                seen.add(key)
                cards.append(text[:1200])
                if len(cards) >= limit:
                    return

    collect_once()
    events.append(f"drission_collect_initial:{len(cards)}")
    stable_rounds = 0
    for idx in range(12):
        before = len(cards)
        try:
            page.run_js("window.scrollBy(0, Math.max(window.innerHeight * 0.9, 700));")
            time.sleep(0.8)
            collect_once()
            events.append(f"drission_collect_round:{idx + 1}:{len(cards)}")
            if len(cards) == before:
                stable_rounds += 1
            else:
                stable_rounds = 0
            if stable_rounds >= 3 or len(cards) >= limit:
                break
        except Exception:
            events.append(f"drission_collect_round_failed:{idx + 1}")
            break
    return cards, events


def fetch_with_drission(url: str, timeout: int = 30, limit: int = 80) -> tuple[str, dict[str, object]]:
    started = time.time()
    try:
        from DrissionPage import ChromiumPage  # type: ignore
    except Exception as exc:
        raise RuntimeError(f"DrissionPage 未安装或不可用: {exc}") from exc

    page = None
    try:
        page = ChromiumPage(make_options(headless=BROWSER_HEADLESS))
        try:
            page.set.timeouts(base=timeout)
        except Exception:
            pass
        page.get(url)
        time.sleep(1.2)
        for text in ["查看更多", "展开", "更多"]:
            try:
                ele = page.ele(f"text:{text}", timeout=0.5)
                if ele:
                    ele.click()
                    time.sleep(0.5)
            except Exception:
                pass
        cards, events = collect_cards(page, limit=limit)
        text = "\n".join(f"[岗位卡片{idx}] {card}" for idx, card in enumerate(cards, start=1))
        if not text:
            text = page_text(page)
        html_len = 0
        try:
            html_len = len(str(page.html).encode("utf-8", errors="ignore"))
        except Exception:
            pass
        return text, {
            "url": url,
            "fetch_mode": "drissionpage_chromium",
            "browser_headless": BROWSER_HEADLESS,
            "elapsed_ms": round((time.time() - started) * 1000, 2),
            "bytes": html_len,
            "job_card_count": len(cards),
            "wait_events": events,
            "reader_text_chars": len(text),
            "reader_text_preview": text[:300],
        }
    finally:
        if page is not None:
            try:
                page.quit()
            except Exception:
                pass


def is_script_like(text: str) -> bool:
    markers = ["var staticPath", "_PAGE =", "captcha", "\\u003C", "webpack", "function("]
    return sum(1 for marker in markers if marker in text) >= 2
