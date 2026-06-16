from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data" / "baseline_jobs.csv"


def salary_for(category: str, city: str, exp_idx: int, row_idx: int) -> str:
    base = {
        "数据分析": 9,
        "后端开发": 13,
        "产品经理": 11,
    }[category]
    city_add = {"北京": 5, "上海": 4, "广州": 2, "深圳": 4}[city]
    exp_add = [0, 4, 8][exp_idx]
    low = base + city_add + exp_add + (row_idx % 3)
    high = low + 4 + (row_idx % 4)
    months = [12, 13, 14][row_idx % 3]
    if row_idx % 17 == 0:
        return "面议"
    if row_idx % 19 == 0:
        return f"{low * 1000}-{high * 1000}/月"
    if row_idx % 11 == 0:
        return f"{round(low / 10, 1)}-{round(high / 10, 1)}万"
    return f"{low}-{high}K·{months}薪"


def main() -> None:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    categories = {
        "数据分析": ["数据分析师", "BI分析师", "商业分析师"],
        "后端开发": ["Java后端开发工程师", "Python后端工程师", "服务端开发工程师"],
        "产品经理": ["产品经理", "数据产品经理", "B端产品经理"],
    }
    cities = ["北京", "上海", "广州", "深圳"]
    experiences = ["1-3年", "3-5年", "5-10年"]
    educations = ["大专", "本科", "硕士"]
    sources = ["课程样例", "公开页面手动整理", "CSV导入样例"]
    rows = []
    idx = 1
    for category, titles in categories.items():
        for city in cities:
            for exp_idx, exp in enumerate(experiences):
                for repeat in range(5):
                    title = titles[(repeat + exp_idx) % len(titles)]
                    rows.append(
                        {
                            "岗位名称": title,
                            "岗位类别": category,
                            "公司": f"{city}样例科技{idx:03d}",
                            "城市": city,
                            "薪资": salary_for(category, city, exp_idx, idx),
                            "经验": exp,
                            "学历": educations[(idx + repeat) % len(educations)],
                            "发布时间": f"2026-05-{(idx % 18) + 1:02d}",
                            "来源": sources[idx % len(sources)],
                        }
                    )
                    idx += 1
    with DATA_PATH.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(DATA_PATH)


if __name__ == "__main__":
    main()
