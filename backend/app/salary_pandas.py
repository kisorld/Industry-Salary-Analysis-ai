from __future__ import annotations

import re
from pathlib import Path

import pandas as pd


COLUMN_MAP = {
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
    "后端开发": ["后端", "java", "python", "go", "服务端"],
    "产品经理": ["产品经理", "产品专员", "产品运营", "b端产品"],
    "前端开发": ["前端", "vue", "react", "小程序"],
}


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={col: COLUMN_MAP.get(str(col).strip(), str(col).strip()) for col in df.columns})
    for col in ["job_title", "job_category", "company", "city", "salary_text", "experience", "education", "publish_date", "source"]:
        if col not in df.columns:
            df[col] = ""
    return df


def infer_category(title: str, current: str = "") -> str:
    if isinstance(current, str) and current.strip():
        return current.strip()
    low = str(title).lower()
    for category, aliases in CATEGORY_ALIASES.items():
        if any(alias in low for alias in aliases):
            return category
    return "其他"


def to_k(value: str, unit: str | None) -> float:
    number = float(value)
    if unit in {"万", "w", "W"}:
        return number * 10
    if unit in {"元"}:
        return number / 1000
    return number


def parse_salary(text: object) -> tuple[float | None, float | None, int | None, str]:
    raw = "" if text is None else str(text).strip()
    if not raw or any(token in raw for token in ["面议", "保密", "薪资不限"]):
        return None, None, None, "薪资为空或面议"
    compact = (
        raw.replace(" ", "")
        .replace("－", "-")
        .replace("—", "-")
        .replace("～", "-")
        .replace("~", "-")
        .replace("Ｋ", "K")
        .replace("k", "K")
    )
    months = 12
    month_match = re.search(r"(?:·|x|X|\*)(1[0-8])薪", compact)
    if month_match:
        months = int(month_match.group(1))

    annual = "年薪" in compact
    day_match = re.search(r"(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)(?:元)?/?天", compact)
    if day_match:
        low = float(day_match.group(1)) * 21.75 / 1000
        high = float(day_match.group(2)) * 21.75 / 1000
        return round(low, 2), round(high, 2), 12, ""

    hour_match = re.search(r"(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)(?:元)?/?时", compact)
    if hour_match:
        low = float(hour_match.group(1)) * 8 * 21.75 / 1000
        high = float(hour_match.group(2)) * 8 * 21.75 / 1000
        return round(low, 2), round(high, 2), 12, ""

    range_match = re.search(r"(\d+(?:\.\d+)?)(K|千|万|w|W|元)?-(\d+(?:\.\d+)?)(K|千|万|w|W|元)?", compact)
    if range_match:
        low_unit = range_match.group(2) or range_match.group(4) or "K"
        high_unit = range_match.group(4) or low_unit
        low = to_k(range_match.group(1), low_unit)
        high = to_k(range_match.group(3), high_unit)
        if not range_match.group(2) and not range_match.group(4) and high >= 1000:
            low = low / 1000
            high = high / 1000
        if annual:
            low = low / 12
            high = high / 12
        if low > high:
            return None, None, months, "薪资下限高于上限"
        return round(low, 2), round(high, 2), months, ""

    single_match = re.search(r"(\d+(?:\.\d+)?)(K|千|万|w|W|元)", compact)
    if single_match:
        value = to_k(single_match.group(1), single_match.group(2))
        if annual:
            value = value / 12
        return round(value, 2), round(value, 2), months, ""
    return None, None, months, "薪资格式无法解析"


def load_dataframe(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in {".xlsx", ".xls"}:
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path, encoding="utf-8-sig")
    return normalize_columns(df)


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = normalize_columns(df).copy()
    df = df.fillna("")
    df["job_category"] = [infer_category(title, current) for title, current in zip(df["job_title"], df["job_category"])]
    parsed = df["salary_text"].apply(parse_salary)
    df["salary_min_k"] = parsed.apply(lambda item: item[0])
    df["salary_max_k"] = parsed.apply(lambda item: item[1])
    df["pay_months"] = parsed.apply(lambda item: item[2])
    df["issue"] = parsed.apply(lambda item: item[3])
    df["is_valid_salary"] = df["issue"].eq("")
    df["salary_mid_k"] = (df["salary_min_k"] + df["salary_max_k"]) / 2
    df["annual_min_k"] = df["salary_min_k"] * df["pay_months"].fillna(12)
    df["annual_max_k"] = df["salary_max_k"] * df["pay_months"].fillna(12)
    return df.drop_duplicates(subset=["job_title", "company", "city", "salary_text"])


def stats_by(df: pd.DataFrame, dimension: str) -> list[dict[str, object]]:
    valid = df[df["is_valid_salary"] & df["salary_mid_k"].notna()]
    if valid.empty:
        return []
    grouped = valid.groupby(dimension, dropna=False)["salary_mid_k"]
    result = grouped.agg(
        样本量="count",
        均值K月="mean",
        P25=lambda s: s.quantile(0.25),
        中位数="median",
        P75=lambda s: s.quantile(0.75),
        P90=lambda s: s.quantile(0.90),
        最低="min",
        最高="max",
    ).reset_index()
    result = result.rename(columns={dimension: "维度"})
    for col in ["均值K月", "P25", "中位数", "P75", "P90", "最低", "最高"]:
        result[col] = result[col].round(2)
    return result.sort_values(["样本量", "维度"], ascending=[False, True]).to_dict(orient="records")


def analyze_dataframe(df: pd.DataFrame) -> dict[str, object]:
    cleaned = clean_dataframe(df)
    valid = cleaned[cleaned["is_valid_salary"] & cleaned["salary_mid_k"].notna()]
    values = valid["salary_mid_k"]
    overall = {
        "平均值K月": round(float(values.mean()), 2) if not values.empty else 0.0,
        "中位数K月": round(float(values.median()), 2) if not values.empty else 0.0,
        "P25": round(float(values.quantile(0.25)), 2) if not values.empty else 0.0,
        "P75": round(float(values.quantile(0.75)), 2) if not values.empty else 0.0,
        "P90": round(float(values.quantile(0.90)), 2) if not values.empty else 0.0,
    }
    issues = cleaned.loc[cleaned["issue"].ne(""), "issue"].value_counts().to_dict()
    return {
        "total": int(len(cleaned)),
        "valid": int(len(valid)),
        "invalid": int(len(cleaned) - len(valid)),
        "parse_accuracy": round(float(len(valid) / len(cleaned) * 100), 2) if len(cleaned) else 0.0,
        "overall": overall,
        "by_category": stats_by(cleaned, "job_category"),
        "by_city": stats_by(cleaned, "city"),
        "by_experience": stats_by(cleaned, "experience"),
        "by_education": stats_by(cleaned, "education"),
        "issues": issues,
        "cleaned_preview": cleaned.head(50).where(pd.notna(cleaned), "").to_dict(orient="records"),
    }


def analyze_file(path: Path) -> tuple[pd.DataFrame, dict[str, object]]:
    df = load_dataframe(path)
    cleaned = clean_dataframe(df)
    return cleaned, analyze_dataframe(df)

