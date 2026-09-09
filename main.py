import calendar
from datetime import datetime
import re
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
    # 인증키가 없을 경우 sample 키를 사용하도록 설정
    key_param = api_key.strip() if api_key.strip() else "sample"

    params = {
        "KEY": key_param,
        "Type": "json",
        "pIndex": 1,
        "pSize": 10,
        "SCHUL_NM": school_name,
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        if "schoolInfo" in data:
            row = data["schoolInfo"][1]["row"][0]
            return (
                row["ATPT_OFCDC_SC_CODE"],
                row["SD_SCHUL_CODE"],
                row["SCHUL_NM"],
                None,
            )
        elif "RESULT" in data:
            return None, None, None, data["RESULT"]["MESSAGE"]
    except Exception as e:
        return None, None, None, str(e)

    return None, None, None, "학교 정보를 찾을 수 없습니다."


@st.cache_data(ttl=3600)
def fetch_monthly_meal(
    api_key, office_code, school_code, year, month, remove_allergy=True
):
    """지정한 연/월의 한 달치 급식 정보 조회"""
    from_date = f"{year}{month:02d}01"
    last_day = calendar.monthrange(year, month)[1]
    to_date = f"{year}{month:02d}{last_day:02d}"

    key_param = api_key.strip() if api_key.strip() else "sample"

    url = "https://open.neis.go.kr/hub/mealServiceDietInfo"
    params = {
        "KEY": key_param,
        "Type": "json",
        "pIndex": 1,
        "pSize": 1000,  # 한 달치 조식/중식/석식을 모두 가져오기 위해 충분히 크게 설정
        "ATPT_OFCDC_SC_CODE": office_code,
        "SD_SCHUL_CODE": school_code,
        "MLSV_FROM_YMD": from_date,
        "MLSV_TO_YMD": to_date,
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        meals_by_date = {}
        if "mealServiceDietInfo" in data:
            rows = data["mealServiceDietInfo"][1]["row"]
            for row in rows:
                ymd = row["MLSV_YMD"]
                raw_menu = row["DDISH_NM"]

                # <br/> 태그 줄바꿈 변환
                cleaned_menu = raw_menu.replace("<br/>", "\n")

                # 알레르기 유발물질 숫자(예: 1.2.5.13.) 제거 옵션
                if remove_allergy:
                    cleaned_menu = re.sub(r"\([0-9\.]+\)", "", cleaned_menu)
                    cleaned_menu = re.sub(r"[0-9\.]+", "", cleaned_menu)

                # 메뉴 항목 앞뒤 공백 정리
                lines = [line.strip() for line in cleaned_menu.split("\n") if line.strip()]
                cleaned_menu = "\n".join(lines)

                meal_type = row["MMEAL_SC_NM"]  # 조식, 중식, 석식

                if ymd not in meals_by_date:
                    meals_by_date[ymd] = []

                meals_by_date[ymd].append(
                    f"**[{meal_type}]**\n{cleaned_menu}"
                )

            return meals_by_date, None
        elif "RESULT" in data:
            return {}, data["RESULT"]["MESSAGE"]
    except Exception as e:
        return {}, str(e)

    return {}, "급식 데이터를 가져오지 못했습니다."


# ----------------------------------------------------
# UI 레이아웃
# ----------------------------------------------------
st.title("🍱 우리 학교 급식 달력")

# 사이드바 설정
with st.sidebar:
    st.header("⚙️ 검색 설정")

    api_key = st.text_input(
        "NEIS API Key (선택)",
        value="",
        help="나이스 개방포털에서 발급받은 KEY를 입력하세요. 미입력 시 sample 키로 동작합니다.",
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

    remove_allergy_option = st.checkbox("알레르기 표시 숫자 제거", value=True)

    search_btn = st.button("급식 조회하기", type="primary", use_container_width=True)

# 메인 달력 렌더링
if search_btn or school_name_input:
    with st.spinner("급식 정보를 불러오는 중..."):
        office_code, school_code, full_school_name, err_msg = fetch_school_code(
            api_key, school_name_input
        )

        if not school_code:
            st.error(f"학교 검색 실패: {err_msg}")
        else:
            st.subheader(
                f"🏫 {full_school_name} - {selected_year}년 {selected_month}월 급식표"
            )

            # 월별 급식 데이터 로드
            meal_data, meal_err_msg = fetch_monthly_meal(
                api_key,
                office_code,
                school_code,
                selected_year,
                selected_month,
                remove_allergy=remove_allergy_option,
            )

            if meal_err_msg and not meal_data:
                st.warning(f"급식 정보 안내: {meal_err_msg}")

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
                            st.empty()
                        else:
                            ymd_key = (
                                f"{selected_year}{selected_month:02d}{day:02d}"
                            )
                            day_str = f"**{day}일**"

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
