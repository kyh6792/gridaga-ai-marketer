import streamlit as st
from core.ui import display_intro
from core.marketer import run_marketing_ui  # 마케팅팀 모듈 호출
from core.students import run_student_ui
# --- 1. 페이지 설정 ---
st.set_page_config(
    page_title="작업실 그리다가 OS", 
    page_icon="🎨", 
    layout="centered" # 모바일은 wide보다 centered가 가독성이 좋습니다.
)
# app.py 상단

# --- 2. 인트로 화면 실행 ---
# intro 폴더의 로고를 2.5초간 노출
display_intro("intro/logo.jpg", duration=3)

if st.session_state.get('intro_done'):
    with st.sidebar:
        st.title("Studio 그리다가")
        menu = st.sidebar.radio(
            "업무 부서를 선택하세요",
            ["📢 마케팅팀", "👥 회원관리팀", "💰 재무팀", "📚 커리큘럼"],
            index=0,
            key="main_menu_radio" # 고유 키 부여
        )
        st.markdown("---")
        st.caption("Developed by 엔지니어 남편 v1.2")

    # 각 부서별 화면 렌더링
    if menu == "📢 마케팅팀":
        st.header("📢 마케팅팀 (AI 홍보 엔진)")
        # marketer.py에 있는 UI 실행 함수 호출
        run_marketing_ui()

    elif menu == "👥 회원관리팀":
        st.header("👥 회원관리팀")
        st.info("🚧 서비스 준비 중입니다. (아이디어: 수강생 출석 및 진도 관리)")
        run_student_ui()
        # [아이디어 섹션] 와이프분과 상의할 내용들
        with st.expander("💡 회원관리팀 로드맵 보기"):
            st.write("- 수강생별 작품 히스토리 아카이빙")
            st.write("- 재등록 알림톡 자동 생성")
            st.write("- 신규 상담 문의 가이드라인 제공")

    elif menu == "💰 재무팀":
        st.header("💰 재무팀")
        st.info("🚧 서비스 준비 중입니다. (아이디어: 영수증 OCR 및 매출 통계)")

    elif menu == "📚 커리큘럼":
        st.header("📚 커리큘럼")
        st.info("🚧 서비스 준비 중입니다. (아이디어: 유화/수채화 수업 가이드)")

# --- 4. 푸터 ---
if st.session_state.get('intro_done'):
    st.markdown("---")
    st.caption("© 2026 작업실 그리다가. All rights reserved.")