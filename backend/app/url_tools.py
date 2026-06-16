from __future__ import annotations

import re
from urllib.parse import urlparse


URL_RE = re.compile(r"https?://[^\s,，;；]+|(?:www\.)?[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?:/[^\s,，;；]*)?")


def normalize_url(raw: str) -> str:
    value = (raw or "").strip().strip("\"'")
    if not value:
        return ""
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    parsed = urlparse(value)
    if not parsed.netloc or "." not in parsed.netloc:
        raise ValueError(f"URL 不合法: {raw}")
    return value


def extract_urls(text: str) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []
    for match in URL_RE.findall(text or ""):
        try:
            url = normalize_url(match)
        except ValueError:
            continue
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def resolve_url_inputs(url: str = "", urls: list[str] | None = None) -> list[str]:
    candidates: list[str] = []
    if url:
        candidates.extend(extract_urls(url) or [url])
    for item in urls or []:
        candidates.extend(extract_urls(item) or [item])
    normalized = []
    seen: set[str] = set()
    for item in candidates:
        value = normalize_url(item)
        if value not in seen:
            seen.add(value)
            normalized.append(value)
    return normalized

