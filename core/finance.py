import re
import streamlit as st
import pandas as pd
from datetime import datetime
from core.database import get_conn
from core.curriculum import get_course_price_map


WORKSHEET_NAME = "finance_transactions"
BASE_COLUMNS = [
    "tx_id",
    "date",
    "year_month",
    "year_week",
    "student_id",
    "student_name",
    "course",
    "event_type",
    "amount",
    "note",
]


def _read_or_init_transactions():
    conn = get_conn()
    try:
        df = conn.read(worksheet=WORKSHEET_NAME, ttl=0)
    except Exception:
        df = pd.DataFrame(columns=BASE_COLUMNS)
        conn.update(worksheet=WORKSHEET_NAME, data=df)
        df = conn.read(worksheet=WORKSHEET_NAME, ttl=0)

    if df is None or df.empty:
        df = pd.DataFrame(columns=BASE_COLUMNS)
    for c in BASE_COLUMNS:
        if c not in df.columns:
            df[c] = ""
    return conn, df[BASE_COLUMNS].copy()


def _to_int_amount(v):
    if isinstance(v, (int, float)):
        return int(v)
    txt = str(v)
    nums = re.sub(r"[^0-9]", "", txt)
    return int(nums) if nums else 0


def _resolve_course_amount(course_name):
    price_map = get_course_price_map()
    if course_name in price_map:
        return _to_int_amount(price_map[course_name])
    # 정확 일치 실패 시 부분 매칭
    for k, v in price_map.items():
        if str(k) in str(course_name) or str(course_name) in str(k):
            return _to_int_amount(v)
    return 0


def record_registration_payment(student_id, student_name, course, event_type="등록", amount=None, note=""):
    """등록/재등록 시 재무 거래를 누적 저장"""
    conn, df = _read_or_init_transactions()
    now = datetime.now()
    tx_amount = _resolve_course_amount(course) if amount is None else _to_int_amount(amount)
    new_row = pd.DataFrame([{
        "tx_id": f"tx_{now.strftime('%Y%m%d%H%M%S%f')}",
        "date": now.strftime("%Y-%m-%d %H:%M:%S"),
        "year_month": now.strftime("%Y-%m"),
        "year_week": f"{now.strftime('%Y')}-W{now.isocalendar().week:02d}",
        "student_id": str(student_id),
        "student_name": str(student_name),
        "course": str(course),
        "event_type": str(event_type),
        "amount": int(tx_amount),
        "note": str(note),
    }])
    updated = pd.concat([df, new_row], ignore_index=True) if not df.empty else new_row
    conn.update(worksheet=WORKSHEET_NAME, data=updated)


def run_finance_ui():
    st.header("💰 재무")
    try:
        import core.ui as _ui

        _style = getattr(_ui, "apply_owner_dashboard_style", None)
        if callable(_style):
            _style()
    except Exception:
        pass
    if "finance_detail_panel" not in st.session_state:
        st.session_state["finance_detail_panel"] = "annual"

    conn, df = _read_or_init_transactions()

    if df.empty:
        st.info("아직 등록된 재무 거래가 없습니다. 원생 등록/재등록 시 자동 누적됩니다.")
        return

    view = df.copy()
    view["amount"] = pd.to_numeric(view["amount"], errors="coerce").fillna(0).astype(int)
    view["year_month"] = view["year_month"].astype(str).str.strip()
    view["event_type"] = view["event_type"].astype(str).str.strip()

    year = datetime.now().year
    ym_march = f"{year}-03"
    year_prefix = f"{year}-"
    year_view = view[view["year_month"].str.startswith(year_prefix, na=False)].copy()
    march_view = view[view["year_month"] == ym_march].copy()

    annual_total = int(year_view["amount"].sum()) if not year_view.empty else 0
    march_total = int(march_view["amount"].sum()) if not march_view.empty else 0
    year_reg_count = int((year_view["event_type"] == "등록").sum()) if not year_view.empty else 0
    year_rereg_count = int((year_view["event_type"] == "재등록").sum()) if not year_view.empty else 0

    fin_keys = ["annual", "march", "reg", "rereg"]
    fin_labels = ["📈 연 총매출", "📅 3월 매출", "📝 등록 건수", "🔁 재등록 건수"]
    cur = st.session_state.get("finance_detail_panel", "annual")
    if cur not in fin_keys:
        cur = "annual"
    default_i = fin_keys.index(cur)

    st.caption(
        f"올해 `{year}` · 3월 `{ym_march}` · "
        f"연매출 **{annual_total:,}원** · 3월 **{march_total:,}원** · "
        f"등록 **{year_reg_count}건** · 재등록 **{year_rereg_count}건**"
    )
    picked = st.radio(
        "항목",
        fin_labels,
        index=default_i,
        horizontal=True,
        label_visibility="collapsed",
    )
    detail = fin_keys[fin_labels.index(picked)]
    st.session_state["finance_detail_panel"] = detail

    tx_cols = ["date", "event_type", "student_name", "student_id", "course", "amount", "note", "tx_id"]

    if detail == "annual":
        st.markdown("---")
        st.subheader(f"📈 {year}년 연 총매출")
        st.metric("합계", f"{annual_total:,}원")
        if year_view.empty:
            st.info("올해 거래 내역이 없습니다.")
        else:
            by_month = (
                year_view.groupby("year_month", as_index=False)["amount"]
                .sum()
                .sort_values("year_month")
            )
            st.caption("월별 매출")
            st.dataframe(by_month, use_container_width=True, hide_index=True)
            st.caption("코스별 누적 (올해)")
            course_sum = (
                year_view.groupby("course", as_index=False)["amount"]
                .sum()
                .sort_values("amount", ascending=False)
            )
            st.dataframe(course_sum, use_container_width=True, hide_index=True)

    elif detail == "march":
        st.markdown("---")
        st.subheader(f"📅 {ym_march} 매출")
        st.metric("3월 합계", f"{march_total:,}원")
        if march_view.empty:
            st.info(f"{ym_march} 거래가 없습니다.")
        else:
            by_course = (
                march_view.groupby("course", as_index=False)["amount"]
                .sum()
                .sort_values("amount", ascending=False)
            )
            st.caption("코스별")
            st.dataframe(by_course, use_container_width=True, hide_index=True)
            st.caption("거래 목록")
            st.dataframe(
                march_view.sort_values(by="date", ascending=False)[tx_cols],
                use_container_width=True,
                hide_index=True,
            )

    elif detail == "reg":
        st.markdown("---")
        st.subheader(f"📝 {year}년 등록 건수")
        st.metric("등록", f"{year_reg_count}건")
        reg_only = year_view[year_view["event_type"] == "등록"].sort_values("date", ascending=False)
        if reg_only.empty:
            st.info("올해 등록 거래가 없습니다.")
        else:
            st.dataframe(reg_only[tx_cols], use_container_width=True, hide_index=True)

    elif detail == "rereg":
        st.markdown("---")
        st.subheader(f"🔁 {year}년 재등록 건수")
        st.metric("재등록", f"{year_rereg_count}건")
        rereg_only = year_view[year_view["event_type"] == "재등록"].sort_values("date", ascending=False)
        if rereg_only.empty:
            st.info("올해 재등록 거래가 없습니다.")
        else:
            st.dataframe(rereg_only[tx_cols], use_container_width=True, hide_index=True)

    st.markdown("---")
    tab1, tab2, tab3 = st.tabs(["📅 월별 코스 매출", "🗓 주별 코스 매출", "📜 전체 거래 내역"])

    with tab1:
        month_pivot = (
            view.groupby(["year_month", "course"], as_index=False)["amount"]
            .sum()
            .sort_values(by=["year_month", "course"], ascending=[False, True])
        )
        st.dataframe(month_pivot, use_container_width=True, hide_index=True)

    with tab2:
        week_pivot = (
            view.groupby(["year_week", "course"], as_index=False)["amount"]
            .sum()
            .sort_values(by=["year_week", "course"], ascending=[False, True])
        )
        st.dataframe(week_pivot, use_container_width=True, hide_index=True)

    with tab3:
        st.dataframe(view.sort_values(by="date", ascending=False)[tx_cols], use_container_width=True, hide_index=True)
