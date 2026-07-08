#!/usr/bin/env python3
"""
GitHub Actions용 신규 코스 크롤링 스크립트.
repo 루트의 golfzon_all_courses.csv를 갱신합니다. (git commit/push는 workflow가 담당)
"""
import csv
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
CSV_PATH = REPO_ROOT / "golfzon_all_courses.csv"

sys.path.insert(0, str(SCRIPTS_DIR))

from golfzon_crawler import crawl_new_courses_only, save_csv


def main() -> int:
    print("=" * 60)
    print("신규 코스 크롤링 (CI)")
    print("=" * 60)

    if not CSV_PATH.exists():
        print(f"ERROR: CSV 없음 — {CSV_PATH}")
        return 1

    print(f"기준 CSV: {CSV_PATH}")

    new_rows = crawl_new_courses_only(
        existing_csv_path=str(CSV_PATH),
        start_page=1,
        max_pages=50,
        pause=0.5,
    )

    if not new_rows:
        print("신규 코스 없음 — CSV 변경 없음")
        return 0

    print(f"신규 레코드 {len(new_rows)}개 발견 — CSV 병합 중...")

    existing_rows = []
    with open(CSV_PATH, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        existing_rows = list(reader)

    merged = existing_rows + new_rows
    save_csv(merged, str(CSV_PATH))

    new_course_names = sorted({row["course_name"] for row in new_rows})
    print(f"저장 완료: 총 {len(merged)}개 레코드, 신규 코스 {len(new_course_names)}개")
    for name in new_course_names[:10]:
        print(f"  + {name}")
    if len(new_course_names) > 10:
        print(f"  ... 외 {len(new_course_names) - 10}개")

    return 0


if __name__ == "__main__":
    sys.exit(main())
