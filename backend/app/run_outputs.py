from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .config import TASK_RUNS_DIR


MAX_TASK_RUNS = 10


def safe_name(value: str, fallback: str = "task") -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", str(value or "").strip(), flags=re.UNICODE)
    cleaned = cleaned.strip("_")[:36]
    return cleaned or fallback


def create_task_run_dir(label: str) -> Path:
    TASK_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = TASK_RUNS_DIR / f"{timestamp}_{safe_name(label)}"
    path = base
    suffix = 1
    while path.exists():
        path = TASK_RUNS_DIR / f"{base.name}_{suffix}"
        suffix += 1
    path.mkdir(parents=True)
    return path


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def copy_if_exists(source: str | Path, target: Path) -> str:
    source_path = Path(source)
    if not source_path.exists():
        return ""
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, target)
    return str(target)


def prune_task_runs(max_runs: int = MAX_TASK_RUNS) -> None:
    TASK_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    dirs = [path for path in TASK_RUNS_DIR.iterdir() if path.is_dir()]
    dirs.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    for old_dir in dirs[max_runs:]:
        shutil.rmtree(old_dir, ignore_errors=True)


def list_task_runs() -> list[dict[str, Any]]:
    TASK_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    result: list[dict[str, Any]] = []
    dirs = [path for path in TASK_RUNS_DIR.iterdir() if path.is_dir()]
    dirs.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    for path in dirs[:MAX_TASK_RUNS]:
        metadata_path = path / "metadata.json"
        if metadata_path.exists():
            try:
                result.append(json.loads(metadata_path.read_text(encoding="utf-8")))
                continue
            except Exception:
                pass
        result.append({"label": path.name, "run_dir": str(path), "files": {}})
    return result


def find_task_file(run_dir: str, file_key: str) -> Path | None:
    allowed_keys = {
        "cleaned_jobs_csv",
        "report_docx",
        "rows_preview_csv",
        "partial_rows_csv",
        "analysis_json",
        "ai_output_json",
        "scrape_logs_json",
        "agent_steps_json",
    }
    if file_key not in allowed_keys:
        return None
    base = Path(run_dir).resolve()
    root = TASK_RUNS_DIR.resolve()
    try:
        base.relative_to(root)
    except ValueError:
        return None
    metadata_path = base / "metadata.json"
    if not metadata_path.exists():
        return None
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    files = metadata.get("files") if isinstance(metadata, dict) else {}
    if not isinstance(files, dict):
        return None
    file_path = files.get(file_key)
    if not file_path:
        return None
    path = Path(str(file_path)).resolve()
    try:
        path.relative_to(base)
    except ValueError:
        return None
    return path if path.exists() else None


def archive_task_run(
    label: str,
    *,
    query: dict[str, Any] | None = None,
    rows: list[dict[str, Any]] | None = None,
    partial_rows: list[dict[str, Any]] | None = None,
    analysis: dict[str, Any] | None = None,
    ai: dict[str, Any] | None = None,
    logs: list[dict[str, Any]] | None = None,
    steps: list[dict[str, Any]] | None = None,
    report_path: str | Path | None = None,
    cleaned_path: str | Path | None = None,
    source_csv_paths: list[str] | None = None,
) -> dict[str, Any]:
    run_dir = create_task_run_dir(label)
    files: dict[str, str] = {}

    if rows:
        rows_path = run_dir / "rows_preview.csv"
        pd.DataFrame(rows).to_csv(rows_path, index=False, encoding="utf-8-sig")
        files["rows_preview_csv"] = str(rows_path)
    if partial_rows:
        partial_path = run_dir / "partial_rows.csv"
        pd.DataFrame(partial_rows).to_csv(partial_path, index=False, encoding="utf-8-sig")
        files["partial_rows_csv"] = str(partial_path)
    if analysis is not None:
        analysis_path = run_dir / "analysis.json"
        write_json(analysis_path, analysis)
        files["analysis_json"] = str(analysis_path)
    if ai is not None:
        ai_path = run_dir / "ai_output.json"
        write_json(ai_path, ai)
        files["ai_output_json"] = str(ai_path)
    if logs is not None:
        logs_path = run_dir / "scrape_logs.json"
        write_json(logs_path, logs)
        files["scrape_logs_json"] = str(logs_path)
    if steps is not None:
        steps_path = run_dir / "agent_steps.json"
        write_json(steps_path, steps)
        files["agent_steps_json"] = str(steps_path)
    if cleaned_path:
        copied = copy_if_exists(cleaned_path, run_dir / "cleaned_jobs.csv")
        if copied:
            files["cleaned_jobs_csv"] = copied
    if report_path:
        copied = copy_if_exists(report_path, run_dir / "report.docx")
        if copied:
            files["report_docx"] = copied
    if source_csv_paths:
        raw_dir = run_dir / "source_csv"
        copied_sources: list[str] = []
        for index, path in enumerate(source_csv_paths, start=1):
            source = Path(path)
            if not source.exists():
                continue
            target = raw_dir / f"{index:02d}_{source.name}"
            copied_sources.append(copy_if_exists(source, target))
        if copied_sources:
            files["source_csv_dir"] = str(raw_dir)

    metadata = {
        "label": label,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "run_dir": str(run_dir),
        "query": query or {},
        "files": files,
    }
    write_json(run_dir / "metadata.json", metadata)
    prune_task_runs()
    return metadata
