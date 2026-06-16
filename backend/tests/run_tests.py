from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from test_salary_parser import test_parse_salary_cases


def main() -> None:
    test_parse_salary_cases()
    print("all tests passed")


if __name__ == "__main__":
    main()
