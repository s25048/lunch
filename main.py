import calendar
from datetime import datetime
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="학교 급식 달력", layout="wide")


# ----------------------------------------------------
# NEIS API 데이터 조회 함수
# ----------------------------------------------------
@st.cache_data(ttl=3600)
def fetch_school_code(api_key, school_name):
    """학교명으로 ATPT_OFCDC_SC_CODE(시도교육청코드) 및 SD_SCHUL_CODE(행정표준코드) 검색"""
    url = "https://open.neis.go.kr/hub/schoolInfo"
    params = {
        "KEY": api_key,
        "Type": "json",
        "pIndex": 1,
        "pSize": 5,
        "SCHUL_NM": school_name,
    }
    response = requests.get(url, params=params)
    data = response.json()

    if "schoolInfo" in data:
        row = data["schoolInfo"][1]["row"][0]
        return row["ATPT_OFCDC_SC_CODE"], row["SD_SCHUL_CODE"], row["SCHUL_NM"]
    return None, None, None


@st.cache_data(ttl=3600)
def fetch_monthly_meal(api_key, office_code, school_code, year, month):
    """지정한 연/월의 한 달치 급식 정보 조회"""
    from_date = f"{year}{month:02d}01"
    last_day = calendar.monthrange(year, month)[1]
    to_date = f"{year}{month:02d}{last_day:02d}"

    url = "https://open.neis.go.kr/hub/mealServiceDietInfo"
    params = {
        "KEY": api_key,
        "Type": "json",
        "pIndex": 1,
        "pSize": 100,
        "ATPT_OFCDC_SC_CODE": office_code,
        "SD_SCHUL_CODE": school_code,
        "MLSV_FROM_YMD": from_date,
        "MLSV_TO_YMD": to_date,
    }

    response = requests.get(url, params=params)
    data = response.json()

    meals_by_date = {}
    if "mealServiceDietInfo" in data:
        rows = data["mealServiceDietInfo"][1]["row"]
        for row in rows:
            ymd = row["MLSV_YMD"]
            # 알레르기 정보 숫자 제거 및 <br/> 태그 정제
            raw_menu = row["DDISH_NM"]
            cleaned_menu = raw_menu.replace("<br/>", "\n")
            # 필요시 알레르기 표기(숫자)를 제거하려면 아래 주석 해제
            # import re; cleaned_menu = re.sub(r'\d+\.', '', cleaned_menu)

            meal_type = row["MMEAL_SC_NM"]  # 중식, 석식 등
            if ymd not in meals_by_date:
                meals_by_date[ymd] = []
            meals_by_date[ymd].append(
                f"**[{meal_type}]**\n{cleaned_menu}"
            )

    return meals_by_date


# ----------------------------------------------------
# UI 레이아웃
# ----------------------------------------------------
st.title("🍱 우리 학교 급식 달력")

# 사이드바 설정
with st.sidebar:
    st.header("⚙️ 검색 설정")

    # 오픈 API 키 입력 (기본 무료 인증키 또는 개인 발급 키)
    # NEIS 인증키가 없어도 기본 조회용 sample키로 작동 가능한 경우가 많으나, 개인 키 발급을 권장합니다.
    api_key = st.text_input(
        "NEIS API Key", value="", help="나이스 교육정보 개방포털에서 발급받은 키를 입력하세요."
    )

    school_name_input = st.text_input(
        "학교 이름", value="제주중앙고등학교", placeholder="예: 서울고등학교"
    )

    today = datetime.now()
    col_y, col_m = st.columns(2)
    selected_year = col_y.number_input(
        "연도", min_value=2020, max_value=2030, value=today.year
    )
    selected_month = col_m.number_input(
        "월", min_value=1, max_value=12, value=today.month
    )

    search_btn = st.button("급식 조회하기", type="primary", use_container_width=True)

# 메인 달력 렌더링
if search_btn or school_name_input:
    with st.spinner("급식 정보를 불러오는 중..."):
        office_code, school_code, full_school_name = fetch_school_code(
            api_key, school_name_input
        )

        if not school_code:
            st.error("학교를 찾을 수 없습니다. 정확한 학교명을 입력해 주세요.")
        else:
            st.subheader(
                f"🏫 {full_school_name} - {selected_year}년 {selected_month}월 급식표"
            )

            # 월별 급식 데이터 로드
            meal_data = fetch_monthly_meal(
                api_key, office_code, school_code, selected_year, selected_month
            )

            # 달력 데이터 생성 (월요일 시작)
            cal = calendar.Calendar(firstweekday=0)
            month_days = cal.monthdayscalendar(selected_year, selected_month)

            # 요일 헤더
            days_header = ["월", "화", "수", "목", "금", "토", "일"]
            cols = st.columns(7)
            for idx, col in enumerate(cols):
                col.markdown(
                    f"<h4 style='text-align: center;'>{days_header[idx]}</h4>",
                    unsafe_allow_html=True,
                )

            # 주 단위로 달력 칸 그리기
            for week in month_days:
                cols = st.columns(7)
                for i, day in enumerate(week):
                    with cols[i]:
                        if day == 0:
                            # 해당 월에 안 들어가는 빈 날짜
                            st.empty()
                        else:
                            ymd_key = f"{selected_year}{selected_month:02d}{day:02d}"
                            day_str = f"**{day}일**"

                            # 토/일요일 색상 안내
                            if i == 5:
                                day_str = f":blue[{day_str}]"
                            elif i == 6:
                                day_str = f":red[{day_str}]"

                            st.markdown(day_str)

                            # 해당 날짜 급식 데이터 표기
                            if ymd_key in meal_data:
                                for meal in meal_data[ymd_key]:
                                    st.caption(meal)
                            else:
                                st.caption(
                                    "<span style='color:gray;'>급식 없음</span>",
                                    unsafe_allow_html=True,
                                )

                        st.divider()
