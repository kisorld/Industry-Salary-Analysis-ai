from __future__ import annotations

import csv
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median
from typing import Iterable


CANONICAL_COLUMNS = [
    "job_title",
    "job_category",
    "company",
    "city",
    "salary_text",
    "experience",
    "education",
    "publish_date",
    "source",
]

CHINESE_COLUMNS = {
    "岗位名称": "job_title",
    "岗位类别": "job_category",
    "公司": "company",
    "城市": "city",
    "薪资": "salary_text",
    "薪资文本": "salary_text",
    "经验": "experience",
    "学历": "education",
    "发布时间": "publish_date",
    "来源": "source",
}

CATEGORY_ALIASES = {
    "数据分析": ["数据分析", "bi", "商业分析", "数据运营", "数据专员"],
    "后端开发": ["后端", "java", "python开发", "go开发", "服务端"],
    "产品经理": ["产品经理", "产品专员", "产品运营"],
}


@dataclass
class CleanJob:
    job_title: str
    job_category: str
    company: str
    city: str
    salary_text: str
    experience: str
    education: str
    publish_date: str
    source: str
    salary_min_k: float | None
    salary_max_k: float | None
    salary_mid_k: float | None
    annual_min_k: float | None
    annual_max_k: float | None
    pay_months: int | None
    is_valid_salary: bool
    issue: str


def load_jobs(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = []
        for row in reader:
            normalized = {}
            for key, value in row.items():
                if key is None:
                    continue
                normalized_key = CHINESE_COLUMNS.get(key.strip(), key.strip())
                normalized[normalized_key] = (value or "").strip()
            rows.append(normalized)
    return rows


def infer_category(title: str, existing: str = "") -> str:
    if existing:
        return existing
    low = title.lower()
    for category, aliases in CATEGORY_ALIASES.items():
        if any(alias in low for alias in aliases):
            return category
    return "其他"


def _to_k(value: str, unit: str | None) -> float:
    number = float(value)
    if unit in ("万", "w", "W"):
        return number * 10
    if unit in ("千",):
        return number
    return number


def parse_salary(salary_text: str) -> tuple[float | None, float | None, int | None, str]:
    text = salary_text.strip()
    if not text or any(token in text for token in ["面议", "保密", "薪资不限"]):
        return None, None, None, "薪资为空或面议"

    compact = text.replace(" ", "").replace("Ｋ", "K").replace("k", "K")
    months = 12
    month_match = re.search(r"[·xX*](1[0-8])薪", compact)
    if month_match:
        months = int(month_match.group(1))
    elif "年薪" in compact:
        months = 12

    # Examples: 10-15K, 8千-1.2万, 1.5-2.2万, 300-500/天
    day_match = re.search(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)/?天", compact)
    if day_match:
        low = float(day_match.group(1)) * 21.75 / 1000
        high = float(day_match.group(2)) * 21.75 / 1000
        return round(low, 2), round(high, 2), 12, ""

    hour_match = re.search(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)/?时", compact)
    if hour_match:
        low = float(hour_match.group(1)) * 8 * 21.75 / 1000
        high = float(hour_match.group(2)) * 8 * 21.75 / 1000
        return round(low, 2), round(high, 2), 12, ""

    range_match = re.search(
        r"(\d+(?:\.\d+)?)(K|千|万|w|W)?-(\d+(?:\.\d+)?)(K|千|万|w|W)?",
        compact,
    )
    if range_match:
        low_unit = range_match.group(2) or range_match.group(4) or "K"
        high_unit = range_match.group(4) or low_unit
        low = _to_k(range_match.group(1), low_unit)
        high = _to_k(range_match.group(3), high_unit)
        if not range_match.group(2) and not range_match.group(4) and high >= 1000:
            low = low / 1000
            high = high / 1000
        if low > high:
            return None, None, months, "薪资下限高于上限"
        return round(low, 2), round(high, 2), months, ""

    single_match = re.search(r"(\d+(?:\.\d+)?)(K|千|万|w|W)", compact)
    if single_match:
        value = _to_k(single_match.group(1), single_match.group(2))
        return round(value, 2), round(value, 2), months, ""

    return None, None, months, "薪资格式无法解析"


def clean_jobs(rows: Iterable[dict[str, str]]) -> list[CleanJob]:
    cleaned: list[CleanJob] = []
    seen: set[tuple[str, str, str, str]] = set()
    for row in rows:
        title = row.get("job_title", "")
        company = row.get("company", "")
        city = row.get("city", "")
        salary_text = row.get("salary_text", "")
        key = (title, company, city, salary_text)
        if key in seen:
            continue
        seen.add(key)
        low, high, months, issue = parse_salary(salary_text)
        mid = round((low + high) / 2, 2) if low is not None and high is not None else None
        annual_low = round(low * (months or 12), 2) if low is not None else None
        annual_high = round(high * (months or 12), 2) if high is not None else None
        cleaned.append(
            CleanJob(
                job_title=title,
                job_category=infer_category(title, row.get("job_category", "")),
                company=company,
                city=city,
                salary_text=salary_text,
                experience=row.get("experience", ""),
                education=row.get("education", ""),
                publish_date=row.get("publish_date", ""),
                source=row.get("source", ""),
                salary_min_k=low,
                salary_max_k=high,
                salary_mid_k=mid,
                annual_min_k=annual_low,
                annual_max_k=annual_high,
                pay_months=months,
                is_valid_salary=issue == "",
                issue=issue,
            )
        )
    return cleaned


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return round(sorted_values[0], 2)
    k = (len(sorted_values) - 1) * p
    lower = math.floor(k)
    upper = math.ceil(k)
    if lower == upper:
        return round(sorted_values[int(k)], 2)
    return round(sorted_values[lower] * (upper - k) + sorted_values[upper] * (k - lower), 2)


def group_stats(jobs: Iterable[CleanJob], dimension: str) -> list[dict[str, object]]:
    groups: dict[str, list[float]] = defaultdict(list)
    for job in jobs:
        value = getattr(job, dimension)
        if job.salary_mid_k is not None:
            groups[value or "未填写"].append(job.salary_mid_k)
    result = []
    for name, values in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0])):
        result.append(
            {
                "维度": name,
                "样本量": len(values),
                "均值K/月": round(mean(values), 2),
                "P25": percentile(values, 0.25),
                "中位数": round(median(values), 2),
                "P75": percentile(values, 0.75),
                "P90": percentile(values, 0.90),
                "最低": round(min(values), 2),
                "最高": round(max(values), 2),
            }
        )
    return result


def analyze(jobs: list[CleanJob]) -> dict[str, object]:
    valid = [job for job in jobs if job.salary_mid_k is not None]
    mid_values = [job.salary_mid_k for job in valid if job.salary_mid_k is not None]
    issues = Counter(job.issue for job in jobs if job.issue)
    return {
        "total": len(jobs),
        "valid": len(valid),
        "invalid": len(jobs) - len(valid),
        "parse_accuracy": round(len(valid) / len(jobs) * 100, 2) if jobs else 0.0,
        "overall": {
            "平均值K/月": round(mean(mid_values), 2) if mid_values else 0.0,
            "中位数K/月": round(median(mid_values), 2) if mid_values else 0.0,
            "P25": percentile(mid_values, 0.25),
            "P75": percentile(mid_values, 0.75),
            "P90": percentile(mid_values, 0.90),
        },
        "by_category": group_stats(valid, "job_category"),
        "by_city": group_stats(valid, "city"),
        "by_experience": group_stats(valid, "experience"),
        "by_education": group_stats(valid, "education"),
        "issues": dict(issues),
    }


def write_cleaned_csv(jobs: list[CleanJob], path: Path) -> None:
    fieldnames = list(CleanJob.__dataclass_fields__.keys())
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for job in jobs:
            writer.writerow(job.__dict__)


def write_stats_csv(rows: list[dict[str, object]], path: Path) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def make_insight_text(analysis: dict[str, object]) -> list[str]:
    overall = analysis["overall"]
    by_category = analysis["by_category"]
    by_city = analysis["by_city"]
    insights = [
        f"本次基线数据共 {analysis['total']} 条，成功解析 {analysis['valid']} 条，薪资解析准确率/成功率为 {analysis['parse_accuracy']}%。",
        f"整体月薪中位数为 {overall['中位数K/月']}K，P75 为 {overall['P75']}K，P90 为 {overall['P90']}K。",
    ]
    if by_category:
        top_category = max(by_category, key=lambda row: row["中位数"])
        insights.append(
            f"岗位类别中，{top_category['维度']} 的中位薪资最高，为 {top_category['中位数']}K/月。"
        )
    if by_city:
        top_city = max(by_city, key=lambda row: row["中位数"])
        insights.append(f"城市维度中，{top_city['维度']} 的中位薪资最高，为 {top_city['中位数']}K/月。")
    if analysis["invalid"]:
        insights.append("存在少量无法解析或面议薪资，报告中已作为异常样本排除，不参与分位值统计。")
    insights.append("第二周基线以离线 CSV 数据保证演示稳定，真实招聘网站抓取建议放入第三周增强。")
    return insights
