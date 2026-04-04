import streamlit as st
import pandas as pd
from datetime import datetime
import time
from core.database import get_conn
from core.perf import perf_log


WORKSHEET_NAME = "student_schedule"
BASE_COLUMNS = ["id", "student_id", "student_name", "weekday", "time_slot", "start_date", "end_date", "memo", "created_at"]
_SCHEDULE_NEXT_READ_FRESH = "_schedule_next_read_fresh"
WEEKDAY_ORDER = ["월", "화", "수", "목", "금", "토", "일"]
TIME_SLOTS_BY_WEEKDAY = {
    "월": ["10:30~13:00", "14:30~17:00", "18:30~21:00"],
    "화": ["10:30~13:00", "14:30~17:00", "18:30~21:00"],
    "수": ["10:30~13:00", "14:30~17:00", "18:30~21:00"],
    "목": ["10:30~13:00", "14:30~17:00", "18:30~21:00"],
    "금": ["10:30~13:00", "14:30~17:00", "18:30~21:00"],
    "토": ["09:30~12:00", "13:00~15:30"],
    "일": ["자유드로잉"],
}
MAX_STUDENTS_PER_SLOT = 4


def _mark_schedule_dirty():
    """시간표 쓰기 직후 다음 조회 1회는 ttl 캐시를 우회."""
    st.session_state[_SCHEDULE_NEXT_READ_FRESH] = True


def _schedule_read_ttl(default_ttl=60):
    return 0 if st.session_state.pop(_SCHEDULE_NEXT_READ_FRESH, False) else default_ttl


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


def _read_or_init_schedule(ttl=60):
    conn = get_conn()
    try:
        df = _safe_read(conn, worksheet=WORKSHEET_NAME, ttl=ttl)
    except Exception:
        df = pd.DataFrame(columns=BASE_COLUMNS)
        _safe_update(conn, worksheet=WORKSHEET_NAME, data=df)
        df = _safe_read(conn, worksheet=WORKSHEET_NAME, ttl=ttl)

    if df is None or df.empty:
        df = pd.DataFrame(columns=BASE_COLUMNS)
    for c in BASE_COLUMNS:
        if c not in df.columns:
            df[c] = ""
    return conn, df[BASE_COLUMNS].copy()


def _get_registered_students():
    """students에서 일정 등록용 목록. 명부와 동일한 상태 규칙·최신 데이터를 씁니다."""
    from core.students import _normalize_student_id_text, _normalize_student_status

    conn = get_conn()
    try:
        # 명부에 맞춘 직후 반영을 위해 캐시 없이 조회
        sdf = _safe_read(conn, worksheet="students", ttl=0)
    except Exception:
        return pd.DataFrame(columns=["ID", "이름", "상태"])

    if sdf is None or sdf.empty:
        return pd.DataFrame(columns=["ID", "이름", "상태"])

    for c in ["ID", "이름", "상태"]:
        if c not in sdf.columns:
            sdf[c] = ""

    sdf["ID"] = sdf["ID"].map(_normalize_student_id_text)
    sdf = sdf[sdf["ID"] != ""]
    sdf["이름"] = sdf["이름"].astype(str).str.strip()
    sdf["상태"] = _normalize_student_status(sdf["상태"])
    sdf = sdf[~sdf["이름"].isin(("", "nan", "None", "NaN"))]

    # 재원만 (명부 카드의 '재원생만'과 동일). 비어 있으면 전체 후보(이름 있는 행)
    active = sdf[sdf["상태"] == "재원"].copy()
    return active if not active.empty else sdf


def _weekday_to_kor(weekday_idx):
    # Monday=0 ... Sunday=6
    return WEEKDAY_ORDER[int(weekday_idx)]


def get_today_schedule_by_student(student_id):
    """원생용 화면에서 오늘 일정 조회"""
    _, df = _read_or_init_schedule(ttl=_schedule_read_ttl())
    if df.empty:
        return pd.DataFrame(columns=BASE_COLUMNS)

    today_kor = _weekday_to_kor(datetime.now().weekday())
    view = df[
        (df["student_id"].astype(str) == str(student_id))
        & (df["weekday"].astype(str) == today_kor)
    ].copy()
    if view.empty:
        return view

    view = view.sort_values(by=["time_slot", "created_at"], ascending=[True, True])
    return view


def run_schedule_ui(simple_mode=False):
    _t0 = time.perf_counter()
    st.subheader("🗓 원생 시간표")
    conn, df = _read_or_init_schedule(ttl=_schedule_read_ttl())
    if simple_mode:
        section = st.segmented_control(
            "일정 메뉴",
            ["📋 시간표 보기", "🗂 월별 타임테이블", "➕ 일정 등록"],
            default="📋 시간표 보기",
            key="schedule_simple_section",
            label_visibility="collapsed",
        )
        if section == "📋 시간표 보기":
            _render_schedule_view(df)
        elif section == "🗂 월별 타임테이블":
            _render_monthly_timetable(conn, df)
        else:
            _render_schedule_create(conn, df)
    else:
        section = st.segmented_control(
            "일정 메뉴",
            ["📋 시간표 보기", "🗂 월별 타임테이블", "➕ 일정 등록", "🗑 일정 삭제"],
            default="📋 시간표 보기",
            key="schedule_full_section",
            label_visibility="collapsed",
        )
        if section == "📋 시간표 보기":
            _render_schedule_view(df)
        elif section == "🗂 월별 타임테이블":
            _render_monthly_timetable(conn, df)
        elif section == "➕ 일정 등록":
            _render_schedule_create(conn, df)
        else:
            _render_schedule_delete(conn, df)
    perf_log("schedule.run_schedule_ui", (time.perf_counter() - _t0) * 1000.0)


def _monthly_timetable_weekdays_and_slots():
    weekdays = ["월", "화", "수", "목", "금", "토"]
    rows = [
        "10:30~13:00",
        "14:30~17:00",
        "18:30~21:00",
        "09:30~12:00",
        "13:00~15:30",
    ]
    return weekdays, rows


def build_monthly_timetable_parts(df, year: int, month: int):
    """(월별 격자 DataFrame, 해당 월 활성 일정 서브셋). df 비어 있으면 (빈 DF, 빈 DF)."""
    weekdays, slot_rows = _monthly_timetable_weekdays_and_slots()
    if df is None or df.empty:
        return pd.DataFrame(), pd.DataFrame()

    active_df = df[df.apply(lambda r: _is_active_in_month(r, int(year), int(month)), axis=1)].copy()
    table_data = []
    for slot in slot_rows:
        row = {"시간대": slot}
        for wd in weekdays:
            slot_df = active_df[
                (active_df["weekday"].astype(str) == wd)
                & (active_df["time_slot"].astype(str) == slot)
            ]
            names = [str(x).strip() for x in slot_df["student_name"].tolist() if str(x).strip()]
            count = len(names)
            if count == 0:
                cell = "-"
            else:
                people = ", ".join(names[:4])
                over = " ⚠️" if count > MAX_STUDENTS_PER_SLOT else ""
                cell = f"{count}/{MAX_STUDENTS_PER_SLOT}명{over}\n{people}"
            row[wd] = cell
        table_data.append(row)
    return pd.DataFrame(table_data), active_df


def render_monthly_timetable_fullscreen_page():
    """?fullscreen=schedule_month&schedule_year=&schedule_month= — 새 탭 전용."""
    conn, df = _read_or_init_schedule(ttl=_schedule_read_ttl())
    try:
        y = int(float(str(st.query_params.get("schedule_year", datetime.now().year))))
        m = int(float(str(st.query_params.get("schedule_month", datetime.now().month))))
    except Exception:
        y, m = datetime.now().year, datetime.now().month
    y = max(2020, min(2100, y))
    m = max(1, min(12, m))

    st.subheader(f"🗂 월별 타임테이블 · {y}년 {m}월")
    st.caption("시간 수정·등록은 메인 화면 → 원생 관리 → 월별 타임테이블에서 해 주세요.")
    if df.empty:
        st.info("등록된 시간표가 없습니다.")
    else:
        table_df, _ = build_monthly_timetable_parts(df, y, m)
        st.caption(f"{y}년 {m}월 기준 | 시간대별 정원 {MAX_STUDENTS_PER_SLOT}명")
        st.dataframe(table_df, use_container_width=True, hide_index=True)
    st.markdown(
        '<p style="margin-top:1rem;"><a href="/" target="_self">← 메인 화면으로</a></p>',
        unsafe_allow_html=True,
    )


def _is_active_in_month(row, year, month):
    start_txt = str(row.get("start_date", "")).strip()
    end_txt = str(row.get("end_date", "")).strip()
    month_start = datetime(year, month, 1)
    if month == 12:
        month_end = datetime(year + 1, 1, 1)
    else:
        month_end = datetime(year, month + 1, 1)

    def _parse_date(txt):
        if not txt:
            return None
        try:
            return datetime.strptime(txt, "%Y-%m-%d")
        except Exception:
            return None

    s = _parse_date(start_txt)
    e = _parse_date(end_txt)
    if s and s >= month_end:
        return False
    if e and e < month_start:
        return False
    return True


def _render_schedule_view(df):
    if df.empty:
        st.info("등록된 시간표가 없습니다.")
        return

    view = df.copy()
    view["weekday"] = pd.Categorical(view["weekday"], categories=WEEKDAY_ORDER, ordered=True)
    view = view.sort_values(by=["weekday", "time_slot", "student_name"], ascending=[True, True, True])
    st.dataframe(
        view,
        use_container_width=True,
        hide_index=True,
        column_order=["student_name", "student_id", "weekday", "time_slot", "start_date", "end_date", "memo", "id"],
    )


def _render_monthly_timetable(conn, df):
    from core.fullscreen_view import FS_SCHEDULE_MONTH, new_tab_link_markdown

    now = datetime.now()
    c1, c2 = st.columns(2)
    with c1:
        year = st.number_input("연도", min_value=2020, max_value=2100, value=now.year, step=1)
    with c2:
        month = st.number_input("월", min_value=1, max_value=12, value=now.month, step=1)

    st.markdown(
        new_tab_link_markdown(
            "이 연·월 표를 새 창에서 크게 보기",
            FS_SCHEDULE_MONTH,
            schedule_year=int(year),
            schedule_month=int(month),
        ),
        unsafe_allow_html=True,
    )

    if df.empty:
        st.info("등록된 시간표가 없습니다.")
        return

    table_df, active_df = build_monthly_timetable_parts(df, int(year), int(month))

    st.caption(f"{int(year)}년 {int(month)}월 기준 | 시간대별 정원 {MAX_STUDENTS_PER_SLOT}명")
    st.dataframe(table_df, use_container_width=True, hide_index=True)

    # 시간 수정 기능
    st.markdown("---")
    st.markdown("**시간 수정**")
    if active_df.empty:
        st.info("선택한 월에 수정 가능한 일정이 없습니다.")
        return

    edit_view = active_df.copy()
    edit_view["label"] = (
        edit_view["student_name"].astype(str).str.strip()
        + " ("
        + edit_view["student_id"].astype(str).str.strip()
        + ") | "
        + edit_view["weekday"].astype(str).str.strip()
        + " "
        + edit_view["time_slot"].astype(str).str.strip()
    )
    edit_options = edit_view["label"].tolist()
    picked = st.selectbox("수정할 일정", edit_options, key="schedule_edit_pick")
    target = edit_view[edit_view["label"] == picked].head(1)
    if target.empty:
        return

    row = target.iloc[0]
    cur_id = str(row.get("id", ""))
    cur_weekday = str(row.get("weekday", "월"))
    cur_time_slot = str(row.get("time_slot", "10:30~13:00"))
    cur_start = str(row.get("start_date", ""))
    cur_end = str(row.get("end_date", ""))
    cur_memo = str(row.get("memo", ""))

    c3, c4 = st.columns(2)
    with c3:
        new_weekday = st.selectbox(
            "새 요일",
            WEEKDAY_ORDER,
            index=WEEKDAY_ORDER.index(cur_weekday) if cur_weekday in WEEKDAY_ORDER else 0,
            key="schedule_edit_weekday",
        )
    with c4:
        time_options = TIME_SLOTS_BY_WEEKDAY.get(new_weekday, ["10:30~13:00"])
        default_idx = time_options.index(cur_time_slot) if cur_time_slot in time_options else 0
        new_time_slot = st.selectbox(
            "새 시간대",
            time_options,
            index=default_idx,
            key="schedule_edit_time_slot",
        )

    c5, c6 = st.columns(2)
    with c5:
        new_start = st.text_input("시작일", value=cur_start, key="schedule_edit_start")
    with c6:
        new_end = st.text_input("종료일", value=cur_end, key="schedule_edit_end")
    new_memo = st.text_area("메모", value=cur_memo, key="schedule_edit_memo")

    if st.button("선택 일정 시간 수정", use_container_width=True, key="schedule_edit_submit"):
        # 정원 체크(대상 행 제외)
        others = df[df["id"].astype(str) != cur_id].copy()
        active_same = others[
            (others["weekday"].astype(str) == str(new_weekday))
            & (others["time_slot"].astype(str) == str(new_time_slot))
        ]
        if len(active_same) >= MAX_STUDENTS_PER_SLOT:
            st.error(f"{new_weekday} {new_time_slot} 시간대는 정원 {MAX_STUDENTS_PER_SLOT}명입니다.")
            return

        updated = df.copy()
        idx = updated.index[updated["id"].astype(str) == cur_id].tolist()
        if not idx:
            st.error("수정 대상 일정을 찾지 못했습니다. 다시 시도해주세요.")
            return
        i = idx[0]
        updated.at[i, "weekday"] = str(new_weekday)
        updated.at[i, "time_slot"] = str(new_time_slot)
        updated.at[i, "start_date"] = str(new_start).strip()
        updated.at[i, "end_date"] = str(new_end).strip()
        updated.at[i, "memo"] = str(new_memo).strip()

        _safe_update(conn, worksheet=WORKSHEET_NAME, data=updated)
        _mark_schedule_dirty()
        st.success("일정 시간이 수정되었습니다.")
        st.rerun()


def _render_schedule_create(conn, df):
    students_df = _get_registered_students()
    if students_df.empty:
        st.warning("등록된 원생이 없습니다. 먼저 원생을 등록해주세요.")
        return

    student_options = []
    for _, row in students_df.iterrows():
        label = f"{row['이름']} ({row['ID']})"
        student_options.append((label, str(row["ID"]), str(row["이름"])))

    def _on_schedule_weekday_change():
        st.session_state.pop("schedule_create_time_slot", None)

    # 예전 폼과 동일 순서: 좌 — 원생·요일 / 우 — 시간대·시작일·종료일 → 메모 → 등록
    c1, c2 = st.columns(2)
    with c1:
        selected_label = st.selectbox(
            "원생 선택",
            [x[0] for x in student_options],
            key="schedule_create_student_label",
        )
        selected = next((x for x in student_options if x[0] == selected_label), None)
        student_id = selected[1] if selected else ""
        student_name = selected[2] if selected else ""
        weekday = st.selectbox(
            "요일",
            WEEKDAY_ORDER,
            key="schedule_create_weekday",
            on_change=_on_schedule_weekday_change,
        )
    with c2:
        time_options = TIME_SLOTS_BY_WEEKDAY.get(weekday, ["10:30~13:00"])
        time_slot = st.selectbox("시간대", time_options, key="schedule_create_time_slot")
        start_date = st.text_input("시작일", placeholder="예: 2026-03-01", key="schedule_create_start")
        end_date = st.text_input("종료일", placeholder="예: 2026-12-31 (선택)", key="schedule_create_end")
    memo = st.text_area("메모", placeholder="예: 정규반 코스 A", key="schedule_create_memo")

    if st.button("일정 등록", type="primary", use_container_width=True, key="schedule_create_submit"):
        if not student_name.strip() or not student_id.strip() or not str(time_slot).strip():
            st.error("원생 이름, ID, 시간대는 필수입니다.")
            return

        active_same = df[
            (df["weekday"].astype(str) == weekday)
            & (df["time_slot"].astype(str) == time_slot)
        ]
        if len(active_same) >= MAX_STUDENTS_PER_SLOT:
            st.error(f"{weekday} {time_slot} 시간대는 정원 {MAX_STUDENTS_PER_SLOT}명입니다.")
            return

        new_row = pd.DataFrame([{
            "id": f"sch_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
            "student_id": student_id.strip(),
            "student_name": student_name.strip(),
            "weekday": weekday,
            "time_slot": str(time_slot).strip(),
            "start_date": str(start_date).strip(),
            "end_date": str(end_date).strip(),
            "memo": str(memo).strip(),
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }])
        updated = pd.concat([df, new_row], ignore_index=True) if not df.empty else new_row
        _safe_update(conn, worksheet=WORKSHEET_NAME, data=updated)
        _mark_schedule_dirty()
        for k in (
            "schedule_create_student_label",
            "schedule_create_weekday",
            "schedule_create_time_slot",
            "schedule_create_start",
            "schedule_create_end",
            "schedule_create_memo",
        ):
            st.session_state.pop(k, None)
        st.success("시간표가 등록되었습니다.")
        st.rerun()


def _render_schedule_delete(conn, df):
    if df.empty:
        st.info("삭제할 일정이 없습니다.")
        return

    view = df.copy()
    view["label"] = (
        view["student_name"].astype(str).str.strip()
        + " ("
        + view["student_id"].astype(str).str.strip()
        + ") | "
        + view["weekday"].astype(str).str.strip()
        + " "
        + view["time_slot"].astype(str).str.strip()
    )

    st.markdown("**선택 삭제**")
    options = view["label"].tolist()
    selected = st.selectbox("삭제할 일정 선택", options)
    target = view[view["label"] == selected].head(1)
    if not target.empty and st.button("선택 일정 삭제", use_container_width=True, key="schedule_delete_selected"):
        target_id = str(target.iloc[0]["id"])
        updated = df[df["id"].astype(str) != target_id].copy()
        _safe_update(conn, worksheet=WORKSHEET_NAME, data=updated)
        _mark_schedule_dirty()
        st.success("일정이 삭제되었습니다.")
        st.rerun()

    st.markdown("---")
    st.markdown("**목록에서 바로 삭제**")
    for _, row in view.iterrows():
        row_id = str(row.get("id", ""))
        with st.container(border=True):
            st.write(f"{row.get('student_name', '')} ({row.get('student_id', '')})")
            st.caption(f"{row.get('weekday', '')} {row.get('time_slot', '')} | {row.get('start_date', '')} ~ {row.get('end_date', '')}")
            if st.button("삭제", key=f"del_schedule_{row_id}", use_container_width=True):
                updated = df[df["id"].astype(str) != row_id].copy()
                _safe_update(conn, worksheet=WORKSHEET_NAME, data=updated)
                _mark_schedule_dirty()
                st.success("일정이 삭제되었습니다.")
                st.rerun()
