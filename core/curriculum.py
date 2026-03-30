import streamlit as st
import pandas as pd
from datetime import datetime
import time
from core.database import get_conn
from core.perf import perf_log


WORKSHEET_NAME = "curriculum"
_CURRICULUM_NEXT_READ_FRESH = "_curriculum_next_read_fresh"

# 시트 컬럼 (영문): 코스ID, 코스이름, 횟수, 금액, 설명, 만들어진 날짜, 순서
COURSE_COLUMNS = [
    "course_id",
    "course_name",
    "sessions",
    "amount",
    "description",
    "created_at",
    "sort_order",
]


def _mark_curriculum_dirty():
    """커리큘럼 쓰기 직후 다음 조회 1회는 ttl 캐시를 우회."""
    st.session_state[_CURRICULUM_NEXT_READ_FRESH] = True


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


def _coerce_course_df(df):
    if df is None or df.empty:
        return pd.DataFrame(columns=COURSE_COLUMNS)
    out = df.copy()
    for c in COURSE_COLUMNS:
        if c not in out.columns:
            if c in ("course_id", "course_name", "description", "created_at"):
                out[c] = ""
            else:
                out[c] = 0
    out = out[COURSE_COLUMNS].copy()
    out["sessions"] = pd.to_numeric(out["sessions"], errors="coerce").fillna(0).astype(int)
    out["amount"] = pd.to_numeric(out["amount"], errors="coerce").fillna(0).astype(int)
    out["sort_order"] = pd.to_numeric(out["sort_order"], errors="coerce").fillna(9999).astype(int)
    out["course_id"] = out["course_id"].astype(str).str.strip()
    out["course_name"] = out["course_name"].astype(str).str.strip()
    out["description"] = out["description"].astype(str)
    out["created_at"] = out["created_at"].astype(str).str.strip()
    return out


def _normalize_curriculum(df):
    """시트를 읽기만 함. 레거시 형식 자동 변환·시트 덮어쓰기 없음."""
    if df is None or df.empty:
        return pd.DataFrame(columns=COURSE_COLUMNS)
    if "course_id" in df.columns and "course_name" in df.columns:
        return _coerce_course_df(df)
    return pd.DataFrame(columns=COURSE_COLUMNS)


def _safe_read_curriculum(conn, ttl=60):
    try:
        df = _safe_read(conn, worksheet=WORKSHEET_NAME, ttl=ttl)
    except Exception as e:
        msg = str(e)
        if "429" in msg or "RESOURCE_EXHAUSTED" in msg or "RATE_LIMIT_EXCEEDED" in msg:
            st.session_state["curriculum_error"] = "커리큘럼 시트 조회 한도를 초과했습니다. 잠시 후 다시 시도해주세요."
            return pd.DataFrame(columns=COURSE_COLUMNS)
        df = pd.DataFrame(columns=COURSE_COLUMNS)
        _safe_update(conn, worksheet=WORKSHEET_NAME, data=df)
        df = _safe_read(conn, worksheet=WORKSHEET_NAME, ttl=ttl)

    if df is None:
        return pd.DataFrame(columns=COURSE_COLUMNS)
    return df


def _load_curriculum(base_ttl=60):
    """base_ttl=0 이면 항상 시트 재조회. 커리큘럼 저장 직후 플래그가 있으면 1회 ttl=0."""
    conn = get_conn()
    stale_clear = st.session_state.pop(_CURRICULUM_NEXT_READ_FRESH, False)
    ttl = 0 if stale_clear or base_ttl == 0 else base_ttl
    raw = _safe_read_curriculum(conn, ttl=ttl)
    df = _normalize_curriculum(raw)
    if raw is not None and not raw.empty and df.empty:
        st.session_state["curriculum_schema_hint"] = (
            "시트에 행은 있지만 **course_id**, **course_name** 열이 없어 목록에 표시하지 않았습니다. "
            "Google 시트 첫 행 헤더를 수동으로 맞춰 주세요. (레거시 자동 변환·기본 코스 자동 생성 없음)"
        )
    else:
        st.session_state.pop("curriculum_schema_hint", None)
    if not df.empty:
        df = df.sort_values(by=["sort_order", "created_at", "course_id"], ascending=[True, True, True])
    return conn, df


def run_curriculum_ui():
    _t0 = time.perf_counter()
    st.header("📚 커리큘럼")

    conn, df = _load_curriculum(60)
    err = st.session_state.pop("curriculum_error", None)
    if err:
        st.error(str(err))
    hint = st.session_state.pop("curriculum_schema_hint", None)
    if hint:
        st.warning(str(hint))

    section = st.segmented_control(
        "커리큘럼 메뉴",
        ["🎯 코스 관리", "✏️ 일괄 수정"],
        default="🎯 코스 관리",
        key="curriculum_main_section_v2",
        label_visibility="collapsed",
    )

    if section == "🎯 코스 관리":
        _render_course_manage(conn, df)
    else:
        _render_course_bulk_edit(conn, df)
    perf_log("curriculum.run_curriculum_ui", (time.perf_counter() - _t0) * 1000.0)


def _render_course_manage(conn, df):
    st.caption(
        "시트 컬럼: **course_id**, **course_name**, **sessions**(횟수), **amount**(원), "
        "**description**, **created_at**, **sort_order** — 원생 등록의 수강 코스 목록·요금·추천 횟수에 반영됩니다."
    )
    view = df.copy() if not df.empty else pd.DataFrame(columns=COURSE_COLUMNS)
    st.markdown("**현재 코스 목록**")
    if view.empty:
        st.info("등록된 코스가 없습니다. 아래에서 추가하거나 **일괄 수정**에서 넣을 수 있습니다.")
    else:
        st.dataframe(
            view,
            use_container_width=True,
            hide_index=True,
            column_order=COURSE_COLUMNS,
        )

    st.markdown("**코스 추가**")
    with st.form("course_add_form_v2", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            add_name = st.text_input("course_name", placeholder="예: 주 1회 정규반")
            add_sessions = st.number_input("sessions (횟수)", min_value=0, value=4, step=1)
            add_amount = st.number_input("amount (원)", min_value=0, value=0, step=1000)
        with c2:
            add_desc = st.text_input("description", placeholder="선택, 예: 2.5h / 2개월 내 소진")
            add_order = st.number_input("sort_order", min_value=0, value=50, step=1)
        if st.form_submit_button("코스 추가", use_container_width=True):
            if not str(add_name).strip():
                st.error("course_name은 필수입니다.")
            else:
                now_txt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                new_row = pd.DataFrame([{
                    "course_id": f"course_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
                    "course_name": str(add_name).strip(),
                    "sessions": int(add_sessions),
                    "amount": int(add_amount),
                    "description": str(add_desc).strip(),
                    "created_at": now_txt,
                    "sort_order": int(add_order),
                }])
                base = df.copy() if not df.empty else pd.DataFrame(columns=COURSE_COLUMNS)
                updated = pd.concat([base, new_row], ignore_index=True)
                updated = _coerce_course_df(updated)
                _safe_update(conn, worksheet=WORKSHEET_NAME, data=updated)
                _mark_curriculum_dirty()
                st.success("코스가 추가되었습니다.")
                st.rerun()

    st.markdown("**코스 삭제**")
    if view.empty:
        st.caption("삭제할 코스가 없습니다.")
        return
    del_options = {
        f"{row['course_name']} (sort {row['sort_order']}, id {row['course_id']})": str(row["course_id"])
        for _, row in view.iterrows()
    }
    pick = st.selectbox("삭제할 코스", list(del_options.keys()), key="course_delete_pick_v2")
    if st.button("선택 코스 삭제", use_container_width=True, key="course_delete_btn_v2"):
        rm_id = del_options[pick]
        updated = view[view["course_id"].astype(str) != rm_id].copy()
        updated = _coerce_course_df(updated)
        _safe_update(conn, worksheet=WORKSHEET_NAME, data=updated)
        _mark_curriculum_dirty()
        st.success("코스가 삭제되었습니다.")
        st.rerun()


def _render_course_bulk_edit(conn, df):
    st.caption(
        "표에서 직접 수정합니다. 행을 추가·삭제한 뒤 **일괄 저장**을 누르면 시트에 반영됩니다. "
        "**course_id**가 비어 있으면 저장 시 자동 발급됩니다. **course_name**은 원생 화면의 코스 이름으로 쓰입니다."
    )
    edit_df = df.copy() if not df.empty else pd.DataFrame(columns=COURSE_COLUMNS)
    edit_df = _coerce_course_df(edit_df)

    edited = st.data_editor(
        edit_df,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        column_order=COURSE_COLUMNS,
        key="curriculum_bulk_editor_v2",
        column_config={
            "course_id": st.column_config.TextColumn("course_id", help="고유 ID (비우면 자동)"),
            "course_name": st.column_config.TextColumn("course_name", help="수강 코스 표시명"),
            "sessions": st.column_config.NumberColumn("sessions", min_value=0, step=1, help="권장 결제 횟수"),
            "amount": st.column_config.NumberColumn("amount", min_value=0, step=1000, format="%d", help="원 단위"),
            "description": st.column_config.TextColumn("description"),
            "created_at": st.column_config.TextColumn("created_at", help="자동 또는 직접 입력"),
            "sort_order": st.column_config.NumberColumn("sort_order", step=1, help="목록 정렬 (작을수록 위)"),
        },
    )

    if st.button("일괄 저장", type="primary", use_container_width=True, key="curriculum_bulk_save_v2"):
        if edited is None or edited.empty:
            st.error("저장할 데이터가 없습니다.")
            return
        for col in COURSE_COLUMNS:
            if col not in edited.columns:
                edited[col] = "" if col in ("course_id", "course_name", "description", "created_at") else 0
        edited = edited[COURSE_COLUMNS].copy()
        edited["course_id"] = edited["course_id"].astype(str).str.strip()
        edited["course_name"] = edited["course_name"].astype(str).str.strip()
        edited["description"] = edited["description"].astype(str)
        edited["created_at"] = edited["created_at"].astype(str).str.strip()
        edited["sessions"] = pd.to_numeric(edited["sessions"], errors="coerce").fillna(0).astype(int)
        edited["amount"] = pd.to_numeric(edited["amount"], errors="coerce").fillna(0).astype(int)
        edited["sort_order"] = pd.to_numeric(edited["sort_order"], errors="coerce").fillna(0).astype(int)

        if (edited["course_name"] == "").any():
            st.error("course_name은 비울 수 없습니다.")
            return

        dup_mask = edited["course_id"] != ""
        dup_ids = edited.loc[dup_mask, "course_id"]
        if dup_ids.duplicated().any():
            st.error("course_id가 중복되었습니다. 각 코스마다 다른 ID를 사용하세요.")
            return

        now_txt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        empty_id_mask = edited["course_id"] == ""
        if empty_id_mask.any():
            for i in edited[empty_id_mask].index:
                edited.at[i, "course_id"] = f"course_{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{i}"
                if not edited.at[i, "created_at"]:
                    edited.at[i, "created_at"] = now_txt

        edited = _coerce_course_df(edited)
        _safe_update(conn, worksheet=WORKSHEET_NAME, data=edited)
        _mark_curriculum_dirty()
        st.success("일괄 수정 내용이 저장되었습니다.")
        st.rerun()


def _fallback_course_options():
    return ["정규반(주1회)", "정규반(주2회)", "원데이 클래스", "기타"]


def _course_options_from_df(df):
    if df is None or df.empty:
        return _fallback_course_options()
    work = _coerce_course_df(df)
    work = work.sort_values(by=["sort_order", "created_at", "course_id"], ascending=[True, True, True])
    options, seen = [], set()
    for x in work["course_name"].tolist():
        name = str(x).strip()
        if name and name not in seen:
            seen.add(name)
            options.append(name)
    if "기타" not in options:
        options.append("기타")
    return options if options else ["기타"]


def _price_map_from_df(df):
    if df is None or df.empty:
        return {}
    out = {}
    for _, row in _coerce_course_df(df).iterrows():
        name = str(row.get("course_name", "")).strip()
        if not name:
            continue
        out[name] = int(row.get("amount", 0) or 0)
    return out


def _sessions_map_from_df(df):
    if df is None or df.empty:
        return {}
    out = {}
    for _, row in _coerce_course_df(df).iterrows():
        name = str(row.get("course_name", "")).strip()
        if not name:
            continue
        out[name] = int(row.get("sessions", 0) or 0)
    return out


def get_registration_curriculum_bundle():
    """신규 등록 화면용: 커리큘럼 시트를 한 번만 읽어 목록·금액·횟수 맵을 맞춤."""
    _, df = _load_curriculum(60)
    return {
        "options": _course_options_from_df(df),
        "price_map": _price_map_from_df(df),
        "sessions_map": _sessions_map_from_df(df),
    }


def get_course_options(force_refresh=False):
    """원생 등록에서 사용할 코스 목록 (course_name)."""
    _, df = _load_curriculum(0 if force_refresh else 60)
    return _course_options_from_df(df)


def get_course_price_map(force_refresh=False):
    """course_name -> amount(원)."""
    _, df = _load_curriculum(0 if force_refresh else 60)
    return _price_map_from_df(df)


def get_course_sessions_map(force_refresh=False):
    """course_name -> 권장 횟수(sessions)."""
    _, df = _load_curriculum(0 if force_refresh else 60)
    return _sessions_map_from_df(df)
