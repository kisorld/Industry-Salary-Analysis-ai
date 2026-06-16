from __future__ import annotations

from pathlib import Path

from app.scraper import extract_jobs_from_html


def main() -> None:
    html = Path("data/public_page_sample.html").read_text(encoding="utf-8")
    rows = extract_jobs_from_html(html, "local-sample", limit=10)
    for row in rows:
        print(row)


if __name__ == "__main__":
    main()

