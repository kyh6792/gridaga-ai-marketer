"""회원별 진도 기록 (전체 회원 대상). 저장소: progress_records 시트 / Supabase 테이블."""

from __future__ import annotations

import uuid
from datetime import datetime

import pandas as pd
import streamlit as st

from core.database import get_conn
from core.students import _normalize_student_id_text

PROGRESS_WS = "progress_records"
COLS = ["record_id", "student_id", "student_name", "record_date", "body", "updated_at"]
_PROGRESS_FLASH_KEY = "_progress_records_action_notice"


def _progress_set_flash(kind: str, message: str):
    st.session_state[_PROGRESS_FLASH_KEY] = (kind, message)


def _progress_consume_flash():
    raw = st.session_state.pop(_PROGRESS_FLASH_KEY, None)
    if not isinstance(raw, tuple) or len(raw) != 2:
        return
    kind, msg = raw[0], str(raw[1])
    if kind == "success":
        st.success(msg)
    elif kind == "error":
        st.error(msg)
    else:
        st.info(msg)


def _read_progress_df():
    conn = get_conn()
    try:
        df = conn.read(worksheet=PROGRESS_WS, ttl=0)
    except Exception:
        df = None
    if df is None:
        df = pd.DataFrame(columns=COLS)
    if df.empty:
        try:
            conn.update(worksheet=PROGRESS_WS, data=pd.DataFrame(columns=COLS))
        except Exception:
            pass
        return pd.DataFrame(columns=COLS)
    for c in COLS:
        if c not in df.columns:
            df[c] = ""
    return df[COLS].copy()


def _save_progress_df(df: pd.DataFrame):
    conn = get_conn()
    out = df.copy()
    for c in COLS:
        if c not in out.columns:
            out[c] = ""
    conn.update(worksheet=PROGRESS_WS, data=out[COLS])


def _all_student_choices():
    """전체 명부(상태 무관). 라벨: '이름 (ID)'."""
    conn = get_conn()
    try:
        df = conn.read(worksheet="students", ttl=60)
    except Exception:
        return []
    if df is None or df.empty or "ID" not in df.columns:
        return []
    df = df.copy()
    df["ID"] = df["ID"].map(_normalize_student_id_text)
    df = df[df["ID"].astype(str).str.strip() != ""]
    choices = []
    for _, row in df.iterrows():
        sid = str(row["ID"]).strip()
        name = str(row.get("이름", "")).strip() if pd.notna(row.get("이름")) else ""
        label = f"{name} ({sid})" if name else f"({sid})"
        choices.append((label, sid))
    choices.sort(key=lambda x: x[0])
    return choices


def run_progress_records_ui():
    st.caption("명부에 등록된 **전체** 회원 중 선택해 진도를 기록합니다.")
    _progress_consume_flash()

    choices = _all_student_choices()
    if not choices:
        st.info("등록된 회원이 없습니다. 먼저 신규 등록을 해 주세요.")
        return

    labels = [c[0] for c in choices]
    id_by_label = {c[0]: c[1] for c in choices}

    sel = st.selectbox(
        "회원 선택",
        options=labels,
        key="progress_record_student_select",
        label_visibility="visible",
    )
    student_id = id_by_label.get(sel, "")
    if not student_id:
        return

    prev_sid = st.session_state.get("progress_record_prev_sid")
    if prev_sid is not None and str(prev_sid) != str(student_id):
        st.session_state.pop("progress_edit_record_id", None)
    st.session_state["progress_record_prev_sid"] = str(student_id)

    name_for = sel.rsplit(" (", 1)[0].strip() if " (" in sel else sel

    df = _read_progress_df()
    mask = df["student_id"].astype(str).str.strip() == str(student_id).strip()
    sub = df.loc[mask].copy()

    if not sub.empty and "record_date" in sub.columns:
        sub["_d"] = pd.to_datetime(sub["record_date"], errors="coerce")
        sub = sub.sort_values(by=["_d", "record_id"], ascending=[False, False])
        sub = sub.drop(columns=["_d"], errors="ignore")

    eid = st.session_state.get("progress_edit_record_id")

    st.markdown("##### 📋 진도 기록")
    if eid:
        row_match = df.index[df["record_id"].astype(str) == str(eid)].tolist()
        if row_match:
            idx = row_match[0]
            cur_body = str(df.at[idx, "body"] or "")
            st.info("아래에서 내용을 수정한 뒤 저장하거나 취소하세요.")
            with st.form("progress_edit_form"):
                edited = st.text_area("진도 내용", value=cur_body, height=160)
                c1, c2 = st.columns(2)
                with c1:
                    save = st.form_submit_button("저장", use_container_width=True)
                with c2:
                    cancel = st.form_submit_button("취소", use_container_width=True)
            if cancel:
                st.session_state.pop("progress_edit_record_id", None)
                st.rerun()
            if save:
                df.at[idx, "body"] = edited.strip()
                df.at[idx, "updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                _save_progress_df(df)
                st.session_state.pop("progress_edit_record_id", None)
                _progress_set_flash("success", "수정했습니다.")
                st.rerun()
        else:
            st.session_state.pop("progress_edit_record_id", None)

    loop_sub = sub
    if eid:
        loop_sub = sub[sub["record_id"].astype(str) != str(eid)].copy()

    if loop_sub.empty:
        st.caption("아직 기록이 없습니다. 아래에서 추가해 보세요.")
    else:
        for _, row in loop_sub.iterrows():
            rid = str(row.get("record_id", ""))
            d = str(row.get("record_date", "") or "")
            body = str(row.get("body", "") or "")
            with st.container(border=True):
                c1, c2 = st.columns([4, 1])
                with c1:
                    st.markdown(f"**{d}**")
                    st.markdown(body.replace("\n", "\n\n") if body else "_(내용 없음)_")
                with c2:
                    if st.button("수정하기", key=f"pr_edit_btn_{rid}", use_container_width=True):
                        st.session_state["progress_edit_record_id"] = rid
                        st.rerun()

    st.markdown("##### ➕ 진도 기록 추가")
    with st.form("progress_add_form", clear_on_submit=True):
        new_body = st.text_area(
            "진도 내용",
            placeholder="오늘 진도·과제·특이사항 등을 적어 주세요.",
            height=180,
            key="progress_add_body",
        )
        add_submitted = st.form_submit_button("진도기록 추가", use_container_width=True)
    if add_submitted:
        text = (new_body or "").strip()
        if not text:
            st.warning("내용을 입력한 뒤 추가해 주세요.")
        else:
            now = datetime.now()
            rid = str(uuid.uuid4())
            new_row = pd.DataFrame(
                [
                    {
                        "record_id": rid,
                        "student_id": str(student_id),
                        "student_name": name_for,
                        "record_date": now.strftime("%Y-%m-%d"),
                        "body": text,
                        "updated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                    }
                ]
            )
            merged = pd.concat([df, new_row], ignore_index=True)
            _save_progress_df(merged)
            _progress_set_flash("success", "진도 기록을 추가했습니다.")
            st.rerun()
