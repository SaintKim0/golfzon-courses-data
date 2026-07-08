#!/usr/bin/env python3
"""
GitHub Actions PoC: 골프zon 목록 페이지가 Selenium에서 로드되는지 확인합니다.
"""
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
DEBUG_DIR = REPO_ROOT / "poc-debug"
sys.path.insert(0, str(SCRIPTS_DIR))

from golfzon_crawler import BASE_LIST_URL, list_page_cards, setup_driver


def _write_debug(drv, message: str) -> None:
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    (DEBUG_DIR / "error.txt").write_text(message, encoding="utf-8")
    try:
        (DEBUG_DIR / "page.html").write_text(drv.page_source[:50000], encoding="utf-8")
    except Exception:
        pass
    try:
        drv.save_screenshot(str(DEBUG_DIR / "screenshot.png"))
    except Exception:
        pass


def main() -> int:
    print("=" * 60)
    print("PoC: 골프zon 코스 목록 페이지 Selenium 접속 테스트")
    print("=" * 60)

    drv = setup_driver(headless=True)
    try:
        url = BASE_LIST_URL.format(page=1)
        print(f"URL: {url}")
        drv.get(url)
        print(f"title: {drv.title}")
        print(f"current_url: {drv.current_url}")

        courses = list_page_cards(drv)
        if not courses:
            msg = (
                "FAIL: #datalist에서 코스를 찾지 못했습니다.\n"
                f"title: {drv.title}\n"
                f"current_url: {drv.current_url}\n"
                "가능한 원인: GitHub Actions IP 차단, headless 탐지, 사이트 구조 변경\n"
            )
            print(msg)
            _write_debug(drv, msg)
            return 1

        print(f"OK: {len(courses)}개 코스 카드 로드 성공")
        for course in courses[:3]:
            print(f"  - {course['name']}")
        if len(courses) > 3:
            print(f"  ... 외 {len(courses) - 3}개")

        print("\nPoC 성공 — GitHub Actions에서 크롤링 가능합니다.")
        return 0
    finally:
        drv.quit()


if __name__ == "__main__":
    sys.exit(main())
