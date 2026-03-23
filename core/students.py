import streamlit as st
import pandas as pd
from datetime import datetime
from core.database import get_conn

def run_student_ui():
    st.subheader("👥 원생 관리 및 등록")
    
    # 상단 탭 구성 (등록하기 / 명단보기)
    tab1, tab2 = st.tabs(["📝 신규 등록", "📋 원생 명부"])
    
    with tab1:
        st.write("새로운 수강생 정보를 입력해주세요.")
        
        # 입력 폼
        with st.form("student_reg_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("이름", placeholder="이름을 입력하세요")
                contact = st.text_input("연락처", placeholder="010-0000-0000")
            with col2:
                course = st.selectbox("수강 코스", ["정규반(주1회)", "정규반(주2회)", "원데이 클래스", "기타"])
                total_sessions = st.number_input("결제 횟수 (횟수제)", min_value=1, value=10)
            
            reg_date = st.date_input("등록일", value=datetime.now())
            memo = st.text_area("특이사항 및 메모")
            
            submit_btn = st.form_submit_button("✅ 수강생 등록하기", use_container_width=True)
            
            if submit_btn:
                if name and contact:
                    save_student_to_sheet(name, contact, reg_date, course, total_sessions, memo)
                else:
                    st.error("이름과 연락처는 필수 입력 사항입니다.")

    with tab2:
        display_student_list()
def generate_student_id(df):
    """연도+순번 형태의 고유 ID 생성 (예: 26001)"""
    current_year_short = datetime.now().strftime("%y") # '26'
    
    if df.empty or "ID" not in df.columns:
        return f"{current_year_short}001"
    
    # 기존 ID 중 현재 연도로 시작하는 번호들만 추출
    year_prefix = current_year_short
    same_year_ids = df[df["ID"].astype(str).str.startswith(year_prefix)]["ID"]
    
    if same_year_ids.empty:
        return f"{year_prefix}001"
    
    # 가장 큰 번호를 찾아 +1
    last_id = int(max(same_year_ids))
    return str(last_id + 1)
def save_student_to_sheet(name, contact, reg_date, course, total_sessions, memo):
    try:
        conn = get_conn()
        df = conn.read(worksheet="students", ttl=0)
        
        # 1. 고유 ID 생성 (26001...)
        new_id = generate_student_id(df)
        
        # 2. 입력값 정리
        val_int = int(total_sessions)
        
        # 3. 새 데이터 생성 (ID 컬럼 추가)
        new_row = pd.DataFrame([{
            "ID": new_id,
            "이름": str(name),
            "연락처": str(contact),
            "등록일": reg_date.strftime("%Y-%m-%d"),
            "수강코스": str(course),
            "총 횟수": str(val_int),
            "잔여 횟수": str(val_int),
            "상태": "재원", # 기본값은 '재원'
            "메모": str(memo)
        }])
        
        # 4. 합치기 및 업데이트
        if not df.empty:
            df = df.astype(str)
            updated_df = pd.concat([df, new_row], ignore_index=True)
        else:
            updated_df = new_row
            
        conn.update(worksheet="students", data=updated_df)
        st.success(f"🎊 [ID: {new_id}] {name}님 등록 완료!")
        
    except Exception as e:
        st.error(f"등록 중 에러 발생: {e}")
def display_student_list():
    """ID 기반 카드 UI + 출석 차감 버튼 통합 버전"""
    try:
        conn = get_conn()
        df = conn.read(worksheet="students", ttl=0)
        
        if df is not None and not df.empty:
            # 1. 데이터 타입 정돈 (ID 소수점 제거 및 숫자형 확정)
            df["ID"] = pd.to_numeric(df["ID"], errors='coerce').fillna(0).astype(int).astype(str)
            df["잔여 횟수"] = pd.to_numeric(df["잔여 횟수"], errors='coerce').fillna(0).astype(int)
            
            # 2. 상단 필터 UI
            st.markdown("---")
            col_f1, col_f2 = st.columns([2, 1])
            with col_f1:
                view_option = st.radio("🔍 보기 설정", ["재원생만", "전체 명단", "퇴원/휴원"], horizontal=True)
            with col_f2:
                search_name = st.text_input("👤 이름 검색", placeholder="이름 입력")

            # 필터링 로직 적용
            display_df = df.copy()
            if view_option == "재원생만":
                display_df = display_df[display_df["상태"] == "재원"]
            elif view_option == "퇴원/휴원":
                display_df = display_df[display_df["상태"].isin(["퇴원", "휴원"])]
            
            if search_name:
                display_df = display_df[display_df["이름"].str.contains(search_name)]

            st.write(f"📊 검색 결과: {len(display_df)}명")

            # 3. 카드형 리스트 출력
            for _, row in display_df.iterrows():
                status_color = "green" if row['상태'] == "재원" else "gray"
                
                # 카드 테두리 시작
                with st.container(border=True):
                    c1, c2, c3 = st.columns([2, 1, 1])
                    
                    with c1:
                        # [26001] 이름 (상태배지)
                        st.markdown(f"### `{row['ID']}` **{row['이름']}** :{status_color}[[{row['상태']}]]")
                        st.caption(f"🎨 {row['수강코스']} | 📱 {row['연락처']}")
                    
                    with c2:
                        # 잔여 횟수 메트릭 (3회 미만 빨간색)
                        rem_count = int(row['잔여 횟수'])
                        count_style = "normal" if rem_count > 2 else "inverse"
                        st.metric("잔여 횟수", f"{rem_count}회", delta_color=count_style)
                    
                    with c3:
                        st.write("") # 간격 맞춤
                        # [출석] 버튼 팝오버 (실수 방지용)
                        with st.popover("🔔 출석", use_container_width=True):
                            st.write(f"**{row['이름']}**님")
                            st.write("오늘 수업을 차감할까요?")
                            if st.button("확인 (1회 차감)", key=f"att_{row['ID']}", use_container_width=True):
                                success, result = deduct_session(row['ID'])
                                if success:
                                    st.toast(f"✅ {row['이름']}님 차감 완료! 남은 횟수: {result}회")
                                    st.rerun()
                                else:
                                    st.error(result)
        else:
            st.info("아직 등록된 수강생이 없습니다. '신규 등록'에서 첫 학생을 등록해 보세요!")
            
    except Exception as e:
        st.error(f"명단 표시 오류: {e}")
def deduct_session(student_id):
    """특정 ID 수강생의 잔여 횟수를 1 차감합니다."""
    try:
        conn = get_conn()
        df = conn.read(worksheet="students", ttl=0)
        
        # ID 타입 일치 (문자열로 비교)
        df["ID"] = pd.to_numeric(df["ID"], errors='coerce').fillna(0).astype(int).astype(str)
        
        # 해당 학생 찾기
        idx = df.index[df["ID"] == str(student_id)].tolist()
        
        if idx:
            row_idx = idx[0]
            current_count = int(float(df.at[row_idx, "잔여 횟수"]))
            
            if current_count > 0:
                df.at[row_idx, "잔여 횟수"] = current_count - 1
                conn.update(worksheet="students", data=df)
                return True, current_count - 1
            else:
                return False, "잔여 횟수가 0회입니다. 충전이 필요합니다."
        return False, "수강생을 찾을 수 없습니다."
    except Exception as e:
        return False, f"오류 발생: {e}"