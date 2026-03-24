import re
import streamlit as st
import pandas as pd
from datetime import datetime
from core.database import get_conn
from core.curriculum import get_course_price_map


WORKSHEET_NAME = "finance_transactions"
EXPENSE_WORKSHEET_NAME = "finance_expenses"
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
    "base_amount",
    "discount_type",
    "discount_value",
    "discount_amount",
    "event_name",
    "note",
]
EXPENSE_COLUMNS = [
    "ex_id",
    "date",
    "year_month",
    "category",
    "item",
    "amount",
    "note",
]


def _read_or_init_transactions(ttl=0):
    """ttl>0 이면 짧은 캐시로 시트 재조회·상단 Running 체감 완화. 저장 직전에는 ttl=0."""
    conn = get_conn()
    try:
        df = conn.read(worksheet=WORKSHEET_NAME, ttl=ttl)
    except Exception:
        # 읽기 실패 시 빈 시트로 덮어쓰지 않는다(데이터 유실 방지).
        df = pd.DataFrame(columns=BASE_COLUMNS)

    if df is None or df.empty:
        df = pd.DataFrame(columns=BASE_COLUMNS)
    for c in BASE_COLUMNS:
        if c not in df.columns:
            df[c] = ""
    return conn, df[BASE_COLUMNS].copy()


def _read_or_init_expenses(ttl=0):
    conn = get_conn()
    try:
        df = conn.read(worksheet=EXPENSE_WORKSHEET_NAME, ttl=ttl)
    except Exception:
        # 읽기 실패 시 빈 시트로 덮어쓰지 않는다(데이터 유실 방지).
        df = pd.DataFrame(columns=EXPENSE_COLUMNS)

    if df is None or df.empty:
        df = pd.DataFrame(columns=EXPENSE_COLUMNS)
    for c in EXPENSE_COLUMNS:
        if c not in df.columns:
            df[c] = ""
    return conn, df[EXPENSE_COLUMNS].copy()


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


def record_registration_payment(
    student_id,
    student_name,
    course,
    event_type="등록",
    amount=None,
    note="",
    *,
    base_amount=None,
    discount_type="없음",
    discount_value=0,
    discount_amount=0,
    event_name="",
):
    """등록/재등록 시 재무 거래를 누적 저장"""
    conn, df = _read_or_init_transactions()
    now = datetime.now()
    resolved_base = _resolve_course_amount(course)
    base_amt = resolved_base if base_amount is None else _to_int_amount(base_amount)
    tx_amount = base_amt if amount is None else _to_int_amount(amount)
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
        "base_amount": int(base_amt),
        "discount_type": str(discount_type),
        "discount_value": int(_to_int_amount(discount_value)),
        "discount_amount": int(_to_int_amount(discount_amount)),
        "event_name": str(event_name),
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
    conn, df = _read_or_init_transactions(ttl=25)
    ex_conn, ex_df = _read_or_init_expenses(ttl=25)

    view = df.copy() if df is not None else pd.DataFrame(columns=BASE_COLUMNS)
    view["amount"] = pd.to_numeric(view["amount"], errors="coerce").fillna(0).astype(int)
    view["year_month"] = view["year_month"].astype(str).str.strip()
    view["event_type"] = view["event_type"].astype(str).str.strip()

    year = datetime.now().year
    ym_now = datetime.now().strftime("%Y-%m")
    year_prefix = f"{year}-"
    full_year_sales = view[view["year_month"].str.startswith(year_prefix, na=False)].copy()
    full_month_sales = view[view["year_month"] == ym_now].copy()

    tx_cols = [
        "date",
        "event_type",
        "student_name",
        "student_id",
        "course",
        "base_amount",
        "discount_type",
        "discount_amount",
        "amount",
        "note",
        "tx_id",
    ]

    ex_view = ex_df.copy() if ex_df is not None else pd.DataFrame(columns=EXPENSE_COLUMNS)
    ex_view["amount"] = pd.to_numeric(ex_view["amount"], errors="coerce").fillna(0).astype(int)
    ex_view["year_month"] = ex_view["year_month"].astype(str).str.strip()

    # 1) 원비 관리
    with st.expander("💳 원비 관리", expanded=True):
        year_view = full_year_sales.copy()
        month_view = full_month_sales.copy()

        tx_filter = st.radio("거래 유형", ["전체", "등록만", "재등록만"], horizontal=True)
        if tx_filter == "등록만":
            year_view = year_view[year_view["event_type"] == "등록"].copy()
            month_view = month_view[month_view["event_type"] == "등록"].copy()
        elif tx_filter == "재등록만":
            year_view = year_view[year_view["event_type"] == "재등록"].copy()
            month_view = month_view[month_view["event_type"] == "재등록"].copy()

        annual_total = int(year_view["amount"].sum()) if not year_view.empty else 0
        month_total = int(month_view["amount"].sum()) if not month_view.empty else 0
        year_reg_count = int((year_view["event_type"] == "등록").sum()) if not year_view.empty else 0
        year_rereg_count = int((year_view["event_type"] == "재등록").sum()) if not year_view.empty else 0

        st.caption(
            f"필터 `{tx_filter}` · 올해 `{year}` · 이번 달 `{ym_now}` · "
            f"연매출 **{annual_total:,}원** · 월매출 **{month_total:,}원** · "
            f"등록 **{year_reg_count}건** · 재등록 **{year_rereg_count}건**"
        )

        with st.expander("📈 연 총매출", expanded=False):
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
                course_sum = (
                    year_view.groupby("course", as_index=False)["amount"]
                    .sum()
                    .sort_values("amount", ascending=False)
                )
                st.caption("코스별 누적 (올해)")
                st.dataframe(course_sum, use_container_width=True, hide_index=True)

        with st.expander("📅 월별 매출", expanded=False):
            st.metric("이번 달 합계", f"{month_total:,}원")
            if month_view.empty:
                st.info(f"{ym_now} 거래가 없습니다.")
            else:
                by_course = (
                    month_view.groupby("course", as_index=False)["amount"]
                    .sum()
                    .sort_values("amount", ascending=False)
                )
                st.caption("코스별")
                st.dataframe(by_course, use_container_width=True, hide_index=True)
                st.caption("거래 목록")
                st.dataframe(
                    month_view.sort_values(by="date", ascending=False)[tx_cols],
                    use_container_width=True,
                    hide_index=True,
                )

        with st.expander("📝 등록 건수", expanded=False):
            st.metric("등록", f"{year_reg_count}건")
            reg_only = year_view[year_view["event_type"] == "등록"].sort_values("date", ascending=False)
            if reg_only.empty:
                st.info("올해 등록 거래가 없습니다.")
            else:
                st.dataframe(reg_only[tx_cols], use_container_width=True, hide_index=True)

        with st.expander("🔁 재등록 건수", expanded=False):
            st.metric("재등록", f"{year_rereg_count}건")
            rereg_only = year_view[year_view["event_type"] == "재등록"].sort_values("date", ascending=False)
            if rereg_only.empty:
                st.info("올해 재등록 거래가 없습니다.")
            else:
                st.dataframe(rereg_only[tx_cols], use_container_width=True, hide_index=True)

    # 2) 비용 처리
    with st.expander("🧾 비용 처리", expanded=False):
        with st.expander("➕ 비용 등록", expanded=False):
            with st.form("expense_create_form", clear_on_submit=True):
                c1, c2 = st.columns(2)
                with c1:
                    ex_category = st.text_input("비용 분류", placeholder="예: 임대료, 재료비, 광고비")
                    ex_item = st.text_input("항목명", placeholder="예: 3월 캔버스 구입")
                with c2:
                    ex_amount = st.number_input("비용 금액(원)", min_value=0, value=0, step=1000)
                    ex_date = st.date_input("지출일", value=datetime.now())
                ex_note = st.text_area("메모", placeholder="선택 입력")
                if st.form_submit_button("비용 저장", use_container_width=True):
                    if ex_amount <= 0:
                        st.error("비용 금액은 0보다 커야 합니다.")
                    else:
                        now = datetime.now()
                        new_row = pd.DataFrame([{
                            "ex_id": f"ex_{now.strftime('%Y%m%d%H%M%S%f')}",
                            "date": ex_date.strftime("%Y-%m-%d"),
                            "year_month": ex_date.strftime("%Y-%m"),
                            "category": str(ex_category).strip(),
                            "item": str(ex_item).strip(),
                            "amount": int(ex_amount),
                            "note": str(ex_note).strip(),
                        }])
                        updated = pd.concat([ex_view, new_row], ignore_index=True) if not ex_view.empty else new_row
                        ex_conn.update(worksheet=EXPENSE_WORKSHEET_NAME, data=updated)
                        st.success("비용이 저장되었습니다.")
                        st.rerun()

        ex_year_view = ex_view[ex_view["year_month"].str.startswith(year_prefix, na=False)].copy()
        ex_month_view = ex_view[ex_view["year_month"] == ym_now].copy()
        annual_expense = int(ex_year_view["amount"].sum()) if not ex_year_view.empty else 0
        month_expense = int(ex_month_view["amount"].sum()) if not ex_month_view.empty else 0
        annual_expense_count = int(len(ex_year_view))

        with st.expander("📉 연 총비용", expanded=False):
            st.metric("연 총비용", f"{annual_expense:,}원")
            if ex_year_view.empty:
                st.info("올해 비용 데이터가 없습니다.")
            else:
                by_month_ex = (
                    ex_year_view.groupby("year_month", as_index=False)["amount"]
                    .sum()
                    .sort_values("year_month")
                )
                st.caption("월별 비용")
                st.dataframe(by_month_ex, use_container_width=True, hide_index=True)

        with st.expander("🗓 월별 비용", expanded=False):
            st.metric("이번 달 비용", f"{month_expense:,}원")
            if ex_month_view.empty:
                st.info(f"{ym_now} 비용 데이터가 없습니다.")
            else:
                st.dataframe(
                    ex_month_view.sort_values(by="date", ascending=False)[["date", "category", "item", "amount", "note", "ex_id"]],
                    use_container_width=True,
                    hide_index=True,
                )

        with st.expander("🔢 비용 등록건수", expanded=False):
            st.metric("올해 등록건수", f"{annual_expense_count}건")

    # 3) 총 비용(실질 수입)
    with st.expander("📊 총 비용", expanded=False):
        annual_sales_total = int(full_year_sales["amount"].sum()) if not full_year_sales.empty else 0
        month_sales_total = int(full_month_sales["amount"].sum()) if not full_month_sales.empty else 0
        annual_expense_total = int(
            ex_view[ex_view["year_month"].str.startswith(year_prefix, na=False)]["amount"].sum()
        ) if not ex_view.empty else 0
        month_expense_total = int(
            ex_view[ex_view["year_month"] == ym_now]["amount"].sum()
        ) if not ex_view.empty else 0
        annual_income = annual_sales_total - annual_expense_total
        month_income = month_sales_total - month_expense_total

        c1, c2 = st.columns(2)
        with c1:
            st.metric(f"{year}년 수입", f"{annual_income:,}원")
            st.caption(f"연매출 {annual_sales_total:,}원 - 연비용 {annual_expense_total:,}원")
        with c2:
            st.metric(f"{ym_now} 수입", f"{month_income:,}원")
            st.caption(f"월매출 {month_sales_total:,}원 - 월비용 {month_expense_total:,}원")
