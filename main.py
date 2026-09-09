import calendar
from datetime import datetime
import io
import re
import pandas as pd
import requests
import streamlit as st

# SSL 인증서 경고 메시지 억제
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(page_title="우리 학교 급식 달력", layout="wide")


# ----------------------------------------------------
# 영양 정보 텍스트 파싱 함수
# ----------------------------------------------------
def parse_nutrition(ntr_str):
    """NEIS 영양 정보 텍스트를 딕셔너리 형태로 변환"""
    if not ntr_str:
        return {}

    # <br/> 태그 정리 및 줄바꿈 단위 분할
    cleaned = ntr_str.replace("<br/>", "\n").replace("<br>", "\n")
    lines = [line.strip() for line in cleaned.split("\n") if line.strip()]

    nutrition_dict = {}
    for line in lines:
        if ":" in line:
            parts = line.split(":")
            key = parts[0].strip()
            val = parts[1].strip()
            nutrition_dict[key] = val

    return nutrition_dict


# ----------------------------------------------------
# NEIS API 데이터 조회 함수
# ----------------------------------------------------
@st.cache_data(ttl=3600)
def fetch_school_code(api_key, school_name):
    """학교명으로 ATPT_OFCDC_SC_CODE(시도교육청코드) 및 SD_SCHUL_CODE(행정표준코드) 검색"""
    url = "https://open.neis.go.kr/hub/schoolInfo"
    key_param = api_key.strip() if api_key.strip() else "sample"

    params = {
        "KEY": key_param,
        "Type": "json",
        "pIndex": 1,
        "pSize": 10,
        "SCHUL_NM": school_name,
    }

    try:
        # verify=False 옵션을 추가하여 SSL 인증서 검증 건너뛰기
        response = requests.get(url, params=params, timeout=10, verify=False)
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
    """지정한 연/월의 한 달치 급식 정보 및 영양 정보 조회"""
    from_date = f"{year}{month:02d}01"
    last_day = calendar.monthrange(year, month)[1]
    to_date = f"{year}{month:02d}{last_day:02d}"

    key_param = api_key.strip() if api_key.strip() else "sample"

    url = "https://open.neis.go.kr/hub/mealServiceDietInfo"
    params = {
        "KEY": key_param,
        "Type": "json",
        "pIndex": 1,
        "pSize": 1000,
        "ATPT_OFCDC_SC_CODE": office_code,
        "SD_SCHUL_CODE": school_code,
        "MLSV_FROM_YMD": from_date,
        "MLSV_TO_YMD": to_date,
    }

    try:
        # verify=False 옵션을 추가하여 SSL 인증서 검증 건너뛰기
        response = requests.get(url, params=params, timeout=10, verify=False)
        data = response.json()

        meals_by_date = {}
        raw_list = []

        if "mealServiceDietInfo" in data:
            rows = data["mealServiceDietInfo"][1]["row"]
            for row in rows:
                ymd = row["MLSV_YMD"]
                raw_menu = row["DDISH_NM"]

                # 태그 및 알레르기 정제
                cleaned_menu = raw_menu.replace("<br/>", "\n")
                if remove_allergy:
                    cleaned_menu = re.sub(r"\([0-9\.]+\)", "", cleaned_menu)
                    cleaned_menu = re.sub(r"[0-9\.]+", "", cleaned_menu)

                lines = [
                    line.strip()
                    for line in cleaned_menu.split("\n")
                    if line.strip()
                ]
                cleaned_menu = "\n".join(lines)

                meal_type = row["MMEAL_SC_NM"]  # 조식, 중식, 석식
                cal_info = row.get("CAL_INFO", "정보 없음")
                ntr_info_raw = row.get("NTR_INFO", "")
                nutrition_parsed = parse_nutrition(ntr_info_raw)

                item = {
                    "ymd": ymd,
                    "type": meal_type,
                    "menu": cleaned_menu,
                    "calorie": cal_info,
                    "nutrition_raw": ntr_info_raw.replace("<br/>", "\n"),
                    "nutrition_dict": nutrition_parsed,
                }

                if ymd not in meals_by_date:
                    meals_by_date[ymd] = []
                meals_by_date[ymd].append(item)
                raw_list.append(item)

            return meals_by_date, raw_list, None
        elif "RESULT" in data:
            return {}, [], data["RESULT"]["MESSAGE"]
    except Exception as e:
        return {}, [], str(e)

    return {}, [], "급식 데이터를 가져오지 못했습니다."


# ----------------------------------------------------
# 상세보기 모달 (Dialog)
# ----------------------------------------------------
@st.dialog("📋 급식 상세 및 영양 분석")
def show_detail_dialog(date_str, meals):
    st.subheader(f"📅 {date_str[:4]}년 {date_str[4:6]}월 {date_str[6:]}일")
    st.divider()

    for meal in meals:
        st.markdown(f"### 🍱 [{meal['type']}]")

        col_menu, col_ntr = st.columns([1, 1])

        with col_menu:
            st.markdown("**[ 메뉴 목록 ]**")
            st.text(meal["menu"])
            st.info(f"🔥 **열량:** {meal['calorie']}")

        with col_ntr:
            st.markdown("**[ 상세 영양 정보 ]**")
            ntr_dict = meal["nutrition_dict"]

            if ntr_dict:
                # 주요 영양소 하이라이트
                carb = ntr_dict.get("탄수화물(g)", "-")
                prot = ntr_dict.get("단백질(g)", "-")
                fat = ntr_dict.get("지방(g)", "-")

                st.write(f"- 🍚 **탄수화물:** {carb}")
                st.write(f"- 🥩 **단백질:** {prot}")
                st.write(f"- 🥑 **지방:** {fat}")

                with st.expander("전체 영양성분 표 보기"):
                    for k, v in ntr_dict.items():
                        st.write(f"- **{k}:** {v}")
            else:
                st.caption("제공된 세부 영양 정보가 없습니다.")

        st.divider()


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
        help="미입력 시 sample 키로 동작합니다.",
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
    show_nutrition_on_card = st.checkbox("달력에 영양정보 요약 표시", value=True)

    search_btn = st.button("급식 조회하기", type="primary", use_container_width=True)

# 메인 달력 렌더링
if search_btn or school_name_input:
    with st.spinner("급식 및 영양 정보를 불러오는 중..."):
        office_code, school_code, full_school_name, err_msg = fetch_school_code(
            api_key, school_name_input
        )

        if not school_code:
            st.error(f"학교 검색 실패: {err_msg}")
        else:
            st.subheader(
                f"🏫 {full_school_name} - {selected_year}년 {selected_month}월 급식표"
            )

            # 데이터 로드
            meal_data, raw_list, meal_err_msg = fetch_monthly_meal(
                api_key,
                office_code,
                school_code,
                selected_year,
                selected_month,
                remove_allergy=remove_allergy_option,
            )

            if meal_err_msg and not meal_data:
                st.warning(f"급식 정보 안내: {meal_err_msg}")

            # 📥 엑셀 다운로드 버튼
            if raw_list:
                df_export = pd.DataFrame(raw_list)
                # 엑셀 다운로드용 칼럼 정리
                df_export_clean = pd.DataFrame({
                    "날짜": df_export["ymd"],
                    "식사구분": df_export["type"],
                    "메뉴": df_export["menu"],
                    "칼로리": df_export["calorie"],
                    "영양정보": df_export["nutrition_raw"],
                })

                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
                    df_export_clean.to_excel(
                        writer, sheet_name="급식일정", index=False
                    )

                st.sidebar.divider()
                st.sidebar.download_button(
                    label="📥 이번 달 급식 엑셀 다운로드",
                    data=buffer.getvalue(),
                    file_name=f"{full_school_name}_{selected_year}_{selected_month}월_급식.xlsx",
                    mime="application/vnd.ms-excel",
                    use_container_width=True,
                )

            # 달력 데이터 생성 (월요일 시작)
            cal = calendar.Calendar(firstweekday=0)
            month_days = cal.monthdayscalendar(selected_year, selected_month)

            # 🗓️ 주차별 탭 생성
            week_tabs = st.tabs(
                [f"{w + 1}주차" for w in range(len(month_days))]
            )
            days_header = [
                "월요일",
                "화요일",
                "수요일",
                "목요일",
                "금요일",
                "토요일",
                "일요일",
            ]

            for week_idx, week in enumerate(month_days):
                with week_tabs[week_idx]:
                    cols = st.columns(7)

                    # 요일 헤더
                    for i, col in enumerate(cols):
                        col.markdown(f"**{days_header[i]}**")

                    for i, day in enumerate(week):
                        with cols[i]:
                            if day == 0:
                                st.empty()
                            else:
                                ymd_key = f"{selected_year}{selected_month:02d}{day:02d}"

                                # 오늘 날짜 체크
                                is_today = (
                                    selected_year == today.year
                                    and selected_month == today.month
                                    and day == today.day
                                )

                                day_label = f"### {day}일"
                                if is_today:
                                    day_label += " :red[[오늘]]"

                                st.markdown(day_label)

                                # 해당 날짜 급식 정보
                                if ymd_key in meal_data:
                                    meals = meal_data[ymd_key]
                                    for meal in meals:
                                        st.caption(
                                            f"**[{meal['type']}]**\n{meal['menu']}"
                                        )

                                        # 달력 카드에 영양정보 표시 옵션이 켜져 있는 경우
                                        if show_nutrition_on_card:
                                            st.caption(f"🔥 {meal['calorie']}")
                                            ntr = meal["nutrition_dict"]
                                            if ntr:
                                                carb = ntr.get("탄수화물(g)", "-")
                                                prot = ntr.get("단백질(g)", "-")
                                                fat = ntr.get("지방(g)", "-")
                                                st.caption(
                                                    f"🧪 탄:{carb} / 단:{prot} / 지:{fat}"
                                                )

                                    # 상세 팝업 버튼
                                    if st.button(
                                        "🔍 상세/영양",
                                        key=f"btn_{ymd_key}",
                                        use_container_width=True,
                                    ):
                                        show_detail_dialog(ymd_key, meals)
                                else:
                                    st.caption("급식 없음")
