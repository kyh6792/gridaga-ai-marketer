import streamlit as st
import pandas as pd
from datetime import datetime
import time
from core.database import get_conn
from core.curriculum import get_course_options, get_course_price_map
from core.schedule import run_schedule_ui
from core.finance import record_registration_payment

# 운영 대시보드(승인/최근처리): 메뉴 전환마다 시트 재조회 방지 — 쓰기·승인 시에만 무효화
_OWNER_DASH_CACHE_TTL_SEC = 30
_REQ_RAW_CACHE_KEY = "_owner_dash_attendance_requests_raw"
_REQ_RAW_CACHE_TS = "_owner_dash_attendance_requests_ts"
_LOG_DASH_CACHE_KEY = "_owner_dash_attendance_log_recent"
_LOG_DASH_CACHE_TS = "_owner_dash_attendance_log_ts"


def invalidate_owner_dashboard_sheet_caches():
    """승인/요청접수/로그재시도 등 시트가 바뀐 뒤 대시보드가 바로 반영되게 캐시 제거."""
    for k in (
        _REQ_RAW_CACHE_KEY,
        _REQ_RAW_CACHE_TS,
        _LOG_DASH_CACHE_KEY,
        _LOG_DASH_CACHE_TS,
    ):
        st.session_state.pop(k, None)


def _safe_read(conn, worksheet, ttl=0, retries=2):
    last_error = None
    for attempt in range(retries + 1):
        try:
            return conn.read(worksheet=worksheet, ttl=ttl)
        except Exception as e:
            last_error = e
            msg = str(e)
            is_quota = ("429" in msg or "RESOURCE_EXHAUSTED" in msg or "RATE_LIMIT_EXCEEDED" in msg)
            if is_quota and attempt < retries:
                time.sleep(1.0 * (attempt + 1))
                continue
            raise
    raise last_error


def _safe_update(conn, worksheet, data, retries=2):
    last_error = None
    for attempt in range(retries + 1):
        try:
            conn.update(worksheet=worksheet, data=data)
            return
        except Exception as e:
            last_error = e
            msg = str(e)
            is_quota = ("429" in msg or "RESOURCE_EXHAUSTED" in msg or "RATE_LIMIT_EXCEEDED" in msg)
            if is_quota and attempt < retries:
                time.sleep(1.0 * (attempt + 1))
                continue
            raise
    raise last_error

def run_student_ui():
    st.subheader("👥 원생 관리 및 등록")

    def _suggest_sessions(course_name):
        course_text = str(course_name).upper()
        if "코스 A".upper() in course_text:
            return 4
        if "코스 B".upper() in course_text:
            return 8
        return 10

    def _resolve_course_price(course_name):
        price_map = get_course_price_map()
        if course_name in price_map:
            return int(price_map[course_name] or 0)
        for k, v in price_map.items():
            if str(k) in str(course_name) or str(course_name) in str(k):
                return int(v or 0)
        return 0
    
    # 상단 탭 구성 (등록하기 / 명단보기 / 시간표)
    tab1, tab2, tab3 = st.tabs(["📝 신규 등록", "📋 원생 명부", "🗓 시간표"])
    
    with tab1:
        st.write("새로운 수강생 정보를 입력해주세요.")
        
        # 입력 폼
        with st.form("student_reg_form", clear_on_submit=True):
            course_options = get_course_options()
            if "student_reg_course_prev" not in st.session_state:
                st.session_state["student_reg_course_prev"] = ""
            if "student_reg_total_prev" not in st.session_state:
                st.session_state["student_reg_total_prev"] = 10

            name = st.text_input("이름", placeholder="이름을 입력하세요")
            contact = st.text_input("연락처", placeholder="010-0000-0000")
            course = st.selectbox("수강 코스", course_options, key="student_reg_course")
            suggested_sessions = _suggest_sessions(course)

            prev_course = st.session_state.get("student_reg_course_prev", "")
            prev_total = int(st.session_state.get("student_reg_total_prev", 10))
            default_total = prev_total
            if (not prev_course) or (course != prev_course and prev_total == _suggest_sessions(prev_course)):
                default_total = suggested_sessions

            total_sessions = st.number_input(
                "결제 횟수 (횟수제)",
                min_value=1,
                value=int(default_total),
                key="student_reg_total_input",
            )
            st.caption(f"추천 횟수: {suggested_sessions}회 (코스 기준, 직접 수정 가능)")

            base_amount = int(_resolve_course_price(course))
            discount_type = st.selectbox("할인 유형", ["없음", "정액 할인", "정률 할인(%)", "이벤트가 직접입력"])
            event_name = ""
            discount_value = 0
            discount_amount = 0
            final_amount = base_amount

            if discount_type == "정액 할인":
                discount_value = int(
                    st.number_input("할인 금액(원)", min_value=0, value=0, step=1000)
                )
                discount_amount = min(discount_value, base_amount)
                final_amount = max(0, base_amount - discount_amount)
            elif discount_type == "정률 할인(%)":
                discount_value = int(
                    st.number_input("할인율(%)", min_value=0, max_value=100, value=0, step=5)
                )
                discount_amount = int(round(base_amount * (discount_value / 100.0)))
                final_amount = max(0, base_amount - discount_amount)
            elif discount_type == "이벤트가 직접입력":
                event_name = st.text_input("이벤트명", placeholder="예: 봄맞이 원데이 20%")
                final_amount = int(
                    st.number_input("최종 결제금액(원)", min_value=0, value=int(base_amount), step=1000)
                )
                discount_amount = max(0, base_amount - final_amount)
                discount_value = discount_amount

            st.caption(
                f"원가 **{base_amount:,}원** · 할인 **{discount_amount:,}원** · 최종 **{final_amount:,}원**"
            )

            st.session_state["student_reg_course_prev"] = course
            st.session_state["student_reg_total_prev"] = int(total_sessions)
            
            reg_date = st.date_input("등록일", value=datetime.now())
            memo = st.text_area("특이사항 및 메모")
            
            submit_btn = st.form_submit_button("✅ 수강생 등록하기", use_container_width=True)
            
            if submit_btn:
                if name and contact:
                    save_student_to_sheet(
                        name,
                        contact,
                        reg_date,
                        course,
                        total_sessions,
                        memo,
                        final_amount=final_amount,
                        base_amount=base_amount,
                        discount_type=discount_type,
                        discount_value=discount_value,
                        discount_amount=discount_amount,
                        event_name=event_name,
                    )
                else:
                    st.error("이름과 연락처는 필수 입력 사항입니다.")

    with tab2:
        display_student_list()
    with tab3:
        run_schedule_ui()
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
def save_student_to_sheet(
    name,
    contact,
    reg_date,
    course,
    total_sessions,
    memo,
    *,
    final_amount=None,
    base_amount=None,
    discount_type="없음",
    discount_value=0,
    discount_amount=0,
    event_name="",
):
    try:
        conn = get_conn()
        df = _safe_read(conn, worksheet="students", ttl=0)

        if df is None or df.empty:
            df = pd.DataFrame(columns=["ID", "이름", "연락처", "등록일", "수강코스", "총 횟수", "잔여 횟수", "상태", "메모"])

        # 기존 동일 연락처/이름 존재 여부로 등록 유형 분류 (재등록이면 기존 ID 유지)
        is_rereg = False
        existing_row_idx = None
        target_id = None
        if "이름" in df.columns and "연락처" in df.columns and not df.empty:
            same = df[
                (df["이름"].astype(str).str.strip() == str(name).strip())
                & (df["연락처"].astype(str).str.strip() == str(contact).strip())
            ].copy()
            if not same.empty:
                is_rereg = True
                # 가장 최근 등록일 기준으로 대상 선택 (없으면 마지막 행)
                if "등록일" in same.columns:
                    same = same.sort_values(by="등록일", ascending=False)
                existing_row_idx = int(same.index[0])
                target_id = str(df.at[existing_row_idx, "ID"]).strip()

        # 신규 등록인 경우에만 새 ID 발급
        if not is_rereg:
            target_id = generate_student_id(df)

        # 입력값 정리
        val_int = int(total_sessions)

        # 재등록: 기존 행 업데이트 / 신규: 새 행 추가
        if is_rereg and existing_row_idx is not None:
            for col in ["ID", "이름", "연락처", "등록일", "수강코스", "총 횟수", "잔여 횟수", "상태", "메모"]:
                if col not in df.columns:
                    df[col] = ""
            df.at[existing_row_idx, "ID"] = str(target_id)
            df.at[existing_row_idx, "이름"] = str(name)
            df.at[existing_row_idx, "연락처"] = str(contact)
            df.at[existing_row_idx, "등록일"] = reg_date.strftime("%Y-%m-%d")
            df.at[existing_row_idx, "수강코스"] = str(course)
            df.at[existing_row_idx, "총 횟수"] = str(val_int)
            df.at[existing_row_idx, "잔여 횟수"] = str(val_int)
            df.at[existing_row_idx, "상태"] = "재원"
            df.at[existing_row_idx, "메모"] = str(memo)
            updated_df = df.copy()
        else:
            new_row = pd.DataFrame([{
                "ID": str(target_id),
                "이름": str(name),
                "연락처": str(contact),
                "등록일": reg_date.strftime("%Y-%m-%d"),
                "수강코스": str(course),
                "총 횟수": str(val_int),
                "잔여 횟수": str(val_int),
                "상태": "재원",
                "메모": str(memo)
            }])
            if not df.empty:
                df = df.astype(str)
                updated_df = pd.concat([df, new_row], ignore_index=True)
            else:
                updated_df = new_row

        # 저장
        _safe_update(conn, worksheet="students", data=updated_df)
        if is_rereg:
            st.success(f"🔁 [ID 유지: {target_id}] {name}님 재등록 완료!")
        else:
            st.success(f"🎊 [ID: {target_id}] {name}님 등록 완료!")

        # 재무 거래 자동 누적
        pay_note = f"{course} / {val_int}회"
        if discount_type and str(discount_type) != "없음":
            pay_note += f" / 할인:{discount_type}"
        if event_name:
            pay_note += f" / 이벤트:{event_name}"
        if is_rereg:
            pay_note += " / 재등록(ID유지)"

        record_registration_payment(
            student_id=target_id,
            student_name=name,
            course=course,
            event_type="재등록" if is_rereg else "등록",
            amount=final_amount,
            note=pay_note,
            base_amount=base_amount,
            discount_type=discount_type,
            discount_value=discount_value,
            discount_amount=discount_amount,
            event_name=event_name,
        )

    except Exception as e:
        st.error(f"등록 중 에러 발생: {e}")


STUDENT_STATUS_OPTIONS = ("재원", "휴원", "퇴원")


def _normalize_student_status(series_or_val):
    """시트 값을 재원/휴원/퇴원 중 하나로 정규화 (알 수 없는 값은 그대로 문자열)."""
    if hasattr(series_or_val, "astype"):
        s = series_or_val.fillna("").astype(str).str.strip()
        return s.replace("", "재원")
    v = str(series_or_val).strip() if series_or_val is not None and not pd.isna(series_or_val) else ""
    return v if v else "재원"


def _get_latest_reg_event_map(ttl=20):
    """student_id -> 최근 등록유형(등록/재등록) 맵."""
    try:
        conn = get_conn()
        tx = _safe_read(conn, worksheet="finance_transactions", ttl=ttl)
        if tx is None or tx.empty:
            return {}
        needed = {"student_id", "event_type", "date"}
        if not needed.issubset(set(tx.columns)):
            return {}

        view = tx.copy()
        view["student_id"] = pd.to_numeric(view["student_id"], errors="coerce").fillna(0).astype(int).astype(str)
        view["event_type"] = view["event_type"].astype(str).str.strip()
        view = view[view["event_type"].isin(["등록", "재등록"])].copy()
        if view.empty:
            return {}

        # 최신 기록 1건만 학생별 유지
        view = view.sort_values("date", ascending=False)
        latest = view.drop_duplicates(subset=["student_id"], keep="first")
        return dict(zip(latest["student_id"], latest["event_type"]))
    except Exception:
        return {}


def update_student_status(student_id, new_status, note_append=None):
    """Google Sheets `students`의 `상태`를 변경합니다. 선택 시 메모에 한 줄을 덧붙입니다."""
    if new_status not in STUDENT_STATUS_OPTIONS:
        return False, "상태는 재원 / 휴원 / 퇴원 중에서만 선택할 수 있습니다."
    try:
        conn = get_conn()
        df = _safe_read(conn, worksheet="students", ttl=0)
        if df is None or df.empty:
            return False, "명단을 불러올 수 없습니다."

        df["ID"] = pd.to_numeric(df["ID"], errors="coerce").fillna(0).astype(int).astype(str)
        idx = df.index[df["ID"] == str(student_id)].tolist()
        if not idx:
            return False, "수강생을 찾을 수 없습니다."

        row_idx = idx[0]
        df.at[row_idx, "상태"] = new_status

        if note_append and str(note_append).strip():
            if "메모" not in df.columns:
                df["메모"] = ""
            old_memo = df.at[row_idx, "메모"]
            old_memo = "" if pd.isna(old_memo) else str(old_memo)
            tag = datetime.now().strftime("%Y-%m-%d")
            line = f"[{tag} 상태:{new_status}] {str(note_append).strip()}"
            df.at[row_idx, "메모"] = (old_memo + "\n" + line).strip()

        _safe_update(conn, worksheet="students", data=df)
        return True, f"상태가 「{new_status}」(으)로 저장되었습니다."
    except Exception as e:
        return False, f"상태 저장 실패: {e}"


def display_student_list():
    """ID 기반 카드 UI + 출석 차감 버튼 통합 버전"""
    try:
        conn = get_conn()
        df = _safe_read(conn, worksheet="students", ttl=15)
        
        if df is not None and not df.empty:
            # 1. 데이터 타입 정돈 (ID 소수점 제거 및 숫자형 확정)
            df["ID"] = pd.to_numeric(df["ID"], errors='coerce').fillna(0).astype(int).astype(str)
            df["잔여 횟수"] = pd.to_numeric(df["잔여 횟수"], errors='coerce').fillna(0).astype(int)
            if "상태" not in df.columns:
                df["상태"] = "재원"
            df["상태"] = _normalize_student_status(df["상태"])
            
            reg_event_map = _get_latest_reg_event_map(ttl=20)

            # 2. 상단 필터 UI
            st.markdown("---")
            view_option = st.radio("🔍 보기 설정", ["재원생만", "전체 명단", "퇴원/휴원"], horizontal=True)
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
            st.caption(
                "「휴원」은 일시 중단, 「퇴원」은 수강 종료입니다. "
                "둘 다 **시간표 배정·출석 차감**에서 제외됩니다. 아래 카드에서 상태를 바꾸면 시트에 바로 반영됩니다."
            )

            # 3. 카드형 리스트 출력
            for _, row in display_df.iterrows():
                stu_status = str(row["상태"]).strip() if pd.notna(row["상태"]) else "재원"
                status_color = "green" if stu_status == "재원" else "gray"
                reg_kind = reg_event_map.get(str(row["ID"]), "")
                reg_badge = " · 🆕 등록" if reg_kind == "등록" else (" · 🔁 재등록" if reg_kind == "재등록" else "")
                
                # 카드 테두리 시작
                with st.container(border=True):
                    # [26001] 이름 (상태배지)
                    st.markdown(f"### `{row['ID']}` **{row['이름']}** :{status_color}[[{stu_status}]]")
                    st.caption(f"🎨 {row['수강코스']} | 📱 {row['연락처']}{reg_badge}")

                    # 잔여 횟수
                    rem_count = int(row['잔여 횟수'])
                    count_style = "normal" if rem_count > 2 else "inverse"
                    st.metric("잔여 횟수", f"{rem_count}회", delta_color=count_style)

                    with st.expander("재원 · 휴원 · 퇴원 설정", expanded=False):
                        cur = stu_status if stu_status in STUDENT_STATUS_OPTIONS else "재원"
                        idx_sel = list(STUDENT_STATUS_OPTIONS).index(cur)
                        new_status = st.selectbox(
                            "상태",
                            list(STUDENT_STATUS_OPTIONS),
                            index=idx_sel,
                            key=f"status_sel_{row['ID']}",
                            help="휴원: 복귀 예정 / 퇴원: 수강 종료. 재원으로 되돌리면 다시 출석·시간표에 포함됩니다.",
                        )
                        status_note = st.text_input(
                            "메모에 남길 내용 (선택)",
                            key=f"status_note_{row['ID']}",
                            placeholder="예: 3월 한 달 휴원, 가족 일정",
                        )
                        if st.button("상태 저장", key=f"status_save_{row['ID']}", use_container_width=True):
                            ok, msg = update_student_status(
                                row["ID"],
                                new_status,
                                note_append=status_note.strip() or None,
                            )
                            if ok:
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)

                    # 모바일에서 누르기 쉬운 단일 CTA (재원생만)
                    if stu_status == "재원":
                        if st.button("✅ 출석 처리 (1회 차감)", key=f"att_{row['ID']}", use_container_width=True):
                            success, result = deduct_session(row['ID'])
                            if success:
                                st.toast(f"✅ {row['이름']}님 차감 완료! 남은 횟수: {result}회")
                                st.rerun()
                            else:
                                st.error(result)
                    else:
                        st.info(f"「{stu_status}」 상태에서는 출석 차감을 사용할 수 없습니다. 복귀 시 상태를 「재원」으로 바꿔 주세요.")
        else:
            st.info("아직 등록된 수강생이 없습니다. '신규 등록'에서 첫 학생을 등록해 보세요!")
            
    except Exception as e:
        st.error(f"명단 표시 오류: {e}")
def deduct_session(student_id, request_meta=None):
    """특정 ID 수강생의 잔여 횟수를 1 차감합니다."""
    try:
        conn = get_conn()
        df = _safe_read(conn, worksheet="students", ttl=0)
        
        # ID 타입 일치 (문자열로 비교)
        df["ID"] = pd.to_numeric(df["ID"], errors='coerce').fillna(0).astype(int).astype(str)
        
        # 해당 학생 찾기
        idx = df.index[df["ID"] == str(student_id)].tolist()
        
        if idx:
            row_idx = idx[0]
            status_val = _normalize_student_status(df.at[row_idx, "상태"]) if "상태" in df.columns else "재원"
            if isinstance(status_val, str) and status_val != "재원":
                return False, f"현재 상태「{status_val}」에서는 출석 차감이 불가합니다. (재원으로 변경 후 이용)"

            current_count = int(float(df.at[row_idx, "잔여 횟수"]))
            is_sunday = datetime.now().weekday() == 6  # Monday=0, Sunday=6
            
            # 일요일은 자유드로잉: 출석은 기록하되 미차감
            if is_sunday:
                student_name = str(df.at[row_idx, "이름"]) if "이름" in df.columns else ""
                sunday_meta = dict(request_meta or {})
                sunday_meta["event"] = "attendance_free_drawing"
                save_attendance_log(
                    student_id=str(student_id),
                    student_name=student_name,
                    remain_count=current_count,
                    request_meta=sunday_meta,
                )
                return True, current_count

            if current_count > 0:
                df.at[row_idx, "잔여 횟수"] = current_count - 1
                _safe_update(conn, worksheet="students", data=df)
                student_name = str(df.at[row_idx, "이름"]) if "이름" in df.columns else ""
                save_attendance_log(
                    student_id=str(student_id),
                    student_name=student_name,
                    remain_count=current_count - 1,
                    request_meta=request_meta,
                )
                return True, current_count - 1
            else:
                return False, "잔여 횟수가 0회입니다. 충전이 필요합니다."
        return False, "수강생을 찾을 수 없습니다."
    except Exception as e:
        return False, f"오류 발생: {e}"


def _read_or_init_attendance_requests(conn, read_ttl=0):
    base_columns = ["request_id", "time", "student_id", "student_name", "status", "approved_time"]
    try:
        req_df = _safe_read(conn, worksheet="attendance_requests", ttl=read_ttl)
    except Exception:
        req_df = pd.DataFrame(columns=base_columns)
        _safe_update(conn, worksheet="attendance_requests", data=req_df)
        req_df = _safe_read(conn, worksheet="attendance_requests", ttl=read_ttl)

    if req_df is None or req_df.empty:
        req_df = pd.DataFrame(columns=base_columns)
    return req_df


def _get_attendance_requests_raw_cached(conn, *, force_refresh: bool = False):
    """운영 대시보드용: 짧은 세션 캐시로 attendance_requests 1회만 네트워크."""
    now = time.time()
    if not force_refresh:
        ts = st.session_state.get(_REQ_RAW_CACHE_TS)
        if ts is not None and (now - ts) < _OWNER_DASH_CACHE_TTL_SEC:
            cached = st.session_state.get(_REQ_RAW_CACHE_KEY)
            if cached is not None:
                return cached.copy()
    req_df = _read_or_init_attendance_requests(conn, read_ttl=0)
    st.session_state[_REQ_RAW_CACHE_KEY] = req_df.copy()
    st.session_state[_REQ_RAW_CACHE_TS] = now
    return req_df.copy()


def create_attendance_request(student_id):
    """원생 출석 승인 요청을 생성합니다. (실제 차감은 승인 시점)"""
    try:
        conn = get_conn()
        df = _safe_read(conn, worksheet="students", ttl=0)
        if df is None or df.empty:
            return False, "등록된 수강생이 없습니다."

        df["ID"] = pd.to_numeric(df["ID"], errors='coerce').fillna(0).astype(int).astype(str)
        idx = df.index[df["ID"] == str(student_id)].tolist()
        if not idx:
            return False, "수강생을 찾을 수 없습니다."

        row_idx = idx[0]
        status_val = _normalize_student_status(df.at[row_idx, "상태"]) if "상태" in df.columns else "재원"
        if isinstance(status_val, str) and status_val != "재원":
            return False, f"현재 상태「{status_val}」에서는 출석 요청이 불가합니다."

        current_count = int(float(df.at[row_idx, "잔여 횟수"]))
        if current_count <= 0:
            return False, "잔여 횟수가 0회입니다. 충전이 필요합니다."

        # 하루 1회 제한: 이미 승인된 차감 이력이 있으면 요청 불가
        today = datetime.now().strftime("%Y-%m-%d")
        try:
            log_df = _safe_read(conn, worksheet="attendance_log", ttl=15)
        except Exception:
            log_df = pd.DataFrame(columns=["time", "student_id", "student_name", "remain_count", "event"])
        if log_df is not None and not log_df.empty and "student_id" in log_df.columns and "time" in log_df.columns:
            today_logs = log_df[
                (log_df["student_id"].astype(str) == str(student_id))
                & (log_df["time"].astype(str).str.startswith(today))
            ]
            if not today_logs.empty:
                return False, "오늘은 이미 출석 처리되었습니다. (하루 1회)"

        req_df = _read_or_init_attendance_requests(conn)
        if "student_id" in req_df.columns and "status" in req_df.columns:
            pending_same = req_df[
                (req_df["student_id"].astype(str) == str(student_id)) &
                (req_df["status"].astype(str) == "pending")
            ]
            if not pending_same.empty:
                return False, "승인중입니다."

        now_txt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_request = pd.DataFrame([{
            "request_id": f"{student_id}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
            "time": now_txt,
            "student_id": str(student_id),
            "student_name": str(df.at[row_idx, "이름"]) if "이름" in df.columns else "원생",
            "status": "pending",
            "approved_time": "",
        }])
        updated = pd.concat([req_df, new_request], ignore_index=True)
        _safe_update(conn, worksheet="attendance_requests", data=updated)
        invalidate_owner_dashboard_sheet_caches()
        return True, f"{new_request.iloc[0]['student_name']}님 출석 요청이 접수되었습니다."
    except Exception as e:
        return False, f"출석 요청 생성 실패: {e}"


def cancel_pending_attendance_request(student_id):
    """원생 본인이 자신의 pending 요청을 취소합니다."""
    try:
        conn = get_conn()
        req_df = _read_or_init_attendance_requests(conn)
        if req_df.empty:
            return False, "취소할 요청이 없습니다."
        if "student_id" not in req_df.columns or "status" not in req_df.columns:
            return False, "요청 데이터 형식이 올바르지 않습니다."

        target = req_df[
            (req_df["student_id"].astype(str) == str(student_id))
            & (req_df["status"].astype(str) == "pending")
        ]
        if target.empty:
            return False, "현재 취소 가능한 승인 대기 요청이 없습니다."

        # 가장 최근 요청 1건만 취소
        if "time" in target.columns:
            target = target.sort_values(by="time", ascending=False)
        row_idx = int(target.index[0])
        req_df.at[row_idx, "status"] = "cancelled"
        req_df.at[row_idx, "approved_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _safe_update(conn, worksheet="attendance_requests", data=req_df)
        invalidate_owner_dashboard_sheet_caches()
        return True, "출석 요청이 취소되었습니다."
    except Exception as e:
        return False, f"요청 취소 실패: {e}"


def get_pending_attendance_requests(limit=20, force_refresh: bool = False):
    """승인 대기 중인 출석 요청 목록을 최신순으로 반환합니다. (대시보드는 세션 캐시)"""
    try:
        conn = get_conn()
        req_df = _get_attendance_requests_raw_cached(conn, force_refresh=force_refresh)
        if req_df.empty:
            return req_df

        if "status" in req_df.columns:
            req_df = req_df[req_df["status"].astype(str) == "pending"]
        if "time" in req_df.columns:
            req_df = req_df.sort_values(by="time", ascending=False)
        return req_df.head(limit).copy()
    except Exception:
        return pd.DataFrame(columns=["request_id", "time", "student_id", "student_name", "status", "approved_time"])


def approve_attendance_request(request_id):
    """원장이 요청을 승인하면 실제 1회 차감합니다."""
    try:
        conn = get_conn()
        req_df = _read_or_init_attendance_requests(conn)
        if req_df.empty:
            return False, "승인할 요청이 없습니다."

        idx = req_df.index[req_df["request_id"].astype(str) == str(request_id)].tolist()
        if not idx:
            return False, "요청을 찾을 수 없습니다."

        row_idx = idx[0]
        if str(req_df.at[row_idx, "status"]) != "pending":
            return False, "이미 처리된 요청입니다."

        # 이전 실패 메시지가 남아 상태 판정에 영향 주지 않도록 초기화
        st.session_state["attendance_log_error"] = ""

        student_id = str(req_df.at[row_idx, "student_id"])
        request_time = str(req_df.at[row_idx, "time"])
        approved_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        is_sunday = datetime.now().weekday() == 6
        success, result = deduct_session(
            student_id,
            request_meta={
                "request_id": str(request_id),
                "request_time": request_time,
                "approved_time": approved_time,
            },
        )
        if not success:
            return False, str(result)

        # 로그 저장 성공 여부에 따라 상태 분기
        if st.session_state.get("attendance_log_error"):
            req_df.at[row_idx, "status"] = "approved_log_failed"
        else:
            req_df.at[row_idx, "status"] = "approved"
        req_df.at[row_idx, "approved_time"] = approved_time
        _safe_update(conn, worksheet="attendance_requests", data=req_df)
        invalidate_owner_dashboard_sheet_caches()
        student_name = str(req_df.at[row_idx, "student_name"])
        if str(req_df.at[row_idx, "status"]) == "approved_log_failed":
            return True, f"{student_name}님 차감은 완료되었지만 로그 저장은 실패했습니다. (재시도 필요)"
        if is_sunday:
            return True, f"{student_name}님 일요일 자유드로잉 출석 처리 완료! (미차감, 남은 횟수: {result}회)"
        return True, f"{student_name}님 승인 완료! 남은 횟수: {result}회"
    except Exception as e:
        return False, f"승인 처리 실패: {e}"


def reject_attendance_request(request_id):
    """원장이 pending 요청을 거절 처리합니다. (차감 없음)"""
    try:
        conn = get_conn()
        req_df = _read_or_init_attendance_requests(conn)
        if req_df.empty:
            return False, "거절할 요청이 없습니다."

        idx = req_df.index[req_df["request_id"].astype(str) == str(request_id)].tolist()
        if not idx:
            return False, "요청을 찾을 수 없습니다."
        row_idx = idx[0]

        if str(req_df.at[row_idx, "status"]) != "pending":
            return False, "이미 처리된 요청입니다."

        req_df.at[row_idx, "status"] = "rejected"
        req_df.at[row_idx, "approved_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _safe_update(conn, worksheet="attendance_requests", data=req_df)
        invalidate_owner_dashboard_sheet_caches()
        student_name = str(req_df.at[row_idx, "student_name"])
        return True, f"{student_name}님 요청을 거절했습니다."
    except Exception as e:
        return False, f"거절 처리 실패: {e}"


def save_attendance_log(student_id, student_name, remain_count, request_meta=None):
    """출석(차감) 이벤트를 attendance_log 워크시트에 저장합니다."""
    try:
        conn = get_conn()
        base_columns = [
            "time",
            "student_id",
            "student_name",
            "remain_count",
            "event",
            "request_id",
            "request_time",
            "approved_time",
        ]

        try:
            log_df = _safe_read(conn, worksheet="attendance_log", ttl=15)
        except Exception as e:
            # 탭이 없을 수 있으므로 먼저 빈 탭 생성 시도
            empty_df = pd.DataFrame(columns=base_columns)
            try:
                _safe_update(conn, worksheet="attendance_log", data=empty_df)
                log_df = _safe_read(conn, worksheet="attendance_log", ttl=15)
            except Exception as create_error:
                st.session_state["attendance_log_error"] = (
                    f"attendance_log 탭 생성/저장 실패: {repr(create_error)} (원본 오류: {repr(e)})"
                )
                return False

        if log_df is None or log_df.empty:
            log_df = pd.DataFrame(columns=base_columns)

        request_meta = request_meta or {}
        new_row = pd.DataFrame([{
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "student_id": str(student_id),
            "student_name": str(student_name),
            "remain_count": int(remain_count),
            "event": str(request_meta.get("event", "attendance_deducted")),
            "request_id": str(request_meta.get("request_id", "")),
            "request_time": str(request_meta.get("request_time", "")),
            "approved_time": str(request_meta.get("approved_time", "")),
        }])
        updated_df = pd.concat([log_df, new_row], ignore_index=True)
        _safe_update(conn, worksheet="attendance_log", data=updated_df)
        invalidate_owner_dashboard_sheet_caches()
        return True
    except Exception as e:
        # 알림 로그 실패는 차감을 막지 않되, 화면에서 확인 가능하도록 저장
        st.session_state["attendance_log_error"] = f"attendance_log 저장 실패: {repr(e)}"
        return False


def get_failed_log_requests(limit=20, force_refresh: bool = False):
    """차감은 되었지만 로그 저장 실패한 요청 목록"""
    try:
        conn = get_conn()
        req_df = _get_attendance_requests_raw_cached(conn, force_refresh=force_refresh)
        if req_df.empty:
            return req_df
        req_df = req_df[req_df["status"].astype(str) == "approved_log_failed"]
        if "approved_time" in req_df.columns:
            req_df = req_df.sort_values(by="approved_time", ascending=False)
        return req_df.head(limit).copy()
    except Exception:
        return pd.DataFrame(columns=["request_id", "time", "student_id", "student_name", "status", "approved_time"])


def retry_failed_log_request(request_id):
    """로그 저장 실패 건을 재시도하고 성공하면 approved로 변경"""
    try:
        conn = get_conn()
        req_df = _read_or_init_attendance_requests(conn)
        idx = req_df.index[req_df["request_id"].astype(str) == str(request_id)].tolist()
        if not idx:
            return False, "요청을 찾을 수 없습니다."
        row_idx = idx[0]
        if str(req_df.at[row_idx, "status"]) != "approved_log_failed":
            return False, "재시도 대상 상태가 아닙니다."

        # 현재 잔여 횟수 조회 (이미 차감된 상태)
        st_df = _safe_read(conn, worksheet="students", ttl=0)
        st_df["ID"] = pd.to_numeric(st_df["ID"], errors='coerce').fillna(0).astype(int).astype(str)
        sidx = st_df.index[st_df["ID"] == str(req_df.at[row_idx, "student_id"])].tolist()
        if not sidx:
            return False, "원생 정보를 찾을 수 없습니다."
        remain_now = int(float(st_df.at[sidx[0], "잔여 횟수"]))

        ok = save_attendance_log(
            student_id=str(req_df.at[row_idx, "student_id"]),
            student_name=str(req_df.at[row_idx, "student_name"]),
            remain_count=remain_now,
            request_meta={
                "request_id": str(req_df.at[row_idx, "request_id"]),
                "request_time": str(req_df.at[row_idx, "time"]),
                "approved_time": str(req_df.at[row_idx, "approved_time"]),
            },
        )
        if not ok:
            return False, "로그 저장 재시도 실패"

        req_df.at[row_idx, "status"] = "approved"
        _safe_update(conn, worksheet="attendance_requests", data=req_df)
        invalidate_owner_dashboard_sheet_caches()
        return True, "로그 저장 재시도 성공"
    except Exception as e:
        return False, f"로그 재시도 실패: {e}"


def get_recent_attendance_logs(limit=10, force_refresh: bool = False):
    """최근 출석 로그를 최신순으로 반환합니다. (대시보드는 세션 캐시)"""
    try:
        conn = get_conn()
        now = time.time()
        if not force_refresh:
            ts = st.session_state.get(_LOG_DASH_CACHE_TS)
            if ts is not None and (now - ts) < _OWNER_DASH_CACHE_TTL_SEC:
                cached = st.session_state.get(_LOG_DASH_CACHE_KEY)
                if cached is not None:
                    return cached.head(limit).copy()

        try:
            df = _safe_read(conn, worksheet="attendance_log", ttl=0)
        except Exception:
            # 탭이 없으면 빈 탭 자동 생성 시도
            empty_df = pd.DataFrame(
                columns=["time", "student_id", "student_name", "remain_count", "event", "request_id", "request_time", "approved_time"]
            )
            _safe_update(conn, worksheet="attendance_log", data=empty_df)
            df = _safe_read(conn, worksheet="attendance_log", ttl=0)

        if df is None or df.empty:
            out = pd.DataFrame(
                columns=["time", "student_id", "student_name", "remain_count", "event", "request_id", "request_time", "approved_time"]
            )
            st.session_state[_LOG_DASH_CACHE_KEY] = out
            st.session_state[_LOG_DASH_CACHE_TS] = now
            return out
        if "time" in df.columns:
            df = df.sort_values(by="time", ascending=False)
        out = df.copy()
        st.session_state[_LOG_DASH_CACHE_KEY] = out
        st.session_state[_LOG_DASH_CACHE_TS] = now
        return out.head(limit).copy()
    except Exception as e:
        st.session_state["attendance_log_error"] = f"attendance_log 조회 실패: {repr(e)}"
        return pd.DataFrame(
            columns=["time", "student_id", "student_name", "remain_count", "event", "request_id", "request_time", "approved_time"]
        )


def get_student_name(student_id):
    """ID로 수강생 이름을 조회합니다."""
    try:
        conn = get_conn()
        df = _safe_read(conn, worksheet="students", ttl=20)
        if df is None or df.empty or "ID" not in df.columns:
            return None

        df["ID"] = pd.to_numeric(df["ID"], errors='coerce').fillna(0).astype(int).astype(str)
        idx = df.index[df["ID"] == str(student_id)].tolist()
        if not idx:
            return None

        return str(df.at[idx[0], "이름"])
    except Exception:
        return None