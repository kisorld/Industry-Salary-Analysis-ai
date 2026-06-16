from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.salary_pandas import parse_salary


CASES = [
    ("10-15K", 10, 15, 12, ""),
    ("10-15k·13薪", 10, 15, 13, ""),
    ("8千-1.2万", 8, 12, 12, ""),
    ("1.5-2.2万", 15, 22, 12, ""),
    ("18000-26000/月", 18, 26, 12, ""),
    ("300-500元/天", 6.53, 10.88, 12, ""),
    ("80-120元/时", 13.92, 20.88, 12, ""),
    ("20K", 20, 20, 12, ""),
    ("24-36万年薪", 20, 30, 12, ""),
    ("面议", None, None, None, "薪资为空或面议"),
]


def test_parse_salary_cases() -> None:
    failures = []
    for text, expected_low, expected_high, expected_months, expected_issue in CASES:
        low, high, months, issue = parse_salary(text)
        if (low, high, months, issue) != (expected_low, expected_high, expected_months, expected_issue):
            failures.append(
                {
                    "text": text,
                    "expected": (expected_low, expected_high, expected_months, expected_issue),
                    "actual": (low, high, months, issue),
                }
            )
    assert not failures, failures


if __name__ == "__main__":
    test_parse_salary_cases()
    print("salary parser tests passed")
