import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from datetime import datetime
import time
import base64
import re
from pathlib import Path
from googleapiclient.discovery import build
from core.database import get_conn, get_sheet_url
from core.drive import get_service_account_credentials
from core.perf import perf_log

# 운영 대시보드(승인/최근처리): 메뉴 전환마다 시트 재조회 방지 — 쓰기·승인 시에만 무효화
_OWNER_DASH_CACHE_TTL_SEC = 60
_REQ_RAW_CACHE_KEY = "_owner_dash_attendance_requests_raw"
_REQ_RAW_CACHE_TS = "_owner_dash_attendance_requests_ts"
_LOG_DASH_CACHE_KEY = "_owner_dash_attendance_log_recent"
_LOG_DASH_CACHE_TS = "_owner_dash_attendance_log_ts"
_OWNER_DASH_BUNDLE_KEY = "_owner_dash_bundle"
_OWNER_DASH_BUNDLE_TS = "_owner_dash_bundle_ts"
_STUDENTS_API_WS = {"students", "attendance_requests", "attendance_log"}
_SHEETS_API_SESSION_KEY = "_students_sheets_api_service"


def invalidate_owner_dashboard_sheet_caches():
    """승인/요청접수/로그재시도 등 시트가 바뀐 뒤 대시보드가 바로 반영되게 캐시 제거."""
    for k in (
        _REQ_RAW_CACHE_KEY,
        _REQ_RAW_CACHE_TS,
        _LOG_DASH_CACHE_KEY,
        _LOG_DASH_CACHE_TS,
        _OWNER_DASH_BUNDLE_KEY,
        _OWNER_DASH_BUNDLE_TS,
    ):
        st.session_state.pop(k, None)


def _get_students_sheets_api():
    svc = st.session_state.get(_SHEETS_API_SESSION_KEY)
    if svc is not None:
        return svc
    creds = get_service_account_credentials(("https://www.googleapis.com/auth/spreadsheets",))
    if not creds:
        return None
    svc = build("sheets", "v4", credentials=creds, cache_discovery=False)
    st.session_state[_SHEETS_API_SESSION_KEY] = svc
    return svc


def _read_df_via_sheets_api(worksheet: str) -> pd.DataFrame:
    sheet_url = get_sheet_url()
    spreadsheet_id = _spreadsheet_id_from_url(sheet_url)
    if not spreadsheet_id:
        raise ValueError("스프레드시트 ID를 찾지 못했습니다.")
    svc = _get_students_sheets_api()
    if svc is None:
        raise ValueError("Sheets API 인증 정보를 찾지 못했습니다.")
    res = (
        svc.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=f"{worksheet}!A:ZZ")
        .execute()
    )
    rows = res.get("values", [])
    if not rows:
        return pd.DataFrame()
    headers = [str(x) for x in rows[0]]
    body = rows[1:]
    width = len(headers)
    normalized = []
    for r in body:
        row = list(r[:width]) + [""] * max(0, width - len(r))
        normalized.append(row)
    return pd.DataFrame(normalized, columns=headers)


def _update_df_via_sheets_api(worksheet: str, data: pd.DataFrame):
    sheet_url = get_sheet_url()
    spreadsheet_id = _spreadsheet_id_from_url(sheet_url)
    if not spreadsheet_id:
        raise ValueError("스프레드시트 ID를 찾지 못했습니다.")
    svc = _get_students_sheets_api()
    if svc is None:
        raise ValueError("Sheets API 인증 정보를 찾지 못했습니다.")
    df = data.copy() if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
    df = df.astype(object).where(pd.notna(df), "")
    values = [list(map(str, df.columns.tolist()))] + df.astype(str).values.tolist()
    svc.spreadsheets().values().clear(
        spreadsheetId=spreadsheet_id,
        range=f"{worksheet}!A:ZZ",
        body={},
    ).execute()
    svc.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{worksheet}!A1",
        valueInputOption="RAW",
        body={"values": values},
    ).execute()


def _safe_read(conn, worksheet, ttl=0, retries=2):
    if worksheet in _STUDENTS_API_WS:
        try:
            return _read_df_via_sheets_api(worksheet)
        except Exception:
            pass
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
    if worksheet in _STUDENTS_API_WS:
        try:
            _update_df_via_sheets_api(worksheet, data)
            return
        except Exception:
            pass
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


def _spreadsheet_id_from_url(url: str) -> str:
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", str(url or ""))
    return m.group(1) if m else ""


def _a1_col(n: int) -> str:
    s = ""
    x = int(n)
    while x > 0:
        x, r = divmod(x - 1, 26)
        s = chr(65 + r) + s
    return s


def _fast_batch_write_for_approvals(
    students_df: pd.DataFrame,
    req_df: pd.DataFrame,
    students_updates: list[tuple[int, int]],
    req_updates: list[tuple[int, str, str]],
    log_rows: list[dict],
) -> bool:
    """Sheets API row-level write path. Returns True on success."""
    try:
        sheet_url = get_sheet_url()
        spreadsheet_id = _spreadsheet_id_from_url(sheet_url)
        if not spreadsheet_id:
            return False
        creds = get_service_account_credentials(("https://www.googleapis.com/auth/spreadsheets",))
        if not creds:
            return False
        svc = build("sheets", "v4", credentials=creds, cache_discovery=False)

        # students: 잔여 횟수 컬럼만 갱신
        students_col_idx = students_df.columns.get_loc("잔여 횟수") + 1
        students_col = _a1_col(students_col_idx)
        students_data = []
        for ridx, remain_after in students_updates:
            row_no = int(ridx) + 2  # header row + 1
            students_data.append(
                {"range": f"students!{students_col}{row_no}", "values": [[int(remain_after)]]}
            )
        if students_data:
            svc.spreadsheets().values().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"valueInputOption": "RAW", "data": students_data},
            ).execute()

        # attendance_requests: status + approved_time 갱신
        status_col_idx = req_df.columns.get_loc("status") + 1
        approved_col_idx = req_df.columns.get_loc("approved_time") + 1
        status_col = _a1_col(status_col_idx)
        approved_col = _a1_col(approved_col_idx)
        req_data = []
        for ridx, status_val, approved_time in req_updates:
            row_no = int(ridx) + 2
            req_data.append(
                {
                    "range": f"attendance_requests!{status_col}{row_no}:{approved_col}{row_no}",
                    "values": [[str(status_val), str(approved_time)]],
                }
            )
        if req_data:
            svc.spreadsheets().values().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"valueInputOption": "RAW", "data": req_data},
            ).execute()

        # attendance_log: append
        if log_rows:
            append_values = [
                [
                    str(r.get("time", "")),
                    str(r.get("student_id", "")),
                    str(r.get("student_name", "")),
                    int(r.get("remain_count", 0)),
                    str(r.get("event", "")),
                    str(r.get("request_id", "")),
                    str(r.get("request_time", "")),
                    str(r.get("approved_time", "")),
                ]
                for r in log_rows
            ]
            svc.spreadsheets().values().append(
                spreadsheetId=spreadsheet_id,
                range="attendance_log!A1",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": append_values},
            ).execute()

        return True
    except Exception:
        return False

def run_student_ui():
    from core.curriculum import get_course_options, get_course_price_map
    from core.schedule import run_schedule_ui

    st.subheader("👥 회원 등록 관리")
    _attendance_notice = st.session_state.pop("student_attendance_notice", None)
    if isinstance(_attendance_notice, tuple) and len(_attendance_notice) == 2:
        kind, msg = _attendance_notice
        if kind == "success":
            st.success(str(msg))
        else:
            st.error(str(msg))

    def _suggest_sessions(course_name):
        course_text = str(course_name).upper()
        if "코스 A".upper() in course_text:
            return 4
        if "코스 B".upper() in course_text:
            return 8
        return 10

    def _resolve_course_price(course_name):
        # 코스/금액이 시트에서 바뀌면 즉시 반영
        price_map = get_course_price_map(force_refresh=False)
        if course_name in price_map:
            return int(price_map[course_name] or 0)
        for k, v in price_map.items():
            if str(k) in str(course_name) or str(course_name) in str(k):
                return int(v or 0)
        return 0
    
    with st.expander("👥 회원 등록 관리", expanded=False):
        student_section = st.segmented_control(
            "회원 메뉴",
            ["📝 신규 등록", "📋 원생 명부", "✏️ 명부 수정"],
            default="📝 신규 등록",
            key="student_main_section",
            label_visibility="collapsed",
        )

        if student_section == "📝 신규 등록":
            st.write("새로운 수강생 정보를 입력해주세요.")
            # 코스/할인/금액이 선택 즉시 반영되도록 form 대신 일반 위젯 사용
            course_options = get_course_options(force_refresh=False)
            if "student_reg_course_prev" not in st.session_state:
                st.session_state["student_reg_course_prev"] = ""
            if "student_reg_total_prev" not in st.session_state:
                st.session_state["student_reg_total_prev"] = 10

            name = st.text_input("이름", placeholder="이름을 입력하세요", key="student_reg_name")
            contact = st.text_input("연락처", placeholder="010-0000-0000", key="student_reg_contact")
            course = st.selectbox("수강 코스", course_options, key="student_reg_course")
            suggested_sessions = _suggest_sessions(course)
            st.markdown("**결제 정보**")

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
            discount_type = st.selectbox(
                "할인 유형",
                ["없음", "정액 할인", "정률 할인(%)", "이벤트가 직접입력"],
                key="student_reg_discount_type",
            )
            event_name = ""
            discount_value = 0
            discount_amount = 0
            final_amount = base_amount

            if discount_type == "정액 할인":
                discount_value = int(
                    st.number_input("할인 금액(원)", min_value=0, value=0, step=1000, key="student_reg_discount_fixed")
                )
                discount_amount = min(discount_value, base_amount)
                final_amount = max(0, base_amount - discount_amount)
            elif discount_type == "정률 할인(%)":
                discount_value = int(
                    st.number_input("할인율(%)", min_value=0, max_value=100, value=0, step=5, key="student_reg_discount_rate")
                )
                discount_amount = int(round(base_amount * (discount_value / 100.0)))
                final_amount = max(0, base_amount - discount_amount)
            elif discount_type == "이벤트가 직접입력":
                event_name = st.text_input("이벤트명", placeholder="예: 봄맞이 원데이 20%", key="student_reg_event_name")
                final_amount = int(
                    st.number_input("최종 결제금액(원)", min_value=0, value=int(base_amount), step=1000, key="student_reg_final_amount")
                )
                discount_amount = max(0, base_amount - final_amount)
                discount_value = discount_amount

            st.caption(
                f"원가 **{base_amount:,}원** · 할인 **{discount_amount:,}원** · 최종 **{final_amount:,}원**"
            )

            st.session_state["student_reg_course_prev"] = course
            st.session_state["student_reg_total_prev"] = int(total_sessions)

            reg_date = st.date_input("등록일", value=datetime.now(), key="student_reg_date")
            memo = st.text_area("특이사항 및 메모", key="student_reg_memo")

            if st.button("✅ 수강생 등록하기", use_container_width=True, key="student_reg_submit"):
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
    
        elif student_section == "📋 원생 명부":
            display_student_list(show_mode="list")
    
        else:
            display_student_list(show_mode="edit")

    with st.expander("✅ 회원 출석 관리", expanded=bool(st.session_state.pop("open_attendance_manager_once", False))):
        approve_bg = "linear-gradient(120deg, #8ECF9B 0%, #6FB47F 100%)"
        reject_bg = "linear-gradient(120deg, #E7A4A4 0%, #D58282 100%)"
        try:
            root = Path(__file__).resolve().parent.parent
            icon_roots = [root / "assets", root.parent / "assets"]
            for asset_root in icon_roots:
                ap_path = asset_root / "approved.png"
                rj_path = asset_root / "rejected.png"
                if ap_path.exists():
                    ap_b64 = base64.b64encode(ap_path.read_bytes()).decode("ascii")
                    approve_bg = f"url('data:image/png;base64,{ap_b64}') center/cover no-repeat"
                if rj_path.exists():
                    rj_b64 = base64.b64encode(rj_path.read_bytes()).decode("ascii")
                    reject_bg = f"url('data:image/png;base64,{rj_b64}') center/cover no-repeat"
        except Exception:
            pass

        components.html(
            f"""
            <style>
            div[data-testid="stButton"] > button.approve-art-btn {{
                background: {approve_bg} !important;
                background-size: cover !important;
                background-position: center !important;
                background-repeat: no-repeat !important;
                border: none !important;
                outline: none !important;
                box-shadow: 0 3px 8px rgba(0, 0, 0, 0.18) !important;
                color: #ffffff !important;
                text-shadow: 0 1px 2px rgba(0, 0, 0, 0.35) !important;
            }}
            div[data-testid="stButton"] > button.reject-art-btn {{
                background: {reject_bg} !important;
                background-size: cover !important;
                background-position: center !important;
                background-repeat: no-repeat !important;
                border: none !important;
                outline: none !important;
                box-shadow: 0 3px 8px rgba(0, 0, 0, 0.18) !important;
                color: #ffffff !important;
                text-shadow: 0 1px 2px rgba(0, 0, 0, 0.35) !important;
            }}
            div[data-testid="stButton"] > button.approve-art-btn:focus,
            div[data-testid="stButton"] > button.approve-art-btn:focus-visible,
            div[data-testid="stButton"] > button.reject-art-btn:focus,
            div[data-testid="stButton"] > button.reject-art-btn:focus-visible {{
                outline: none !important;
                border: none !important;
                box-shadow: 0 3px 8px rgba(0, 0, 0, 0.18) !important;
            }}
            </style>
            <script>
            (function () {{
              const doc = window.parent && window.parent.document ? window.parent.document : document;
              function applyApproveRejectStyles() {{
                try {{
                  const btns = doc.querySelectorAll('div[data-testid="stButton"] > button');
                  btns.forEach((b) => {{
                    const t = (b.innerText || "").trim();
                    if (t === "승인") {{
                      b.classList.add("approve-art-btn");
                      b.style.setProperty("background", "{approve_bg}", "important");
                      b.style.setProperty("border", "none", "important");
                      b.style.setProperty("outline", "none", "important");
                      b.style.setProperty("color", "#ffffff", "important");
                    }}
                    if (t === "거절") {{
                      b.classList.add("reject-art-btn");
                      b.style.setProperty("background", "{reject_bg}", "important");
                      b.style.setProperty("border", "none", "important");
                      b.style.setProperty("outline", "none", "important");
                      b.style.setProperty("color", "#ffffff", "important");
                    }}
                    if (t.includes("전체 승인")) {{
                      b.classList.add("approve-art-btn");
                      b.style.setProperty("background", "{approve_bg}", "important");
                      b.style.setProperty("border", "none", "important");
                      b.style.setProperty("outline", "none", "important");
                      b.style.setProperty("color", "#ffffff", "important");
                    }}
                  }});
                }} catch (e) {{}}
              }}
              applyApproveRejectStyles();
              setTimeout(applyApproveRejectStyles, 80);
              setTimeout(applyApproveRejectStyles, 250);
              setTimeout(applyApproveRejectStyles, 600);
            }})();
            </script>
            """,
            height=0,
        )

        pending_requests = get_pending_attendance_requests(limit=20, force_refresh=False)
        pending_count = len(pending_requests) if not pending_requests.empty else 0

        if pending_count > 0:
            c1, c2 = st.columns([2, 1], gap="small")
            with c1:
                st.caption(f"승인 대기 {pending_count}건")
            with c2:
                if st.button("✅ 전체 승인", use_container_width=True, key="student_approve_all_pending"):
                    ok, msg = approve_all_pending_requests(limit=200)
                    st.session_state["student_attendance_notice"] = ("success", msg) if ok else ("error", msg)
                    st.rerun()
        else:
            st.info("승인 대기 요청이 없습니다.")

        if not pending_requests.empty:
            for _, row in pending_requests.iterrows():
                req_id = str(row.get("request_id", ""))
                req_time = str(row.get("time", ""))
                student_name = str(row.get("student_name", "회원"))
                student_id = str(row.get("student_id", ""))
                with st.container(border=True):
                    st.markdown(f"**{student_name}** (`{student_id}`)")
                    st.caption(f"요청: {req_time}")
                    c_ok, c_no = st.columns(2, gap="small")
                    with c_ok:
                        if st.button("승인", key=f"student_approve_req_{req_id}", use_container_width=True):
                            ok, msg = approve_attendance_request(req_id)
                            st.session_state["student_attendance_notice"] = ("success", msg) if ok else ("error", msg)
                            st.rerun()
                    with c_no:
                        if st.button("거절", key=f"student_reject_req_{req_id}", use_container_width=True):
                            ok, msg = reject_attendance_request(req_id)
                            st.session_state["student_attendance_notice"] = ("success", msg) if ok else ("error", msg)
                            st.rerun()

        with st.expander("출석표", expanded=False):
            view_scope = st.segmented_control(
                "출석표 범위",
                ["오늘", "이번달"],
                default="오늘",
                key="attendance_log_scope",
                label_visibility="collapsed",
            )
            recent_logs = get_recent_attendance_logs(limit=500, force_refresh=False)
            if recent_logs.empty:
                st.caption("표시할 출석 이력이 없습니다.")
            else:
                work = recent_logs.copy()
                approved_ts = pd.to_datetime(work["approved_time"], errors="coerce") if "approved_time" in work.columns else pd.Series(pd.NaT, index=work.index)
                time_ts = pd.to_datetime(work["time"], errors="coerce") if "time" in work.columns else pd.Series(pd.NaT, index=work.index)
                ts = approved_ts.where(approved_ts.notna(), time_ts)
                now = datetime.now()
                if view_scope == "오늘":
                    mask = ts.dt.date == now.date()
                else:
                    mask = (ts.dt.year == now.year) & (ts.dt.month == now.month)
                filt = work[mask.fillna(False)].copy()
                if filt.empty:
                    st.caption("선택한 범위의 출석 이력이 없습니다.")
                else:
                    out = pd.DataFrame(
                        {
                            "날짜": ts[mask.fillna(False)].dt.strftime("%Y-%m-%d").fillna(""),
                            "시간": ts[mask.fillna(False)].dt.strftime("%H:%M:%S").fillna(""),
                            "이름": filt.get("student_name", pd.Series([""] * len(filt))).astype(str).values,
                        }
                    )
                    st.dataframe(out.reset_index(drop=True), use_container_width=True, hide_index=True)

    with st.expander("🗓 회원 일정 관리", expanded=False):
        run_schedule_ui(simple_mode=True)
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

        from core.finance import record_registration_payment

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


def _normalize_student_id_text(v):
    """'26002.0' 같은 표기를 '26002'로 정규화."""
    try:
        s = "" if v is None or (hasattr(pd, "isna") and pd.isna(v)) else str(v).strip()
        if not s:
            return ""
        n = pd.to_numeric(s, errors="coerce")
        if pd.notna(n):
            return str(int(float(n)))
        return s
    except Exception:
        return str(v).strip()


def _get_latest_reg_event_map(ttl=60):
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


def update_student_profile(
    student_id,
    *,
    name=None,
    contact=None,
    reg_date=None,
    course=None,
    total_sessions=None,
    remain_sessions=None,
    status=None,
    memo=None,
):
    """명부 카드에서 기본 프로필 정보를 즉시 수정 저장합니다."""
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

        for col in ["이름", "연락처", "등록일", "수강코스", "총 횟수", "잔여 횟수", "상태", "메모"]:
            if col not in df.columns:
                df[col] = ""

        if name is not None:
            df.at[row_idx, "이름"] = str(name).strip()
        if contact is not None:
            df.at[row_idx, "연락처"] = str(contact).strip()
        if reg_date is not None:
            if hasattr(reg_date, "strftime"):
                df.at[row_idx, "등록일"] = reg_date.strftime("%Y-%m-%d")
            else:
                df.at[row_idx, "등록일"] = str(reg_date).strip()
        if course is not None:
            df.at[row_idx, "수강코스"] = str(course).strip()
        if total_sessions is not None:
            df.at[row_idx, "총 횟수"] = str(int(total_sessions))
        if remain_sessions is not None:
            df.at[row_idx, "잔여 횟수"] = str(int(remain_sessions))
        if status is not None:
            norm = _normalize_student_status(status)
            df.at[row_idx, "상태"] = norm if norm in STUDENT_STATUS_OPTIONS else "재원"
        if memo is not None:
            df.at[row_idx, "메모"] = str(memo)

        _safe_update(conn, worksheet="students", data=df)
        return True, "원생 정보가 저장되었습니다."
    except Exception as e:
        return False, f"원생 정보 저장 실패: {e}"


def display_student_list(show_mode="list"):
    """ID 기반 카드 UI + 출석 차감 버튼 통합 버전"""
    from core.curriculum import get_course_options

    try:
        conn = get_conn()
        # 목록은 캐시 사용(읽기 요청 절감), 수정/저장 시 rerun으로 즉시 반영
        df = _safe_read(conn, worksheet="students", ttl=60)
        
        if df is not None and not df.empty:
            # 1. 데이터 타입 정돈 (ID 소수점 제거 및 숫자형 확정)
            df["ID"] = pd.to_numeric(df["ID"], errors='coerce').fillna(0).astype(int).astype(str)
            df["잔여 횟수"] = pd.to_numeric(df["잔여 횟수"], errors='coerce').fillna(0).astype(int)
            if "상태" not in df.columns:
                df["상태"] = "재원"
            df["상태"] = _normalize_student_status(df["상태"])
            
            reg_event_map = _get_latest_reg_event_map(ttl=60)

            # 2. 상단 필터 UI
            st.markdown("---")
            view_option = st.radio(
                "🔍 보기 설정",
                ["재원생만", "전체 명단", "퇴원/휴원"],
                horizontal=True,
                key=f"student_list_view_option_{show_mode}",
            )
            search_name = st.text_input(
                "👤 이름 검색",
                placeholder="이름 입력",
                key=f"student_list_search_name_{show_mode}",
            )

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

                    if show_mode != "edit":
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

                    with st.expander("수정", expanded=(show_mode == "edit")):
                        cur = stu_status if stu_status in STUDENT_STATUS_OPTIONS else "재원"
                        fresh_course_options = get_course_options(force_refresh=False)
                        cur_course = str(row["수강코스"]) if pd.notna(row["수강코스"]) else ""
                        course_candidates = list(fresh_course_options)
                        if cur_course and cur_course not in course_candidates:
                            course_candidates = [cur_course] + course_candidates
                        if not course_candidates:
                            course_candidates = ["기타"]
                        try:
                            default_course_idx = course_candidates.index(cur_course)
                        except ValueError:
                            default_course_idx = 0
                        parsed_reg_date = pd.to_datetime(str(row.get("등록일", "")), errors="coerce")
                        default_reg_date = parsed_reg_date if pd.notna(parsed_reg_date) else datetime.now()

                        with st.form(f"student_edit_form_{row['ID']}"):
                            edit_name = st.text_input("이름", value=str(row["이름"]))
                            edit_contact = st.text_input("연락처", value=str(row["연락처"]))
                            edit_reg_date = st.date_input("등록일", value=default_reg_date)
                            edit_course = st.selectbox("수강코스", course_candidates, index=default_course_idx)
                            edit_total = st.number_input("총 횟수", min_value=1, value=max(1, int(pd.to_numeric(row.get("총 횟수", 1), errors="coerce") or 1)))
                            edit_remain = st.number_input("잔여 횟수", min_value=0, value=max(0, int(pd.to_numeric(row.get("잔여 횟수", 0), errors="coerce") or 0)))
                            cur_status_for_edit = stu_status if stu_status in STUDENT_STATUS_OPTIONS else "재원"
                            edit_status = st.selectbox("상태", list(STUDENT_STATUS_OPTIONS), index=list(STUDENT_STATUS_OPTIONS).index(cur_status_for_edit))
                            edit_memo = st.text_area("메모", value=str(row.get("메모", "")))
                            if st.form_submit_button("저장", use_container_width=True):
                                ok, msg = update_student_profile(
                                    row["ID"],
                                    name=edit_name,
                                    contact=edit_contact,
                                    reg_date=edit_reg_date,
                                    course=edit_course,
                                    total_sessions=edit_total,
                                    remain_sessions=edit_remain,
                                    status=edit_status,
                                    memo=edit_memo,
                                )
                                if ok:
                                    st.success(msg)
                                    st.rerun()
                                else:
                                    st.error(msg)

                    if show_mode != "edit":
                        # 모바일에서 누르기 쉬운 단일 CTA (재원생만)
                        if stu_status == "재원":
                            if st.button("✅ 출석 처리 (1회 차감)", key=f"att_{row['ID']}", use_container_width=True):
                                success, result = deduct_session(row['ID'])
                                if success:
                                    if datetime.now().weekday() == 6:
                                        st.toast("✅ 일요일은 출석을 레슨 없는 자율 작업 날이라 승인해도 차감되지 않습니다.")
                                    else:
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
        student_id = _normalize_student_id_text(student_id)
        
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
        student_id = _normalize_student_id_text(student_id)
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

        student_id = _normalize_student_id_text(student_id)
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


def get_owner_dashboard_data(
    pending_limit=20,
    failed_limit=20,
    recent_limit=3,
    force_refresh: bool = False,
):
    """운영 대시보드용 통합 조회(요청/실패/최근로그). 시트 read 횟수를 최소화합니다."""
    _t0 = time.perf_counter()
    try:
        now = time.time()
        if not force_refresh:
            ts = st.session_state.get(_OWNER_DASH_BUNDLE_TS)
            cached = st.session_state.get(_OWNER_DASH_BUNDLE_KEY)
            if ts is not None and cached is not None and (now - ts) < _OWNER_DASH_CACHE_TTL_SEC:
                perf_log("students.get_owner_dashboard_data", (time.perf_counter() - _t0) * 1000.0)
                return cached

        conn = get_conn()
        req_df = _get_attendance_requests_raw_cached(conn, force_refresh=force_refresh)

        if req_df is None or req_df.empty:
            pending = pd.DataFrame(columns=["request_id", "time", "student_id", "student_name", "status", "approved_time"])
            failed = pending.copy()
        else:
            req_work = req_df.copy()
            if "time" in req_work.columns:
                req_work = req_work.sort_values(by="time", ascending=False)
            pending = req_work[req_work["status"].astype(str) == "pending"].head(pending_limit).copy() if "status" in req_work.columns else pd.DataFrame()

            failed_work = req_df.copy()
            if "approved_time" in failed_work.columns:
                failed_work = failed_work.sort_values(by="approved_time", ascending=False)
            failed = failed_work[failed_work["status"].astype(str) == "approved_log_failed"].head(failed_limit).copy() if "status" in failed_work.columns else pd.DataFrame()

        if int(recent_limit) > 0:
            recent = get_recent_attendance_logs(limit=recent_limit, force_refresh=force_refresh)
        else:
            recent = pd.DataFrame(
                columns=["time", "student_id", "student_name", "remain_count", "event", "request_id", "request_time", "approved_time"]
            )
        out = (pending, failed, recent)
        st.session_state[_OWNER_DASH_BUNDLE_KEY] = out
        st.session_state[_OWNER_DASH_BUNDLE_TS] = now
        perf_log("students.get_owner_dashboard_data", (time.perf_counter() - _t0) * 1000.0)
        return out
    except Exception:
        empty_req = pd.DataFrame(columns=["request_id", "time", "student_id", "student_name", "status", "approved_time"])
        empty_log = pd.DataFrame(
            columns=["time", "student_id", "student_name", "remain_count", "event", "request_id", "request_time", "approved_time"]
        )
        perf_log("students.get_owner_dashboard_data", (time.perf_counter() - _t0) * 1000.0)
        return empty_req, empty_req.copy(), empty_log


def approve_attendance_request(request_id):
    """원장이 요청을 승인하면 실제 1회 차감합니다."""
    _t0 = time.perf_counter()
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

        student_id = _normalize_student_id_text(req_df.at[row_idx, "student_id"])
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
            perf_log("students.approve_attendance_request", (time.perf_counter() - _t0) * 1000.0)
            return True, f"{student_name}님 차감은 완료되었지만 로그 저장은 실패했습니다. (재시도 필요)"
        if is_sunday:
            perf_log("students.approve_attendance_request", (time.perf_counter() - _t0) * 1000.0)
            return True, "일요일은 출석을 레슨 없는 자율 작업 날이라 승인해도 차감되지 않습니다."
        perf_log("students.approve_attendance_request", (time.perf_counter() - _t0) * 1000.0)
        return True, f"{student_name}님 승인 완료! 남은 횟수: {result}회"
    except Exception as e:
        perf_log("students.approve_attendance_request", (time.perf_counter() - _t0) * 1000.0)
        return False, f"승인 처리 실패: {e}"


def approve_all_pending_requests(limit=200):
    """대기중 요청을 최신순으로 일괄 승인합니다."""
    _t0 = time.perf_counter()
    try:
        conn = get_conn()
        req_df = _read_or_init_attendance_requests(conn, read_ttl=0)
        if req_df is None or req_df.empty:
            return False, "승인할 대기 요청이 없습니다."
        if "status" not in req_df.columns:
            return False, "요청 데이터 형식이 올바르지 않습니다."

        pending_df = req_df[req_df["status"].astype(str) == "pending"].copy()
        if "time" in pending_df.columns:
            pending_df = pending_df.sort_values(by="time", ascending=False)
        pending_df = pending_df.head(limit)
        if pending_df is None or pending_df.empty:
            return False, "승인할 대기 요청이 없습니다."

        students_df = _safe_read(conn, worksheet="students", ttl=0)
        if students_df is None or students_df.empty:
            return False, "원생 정보를 불러올 수 없습니다."
        if "ID" not in students_df.columns:
            return False, "원생 데이터 형식이 올바르지 않습니다."
        students_df["ID"] = pd.to_numeric(students_df["ID"], errors="coerce").fillna(0).astype(int).astype(str)
        if "잔여 횟수" not in students_df.columns:
            students_df["잔여 횟수"] = 0
        if "상태" not in students_df.columns:
            students_df["상태"] = "재원"

        log_columns = [
            "time",
            "student_id",
            "student_name",
            "remain_count",
            "event",
            "request_id",
            "request_time",
            "approved_time",
        ]

        success_cnt = 0
        fail_cnt = 0
        fail_msgs = []
        log_rows = []
        is_sunday = datetime.now().weekday() == 6
        students_changed = False
        students_updates = []
        req_updates = []

        for req_idx, row in pending_df.iterrows():
            req_id = str(row.get("request_id", "")).strip()
            if not req_id:
                fail_cnt += 1
                continue
            student_id = _normalize_student_id_text(row.get("student_id", ""))
            sidx = students_df.index[students_df["ID"] == str(student_id)].tolist()
            if not sidx:
                fail_cnt += 1
                if len(fail_msgs) < 3:
                    fail_msgs.append(f"{req_id}: 원생 정보를 찾을 수 없습니다.")
                continue

            srow = sidx[0]
            status_val = _normalize_student_status(students_df.at[srow, "상태"])
            if isinstance(status_val, str) and status_val != "재원":
                fail_cnt += 1
                if len(fail_msgs) < 3:
                    fail_msgs.append(f"{req_id}: 상태「{status_val}」는 차감 불가")
                continue

            _remain_num = pd.to_numeric(students_df.at[srow, "잔여 횟수"], errors="coerce")
            current_count = int(0 if pd.isna(_remain_num) else _remain_num)
            if not is_sunday and current_count <= 0:
                fail_cnt += 1
                if len(fail_msgs) < 3:
                    fail_msgs.append(f"{req_id}: 잔여 횟수 부족")
                continue

            approved_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            remain_after = current_count if is_sunday else (current_count - 1)
            if not is_sunday:
                students_df.at[srow, "잔여 횟수"] = remain_after
                students_changed = True
                students_updates.append((int(srow), int(remain_after)))

            req_df.at[req_idx, "status"] = "approved"
            req_df.at[req_idx, "approved_time"] = approved_time
            req_updates.append((int(req_idx), "approved", approved_time))

            log_rows.append(
                {
                    "time": approved_time,
                    "student_id": str(student_id),
                    "student_name": str(row.get("student_name", "회원")),
                    "remain_count": int(remain_after),
                    "event": "attendance_free_drawing" if is_sunday else "attendance_deducted",
                    "request_id": req_id,
                    "request_time": str(row.get("time", "")),
                    "approved_time": approved_time,
                }
            )
            success_cnt += 1

        if success_cnt > 0:
            fast_ok = _fast_batch_write_for_approvals(
                students_df=students_df,
                req_df=req_df,
                students_updates=students_updates if students_changed else [],
                req_updates=req_updates,
                log_rows=log_rows,
            )
            if not fast_ok:
                if students_changed:
                    _safe_update(conn, worksheet="students", data=students_df)
                if log_rows:
                    try:
                        log_df = _safe_read(conn, worksheet="attendance_log", ttl=15)
                    except Exception:
                        log_df = pd.DataFrame(columns=log_columns)
                    if log_df is None or log_df.empty:
                        log_df = pd.DataFrame(columns=log_columns)
                    for col in log_columns:
                        if col not in log_df.columns:
                            log_df[col] = ""
                    log_df = pd.concat([log_df, pd.DataFrame(log_rows)], ignore_index=True)
                    _safe_update(conn, worksheet="attendance_log", data=log_df)
                _safe_update(conn, worksheet="attendance_requests", data=req_df)
            invalidate_owner_dashboard_sheet_caches()

        if fail_cnt == 0 and success_cnt > 0:
            suffix = " (일요일: 차감 없이 승인 처리)" if is_sunday else ""
            perf_log("students.approve_all_pending_requests", (time.perf_counter() - _t0) * 1000.0)
            return True, f"전체 승인 완료: {success_cnt}건{suffix}"
        if success_cnt == 0:
            detail = f" (예: {' | '.join(fail_msgs)})" if fail_msgs else ""
            perf_log("students.approve_all_pending_requests", (time.perf_counter() - _t0) * 1000.0)
            return False, f"승인 실패: {fail_cnt}건{detail}"

        extra = f" / 실패 {fail_cnt}건"
        detail = f" (예: {' | '.join(fail_msgs)})" if fail_msgs else ""
        suffix = " / 일요일: 차감 없이 승인 처리" if is_sunday else ""
        perf_log("students.approve_all_pending_requests", (time.perf_counter() - _t0) * 1000.0)
        return True, f"일괄 처리: 승인 {success_cnt}건{extra}{suffix}{detail}"
    except Exception as e:
        perf_log("students.approve_all_pending_requests", (time.perf_counter() - _t0) * 1000.0)
        return False, f"전체 승인 실패: {e}"


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

        read_ttl = 0 if force_refresh else 60
        try:
            df = _safe_read(conn, worksheet="attendance_log", ttl=read_ttl)
        except Exception:
            # 탭이 없으면 빈 탭 자동 생성 시도
            empty_df = pd.DataFrame(
                columns=["time", "student_id", "student_name", "remain_count", "event", "request_id", "request_time", "approved_time"]
            )
            _safe_update(conn, worksheet="attendance_log", data=empty_df)
            df = _safe_read(conn, worksheet="attendance_log", ttl=read_ttl)

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