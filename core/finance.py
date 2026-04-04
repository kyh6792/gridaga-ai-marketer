import re
import streamlit as st
import pandas as pd
from datetime import datetime
from core.database import get_conn
from core.curriculum import get_course_price_map
from core.streamlit_dataframe import dataframe_for_data_editor


WORKSHEET_NAME = "finance_transactions"
EXPENSE_WORKSHEET_NAME = "finance_expenses"
FINANCE_READ_TTL = 60
_FINANCE_NEXT_READ_FRESH = "_finance_sheet_next_read_fresh"


def mark_finance_sheet_dirty():
    """시트 쓰기 직후 다음 재무 화면 조회 시 ttl 캐시를 쓰지 않도록 표시."""
    st.session_state[_FINANCE_NEXT_READ_FRESH] = True


def _finance_read_ttl():
    return 0 if st.session_state.pop(_FINANCE_NEXT_READ_FRESH, False) else FINANCE_READ_TTL
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


def _expense_row_label(row) -> str:
    d = str(row.get("date", "")).strip()[:10]
    cat = str(row.get("category", "")).strip()
    it = str(row.get("item", "")).strip()
    amt = _to_int_amount(row.get("amount", 0))
    eid = str(row.get("ex_id", "")).strip()
    return f"{d} | {cat} | {it} | {amt:,}원 ({eid})"


def _expense_cell_to_str(v) -> str:
    """비용 표 편집기 TextColumn — 숫자만 들어간 셀(int)이면 str로 바꿔 dtype 오류 방지."""
    if v is None:
        return ""
    if isinstance(v, float) and pd.isna(v):
        return ""
    if isinstance(v, bool):
        return str(v).strip()
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else str(v)
    return str(v).strip()


def _coerce_expense_date_str(v) -> str | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d")
    s = str(v).strip()[:10]
    if len(s) >= 8 and s[4:5] == "-" and s[7:8] == "-":
        return s
    parsed = pd.to_datetime(v, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.strftime("%Y-%m-%d")


def _apply_expense_edits_from_table(ex_full: pd.DataFrame, edited: pd.DataFrame) -> pd.DataFrame:
    """edited: date(또는 date-like), category, item, amount, note, ex_id 열."""
    out = ex_full.copy()
    for _, er in edited.iterrows():
        eid = str(er.get("ex_id", "")).strip()
        if not eid:
            continue
        mask = out["ex_id"].astype(str).str.strip() == eid
        if not mask.any():
            continue
        ds = _coerce_expense_date_str(er.get("date"))
        if not ds:
            continue
        amt = _to_int_amount(er.get("amount", 0))
        if amt <= 0:
            continue
        out.loc[mask, "date"] = ds
        out.loc[mask, "year_month"] = ds[:7]
        out.loc[mask, "category"] = str(er.get("category", "")).strip()
        out.loc[mask, "item"] = str(er.get("item", "")).strip()
        out.loc[mask, "amount"] = int(amt)
        out.loc[mask, "note"] = str(er.get("note", "")).strip()
    out["amount"] = pd.to_numeric(out["amount"], errors="coerce").fillna(0).astype(int)
    for c in EXPENSE_COLUMNS:
        if c not in out.columns:
            out[c] = ""
    return out[EXPENSE_COLUMNS].copy()


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
    mark_finance_sheet_dirty()


def run_finance_ui():
    st.header("💰 재무")
    try:
        import core.ui as _ui

        _style = getattr(_ui, "apply_owner_dashboard_style", None)
        if callable(_style):
            _style()
    except Exception:
        pass
    _ttl = _finance_read_ttl()
    conn, df = _read_or_init_transactions(ttl=_ttl)
    ex_conn, ex_df = _read_or_init_expenses(ttl=_ttl)

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
                        mark_finance_sheet_dirty()
                        st.success("비용이 저장되었습니다.")
                        st.rerun()

        with st.expander("✏️ 비용 수정", expanded=False):
            if ex_view.empty:
                st.info("수정할 비용 데이터가 없습니다.")
            else:
                sorted_ex = ex_view.sort_values(by="date", ascending=False)
                labels: list[str] = []
                ids: list[str] = []
                for _, r in sorted_ex.iterrows():
                    eid = str(r.get("ex_id", "")).strip()
                    if not eid:
                        continue
                    ids.append(eid)
                    labels.append(_expense_row_label(r))
                if not ids:
                    st.info("비용 ID(ex_id)가 있는 항목이 없습니다.")
                else:
                    pick = st.selectbox(
                        "수정할 항목",
                        range(len(ids)),
                        format_func=lambda i: labels[i],
                        key="finance_expense_edit_pick",
                    )
                    sel_id = ids[int(pick)]
                    row = ex_view[ex_view["ex_id"].astype(str).str.strip() == sel_id].iloc[0]
                    with st.form("expense_edit_form"):
                        ed_cat = st.text_input("비용 분류", value=str(row.get("category", "")))
                        ed_item = st.text_input("항목명", value=str(row.get("item", "")))
                        ed_amt = st.number_input(
                            "비용 금액(원)",
                            min_value=0,
                            value=int(_to_int_amount(row.get("amount", 0))),
                            step=1000,
                        )
                        ed_parsed = pd.to_datetime(row.get("date"), errors="coerce")
                        ed_date = st.date_input(
                            "지출일",
                            value=ed_parsed.date() if not pd.isna(ed_parsed) else datetime.now().date(),
                        )
                        ed_note = st.text_area("메모", value=str(row.get("note", "")))
                        if st.form_submit_button("수정 저장", use_container_width=True):
                            if ed_amt <= 0:
                                st.error("비용 금액은 0보다 커야 합니다.")
                            else:
                                conn_e, full = _read_or_init_expenses(ttl=0)
                                mask = full["ex_id"].astype(str).str.strip() == sel_id
                                if not mask.any():
                                    st.error("항목을 찾을 수 없습니다. 새로고침 후 다시 시도하세요.")
                                else:
                                    ds = ed_date.strftime("%Y-%m-%d")
                                    full = full.copy()
                                    full.loc[mask, "date"] = ds
                                    full.loc[mask, "year_month"] = ds[:7]
                                    full.loc[mask, "category"] = str(ed_cat).strip()
                                    full.loc[mask, "item"] = str(ed_item).strip()
                                    full.loc[mask, "amount"] = int(ed_amt)
                                    full.loc[mask, "note"] = str(ed_note).strip()
                                    for c in EXPENSE_COLUMNS:
                                        if c not in full.columns:
                                            full[c] = ""
                                    full["amount"] = pd.to_numeric(full["amount"], errors="coerce").fillna(0).astype(int)
                                    conn_e.update(worksheet=EXPENSE_WORKSHEET_NAME, data=full[EXPENSE_COLUMNS])
                                    mark_finance_sheet_dirty()
                                    st.success("비용이 수정되었습니다.")
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
            # 조회 월 선택: 이번 달 고정이 아니라 월별 항목 조회 가능
            month_options = sorted(
                [m for m in ex_view["year_month"].dropna().astype(str).str.strip().unique().tolist() if m],
                reverse=True,
            )
            default_month = ym_now if ym_now in month_options else (month_options[0] if month_options else ym_now)
            selected_month = st.selectbox("조회 월", month_options if month_options else [ym_now], index=0, key="finance_expense_selected_month")
            if selected_month != default_month and default_month in month_options:
                # 사용자가 선택을 바꿀 수 있으므로, 첫 렌더 기본값만 안내
                pass

            from core.fullscreen_view import FS_FINANCE_EXPENSES, new_tab_link_markdown

            st.markdown(
                new_tab_link_markdown(
                    "이 조회 월 표를 새 창에서 크게 보기",
                    FS_FINANCE_EXPENSES,
                    expense_month=str(selected_month),
                ),
                unsafe_allow_html=True,
            )

            selected_month_view = ex_view[ex_view["year_month"] == selected_month].copy()
            selected_month_expense = int(selected_month_view["amount"].sum()) if not selected_month_view.empty else 0
            st.metric(f"{selected_month} 비용", f"{selected_month_expense:,}원")
            if selected_month_view.empty:
                st.info(f"{selected_month} 비용 데이터가 없습니다.")
            else:
                by_category = (
                    selected_month_view.groupby("category", as_index=False)["amount"]
                    .sum()
                    .sort_values("amount", ascending=False)
                )
                st.caption("분류별 합계")
                st.dataframe(by_category, use_container_width=True, hide_index=True)
                st.caption("비용 항목 목록 — 셀을 직접 고친 뒤 아래 버튼으로 저장하세요 (ID 열은 변경 불가)")
                list_df = selected_month_view.sort_values(by="date", ascending=False)[
                    ["date", "category", "item", "amount", "note", "ex_id"]
                ].copy()
                list_df["amount"] = pd.to_numeric(list_df["amount"], errors="coerce").fillna(0).astype(int)
                dconv = pd.to_datetime(list_df["date"], errors="coerce")
                today_d = datetime.now().date()
                list_df["date"] = [x.date() if pd.notna(x) else today_d for x in dconv]
                for _c in ("category", "item", "note", "ex_id"):
                    list_df[_c] = list_df[_c].map(_expense_cell_to_str)
                    list_df[_c] = list_df[_c].astype(object)
                list_df = dataframe_for_data_editor(list_df)
                edited_tbl = st.data_editor(
                    list_df,
                    column_config={
                        "ex_id": st.column_config.TextColumn("ID", disabled=True),
                        "date": st.column_config.DateColumn("지출일", format="YYYY-MM-DD"),
                        "amount": st.column_config.NumberColumn("금액", format="%d", min_value=1, step=1000),
                        "category": st.column_config.TextColumn("분류"),
                        "item": st.column_config.TextColumn("항목"),
                        "note": st.column_config.TextColumn("메모"),
                    },
                    use_container_width=True,
                    num_rows="fixed",
                    hide_index=True,
                    key=f"finance_expense_table_editor_{selected_month}",
                )
                if st.button("표 수정 내용 저장", key=f"finance_expense_table_save_{selected_month}", use_container_width=True):
                    conn_tbl, full = _read_or_init_expenses(ttl=0)
                    merged = _apply_expense_edits_from_table(full, edited_tbl)
                    conn_tbl.update(worksheet=EXPENSE_WORKSHEET_NAME, data=merged)
                    mark_finance_sheet_dirty()
                    st.success("표에서 수정한 비용이 반영되었습니다.")
                    st.rerun()

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


def render_finance_expenses_fullscreen_page():
    """?fullscreen=finance_expenses&expense_month=YYYY-MM — 새 탭 전용(조회·읽기)."""
    from core.fullscreen_view import fullscreen_page_close_block_html

    try:
        import core.ui as _ui

        _style = getattr(_ui, "apply_owner_dashboard_style", None)
        if callable(_style):
            _style()
    except Exception:
        pass
    _ttl = _finance_read_ttl()
    _, ex_df = _read_or_init_expenses(ttl=_ttl)
    ex_view = ex_df.copy() if ex_df is not None else pd.DataFrame(columns=EXPENSE_COLUMNS)
    ex_view["amount"] = pd.to_numeric(ex_view["amount"], errors="coerce").fillna(0).astype(int)
    ex_view["year_month"] = ex_view["year_month"].astype(str).str.strip()

    ym = str(st.query_params.get("expense_month", "") or "").strip()
    if not ym:
        ym = datetime.now().strftime("%Y-%m")

    st.subheader(f"🗓 월별 비용 · {ym}")
    st.caption("비용 등록·수정·표에서 편집은 메인 화면 → 재무 → 비용 처리에서 해 주세요.")

    selected_month_view = ex_view[ex_view["year_month"] == ym].copy()
    selected_month_expense = int(selected_month_view["amount"].sum()) if not selected_month_view.empty else 0
    st.metric(f"{ym} 비용 합계", f"{selected_month_expense:,}원")

    if selected_month_view.empty:
        st.info(f"{ym} 비용 데이터가 없습니다.")
    else:
        by_category = (
            selected_month_view.groupby("category", as_index=False)["amount"]
            .sum()
            .sort_values("amount", ascending=False)
        )
        st.caption("분류별 합계")
        st.dataframe(by_category, use_container_width=True, hide_index=True)
        st.caption("비용 항목 목록")
        st.dataframe(
            selected_month_view.sort_values(by="date", ascending=False)[
                ["date", "category", "item", "amount", "note", "ex_id"]
            ],
            use_container_width=True,
            hide_index=True,
        )
    st.markdown(fullscreen_page_close_block_html(), unsafe_allow_html=True)
