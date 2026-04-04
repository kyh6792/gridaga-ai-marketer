"""표 전용 뷰: ?fullscreen=… 쿼리로 새 탭에서 넓게 표시."""

from __future__ import annotations

import urllib.parse

import streamlit as st

FS_SCHEDULE_MONTH = "schedule_month"
FS_FINANCE_EXPENSES = "finance_expenses"

_FS_LAYOUT_KEYS = frozenset({FS_SCHEDULE_MONTH, FS_FINANCE_EXPENSES})


def layout_for_fullscreen_query() -> str:
    try:
        fs = str(st.query_params.get("fullscreen", "") or "").strip()
    except Exception:
        fs = ""
    return "wide" if fs in _FS_LAYOUT_KEYS else "centered"


def new_tab_link_markdown(label: str, fs: str, **extra: str | int) -> str:
    q: dict[str, str] = {"fullscreen": str(fs), "mode": "owner"}
    lo = st.session_state.get("owner_login_at") or str(st.query_params.get("owner_login_at", "") or "")
    if lo:
        q["owner_login_at"] = str(lo)
    om = st.session_state.get("owner_menu_index")
    if om is not None:
        q["owner_menu_idx"] = str(int(om))
    for k, v in extra.items():
        if v is None:
            continue
        s = str(v).strip()
        if s:
            q[str(k)] = s
    href = "?" + urllib.parse.urlencode(q, quote_via=urllib.parse.quote, safe="")
    return (
        f'<p style="margin:0.35rem 0 0.6rem 0;">'
        f'<a href="{href}" target="_blank" rel="noopener noreferrer">{label}</a></p>'
    )


def try_render_fullscreen_tables() -> bool:
    """전용 표 페이지를 그렸으면 True (호출측에서 st.stop 권장)."""
    try:
        fs = str(st.query_params.get("fullscreen", "") or "").strip()
    except Exception:
        fs = ""
    if fs not in _FS_LAYOUT_KEYS:
        return False

    if not st.session_state.get("owner_authenticated"):
        st.error("원장 로그인이 필요합니다. 메인 창에서 로그인한 뒤, 다시 **새 창에서 보기**를 눌러 주세요.")
        st.markdown(
            '<p><a href="/" target="_self">← 처음(메인)으로</a></p>',
            unsafe_allow_html=True,
        )
        return True

    if fs == FS_SCHEDULE_MONTH:
        from core.schedule import render_monthly_timetable_fullscreen_page

        render_monthly_timetable_fullscreen_page()
        return True

    if fs == FS_FINANCE_EXPENSES:
        from core.finance import render_finance_expenses_fullscreen_page

        render_finance_expenses_fullscreen_page()
        return True

    return False
