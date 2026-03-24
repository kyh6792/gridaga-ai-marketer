import streamlit as st
import pandas as pd
from datetime import datetime
import re
import time
from core.database import get_conn


WORKSHEET_NAME = "curriculum"


DEFAULT_CURRICULUM_ROWS = [
    {
        "id": "course_001",
        "category": "코스",
        "title": "정규반 | 코스 A",
        "content": "4회권 (2.5h) / 180,000원 (2개월 내 소진)",
        "sort_order": 0,
        "created_at": "",
    },
    {
        "id": "course_002",
        "category": "코스",
        "title": "정규반 | 코스 B",
        "content": "8회권 (2.5h) / 340,000원 (3개월 내 소진)",
        "sort_order": 0,
        "created_at": "",
    },
    {
        "id": "course_003",
        "category": "코스",
        "title": "원데이 클래스 | 체험 코스",
        "content": "원데이 체험 코스",
        "sort_order": 0,
        "created_at": "",
    },
    {
        "id": "edu_001",
        "category": "교육 내용",
        "title": "다양한 재료와 기법",
        "content": "소묘, 드로잉, 수채화, 아크릴, 유화, 오일파스텔, 판화 등 다양한 재료와 기법으로 본인의 그림을 찾아갈 수 있도록 지도합니다.",
        "sort_order": 1,
        "created_at": "",
    },
    {
        "id": "edu_002",
        "category": "교육 내용",
        "title": "개인 맞춤 진도",
        "content": "상담을 통해 기초부터 심화 과정까지 개인의 속도와 취향에 맞춰 진도를 조율합니다.",
        "sort_order": 2,
        "created_at": "",
    },
    {
        "id": "edu_003",
        "category": "교육 내용",
        "title": "소수정예 레슨",
        "content": "타임당 최대 4명 이하의 소수정예 레슨으로 1:1 맞춤형 커리큘럼으로 진행합니다.",
        "sort_order": 3,
        "created_at": "",
    },
    {
        "id": "tt_001",
        "category": "수업 시간표",
        "title": "정규 클래스 안내",
        "content": "여유로운 작업 시간을 위해 정규 클래스는 2시간 30분 동안 진행됩니다.",
        "sort_order": 10,
        "created_at": "",
    },
    {
        "id": "tt_002",
        "category": "수업 시간표",
        "title": "평일 (월~금)",
        "content": "[오전반] 10:30 ~ 13:00\n[오후반] 14:30 ~ 17:00\n[저녁반] 18:30 ~ 21:00",
        "sort_order": 11,
        "created_at": "",
    },
    {
        "id": "tt_003",
        "category": "수업 시간표",
        "title": "토요일",
        "content": "[오전반] 09:30 ~ 12:00\n[오후반] 13:00 ~ 15:30",
        "sort_order": 12,
        "created_at": "",
    },
    {
        "id": "tt_004",
        "category": "수업 시간표",
        "title": "일요일",
        "content": "레슨 없는 '자율 작업'",
        "sort_order": 13,
        "created_at": "",
    },
    {
        "id": "fee_001",
        "category": "수업료",
        "title": "4회권 (2.5h)",
        "content": "180,000원 (2개월 내 소진)",
        "sort_order": 20,
        "created_at": "",
    },
    {
        "id": "fee_002",
        "category": "수업료",
        "title": "8회권 (2.5h)",
        "content": "340,000원 (3개월 내 소진)",
        "sort_order": 21,
        "created_at": "",
    },
]


def _base_columns():
    return ["id", "category", "title", "content", "sort_order", "created_at"]


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


def _safe_read_curriculum(conn, ttl=60):
    try:
        df = _safe_read(conn, worksheet=WORKSHEET_NAME, ttl=ttl)
    except Exception as e:
        msg = str(e)
        # 쿼터 초과 시에는 생성/업데이트 시도하지 않고 빈 데이터로 안전 fallback
        if "429" in msg or "RESOURCE_EXHAUSTED" in msg or "RATE_LIMIT_EXCEEDED" in msg:
            st.session_state["curriculum_error"] = "커리큘럼 시트 조회 한도를 초과했습니다. 잠시 후 다시 시도해주세요."
            return pd.DataFrame(columns=_base_columns())
        df = pd.DataFrame(columns=_base_columns())
        _safe_update(conn, worksheet=WORKSHEET_NAME, data=df)
        df = _safe_read(conn, worksheet=WORKSHEET_NAME, ttl=ttl)

    if df is None or df.empty:
        return pd.DataFrame(columns=_base_columns())

    for col in _base_columns():
        if col not in df.columns:
            df[col] = ""
    return df[_base_columns()].copy()


def _seed_default_if_empty(conn, df):
    if df.empty:
        seeded = pd.DataFrame(DEFAULT_CURRICULUM_ROWS)
        seeded["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _safe_update(conn, worksheet=WORKSHEET_NAME, data=seeded)
        return seeded
    return df


def _ensure_default_courses(conn, df):
    """시트가 비어있지 않아도 기본 코스가 없으면 자동 추가"""
    if df is None:
        df = pd.DataFrame(columns=_base_columns())
    if df.empty:
        return df

    default_courses = [row for row in DEFAULT_CURRICULUM_ROWS if row.get("category") == "코스"]
    existing_titles = set(df[df["category"] == "코스"]["title"].astype(str).str.strip().tolist()) if "category" in df.columns else set()

    missing_rows = []
    now_txt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for row in default_courses:
        title = str(row.get("title", "")).strip()
        if title and title not in existing_titles:
            new_row = row.copy()
            new_row["id"] = f"{row.get('id', 'course')}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
            new_row["created_at"] = now_txt
            missing_rows.append(new_row)

    if not missing_rows:
        return df

    add_df = pd.DataFrame(missing_rows)
    updated = pd.concat([df, add_df], ignore_index=True)
    _safe_update(conn, worksheet=WORKSHEET_NAME, data=updated)
    return updated


def _load_curriculum(ttl=60):
    conn = get_conn()
    df = _safe_read_curriculum(conn, ttl=ttl)
    df = _seed_default_if_empty(conn, df)
    df = _ensure_default_courses(conn, df)
    if not df.empty:
        df["sort_order"] = pd.to_numeric(df["sort_order"], errors="coerce").fillna(9999).astype(int)
        df = df.sort_values(by=["category", "sort_order", "created_at"], ascending=[True, True, True])
    return conn, df


def run_curriculum_ui():
    st.header("📚 커리큘럼")
    conn, df = _load_curriculum()

    tab1, tab2, tab3, tab4 = st.tabs(
        ["🎯 코스 관리", "➕ 등록", "🗑 삭제", "✏️ 일괄 수정"]
    )

    with tab1:
        _render_course_manage(conn, df)

    with tab2:
        _render_curriculum_create(conn, df)

    with tab3:
        _render_curriculum_delete(conn, df)

    with tab4:
        _render_curriculum_bulk_edit(conn, df)


def _render_curriculum_view(df):
    if df.empty:
        st.info("등록된 커리큘럼이 없습니다.")
        return

    view_df = df.copy()
    view_df["sort_order"] = pd.to_numeric(view_df["sort_order"], errors="coerce").fillna(9999).astype(int)
    view_df = view_df.sort_values(by=["category", "sort_order", "created_at"], ascending=[True, True, True])
    st.dataframe(
        view_df,
        use_container_width=True,
        hide_index=True,
        column_order=["category", "title", "content", "sort_order", "created_at", "id"],
    )


def _render_course_manage(conn, df):
    st.caption("원생 등록 시 선택되는 코스 항목입니다.")
    course_df = df[df["category"] == "코스"].copy() if not df.empty else pd.DataFrame(columns=_base_columns())
    if not course_df.empty:
        course_df["sort_order"] = pd.to_numeric(course_df["sort_order"], errors="coerce").fillna(9999).astype(int)
        course_df = course_df.sort_values(by=["sort_order", "created_at"], ascending=[True, True])

    def _split_course_title(title):
        t = str(title).strip()
        if "|" in t:
            group, name = t.split("|", 1)
            return group.strip(), name.strip()
        return "기타", t

    st.markdown("**현재 코스 목록**")
    if course_df.empty:
        st.info("등록된 코스가 없습니다.")
    else:
        view_df = course_df.copy()
        groups, names = [], []
        for _, row in view_df.iterrows():
            g, n = _split_course_title(row.get("title", ""))
            groups.append(g)
            names.append(n)
        view_df["코스 분류"] = groups
        view_df["코스명"] = names
        view_df["설명"] = view_df["content"]
        st.dataframe(
            view_df[["코스 분류", "코스명", "설명", "sort_order", "id"]],
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("**코스 추가**")
    with st.form("course_add_form", clear_on_submit=True):
        course_group = st.selectbox("코스 분류", ["정규반", "원데이 클래스", "기타"])
        course_name = st.text_input("코스명", placeholder="예: 코스 A")
        course_desc = st.text_input("설명", placeholder="예: 기초 드로잉 중심")
        course_order = st.number_input("정렬 순서", min_value=0, value=50, step=1)
        add_submitted = st.form_submit_button("코스 추가", use_container_width=True)
        if add_submitted:
            if not course_name.strip():
                st.error("코스명은 필수입니다.")
                return
            composed_title = f"{course_group} | {course_name.strip()}"
            new_row = pd.DataFrame([{
                "id": f"course_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
                "category": "코스",
                "title": composed_title,
                "content": course_desc.strip(),
                "sort_order": int(course_order),
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }])
            updated = pd.concat([df, new_row], ignore_index=True) if not df.empty else new_row
            _safe_update(conn, worksheet=WORKSHEET_NAME, data=updated)
            st.success("코스가 추가되었습니다.")
            st.rerun()

    st.markdown("**코스 삭제**")
    if course_df.empty:
        st.caption("삭제할 코스가 없습니다.")
        return
    del_options = {
        f"{row['title']} (순서 {row['sort_order']})": row["id"]
        for _, row in course_df.iterrows()
    }
    selected = st.selectbox("삭제할 코스 선택", list(del_options.keys()))
    if st.button("선택 코스 삭제", use_container_width=True):
        target_id = del_options[selected]
        updated = df[df["id"].astype(str) != str(target_id)].copy()
        _safe_update(conn, worksheet=WORKSHEET_NAME, data=updated)
        st.success("코스가 삭제되었습니다.")
        st.rerun()


def _render_curriculum_create(conn, df):
    with st.form("curriculum_create_form", clear_on_submit=True):
        category = st.selectbox("구분", ["코스", "교육 내용", "수업 시간표", "수업료"])
        title = st.text_input("제목", placeholder="예: 평일 (월~금)")
        content = st.text_area("내용", placeholder="예: [오전반] 10:30 ~ 13:00")
        sort_order = st.number_input("정렬 순서", min_value=1, value=100, step=1)
        submitted = st.form_submit_button("등록하기", use_container_width=True)

        if submitted:
            if not content.strip():
                st.error("내용은 필수입니다.")
                return
            new_row = pd.DataFrame([{
                "id": f"cur_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
                "category": category,
                "title": title.strip(),
                "content": content.strip(),
                "sort_order": int(sort_order),
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }])
            updated = pd.concat([df, new_row], ignore_index=True) if not df.empty else new_row
            _safe_update(conn, worksheet=WORKSHEET_NAME, data=updated)
            st.success("커리큘럼 항목이 등록되었습니다.")
            st.rerun()


def _render_curriculum_delete(conn, df):
    if df.empty:
        st.info("삭제할 항목이 없습니다.")
        return

    for _, row in df.iterrows():
        row_id = str(row.get("id", ""))
        title = str(row.get("title", "")).strip()
        content = str(row.get("content", "")).strip()
        with st.container(border=True):
            st.caption(f"{row.get('category', '')} | 순서 {row.get('sort_order', '')}")
            if title:
                st.markdown(f"**{title}**")
            st.write(content if content else "-")
            if st.button("삭제", key=f"delete_cur_{row_id}", use_container_width=True):
                updated = df[df["id"].astype(str) != row_id].copy()
                _safe_update(conn, worksheet=WORKSHEET_NAME, data=updated)
                st.success("삭제되었습니다.")
                st.rerun()


def _render_curriculum_bulk_edit(conn, df):
    st.caption("표에서 직접 수정한 뒤 저장 버튼을 누르면 시트에 반영됩니다.")
    if df.empty:
        st.info("수정할 데이터가 없습니다.")
        return

    edit_df = df.copy()
    edit_df["sort_order"] = pd.to_numeric(edit_df["sort_order"], errors="coerce").fillna(0).astype(int)

    edited = st.data_editor(
        edit_df,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        column_order=["id", "category", "title", "content", "sort_order", "created_at"],
        key="curriculum_bulk_editor",
    )

    if st.button("일괄 저장", type="primary", use_container_width=True, key="curriculum_bulk_save"):
        if edited is None or edited.empty:
            st.error("저장할 데이터가 없습니다.")
            return
        required = _base_columns()
        for col in required:
            if col not in edited.columns:
                edited[col] = ""
        edited = edited[required].copy()
        edited["id"] = edited["id"].astype(str).str.strip()
        edited["category"] = edited["category"].astype(str).str.strip()
        edited["title"] = edited["title"].astype(str).str.strip()
        edited["content"] = edited["content"].astype(str).str.strip()
        edited["sort_order"] = pd.to_numeric(edited["sort_order"], errors="coerce").fillna(0).astype(int)
        edited["created_at"] = edited["created_at"].astype(str).str.strip()

        # 신규 행에서 id가 비어 있으면 자동 발급
        empty_id_mask = edited["id"] == ""
        if empty_id_mask.any():
            for i in edited[empty_id_mask].index:
                edited.at[i, "id"] = f"cur_{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{i}"
                if not edited.at[i, "created_at"]:
                    edited.at[i, "created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        _safe_update(conn, worksheet=WORKSHEET_NAME, data=edited)
        st.success("일괄 수정 내용이 저장되었습니다.")
        st.rerun()


def get_course_options(force_refresh=False):
    """원생 등록에서 사용할 코스 목록을 curriculum 시트에서 가져옵니다."""
    _, df = _load_curriculum(ttl=0 if force_refresh else 60)
    if df is None or df.empty:
        return ["정규반(주1회)", "정규반(주2회)", "원데이 클래스", "기타"]

    course_df = df[df["category"] == "코스"].copy()
    if course_df.empty:
        return ["정규반(주1회)", "정규반(주2회)", "원데이 클래스", "기타"]

    course_df["sort_order"] = pd.to_numeric(course_df["sort_order"], errors="coerce").fillna(9999).astype(int)
    course_df = course_df.sort_values(by=["sort_order", "created_at"], ascending=[True, True])
    options = [str(x).strip() for x in course_df["title"].tolist() if str(x).strip()]
    if "기타" not in options:
        options.append("기타")
    return options if options else ["기타"]


def get_course_price_map(force_refresh=False):
    """코스별 금액 맵 반환 (content에서 숫자 금액 파싱)"""
    _, df = _load_curriculum(ttl=0 if force_refresh else 60)
    if df is None or df.empty:
        return {}
    cdf = df[df["category"] == "코스"].copy()
    if cdf.empty:
        return {}
    out = {}
    for _, row in cdf.iterrows():
        title = str(row.get("title", "")).strip()
        content = str(row.get("content", "")).strip()
        if not title:
            continue
        # content 내 첫 금액 추출 (예: 180,000원)
        m = re.search(r"([0-9][0-9,]*)\s*원", content)
        if m:
            out[title] = int(m.group(1).replace(",", ""))
        else:
            out[title] = 0
    return out
