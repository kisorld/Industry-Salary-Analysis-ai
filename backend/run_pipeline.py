from __future__ import annotations

import json
import sys
from pathlib import Path

from app.ai_agent import generate_ai_report
from app.config import DEFAULT_SAMPLE, OUTPUT_DIR, REPORT_DIR, ensure_dirs
from app.reporting import build_report
from app.salary_pandas import analyze_file


def main() -> int:
    ensure_dirs()
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SAMPLE
    cleaned, analysis = analyze_file(source)
    cleaned.to_csv(OUTPUT_DIR / "cleaned_jobs.csv", index=False, encoding="utf-8-sig")
    ai = generate_ai_report(analysis)
    build_report(analysis, REPORT_DIR / "salary_insight_report.docx", ai.get("text", ""))
    print(json.dumps({"analysis": analysis, "ai": ai}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

