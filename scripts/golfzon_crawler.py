import csv
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

BASE_LIST_URL = "https://www.golfzon.com/course/main?page={page}&orderType=1&areaNo=0"
BASE_HOST = "https://www.golfzon.com"

def setup_driver(headless: bool = True) -> webdriver.Chrome:
    opts = webdriver.ChromeOptions()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1920,1200")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--lang=ko-KR")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument(
        "user-agent=Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    if os.environ.get("CI"):
        drv = webdriver.Chrome(options=opts)
    else:
        service = Service(ChromeDriverManager().install())
        drv = webdriver.Chrome(service=service, options=opts)

    try:
        drv.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": (
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
                )
            },
        )
    except Exception:
        pass

    drv.set_page_load_timeout(60)
    return drv

def wait_css(drv: webdriver.Chrome, css: str, timeout: int = 15):
    return WebDriverWait(drv, timeout).until(EC.presence_of_element_located((By.CSS_SELECTOR, css)))

def list_page_cards(drv: webdriver.Chrome) -> List[Dict[str, str]]:
    """리스트 페이지에서 코스 정보를 즉시 추출하여 반환"""
    try:
        wait_css(drv, "#datalist")
        time.sleep(1.0)  # 충분한 대기 시간
        
        # CSS 셀렉터로 직접 링크와 제목을 찾아서 즉시 추출
        links = drv.find_elements(By.CSS_SELECTOR, "#datalist li dd.course_posi.ellipsis a[title]")
        course_data = []
        
        for link in links:
            try:
                name = link.get_attribute("title").strip()
                href = link.get_attribute("href") or ""
                if href.startswith("/"):
                    href = BASE_HOST + href
                if name and href:
                    course_data.append({"name": name, "url": href})
            except Exception as e:
                print(f"링크 파싱 에러: {e}")
                continue
                
        return course_data
    except Exception as e:
        print(f"카드 목록 가져오기 에러: {e}")
        return []

def _numbers_from_tds(tds: List) -> List[int]:
    """td 텍스트에서 숫자만 뽑아 정수 리스트로 (길이가 9 미만이면 0으로 패딩)"""
    vals: List[int] = []
    for td in tds[:9]:
        txt = td.text.strip()
        num = re.sub(r"[^\d]", "", txt)
        vals.append(int(num) if num else 0)
    while len(vals) < 9:
        vals.append(0)
    return vals

def _table_to_tee_rows(tbl) -> Tuple[List[Dict[str, List[int]]], List[int]]:
    """table -> ([{'tee': 'White Tee', 'holes':[...9개]} ...], [par1, par2, ...])"""
    rows: List[Dict[str, List[int]]] = []
    par_values: List[int] = []
    
    # PAR 정보는 thead에 있음
    try:
        thead = tbl.find_element(By.TAG_NAME, "thead")
        thead_trs = thead.find_elements(By.CSS_SELECTOR, "tr")
        print(f"thead에서 {len(thead_trs)}개 행 발견")
        
        # thead에서 PAR 행 찾기
        for i, tr in enumerate(thead_trs):
            ths = tr.find_elements(By.TAG_NAME, "th")
            if not ths:
                continue
            
            first_cell_text = ths[0].text.strip().upper()
            print(f"thead 행 {i}: 첫 번째 셀 = '{first_cell_text}'")
            
            if first_cell_text == "PAR":
                # PAR 행에서 숫자 추출
                par_candidates = []
                for th in ths[1:]:  # 첫 번째 셀(PAR) 제외
                    text = th.text.strip()
                    num = re.sub(r"[^\d]", "", text)
                    par_candidates.append(int(num) if num else 0)
                
                print(f"PAR 값들: {par_candidates}")
                if any(3 <= val <= 5 for val in par_candidates if val > 0):
                    par_values = par_candidates
                    print(f"PAR 값으로 확정: {par_values}")
                    break
    except Exception as e:
        print(f"thead에서 PAR 찾기 실패: {e}")
    
    # tbody에서 티별 거리 행들 처리
    tbody = tbl.find_element(By.TAG_NAME, "tbody")
    tbody_trs = tbody.find_elements(By.CSS_SELECTOR, "tr")
    print(f"tbody에서 {len(tbody_trs)}개 행 발견")
    
    for i, tr in enumerate(tbody_trs):
        ths = tr.find_elements(By.TAG_NAME, "th")
        tds = tr.find_elements(By.TAG_NAME, "td")
        if not ths or not tds:
            continue
        
        tee = ths[0].text.strip()
        holes = _numbers_from_tds(tds)
        
        print(f"tbody 행 {i}: 티='{tee}', 거리={holes}")
        
        # MAP 행, PAR 행 등 숫자 아닌 행 걸러내기 (모두 0이면 스킵)
        if (any(h > 0 for h in holes) and 
            tee.upper() not in ["PAR", "MAP"] and
            not tee.isdigit() and
            len(tee) > 2):  # 티 이름은 보통 3글자 이상
            rows.append({"tee": tee, "holes": holes})
            print(f"유효한 티 행 추가: {tee}")
    
    print(f"최종 결과: {len(rows)}개 티, PAR={par_values}")
    return rows, par_values

def parse_difficulty_info(drv: webdriver.Chrome) -> Tuple[float, float]:
    """코스 난이도와 그린 난이도 파싱"""
    try:
        course_difficulty = 0.0
        green_difficulty = 0.0
        
        # 코스 난이도 파싱 - star_point_course1 클래스 안에서 찾기
        try:
            course_container = drv.find_element(By.CSS_SELECTOR, "p.star_point_course1")
            course_star = course_container.find_element(By.CSS_SELECTOR, "span[class*='star_s']")
            class_name = course_star.get_attribute("class")
            print(f"코스 난이도 클래스: {class_name}")
            
            import re
            match = re.search(r"star_s(\d+)", class_name)
            if match:
                star_num = int(match.group(1))
                course_difficulty = star_num / 2.0
                print(f"코스 난이도 계산: {star_num} / 2 = {course_difficulty}")
        except Exception as e:
            print(f"코스 난이도 파싱 실패: {e}")
        
        # 그린 난이도 파싱 - star_point_course2 클래스 안에서 찾기
        try:
            green_container = drv.find_element(By.CSS_SELECTOR, "p.star_point_course2")
            green_star = green_container.find_element(By.CSS_SELECTOR, "span[class*='star_s']")
            class_name = green_star.get_attribute("class")
            print(f"그린 난이도 클래스: {class_name}")
            
            import re
            match = re.search(r"star_s(\d+)", class_name)
            if match:
                star_num = int(match.group(1))
                green_difficulty = star_num / 2.0
                print(f"그린 난이도 계산: {star_num} / 2 = {green_difficulty}")
        except Exception as e:
            print(f"그린 난이도 파싱 실패: {e}")
        
        print(f"최종 난이도 정보: 코스={course_difficulty}, 그린={green_difficulty}")
        return course_difficulty, green_difficulty
        
    except Exception as e:
        print(f"난이도 파싱 에러: {e}")
        return 0.0, 0.0

def parse_out_in_tables(drv: webdriver.Chrome) -> Tuple[List[Dict], List[Dict], List[int], List[int], float, float]:
    """상세 페이지에서 OUT, IN 표를 찾아 파싱"""
    try:
        # hall_info 섹션이 로드될 때까지 대기
        wait_css(drv, "div.hall_info")
        time.sleep(1.0)  # 테이블 로딩 대기
        
        # 난이도 정보 파싱
        course_difficulty, green_difficulty = parse_difficulty_info(drv)
        
        # 테이블을 찾고 즉시 파싱
        tables = drv.find_elements(By.CSS_SELECTOR, "div.hall_info table")
        if len(tables) < 2:
            # 구조가 다르면 유연하게: hall_info 전체에서 table을 더 탐색
            all_tables = drv.find_elements(By.TAG_NAME, "table")
            tables = [t for t in all_tables if len(t.find_elements(By.TAG_NAME, "tbody")) > 0][:2]
        
        if not tables:
            print("테이블을 찾을 수 없습니다.")
            return [], [], [], [], course_difficulty, green_difficulty

        # 일반적으로 0번=OUT, 1번=IN
        out_tbl = tables[0] if len(tables) >= 1 else None
        in_tbl  = tables[1] if len(tables) >= 2 else None

        out_rows, out_pars = _table_to_tee_rows(out_tbl) if out_tbl else ([], [])
        in_rows, in_pars = _table_to_tee_rows(in_tbl) if in_tbl else ([], [])

        print(f"OUT 테이블: {len(out_rows)}개 행, PAR: {out_pars}, IN 테이블: {len(in_rows)}개 행, PAR: {in_pars}")
        return out_rows, in_rows, out_pars, in_pars, course_difficulty, green_difficulty
        
    except Exception as e:
        print(f"테이블 파싱 에러: {e}")
        return [], [], [], [], 0.0, 0.0

def merge_out_in(course_name: str, detail_url: str,
                 out_rows: List[Dict], in_rows: List[Dict], 
                 out_pars: List[int], in_pars: List[int],
                 course_difficulty: float, green_difficulty: float) -> List[Dict]:
    """티 이름 기준으로 OUT 9홀 + IN 9홀을 합쳐 18홀 레코드로 변환"""
    # 티 이름을 키로 매핑
    def to_map(rows: List[Dict]) -> Dict[str, List[int]]:
        return {r["tee"]: r["holes"] for r in rows}

    out_map = to_map(out_rows)
    in_map  = to_map(in_rows)

    # PAR 정보를 18홀로 합치기 (9홀씩 패딩)
    out_pars_padded = out_pars + [0] * (9 - len(out_pars)) if len(out_pars) < 9 else out_pars[:9]
    in_pars_padded = in_pars + [0] * (9 - len(in_pars)) if len(in_pars) < 9 else in_pars[:9]
    pars18 = out_pars_padded + in_pars_padded

    tees = sorted(set(out_map.keys()) | set(in_map.keys()))
    merged: List[Dict] = []
    for tee in tees:
        out9 = out_map.get(tee, [0]*9)
        in9  = in_map.get(tee,  [0]*9)
        holes18 = out9 + in9
        merged.append({
            "course_name": course_name,
            "detail_url": detail_url,
            "tee": tee,
            "course_difficulty": course_difficulty,
            "green_difficulty": green_difficulty,
            **{f"hole_{i+1}": holes18[i] for i in range(18)},
            **{f"par_{i+1}": pars18[i] for i in range(18)},
            "out_sum_m": sum(out9),
            "in_sum_m": sum(in9),
            "total_sum_m": sum(holes18),
        })
    return merged

def crawl_all_courses(start_page: int = 1, max_pages: int = 300, pause: float = 0.5, test_limit: int = None) -> List[Dict]:
    """전체 골프장 크롤링 (필터링 없이 모든 데이터 수집)"""
    drv = setup_driver(headless=True)
    rows18: List[Dict] = []
    total_courses = 0
    
    try:
        for p in range(start_page, start_page + max_pages):
            print(f"\n📄 페이지 {p} 처리 중... (총 수집: {total_courses}개 코스)")
            list_url = BASE_LIST_URL.format(page=p)
            drv.get(list_url)
            time.sleep(1.5)  # 페이지 로딩 대기 시간 증가

            # 카드 정보를 즉시 추출
            course_data = list_page_cards(drv)
            if not course_data:
                print(f"페이지 {p}에서 코스 데이터를 찾을 수 없습니다.")
                break

            print(f"페이지 {p}에서 {len(course_data)}개 코스 발견")
            
            for i, course in enumerate(course_data):
                # 테스트 모드인 경우 제한된 수만 처리
                if test_limit and total_courses >= test_limit:
                    print(f"\n🎯 테스트 모드: {test_limit}개 코스 수집 완료. 크롤링을 종료합니다.")
                    break
                
                try:
                    course_name = course["name"]
                    detail_url = course["url"]
                    
                    print(f"\n🏌️ 코스 {total_courses + 1}: {course_name} 처리 중...")
                    drv.get(detail_url)
                    time.sleep(1.5)  # 상세 페이지 로딩 대기

                    out_rows, in_rows, out_pars, in_pars, course_difficulty, green_difficulty = parse_out_in_tables(drv)
                    if not out_rows and not in_rows:
                        print(f"❌ 테이블 데이터를 찾을 수 없음 - 스킵")
                        continue

                    merged = merge_out_in(course_name, detail_url, out_rows, in_rows, out_pars, in_pars, course_difficulty, green_difficulty)
                    rows18.extend(merged)
                    total_courses += 1
                    print(f"✅ {len(merged)}개 티 데이터 수집 완료 (코스:{course_difficulty}, 그린:{green_difficulty})")

                    time.sleep(pause)
                except Exception as e:
                    print(f"❌ 처리 중 에러: {e}")
                    continue
            
            # 테스트 모드인 경우 목표 달성 시 중단
            if test_limit and total_courses >= test_limit:
                break
    finally:
        drv.quit()
    return rows18

def save_csv(rows: List[Dict], path: str = "golfzon_all_courses.csv") -> None:
    """CSV 파일로 저장"""
    cols = ["course_name", "detail_url", "tee", "course_difficulty", "green_difficulty"] + [f"hole_{i}" for i in range(1, 19)] + [f"par_{i}" for i in range(1, 19)] + [
        "out_sum_m", "in_sum_m", "total_sum_m"
    ]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, 0) for k in cols})


def load_existing_course_keys(path: str) -> Dict[str, set]:
    """
    기존 CSV에서 코스 식별 키 세트를 로드한다.
    - name_set: course_name
    - url_set: detail_url
    이미 저장된 코스를 빠르게 건너뛰기 위한 용도.
    """
    name_set = set()
    url_set = set()

    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = (row.get("course_name") or "").strip()
                url = (row.get("detail_url") or "").strip()
                if name:
                    name_set.add(name)
                if url:
                    url_set.add(url)
        print(f"✅ 기존 CSV에서 {len(name_set)}개 코스 이름, {len(url_set)}개 URL 로드")
    except FileNotFoundError:
        print("📁 기존 CSV 파일이 없어, 전체 코스를 신규로 간주합니다.")
    except Exception as e:
        print(f"❌ 기존 CSV 로드 중 오류: {e}")

    return {"names": name_set, "urls": url_set}


def crawl_new_courses_only(
    existing_csv_path: str = "golfzon_all_courses.csv",
    start_page: int = 1,
    max_pages: int = 100,
    pause: float = 0.5,
) -> List[Dict]:
    """
    기존 CSV에 없는 '신규 코스'만 크롤링한다.
    - 리스트 페이지에서 코스 카드 정보를 읽어오고,
    - 기존 CSV의 course_name / detail_url 과 비교하여
      아직 없는 코스만 상세 페이지 크롤링.
    - 연속으로 여러 페이지에서 신규 코스가 전혀 없으면 조기 종료.
    """
    key_sets = load_existing_course_keys(existing_csv_path)
    existing_names = key_sets["names"]
    existing_urls = key_sets["urls"]

    drv = setup_driver(headless=True)
    rows18: List[Dict] = []
    new_courses_count = 0
    consecutive_empty_pages = 0

    try:
        for p in range(start_page, start_page + max_pages):
            print(f"\n📄 [신규 모드] 페이지 {p} 처리 중... (현재 신규 수집: {new_courses_count}개 코스)")
            list_url = BASE_LIST_URL.format(page=p)
            drv.get(list_url)
            time.sleep(1.5)

            course_data = list_page_cards(drv)
            if not course_data:
                print(f"페이지 {p}에서 코스 데이터를 찾을 수 없습니다.")
                break

            print(f"페이지 {p}에서 {len(course_data)}개 코스 발견")

            page_new_found = 0

            for course in course_data:
                try:
                    course_name = course["name"]
                    detail_url = course["url"]

                    # 기존 CSV에 이미 있는 코스면 스킵
                    if course_name in existing_names or detail_url in existing_urls:
                        continue

                    print(f"\n🆕 신규 코스 {new_courses_count + 1}: {course_name} 처리 중...")
                    drv.get(detail_url)
                    time.sleep(1.5)

                    out_rows, in_rows, out_pars, in_pars, course_difficulty, green_difficulty = parse_out_in_tables(drv)
                    if not out_rows and not in_rows:
                        print("❌ 테이블 데이터를 찾을 수 없음 - 스킵")
                        continue

                    merged = merge_out_in(
                        course_name,
                        detail_url,
                        out_rows,
                        in_rows,
                        out_pars,
                        in_pars,
                        course_difficulty,
                        green_difficulty,
                    )
                    rows18.extend(merged)
                    new_courses_count += 1
                    page_new_found += 1

                    # 방금 수집한 코스를 기존 세트에 추가하여 중복 방지
                    existing_names.add(course_name)
                    existing_urls.add(detail_url)

                    print(f"✅ 신규 코스 티 데이터 {len(merged)}개 수집 완료 (코스:{course_difficulty}, 그린:{green_difficulty})")
                    time.sleep(pause)
                except Exception as e:
                    print(f"❌ 신규 코스 처리 중 에러: {e}")
                    continue

            if page_new_found == 0:
                consecutive_empty_pages += 1
                print(f"ℹ️ 페이지 {p}에서 신규 코스가 없습니다. 연속 {consecutive_empty_pages}페이지 무신규.")
            else:
                consecutive_empty_pages = 0

            # 연속 3페이지 동안 신규 코스가 전혀 없으면 조기 종료
            if consecutive_empty_pages >= 3:
                print("✅ 최근 여러 페이지에서 신규 코스가 없어 크롤링을 종료합니다.")
                break
    finally:
        drv.quit()

    print(f"\n🎯 신규 코스 크롤링 완료: 총 {new_courses_count}개 코스, {len(rows18)}개 레코드")
    return rows18

def print_summary(rows: List[Dict]) -> None:
    """수집 결과 요약을 터미널에 출력"""
    if not rows:
        print("❌ 수집된 데이터가 없습니다.")
        return
    
    print("\n" + "="*80)
    print("📊 골프존 전체 코스 크롤링 결과 요약")
    print("="*80)
    
    # 코스별 통계
    courses = {}
    for row in rows:
        course_name = row["course_name"]
        if course_name not in courses:
            courses[course_name] = {
                "tees": [],
                "total_distance": 0,
                "url": row["detail_url"]
            }
        courses[course_name]["tees"].append(row["tee"])
        courses[course_name]["total_distance"] = max(courses[course_name]["total_distance"], row["total_sum_m"])
    
    print(f"🏌️ 총 수집된 코스 수: {len(courses)}개")
    print(f"📋 총 레코드 수 (코스 x 티): {len(rows)}개")
    
    # White Tee 데이터만 필터링하여 상세 정보 출력
    white_tee_rows = [row for row in rows if "White" in row["tee"]]
    
    if white_tee_rows:
        print(f"\n🏌️ White Tee 코스별 홀 거리 상세 정보:")
        print("="*80)
        
        for i, row in enumerate(white_tee_rows, 1):
            course_name = row["course_name"]
            course_difficulty = row.get("course_difficulty", 0.0)
            green_difficulty = row.get("green_difficulty", 0.0)
            
            # 난이도 정보가 있으면 표시
            if course_difficulty > 0 or green_difficulty > 0:
                difficulty_info = f" (코스난이도: {course_difficulty}, 그린난이도: {green_difficulty})"
            else:
                difficulty_info = ""
            
            print(f"\n{i:2d}. {course_name}{difficulty_info}")
            print(f"    🔗 URL: {row['detail_url']}")
            print(f"    📏 총 거리: {row['total_sum_m']:,}m (OUT: {row['out_sum_m']:,}m + IN: {row['in_sum_m']:,}m)")
            
            # OUT 코스 (1-9홀)
            print(f"\n    🏌️ OUT 코스 (1-9홀):")
            out_holes = []
            for hole_num in range(1, 10):
                distance = row.get(f"hole_{hole_num}", 0)
                par = row.get(f"par_{hole_num}", 0)
                if par > 0:
                    out_holes.append(f"{hole_num}홀(파{par}):{distance}m")
                else:
                    out_holes.append(f"{hole_num}홀:{distance}m")
            print(f"        {' | '.join(out_holes)}")
            
            # IN 코스 (10-18홀)
            print(f"\n    🏌️ IN 코스 (10-18홀):")
            in_holes = []
            for hole_num in range(10, 19):
                distance = row.get(f"hole_{hole_num}", 0)
                par = row.get(f"par_{hole_num}", 0)
                if par > 0:
                    in_holes.append(f"{hole_num}홀(파{par}):{distance}m")
                else:
                    in_holes.append(f"{hole_num}홀:{distance}m")
            print(f"        {' | '.join(in_holes)}")
            
            print("-" * 80)
    else:
        print("\n❌ White Tee 데이터를 찾을 수 없습니다.")
    
    # 전체 티별 통계
    tee_stats = {}
    for row in rows:
        tee = row["tee"]
        if tee not in tee_stats:
            tee_stats[tee] = {"count": 0, "total_distance": 0}
        tee_stats[tee]["count"] += 1
        tee_stats[tee]["total_distance"] += row["total_sum_m"]
    
    print(f"\n🏆 전체 티별 통계:")
    print("-" * 60)
    for tee, stats in sorted(tee_stats.items()):
        avg_distance = stats["total_distance"] // stats["count"] if stats["count"] > 0 else 0
        print(f"   {tee}: {stats['count']}개 코스, 평균 거리 {avg_distance:,}m")
    
    print("\n" + "="*80)

if __name__ == "__main__":
    print("="*60)
    print("🏌️ 골프존 코스 크롤링 시작")
    print("="*60)
    
    # 테스트 모드 선택
    test_mode = input("테스트 모드로 10개만 크롤링하시겠습니까? (y/n): ").strip().lower()
    
    if test_mode == 'y':
        print("🧪 테스트 모드: 10개 코스만 크롤링합니다.")
        test_limit = 10
        filename = "golfzon_test_10개.csv"
    else:
        print("전체 골프장의 데이터를 수집합니다.")
        print("필터링 없이 모든 데이터를 수집하므로 시간이 오래 걸릴 수 있습니다.")
        
        # 사용자 확인
        confirm = input("\n계속 진행하시겠습니까? (y/n): ").strip().lower()
        if confirm != 'y':
            print("크롤링을 취소했습니다.")
            exit()
        
        test_limit = None
        filename = "golfzon_all_courses.csv"
    
    # 크롤링 실행
    data = crawl_all_courses(start_page=1, max_pages=300, pause=0.5, test_limit=test_limit)
    
    # 수집 결과 요약 출력
    print_summary(data)
    
    # CSV 파일 저장
    save_csv(data, filename)
    print(f"\n💾 데이터 저장 완료: {filename}")
    
    print(f"\n🎉 크롤링 완료! 총 {len(data)}개 레코드가 수집되었습니다.")
    
    # GitHub 자동 업로드 (전체 크롤링인 경우 무조건 실행)
    if test_mode != 'y' and filename == "golfzon_all_courses.csv":
        print("\n📤 GitHub 자동 업로드 중...")
        try:
            from golfzon_github_uploader import upload_to_github
            success = upload_to_github(
                csv_file_path=filename,
                commit_message=f"전체 코스 데이터 자동 업데이트 ({len(data)}개 레코드)",
                also_update_flutter_assets=True,
            )
            if success:
                print("✅ GitHub 및 Flutter assets 업로드 완료!")
            else:
                print("⚠️ GitHub 업로드 실패. 수동으로 확인해주세요.")
        except ImportError:
            print("⚠️ GitHub 업로드 모듈을 찾을 수 없습니다.")
        except Exception as e:
            print(f"⚠️ GitHub 업로드 중 오류: {e}")
    
    if test_mode == 'y':
        print("\n💡 테스트가 성공하면 전체 크롤링을 위해 다시 실행하세요!")
