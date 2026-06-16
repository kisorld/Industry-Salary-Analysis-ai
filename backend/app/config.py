from __future__ import annotations

import os
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
LEGACY_ROOT = PROJECT_ROOT
ENV_PATH = BACKEND_ROOT / ".env"
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "outputs"
REPORT_DIR = PROJECT_ROOT / "reports"
TASK_RUNS_DIR = OUTPUT_DIR / "task_runs"


def load_env_file(path: Path = ENV_PATH) -> None:
    candidate_paths = [path, PROJECT_ROOT / ".env"]
    existing = next((candidate for candidate in candidate_paths if candidate.exists()), None)
    if existing is None:
        return
    for raw_line in existing.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_env_file()

QWEN_API_KEY = os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY", "")
QWEN_BASE_URL = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen2.5-32b-instruct")
BROWSER_HEADLESS = os.getenv("BROWSER_HEADLESS", "true").strip().lower() not in {"0", "false", "no", "off"}
PLATFORM_SCRAPE_HEADLESS = os.getenv("PLATFORM_SCRAPE_HEADLESS", "true").strip().lower() not in {"0", "false", "no", "off"}
AUTO_OPEN_LOGIN_PAGE = os.getenv("AUTO_OPEN_LOGIN_PAGE", "true").strip().lower() not in {"0", "false", "no", "off"}
BROWSER_USER_DATA_DIR = Path(os.getenv("BROWSER_USER_DATA_DIR", str(BACKEND_ROOT / ".browser_profile")))
LOGIN_BROWSER_USER_DATA_DIR = Path(os.getenv("LOGIN_BROWSER_USER_DATA_DIR", str(BROWSER_USER_DATA_DIR)))

DEFAULT_SAMPLE = PROJECT_ROOT / "data" / "baseline_jobs.csv"
if not DEFAULT_SAMPLE.exists():
    DEFAULT_SAMPLE = DATA_DIR / "baseline_jobs.csv"


def ensure_dirs() -> None:
    for path in [DATA_DIR, OUTPUT_DIR, REPORT_DIR, TASK_RUNS_DIR]:
        path.mkdir(parents=True, exist_ok=True)
