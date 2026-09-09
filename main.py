import calendar
from datetime import datetime
import io
import re
import pandas as pd
import requests
import streamlit as st

# 페이지 기본 설정
st.set_page_config(
    page_title="👑 핑크 공주님의 급식 달력 👑",
    page_icon="🎀",
    layout="wide",
)

# ----------------------------------------------------
# 공주공주 핑크 커스텀 CSS 적용 🎀
# ----------------------------------------------------
st.markdown(
    """
    <style>
    /* 전체 배경을 파스텔 핑크 톤으로 변경 */
    .stApp {
        background-color: #FFF5F7;
        font-family: 'Malgun Gothic', sans-serif;
    }
    
    /* 사이드바 스타일링 */
    [data-testid="stSidebar"] {
        background-color: #FFE6EC !important;
        border-right: 2px solid #FFB6C1;
    }
    
    /* 제목 및 스몰 텍스트 핑크 컬러 적용 */
    h1, h2, h3, h4, h5, h6 {
        color: #D81B60 !important;
        font-weight: bold;
    }

    /* 버튼 스타일링: 러블리 핑크 둥근 버튼 */
    .stButton > button {
        background-color: #FF85A2 !important;
        color: white !important;
        border-radius: 20px !important;
        border: 2px solid #FFB6C1 !important;
        font-weight: bold !important;
        box-shadow: 0 4px 6px rgba(255, 133, 162, 0.3) !important;
        transition: all 0.3s ease !important;
    }
    
    .stButton > button:hover {
        background-color: #FF5C8D !important;
        transform: translateY(-2px);
        box-shadow: 0 6px 12px rgba(255, 92, 141, 0.4) !important;
    }

    /* 탭(Tab) 스타일링 */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }

    .stTabs [data-baseweb="tab"] {
        background-color: #FFE6EC !important;
        border-radius: 15px 15px 0 0 !important;
        color: #D81B60 !important;
        font-weight: bold !important;
        padding: 8px 16px !important;
    }

    .stTabs [aria-selected="true"] {
        background-color: #FF85A2 !important;
        color: white !important;
    }

    /* 달력 일자별 카드 상자 스타일링 */
    div[data-testid="column"] {
        background-color: #FFFFFF;
        border-radius: 15px;
        padding: 12px;
        border: 2px solid #FFC0CB;
        box-shadow: 0 2px 8px rgba(255, 192, 203, 0.25);
        margin-bottom: 10px;
    }

    /* 스크롤바 핑크 스타일 */
    ::-webkit-scrollbar {
        width: 8px;
    }
    ::-webkit-scrollbar-track {
        background: #FFF5F7;
    }
    ::-webkit-scrollbar-thumb {
        background: #FFB6C1;
        border-radius: 10px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ----------------------------------------------------
# NEIS API 키 검증 및 시크릿 불러오기 🔑
# ----------------------------------------------------
if "NEIS_KEY" not in st.secrets or not st.secrets["NEIS_KEY"].strip():
    st.error(
        "🌸 **NEIS API 키가 설정되지 않았어요!** 🌸\n\n"
        "Streamlit 실행 환경의 `.streamlit/secrets.toml` 파일에 아래와 같이 인증키를 추가해주세요 🎀\n\n"
        "```toml\n"
        'NEIS_KEY = "발급받은_NEIS_API_키"\n'
        "```\n\n"
        "테스트용 샘플 키를 사용하려면 `NEIS_KEY = \"sample\"` 로 설정할 수 있습니다."
    )
    st.stop()

API_KEY = st.secrets["NEIS_KEY"].strip()


# ----------------------------------------------------
# 영양 정보 텍스트 파싱 함수
# ----------------------------------------------------
def parse_nutrition(ntr_str):
    """NEIS 영양 정보 텍스트를 딕셔너리 형태로 변환"""
    if not ntr_str:
        return {}

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
# NEIS API 데이터 조회 함수 (st.secrets 적용)
# ----------------------------------------------------
@st.cache_data(ttl=3600)
def fetch_school_code(api_key, school_name):
    """학교명으로 ATPT_OFCDC_SC_CODE(시도교육청코드) 및 SD_SCHUL_CODE(행정표준코드) 검색"""
    url = "https://open.neis.go.kr/hub/schoolInfo"

    params = {
        "KEY": api_key,
        "Type": "json",
        "pIndex": 1,
        "pSize": 10,
        "SCHUL_NM": school_name.strip(),
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
            err_code = data["RESULT"].get("CODE", "UNKNOWN")
            err_msg = data["RESULT"].get("MESSAGE", "알 수 없는 오류")
            return None, None, None, f"[{err_code}] {err_msg}"
        elif "head" in data:
            head_result = data["head"][1]["RESULT"]
            return (
                None,
                None,
                None,
                f"[{head_result.get('CODE')}] {head_result.get('MESSAGE')}",
            )

    except Exception as e:
        return None, None, None, f"통신 오류: {str(e)}"

    return None, None, None, "학교 정보를 찾을 수 없습니다."


@st.cache_data(ttl=3600)
def fetch_monthly_meal(
    api_key, office_code, school_code, year, month, remove_allergy=True
):
    """지정한 연/월의 한 달치 급식 정보 및 영양 정보 조회"""
    from_date = f"{year}{month:02d}01"
    last_day = calendar.monthrange(year, month)[1]
    to_date = f"{year}{month:02d}{last_day:02d}"

    url = "https://open.neis.go.kr/hub/mealServiceDietInfo"
    params = {
        "KEY": api_key,
        "Type": "json",
        "pIndex": 1,
        "pSize": 1000,
        "ATPT_OFCDC_SC_CODE": office_code,
        "SD_SCHUL_CODE": school_code,
        "MLSV_FROM_YMD": from_date,
        "MLSV_TO_YMD": to_date,
    }

    try:
        response = requests.get(url, params=params, timeout=10)
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
            err_code = data["RESULT"].get("CODE", "UNKNOWN")
            err_msg = data["RESULT"].get("MESSAGE", "알 수 없는 오류")
            return {}, [], f"[{err_code}] {err_msg}"
    except Exception as e:
        return {}, [], f"통신 오류: {str(e)}"

    return {}, [], "급식 데이터를 가져오지 못했습니다."


# ----------------------------------------------------
# 공주님 전용 상세보기 팝업 (Dialog) 💖
# ----------------------------------------------------
@st.dialog("👑 공주님의 급식 & 영양 리포트 ✨")
def show_detail_dialog(date_str, meals):
    st.markdown(
        f"### 💖 {date_str[:4]}년 {date_str[4:6]}월 {date_str[6:]}일 메뉴"
    )
    st.divider()

    for meal in meals:
        st.markdown(f"#### 🍰 [{meal['type']}]")

        col_menu, col_ntr = st.columns([1, 1])

        with col_menu:
            st.markdown("**🎀 메뉴 목록**")
            st.text(meal["menu"])
            st.info(f"💖 **열량:** {meal['calorie']}")

        with col_ntr:
            st.markdown("**🌸 상세 영양 성분**")
            ntr_dict = meal["nutrition_dict"]

            if ntr_dict:
                carb = ntr_dict.get("탄수화물(g)", "-")
                prot = ntr_dict.get("단백질(g)", "-")
                fat = ntr_dict.get("지방(g)", "-")

                st.write(f"🍥 **탄수화물:** {carb}")
                st.write(f"🍓 **단백질:** {prot}")
                st.write(f"🥑 **지방:** {fat}")

                with st.expander("✨ 전체 영양 정보 펼쳐보기"):
                    for k, v in ntr_dict.items():
                        st.write(f"- **{k}:** {v}")
            else:
                st.caption("영양 정보가 제공되지 않았어요 🥺")

        st.divider()


# ----------------------------------------------------
# UI 레이아웃
# ----------------------------------------------------
st.title("👑 ✨ 공주님의 핑크 급식 달력 👑 ✨")
st.caption("💖 오늘 우리 학교에는 맛있는 급식이 나올까요? 🎀")

# 사이드바 설정
with st.sidebar:
    st.header("⚙️ 핑크 검색 설정 🌸")

    st.success("🔑 NEIS API 키가 성공적으로 로드되었습니다.")

    school_name_input = st.text_input(
        "🏫 학교 이름", value="제주중앙고등학교", placeholder="예: 서울고등학교"
    )

    today = datetime.now()
    col_y, col_m = st.columns(2)
    selected_year = col_y.number_input(
        "📅 연도", min_value=2020, max_value=2030, value=today.year
    )
    selected_month = col_m.number_input(
        "🗓️ 월", min_value=1, max_value=12, value=today.month
    )

    remove_allergy_option = st.checkbox("알레르기 숫자 감추기 🍓", value=True)
    show_nutrition_on_card = st.checkbox("카드에 영양 요약 보기 💖", value=True)

    search_btn = st.button(
        "💖 급식 검색하기 💖", type="primary", use_container_width=True
    )

# 메인 달력 렌더링
if search_btn or school_name_input:
    with st.spinner("💖 공주님의 맛있는 급식표를 가져오는 중... ✨"):
        office_code, school_code, full_school_name, err_msg = fetch_school_code(
            API_KEY, school_name_input
        )

        if not school_code:
            st.error(f"학교를 찾지 못했어요 🥺: {err_msg}")
        else:
            st.subheader(
                f"🏫 {full_school_name} - {selected_year}년 {selected_month}월 급식 달력 🎀"
            )

            # 데이터 로드
            meal_data, raw_list, meal_err_msg = fetch_monthly_meal(
                API_KEY,
                office_code,
                school_code,
                selected_year,
                selected_month,
                remove_allergy=remove_allergy_option,
            )

            if meal_err_msg and not meal_data:
                st.warning(f"급식 안내 🌸: {meal_err_msg}")

            # 📥 엑셀 다운로드 버튼 (사이드바)
            if raw_list:
                df_export = pd.DataFrame(raw_list)
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
                    label="📥 엑셀로 급식 소장하기 🎀",
                    data=buffer.getvalue(),
                    file_name=f"{full_school_name}_{selected_year}_{selected_month}월_핑크급식표.xlsx",
                    mime="application/vnd.ms-excel",
                    use_container_width=True,
                )

            # 달력 데이터 생성
            cal = calendar.Calendar(firstweekday=0)
            month_days = cal.monthdayscalendar(selected_year, selected_month)

            # 🗓️ 주차별 탭 생성
            week_tabs = st.tabs(
                [f"🌸 {w + 1}주차" for w in range(len(month_days))]
            )
            days_header = [
                "월요일 🎀",
                "화요일 🎀",
                "수요일 🎀",
                "목요일 🎀",
                "금요일 🎀",
                "토요일 🌸",
                "일요일 🌸",
            ]

            for week_idx, week in enumerate(month_days):
                with week_tabs[week_idx]:
                    cols = st.columns(7)

                    # 요일 헤더
                    for i, col in enumerate(cols):
                        col.markdown(
                            f"<p style='text-align: center; color: #D81B60; font-weight: bold;'>{days_header[i]}</p>",
                            unsafe_allow_html=True,
                        )

                    for i, day in enumerate(week):
                        with cols[i]:
                            if day == 0:
                                st.empty()
                            else:
                                ymd_key = f"{selected_year}{selected_month:02d}{day:02d}"

                                is_today = (
                                    selected_year == today.year
                                    and selected_month == today.month
                                    and day == today.day
                                )

                                day_label = f"#### {day}일"
                                if is_today:
                                    day_label += " 👑[오늘]"

                                st.markdown(day_label)

                                # 해당 날짜 급식 정보
                                if ymd_key in meal_data:
                                    meals = meal_data[ymd_key]
                                    for meal in meals:
                                        st.caption(
                                            f"**[{meal['type']}]**\n{meal['menu']}"
                                        )

                                        if show_nutrition_on_card:
                                            st.caption(f"💖 {meal['calorie']}")
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
                                        "💖 영양보기",
                                        key=f"btn_{ymd_key}",
                                        use_container_width=True,
                                    ):
                                        show_detail_dialog(ymd_key, meals)
                                else:
                                    st.caption("급식 없음 ☁️")
