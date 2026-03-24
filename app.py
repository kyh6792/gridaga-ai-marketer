import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime, timedelta
import base64
from pathlib import Path

# 배포본 core/ui.py 버전이 달라도 ImportError 나지 않게 모듈 단위로 로드
import core.ui as _ui

def _noop():
    return None


def _stub_intro(image_path, duration=2.5):
    st.session_state["intro_done"] = True


def _stub_owner_menu_grid(owner_login_at="", active_idx=None):
    st.warning("운영 메뉴 UI(`render_owner_menu_grid`)를 찾을 수 없습니다. 저장소의 `core/ui.py`를 최신으로 맞춰 주세요.")


display_intro = getattr(_ui, "display_intro", _stub_intro)
render_owner_brand_header = getattr(_ui, "render_owner_brand_header", _noop)
render_owner_menu_grid = getattr(_ui, "render_owner_menu_grid", _stub_owner_menu_grid)
apply_owner_dashboard_style = getattr(_ui, "apply_owner_dashboard_style", _noop)

from core.marketer import run_marketing_ui  # 마케팅팀 모듈 호출
from core.curriculum import run_curriculum_ui
from core.finance import run_finance_ui
from core.students import (
    run_student_ui,
    get_recent_attendance_logs,
    create_attendance_request,
    get_pending_attendance_requests,
    approve_attendance_request,
    get_failed_log_requests,
    retry_failed_log_request,
)
from core.schedule import get_today_schedule_by_student
# --- 1. 페이지 설정 ---
st.set_page_config(
    page_title="작업실 그리다가 OS", 
    page_icon="🎨", 
    layout="centered" # 모바일은 wide보다 centered가 가독성이 좋습니다.
)
_inject_chrome = getattr(_ui, "inject_global_streamlit_chrome_hide", None)
if callable(_inject_chrome):
    _inject_chrome()
else:
    _css = getattr(_ui, "STREAMLIT_CHROME_HIDE_CSS", None)
    if _css:
        st.markdown(f"<style>{_css}</style>", unsafe_allow_html=True)
    else:
        st.markdown(
            '<style>[data-testid="stStatusWidget"]{display:none!important;}</style>',
            unsafe_allow_html=True,
        )

# Google Drive OAuth 콜백 (?code= / ?state=) — 인트로보다 먼저 처리
from core import drive_oauth

drive_oauth.try_finish_google_drive_oauth()

# --- 2. 인트로 화면 실행 ---
# mode가 없는 진입 화면에서만 세션당 1회 재생 (skip_intro 쿼리 의존 제거)
qp_mode_for_intro = str(st.query_params.get("mode", ""))
if qp_mode_for_intro not in ("student", "owner"):
    display_intro("intro/logo.jpg", duration=1.5)
else:
    # URL로 바로 진입(student/owner)한 경우도 메인 렌더는 진행되어야 함
    st.session_state["intro_done"] = True

def init_entry_state():
    defaults = {
        "entry_mode": None,
        "owner_authenticated": False,
        "student_id_input": "",
        "student_message": "",
        "student_message_type": "",
        "attendance_log_error": "",
        "owner_prev_pending_count": 0,
        "owner_login_at": "",
        "owner_menu_index": 0,
        "owner_prev_menu_index": 0,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    # 새로고침 시 UI 모드 복원 (student/owner)
    try:
        qp_mode = str(st.query_params.get("mode", ""))
        if qp_mode in ("student", "owner") and not st.session_state.get("entry_mode"):
            st.session_state["entry_mode"] = qp_mode
    except Exception:
        pass


def get_owner_password():
    try:
        if "owner_password" in st.secrets:
            return str(st.secrets["owner_password"])
        if "auth" in st.secrets and "owner_password" in st.secrets["auth"]:
            return str(st.secrets["auth"]["owner_password"])
    except Exception:
        return ""
    return ""


def is_owner_session_valid():
    """원장 로그인 세션 유효성(설정된 분) 검사"""
    login_at = st.session_state.get("owner_login_at", "")
    if not login_at:
        return False
    try:
        login_dt = datetime.strptime(str(login_at), "%Y-%m-%d %H:%M:%S")
    except Exception:
        return False

    session_minutes = 60
    try:
        if "owner_session_minutes" in st.secrets:
            session_minutes = int(st.secrets["owner_session_minutes"])
        elif "auth" in st.secrets and "owner_session_minutes" in st.secrets["auth"]:
            session_minutes = int(st.secrets["auth"]["owner_session_minutes"])
    except Exception:
        session_minutes = 60

    if session_minutes < 1:
        session_minutes = 1
    return datetime.now() <= (login_dt + timedelta(minutes=session_minutes))


def sync_owner_session_from_query():
    """새로고침 시 원장 세션(유지시간 내) 복원"""
    try:
        qp_login_at = str(st.query_params.get("owner_login_at", ""))
        qp_mode = str(st.query_params.get("mode", ""))
    except Exception:
        return

    if qp_mode != "owner" or not qp_login_at:
        return

    if not st.session_state.get("owner_login_at"):
        st.session_state["owner_login_at"] = qp_login_at
    if is_owner_session_valid():
        st.session_state["owner_authenticated"] = True

    try:
        qp_menu_idx = int(str(st.query_params.get("owner_menu_idx", "0")))
        if 0 <= qp_menu_idx <= 3:
            st.session_state["owner_menu_index"] = qp_menu_idx
    except Exception:
        pass


def render_intro_branch():
    student_bg = "linear-gradient(120deg, #C09066 0%, #B47F57 55%, #A86E48 100%)"
    teacher_bg = "linear-gradient(120deg, #9E6B43 0%, #8E5F3D 58%, #7E5233 100%)"
    try:
        root = Path(__file__).resolve().parent
        s_path = root / "assets" / "student_bt.png"
        t_path = root / "assets" / "teacher_bt.png"
        if s_path.exists():
            s_b64 = base64.b64encode(s_path.read_bytes()).decode("ascii")
            student_bg = f"url('data:image/png;base64,{s_b64}') center/cover no-repeat"
        if t_path.exists():
            t_b64 = base64.b64encode(t_path.read_bytes()).decode("ascii")
            teacher_bg = f"url('data:image/png;base64,{t_b64}') center/cover no-repeat"
    except Exception:
        pass

    css = """
        <style>
        .home-welcome-card {
            border: 1px solid #B78F6A;
            border-radius: 16px;
            padding: 0.95rem 1rem;
            margin: 0.2rem 0 0.75rem 0;
            background: linear-gradient(180deg, #E8D4BE 0%, #DDBE9D 100%);
            box-shadow: 0 3px 10px rgba(96, 72, 48, 0.12);
        }
        .home-welcome-title {
            margin: 0;
            color: #4A3526;
            font-size: 1.2rem;
            font-weight: 800;
            line-height: 1.25;
        }
        .home-welcome-sub {
            margin: 0.35rem 0 0 0;
            color: #5F4736;
            font-size: 0.93rem;
            line-height: 1.4;
        }
        div[data-testid="stButton"] > button.entry-student-btn,
        div[data-testid="stButton"] > button.entry-teacher-btn {
            border: none !important;
            box-shadow: none !important;
            color: #4A3526 !important;
            font-weight: 700 !important;
            min-height: 54px !important;
            transition: transform 120ms ease, filter 120ms ease !important;
        }
        div[data-testid="stButton"] > button.entry-student-btn {
            background: __STUDENT_BG__ !important;
            background-size: cover !important;
            background-position: center !important;
            background-repeat: no-repeat !important;
        }
        div[data-testid="stButton"] > button.entry-teacher-btn {
            background: __TEACHER_BG__ !important;
            background-size: cover !important;
            background-position: center !important;
            background-repeat: no-repeat !important;
        }
        div[data-testid="stButton"] > button.entry-student-btn:active,
        div[data-testid="stButton"] > button.entry-teacher-btn:active {
            transform: translateY(2px) scale(0.988) !important;
            filter: brightness(0.93) !important;
        }
        </style>
        <div class="home-welcome-card">
            <p class="home-welcome-title">작업실 그리다가</p>
            <p class="home-welcome-sub">오늘도 반가워요. 아래에서 사용자 유형을 선택해 주세요.</p>
        </div>
    """
    st.markdown(
        css.replace("__STUDENT_BG__", student_bg).replace("__TEACHER_BG__", teacher_bg),
        unsafe_allow_html=True,
    )
    if st.button("🎓 원생용", use_container_width=True, key="entry_student"):
        st.session_state["entry_mode"] = "student"
        st.query_params["mode"] = "student"
        st.query_params.pop("owner_login_at", None)
        st.session_state["student_id_input"] = ""
        st.session_state["student_message"] = ""
        st.session_state["student_message_type"] = ""
        st.rerun()
    if st.button("🧑‍🏫 선생님", use_container_width=True, key="entry_owner"):
        st.session_state["entry_mode"] = "owner"
        st.query_params["mode"] = "owner"
        st.rerun()

    components.html(
        """
        <script>
        (function () {
          const doc = window.parent && window.parent.document ? window.parent.document : document;
          function applyEntryBtnClass() {
            try {
              const btns = doc.querySelectorAll('div[data-testid="stButton"] > button');
              btns.forEach((b) => {
                const t = (b.innerText || "").trim();
                if (t.includes("원생용")) b.classList.add("entry-student-btn");
                if (t.includes("선생님")) b.classList.add("entry-teacher-btn");
              });
            } catch (e) {}
          }
          applyEntryBtnClass();
          setTimeout(applyEntryBtnClass, 80);
          setTimeout(applyEntryBtnClass, 250);
        })();
        </script>
        """,
        height=0,
    )


def render_student_entry():
    st.subheader("🎓 원생 출석")
    st.caption("ID를 입력하면 오늘 수업 1회가 차감됩니다.")
    st.markdown(
        """
        <style>
        /* 원생 출석 화면에서는 버튼 패딩을 줄여 3열 키패드 고정 */
        div[data-testid="stButton"] > button {
            width: 100% !important;
            box-sizing: border-box !important;
            padding: 0.4rem 0.2rem !important;
            min-height: 44px !important;
            font-size: 0.95rem !important;
        }
        /* Streamlit 모바일 자동 스택 방지: 키패드 3열 강제 유지 */
        div[data-testid="stHorizontalBlock"] {
            display: flex !important;
            flex-wrap: nowrap !important;
            gap: 0.25rem !important;
        }
        div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
            flex: 1 1 0 !important;
            min-width: 0 !important;
            max-width: 33.33% !important;
        }
        /* 세로 모드(좁은 폭)에서 추가 축소 */
        @media (max-width: 480px) {
            div[data-testid="stButton"] > button {
                padding: 0.3rem 0.08rem !important;
                min-height: 40px !important;
                font-size: 0.85rem !important;
            }
            div[data-testid="stHorizontalBlock"] {
                gap: 0.18rem !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    current_id = st.session_state.get("student_id_input", "")
    st.code(current_id if current_id else "ID를 입력하세요", language="text")
    if current_id:
        today_df = get_today_schedule_by_student(current_id)
        if today_df is not None and not today_df.empty:
            first = today_df.iloc[0]
            st.info(f"오늘 일정: {first.get('weekday', '')} {first.get('time_slot', '')}")
        else:
            st.caption("오늘 등록된 시간표가 없습니다.")

    if st.session_state.get("student_message"):
        msg_type = st.session_state.get("student_message_type")
        if msg_type == "success":
            st.success(st.session_state["student_message"])
        else:
            st.error(st.session_state["student_message"])

    keypad = [
        ["1", "2", "3"],
        ["4", "5", "6"],
        ["7", "8", "9"],
        ["⌫", "0", "C"],
    ]

    for row_idx, row in enumerate(keypad):
        cols = st.columns(3, gap="small")
        for col_idx, key_val in enumerate(row):
            with cols[col_idx]:
                if st.button(key_val, use_container_width=True, key=f"kp_{row_idx}_{col_idx}"):
                    if key_val == "⌫":
                        st.session_state["student_id_input"] = st.session_state["student_id_input"][:-1]
                    elif key_val == "C":
                        st.session_state["student_id_input"] = ""
                    else:
                        st.session_state["student_id_input"] += key_val
                    st.session_state["student_message"] = ""
                    st.session_state["student_message_type"] = ""
                    st.rerun()

    if st.button("입력값 지우기", use_container_width=True, key="id_clear"):
        st.session_state["student_id_input"] = ""
        st.session_state["student_message"] = ""
        st.session_state["student_message_type"] = ""
        st.rerun()

    if st.button("✅ 확인 (1회 차감)", type="primary", use_container_width=True):
        student_id = st.session_state.get("student_id_input", "").strip()
        if not student_id:
            st.session_state["student_message"] = "ID를 먼저 입력해주세요."
            st.session_state["student_message_type"] = "error"
            st.rerun()

        success, result = create_attendance_request(student_id)
        if success:
            st.session_state["student_message"] = f"✅ {result} (원장 승인 후 차감됩니다)"
            st.session_state["student_message_type"] = "success"
            st.session_state["student_id_input"] = ""
        else:
            st.session_state["student_message"] = str(result)
            st.session_state["student_message_type"] = "error"
        st.rerun()

    st.markdown("---")
    if st.button("⬅️ 처음으로", use_container_width=True, key="back_from_student"):
        st.session_state["entry_mode"] = None
        st.session_state["intro_done"] = False
        st.session_state["student_id_input"] = ""
        st.session_state["student_message"] = ""
        st.session_state["student_message_type"] = ""
        st.query_params.pop("mode", None)
        st.query_params.pop("skip_intro", None)
        st.rerun()


def render_owner_auth():
    st.subheader("🧑‍🏫 원장 인증")
    owner_password = get_owner_password()
    if not owner_password:
        st.warning("원장 비밀번호가 설정되지 않았습니다. `st.secrets`에 `owner_password`를 추가해주세요.")

    with st.form("owner_login_form", clear_on_submit=True):
        pwd = st.text_input("비밀번호", type="password", placeholder="원장 비밀번호 입력")
        submitted = st.form_submit_button("로그인", use_container_width=True)
        if submitted:
            if owner_password and pwd == owner_password:
                st.session_state["owner_authenticated"] = True
                st.session_state["owner_login_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                st.query_params["mode"] = "owner"
                st.query_params["owner_login_at"] = st.session_state["owner_login_at"]
                st.rerun()
            st.error("비밀번호가 올바르지 않습니다.")

    st.markdown("---")
    if st.button("⬅️ 처음으로", use_container_width=True, key="back_from_owner"):
        st.session_state["entry_mode"] = None
        st.session_state["intro_done"] = False
        st.session_state["owner_authenticated"] = False
        st.session_state["owner_login_at"] = ""
        st.query_params.pop("mode", None)
        st.query_params.pop("owner_login_at", None)
        st.query_params.pop("skip_intro", None)
        st.rerun()


def render_owner_menu():
    apply_owner_dashboard_style()
    render_owner_brand_header()

    def render_dashboard_cards():
        pending_requests = get_pending_attendance_requests(limit=20)
        failed_log_requests = get_failed_log_requests(limit=20)
        recent_logs = get_recent_attendance_logs(limit=3)
        pending_count = len(pending_requests) if not pending_requests.empty else 0
        pending_bg = "rgba(179, 123, 94, 0.72)" if pending_count > 0 else "rgba(232, 212, 190, 0.68)"
        pending_border = "#8F5C44" if pending_count > 0 else "#B78F6A"
        pending_text = "#FFF8F2" if pending_count > 0 else "#4A3526"

        # 승인대기 수 / 최근 갱신 반반 카드 (모바일 고정)
        components.html(
            f"""
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:0 0 14px 0;">
                <div style="border:1px solid {pending_border};border-radius:12px;background:{pending_bg};padding:7px;min-height:66px;">
                    <div style="font-size:12px;color:{pending_text};">승인대기 수</div>
                    <div style="font-size:20px;font-weight:700;color:{pending_text};line-height:1.1;">{pending_count}</div>
                </div>
                <div style="border:1px solid #B78F6A;border-radius:12px;background:rgba(232,212,190,0.62);padding:7px;min-height:66px;">
                    <div style="font-size:12px;color:#6D5543;">최근 갱신</div>
                    <div style="font-size:20px;font-weight:700;color:#4A3526;line-height:1.1;">{datetime.now().strftime('%H:%M')}</div>
                </div>
            </div>
            """,
            height=98,
        )

        st.markdown("### 승인 하기")
        if pending_requests.empty:
            st.info("승인 대기 요청이 없습니다.")
        else:
            for _, row in pending_requests.iterrows():
                req_id = str(row.get("request_id", ""))
                req_time = str(row.get("time", ""))
                student_name = str(row.get("student_name", "원생"))
                student_id = str(row.get("student_id", ""))
                with st.container(border=True):
                    st.markdown(f"**{student_name}** (`{student_id}`)")
                    st.caption(f"요청: {req_time}")
                    if st.button("승인", key=f"approve_req_{req_id}", use_container_width=True):
                        ok, msg = approve_attendance_request(req_id)
                        if ok:
                            st.success(msg)
                        else:
                            st.error(msg)
                        st.rerun()

        st.markdown("### 최근 처리")
        if recent_logs.empty:
            st.caption("아직 처리 이력이 없습니다.")
        else:
            for _, row in recent_logs.iterrows():
                with st.container(border=True):
                    nm = str(row.get("student_name", "원생"))
                    sid = str(row.get("student_id", ""))
                    rem = str(row.get("remain_count", ""))
                    ap = str(row.get("approved_time", "")) or str(row.get("time", ""))
                    st.write(f"{nm} (`{sid}`) - 남은 {rem}회")
                    st.caption(f"승인 시각: {ap}")

        if not failed_log_requests.empty:
            st.markdown("### 로그 저장 재시도")
            for _, row in failed_log_requests.iterrows():
                req_id = str(row.get("request_id", ""))
                nm = str(row.get("student_name", "원생"))
                sid = str(row.get("student_id", ""))
                with st.container(border=True):
                    st.write(f"{nm} (`{sid}`)")
                    if st.button("로그 재시도", key=f"retry_log_{req_id}", use_container_width=True):
                        ok, msg = retry_failed_log_request(req_id)
                        if ok:
                            st.success(msg)
                            st.session_state["attendance_log_error"] = ""
                        else:
                            st.error(msg)
                        st.rerun()

        if st.session_state.get("attendance_log_error"):
            st.error(st.session_state["attendance_log_error"])
            if st.button("로그 에러 닫기", key="dismiss_attendance_error"):
                st.session_state["attendance_log_error"] = ""
                st.rerun()

        prev_pending_count = int(st.session_state.get("owner_prev_pending_count", 0))
        if pending_count > prev_pending_count and pending_count > 0:
            components.html(
                """
                <script>
                    (function () {
                        try {
                            const Ctx = window.AudioContext || window.webkitAudioContext;
                            if (!Ctx) return;
                            const ctx = new Ctx();
                            const osc = ctx.createOscillator();
                            const gain = ctx.createGain();
                            osc.type = "sine";
                            osc.frequency.value = 880;
                            gain.gain.value = 0.08;
                            osc.connect(gain);
                            gain.connect(ctx.destination);
                            osc.start();
                            setTimeout(() => { osc.stop(); ctx.close(); }, 180);
                        } catch (e) {}
                    })();
                </script>
                """,
                height=0,
            )
        st.session_state["owner_prev_pending_count"] = pending_count

    # 모바일에서 2열 → 세로 스택(CSS :has + 아래 JS). 앵커 바로 다음 형제가 메인 stHorizontalBlock 래퍼.
    st.markdown(
        '<span class="owner-main-split-anchor" aria-hidden="true"></span>',
        unsafe_allow_html=True,
    )
    left_col, right_col = st.columns([1, 1], gap="large")

    # 메뉴 버튼이 먼저 실행되어야 같은 실행에서 오른쪽 패널이 갱신됨 (이전엔 selected_idx가 먼저 잡혀 두 번 눌러야 했음)
    with left_col:
        with st.expander("운영 대시보드", expanded=True):
            render_owner_menu_grid(
                st.session_state.get("owner_login_at", ""),
                active_idx=int(st.session_state.get("owner_menu_index", 0)),
            )
            # 2분 자동 갱신(카드 영역)
            if hasattr(st, "fragment"):
                @st.fragment(run_every="120s")
                def auto_refresh_owner_cards():
                    render_dashboard_cards()
                auto_refresh_owner_cards()
            else:
                render_dashboard_cards()

    selected_idx = int(st.session_state.get("owner_menu_index", 0))
    if selected_idx < 0 or selected_idx > 3:
        selected_idx = 0
    st.query_params["owner_menu_idx"] = str(selected_idx)

    prev_idx = int(st.session_state.get("owner_prev_menu_index", selected_idx))
    menu_changed = selected_idx != prev_idx
    st.session_state["owner_prev_menu_index"] = selected_idx

    with right_col:
        with st.container(border=True):
            if selected_idx == 0:
                run_marketing_ui()
            elif selected_idx == 1:
                run_student_ui()
            elif selected_idx == 2:
                run_finance_ui()
            elif selected_idx == 3:
                run_curriculum_ui()

    # 두 열 아래에 두어 2열 레이아웃이 깨지지 않게 함
    if menu_changed:
        st.markdown(
            """
            <style>
            [data-testid="stAppViewContainer"] .block-container {
                animation: slideFromRight 280ms ease-out;
            }
            @keyframes slideFromRight {
                from {
                    transform: translateX(22px);
                    opacity: 0.75;
                }
                to {
                    transform: translateX(0);
                    opacity: 1;
                }
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

    components.html(
        f"""
        <script>
            (function () {{
                let startX = null;
                const currentIdx = {selected_idx};
                const maxIdx = 3;
                function updateIdx(nextIdx) {{
                    const url = new URL(window.parent.location.href);
                    url.searchParams.set("owner_menu_idx", String(nextIdx));
                    window.parent.location.href = url.toString();
                }}
                window.addEventListener("touchstart", function(e) {{
                    if (e.touches && e.touches.length > 0) startX = e.touches[0].clientX;
                }}, {{ passive: true }});
                window.addEventListener("touchend", function(e) {{
                    if (startX === null) return;
                    const endX = (e.changedTouches && e.changedTouches.length > 0) ? e.changedTouches[0].clientX : startX;
                    const delta = endX - startX;
                    if (delta < -60 && currentIdx < maxIdx) updateIdx(currentIdx + 1);   // left swipe
                    if (delta > 60 && currentIdx > 0) updateIdx(currentIdx - 1);         // right swipe
                    startX = null;
                }}, {{ passive: true }});

                function findOwnerMainHorizontal(doc) {{
                    const anchor = doc.querySelector("span.owner-main-split-anchor");
                    if (!anchor) return null;
                    const ec = anchor.closest('[data-testid="stElementContainer"]');
                    if (!ec || !ec.nextElementSibling) return null;
                    return ec.nextElementSibling.querySelector('[data-testid="stHorizontalBlock"]');
                }}
                function ownerMainSplitApply() {{
                    let doc = document;
                    let win = window;
                    try {{
                        if (window.parent && window.parent.document) {{
                            const pdoc = window.parent.document;
                            if (pdoc.querySelector("span.owner-main-split-anchor")) {{
                                doc = pdoc;
                                win = window.parent;
                            }}
                        }}
                    }} catch (e) {{}}
                    const hb = findOwnerMainHorizontal(doc);
                    if (!hb) return;
                    const narrow = win.innerWidth <= 900;
                    hb.style.flexDirection = narrow ? "column" : "row";
                    hb.style.alignItems = narrow ? "stretch" : "";
                    const gap = narrow ? "0.75rem" : "";
                    hb.style.gap = gap;
                    const kids = hb.children;
                    for (let i = 0; i < kids.length; i++) {{
                        const c = kids[i];
                        if (narrow) {{
                            c.style.width = "100%";
                            c.style.maxWidth = "100%";
                            c.style.minWidth = "0";
                            c.style.flex = "1 1 auto";
                        }} else {{
                            c.style.width = "";
                            c.style.maxWidth = "";
                            c.style.minWidth = "";
                            c.style.flex = "";
                        }}
                    }}
                }}
                ownerMainSplitApply();
                try {{
                    (window.parent || window).addEventListener("resize", ownerMainSplitApply);
                }} catch (e) {{
                    window.addEventListener("resize", ownerMainSplitApply);
                }}
            }})();
        </script>
        """,
        height=0,
    )

    st.markdown("<br><br>", unsafe_allow_html=True)
    if st.button("로그아웃", use_container_width=True, key="owner_logout_bottom"):
        st.session_state["owner_authenticated"] = False
        st.session_state["entry_mode"] = None
        st.session_state["intro_done"] = False
        st.session_state["owner_login_at"] = ""
        st.query_params.pop("mode", None)
        st.query_params.pop("owner_login_at", None)
        st.query_params.pop("owner_menu_idx", None)
        st.query_params.pop("skip_intro", None)
        st.rerun()
    st.caption("Developed by 엔지니어 남편 v1.5")


if st.session_state.get('intro_done'):
    try:
        from core.sheet_backup import maybe_run_daily_sheet_backup

        maybe_run_daily_sheet_backup()
    except Exception:
        pass
    init_entry_state()
    sync_owner_session_from_query()
    # 원장 세션 1시간 만료 처리
    if st.session_state.get("owner_authenticated") and not is_owner_session_valid():
        st.session_state["owner_authenticated"] = False
        st.session_state["owner_login_at"] = ""
        st.query_params.pop("owner_login_at", None)
        if st.session_state.get("entry_mode") == "owner":
            st.warning("원장 로그인 유지 시간이 만료되었습니다. 다시 로그인해주세요.")

    mode = st.session_state.get("entry_mode")
    if mode is None:
        render_intro_branch()
    elif mode == "student":
        st.query_params["mode"] = "student"
        render_student_entry()
    elif mode == "owner":
        st.query_params["mode"] = "owner"
        if st.session_state.get("owner_authenticated"):
            render_owner_menu()
        else:
            render_owner_auth()

# --- 4. 푸터 ---
if st.session_state.get('intro_done'):
    st.markdown("---")
    fc1, fc2 = st.columns([3, 1], vertical_alignment="center")
    with fc1:
        st.caption("© 2026 작업실 그리다가. All rights reserved.")
    with fc2:
        _gd_connected = drive_oauth.has_valid_session_credentials()
        if st.button(
            "백업하기",
            key="manual_sheet_backup",
            help="스프레드시트 전체 → Drive에 .json.gz 저장. 마케팅에서 Google 드라이브 연결 후 사용.",
            disabled=not _gd_connected,
        ):
            from core.sheet_backup import run_sheet_backup_now

            ok, msg = run_sheet_backup_now()
            if ok:
                st.success(f"백업 완료: `{msg}`")
            else:
                st.error(f"백업 실패: {msg}")