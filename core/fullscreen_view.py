"""표 전용 뷰: ?fullscreen=… 쿼리로 새 탭에서 넓게 표시."""

from __future__ import annotations

import html
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


def schedule_month_fullscreen_href(year: int, month: int) -> str:
    """월별 타임테이블 전용 새 탭 URL(현재 앱 기준 상대 `?…` 쿼리)."""
    return _fullscreen_table_href(FS_SCHEDULE_MONTH, schedule_year=int(year), schedule_month=int(month))


def _fullscreen_table_href(fs: str, **extra: str | int) -> str:
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
    return "?" + urllib.parse.urlencode(q, quote_via=urllib.parse.quote, safe="")


def new_tab_link_markdown(label: str, fs: str, **extra: str | int) -> str:
    href = html.escape(_fullscreen_table_href(fs, **extra))
    lab = html.escape(label)
    return (
        f'<p style="margin:0.35rem 0 0.6rem 0;">'
        f'<a href="{href}" target="_blank" rel="noopener noreferrer">{lab}</a></p>'
    )


def fullscreen_page_close_block_html() -> str:
    """새 탭으로 연 전용 표 페이지 하단: 이 탭만 닫기(일부 브라우저는 스크립트로 탭 닫기를 막음)."""
    return (
        '<p style="margin-top:1rem;">'
        '<button type="button" onclick="window.close();" '
        'style="cursor:pointer;padding:0.45rem 0.9rem;border-radius:0.5rem;'
        'border:1px solid rgba(60,60,60,0.2);background:#f8f8f8;font-size:1rem;">'
        "닫기</button></p>"
        '<p style="font-size:0.8rem;color:#6c6c6c;margin:0.35rem 0 0 0;">'
        "일부 브라우저에서는 탭이 닫히지 않을 수 있습니다. 그때는 탭을 직접 닫아 주세요."
        "</p>"
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
        st.markdown(fullscreen_page_close_block_html(), unsafe_allow_html=True)
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
