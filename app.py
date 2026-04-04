import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime, timedelta
import time
import base64
from pathlib import Path
import pandas as pd
from core.perf import perf_log, perf_enabled, perf_recent_top

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

import core.students as _students


def _stub_cancel_pending_attendance_request(student_id):
    return False, "요청 취소 기능을 불러오지 못했습니다. 앱을 새로고침해 주세요."


def _stub_reject_attendance_request(request_id):
    return False, "요청 거절 기능을 불러오지 못했습니다. 앱을 새로고침해 주세요."


run_student_ui = getattr(_students, "run_student_ui", _noop)
get_recent_attendance_logs = getattr(_students, "get_recent_attendance_logs", lambda *args, **kwargs: [])
create_attendance_request = getattr(
    _students,
    "create_attendance_request",
    lambda *args, **kwargs: (False, "출석 요청 기능을 불러오지 못했습니다."),
)
cancel_pending_attendance_request = getattr(
    _students,
    "cancel_pending_attendance_request",
    _stub_cancel_pending_attendance_request,
)
get_pending_attendance_requests = getattr(
    _students,
    "get_pending_attendance_requests",
    lambda *args, **kwargs: pd.DataFrame(),
)
approve_attendance_request = getattr(
    _students,
    "approve_attendance_request",
    lambda *args, **kwargs: (False, "승인 기능을 불러오지 못했습니다."),
)
approve_all_pending_requests = getattr(
    _students,
    "approve_all_pending_requests",
    lambda *args, **kwargs: (False, "전체 승인 기능을 불러오지 못했습니다."),
)
reject_attendance_request = getattr(
    _students,
    "reject_attendance_request",
    _stub_reject_attendance_request,
)
get_failed_log_requests = getattr(
    _students,
    "get_failed_log_requests",
    lambda *args, **kwargs: pd.DataFrame(),
)
get_owner_dashboard_data = getattr(
    _students,
    "get_owner_dashboard_data",
    lambda *args, **kwargs: (
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
    ),
)
retry_failed_log_request = getattr(
    _students,
    "retry_failed_log_request",
    lambda *args, **kwargs: (False, "로그 재시도 기능을 불러오지 못했습니다."),
)
from core.schedule import get_today_schedule_by_student
from core.fullscreen_view import layout_for_fullscreen_query, try_render_fullscreen_tables

_t_boot0 = time.perf_counter()

# --- 1. 페이지 설정 ---
st.set_page_config(
    page_title="작업실 그리다가 OS",
    page_icon="🎨",
    layout=layout_for_fullscreen_query(),
)
perf_log("boot.set_page_config", (time.perf_counter() - _t_boot0) * 1000.0)
_inject_chrome = getattr(_ui, "inject_global_streamlit_chrome_hide", None)
if callable(_inject_chrome):
    _t = time.perf_counter()
    _inject_chrome()
    perf_log("boot.inject_chrome_hide", (time.perf_counter() - _t) * 1000.0)
else:
    _css = getattr(_ui, "STREAMLIT_CHROME_HIDE_CSS", None)
    if _css:
        _t = time.perf_counter()
        st.markdown(f"<style>{_css}</style>", unsafe_allow_html=True)
        perf_log("boot.inject_css_hide", (time.perf_counter() - _t) * 1000.0)
    else:
        _t = time.perf_counter()
        st.markdown(
            '<style>[data-testid="stStatusWidget"]{display:none!important;}</style>',
            unsafe_allow_html=True,
        )
        perf_log("boot.inject_css_hide_fallback", (time.perf_counter() - _t) * 1000.0)

# Google Drive OAuth 콜백 (?code= / ?state=) — 인트로보다 먼저 처리
from core import drive_oauth

_t = time.perf_counter()
drive_oauth.try_finish_google_drive_oauth()
perf_log("boot.try_finish_drive_oauth", (time.perf_counter() - _t) * 1000.0)

# --- 2. 인트로 화면(스플래시) 제거 ---
# 첫 화면(원생용/선생님 선택) 안에서 로고+문구를 보여주므로, 별도 인트로 재생은 하지 않음.
_t = time.perf_counter()
qp_mode_for_intro = str(st.query_params.get("mode", ""))
perf_log("boot.read_query_params_mode", (time.perf_counter() - _t) * 1000.0)
st.session_state["intro_done"] = True

def init_entry_state():
    defaults = {
        "entry_mode": None,
        "owner_authenticated": False,
        "owner_auth_method": "",
        "student_id_input": "",
        "student_message": "",
        "student_message_type": "",
        "attendance_log_error": "",
        "owner_prev_pending_count": 0,
        "owner_login_at": "",
        "owner_menu_index": 0,
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
        if not st.session_state.get("owner_auth_method"):
            st.session_state["owner_auth_method"] = "password"

    try:
        qp_menu_idx = int(str(st.query_params.get("owner_menu_idx", "0")))
        if 0 <= qp_menu_idx <= 3:
            st.session_state["owner_menu_index"] = qp_menu_idx
    except Exception:
        pass


def render_intro_branch():
    # 첫 화면에서도 캔버스 배경/폰트 테마 적용(기존 스플래시 인트로에서 하던 역할)
    try:
        _set = getattr(_ui, "set_custom_style", None)
        if callable(_set):
            _set()
    except Exception:
        pass

    # 이미지가 있을 때: 뒤 레이어 없음 → PNG 투명 부분이 앱 캔버스 배경을 비춤 (베이지 박스 금지)
    student_fallback = "linear-gradient(120deg, #C09066 0%, #B47F57 55%, #A86E48 100%)"
    teacher_fallback = "linear-gradient(120deg, #9E6B43 0%, #8E5F3D 58%, #7E5233 100%)"
    _intro_bg_cache_key = "_intro_entry_button_bg_b64"
    if _intro_bg_cache_key in st.session_state:
        student_bg = st.session_state[_intro_bg_cache_key]["student"]
        teacher_bg = st.session_state[_intro_bg_cache_key]["teacher"]
    else:
        student_bg = student_fallback
        teacher_bg = teacher_fallback
        try:
            root = Path(__file__).resolve().parent
            assets = root / "assets"
            for s_name in ("student_bt.png", "student_bt.PNG"):
                s_path = assets / s_name
                if s_path.exists():
                    s_b64 = base64.b64encode(s_path.read_bytes()).decode("ascii")
                    student_bg = f"url('data:image/png;base64,{s_b64}') center center / cover no-repeat"
                    break
            for t_name in ("teacher_bt.png", "teacher_bt.PNG"):
                t_path = assets / t_name
                if t_path.exists():
                    t_b64 = base64.b64encode(t_path.read_bytes()).decode("ascii")
                    teacher_bg = f"url('data:image/png;base64,{t_b64}') center center / cover no-repeat"
                    break
        except Exception:
            pass
        st.session_state[_intro_bg_cache_key] = {"student": student_bg, "teacher": teacher_bg}

    css = """
        <style>
        .st-key-intro-center-wrap {
            min-height: calc(100dvh - 4.2rem) !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            width: 100% !important;
            padding-top: 1.1rem !important; /* 전체를 살짝 아래로 */
        }
        .st-key-intro-center-wrap > div[data-testid="stVerticalBlock"] {
            width: min(560px, 96vw) !important;
            margin: 0 auto !important;
            transform: translateY(10px);
        }
        /* intro 내부 요소 가운데 정렬 */
        .st-key-intro-center-wrap [data-testid="stImage"] {
            display: flex !important;
            justify-content: center !important;
        }
        .st-key-intro-center-wrap [data-testid="stImage"] > div {
            margin-left: auto !important;
            margin-right: auto !important;
        }
        @media (max-width: 768px) {
            .st-key-intro-center-wrap {
                min-height: calc(100dvh - 3.2rem) !important;
                padding-top: 0.9rem !important;
            }
            .st-key-intro-center-wrap > div[data-testid="stVerticalBlock"] {
                width: min(520px, 96vw) !important;
                transform: translateY(8px);
            }
        }
        /* 로고는 st.image로 렌더링 — 깨진 아이콘(가짜 img) 방지 */
        [data-testid="stImage"] img {
            filter: drop-shadow(0 4px 10px rgba(50, 34, 22, 0.18));
        }
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
        /* 입장 버튼: 래퍼까지 투명 — 스트림릿 기본 박스색이 붓 뒤로 비치지 않게 */
        div[data-testid="stButton"].entry-btn-shell {
            background: transparent !important;
            background-color: transparent !important;
            border: none !important;
            box-shadow: none !important;
            padding: 0 !important;
        }
        div[data-testid="stButton"].entry-btn-shell > div {
            background: transparent !important;
            background-color: transparent !important;
            box-shadow: none !important;
        }
        div[data-testid="stButton"] > button.entry-student-btn,
        div[data-testid="stButton"] > button.entry-teacher-btn {
            position: relative !important;
            border: none !important;
            outline: none !important;
            box-shadow: none !important;
            -webkit-appearance: none !important;
            appearance: none !important;
            padding: 0 !important;
            margin: 0 !important;
            width: 100% !important;
            max-width: 100% !important;
            box-sizing: border-box !important;
            /* 두 버튼 동일 박스(현재 대비 1/2) */
            min-height: 38px !important;
            height: 38px !important;
            max-height: 38px !important;
            border-radius: 12px !important;
            /* hidden 켜면 투명 영역이 잘려 캔버스가 안 보일 수 있음 */
            overflow: visible !important;
            transition: transform 120ms ease, filter 120ms ease !important;
            box-sizing: border-box !important;
            background-color: transparent !important;
        }
        div[data-testid="stButton"] > button.entry-student-btn:focus-visible,
        div[data-testid="stButton"] > button.entry-teacher-btn:focus-visible {
            outline: 2px solid #B88962 !important;
            outline-offset: 3px !important;
        }
        div[data-testid="stButton"] > button.entry-student-btn > div,
        div[data-testid="stButton"] > button.entry-teacher-btn > div {
            position: absolute !important;
            inset: 0 !important;
            border: none !important;
            box-shadow: none !important;
            padding: 0 0.75rem !important;
            margin: 0 !important;
            width: 100% !important;
            height: 100% !important;
            min-width: 0 !important;
            box-sizing: border-box !important;
            display: flex !important;
            flex-direction: column !important;
            justify-content: center !important;
            align-items: center !important;
            /* 배경 이미지는 button에만 — 여기서 어두운 막 깔면 또 ‘뒷판’처럼 보일 수 있음 */
            background: transparent !important;
            pointer-events: none !important;
        }
        div[data-testid="stButton"] > button.entry-student-btn p,
        div[data-testid="stButton"] > button.entry-student-btn span,
        div[data-testid="stButton"] > button.entry-teacher-btn p,
        div[data-testid="stButton"] > button.entry-teacher-btn span {
            pointer-events: none !important;
            position: relative !important;
            width: auto !important;
            max-width: 100% !important;
            height: auto !important;
            margin: 0 !important;
            padding: 0 !important;
            overflow: visible !important;
            clip: auto !important;
            white-space: normal !important;
            border: 0 !important;
            color: #FFF8F0 !important;
            font-size: 1.02rem !important;
            font-weight: 800 !important;
            line-height: 1.25 !important;
            letter-spacing: -0.02em !important;
            text-align: center !important;
            text-shadow: 0 1px 4px rgba(24, 14, 8, 0.75), 0 0 1px rgba(24, 14, 8, 0.5) !important;
        }
        div[data-testid="stButton"] > button.entry-student-btn {
            background: __STUDENT_BG__ !important;
            background-color: transparent !important;
        }
        div[data-testid="stButton"] > button.entry-teacher-btn {
            background: __TEACHER_BG__ !important;
            background-color: transparent !important;
        }
        div[data-testid="stButton"] > button.entry-student-btn:active,
        div[data-testid="stButton"] > button.entry-teacher-btn:active {
            transform: translateY(2px) scale(0.988) !important;
            filter: brightness(0.93) !important;
        }
        </style>
    """
    st.markdown(
        css.replace("__STUDENT_BG__", student_bg).replace("__TEACHER_BG__", teacher_bg),
        unsafe_allow_html=True,
    )
    with st.container(key="intro-center-wrap"):
        # 로고 + 태그라인 (항상 중앙)
        try:
            st.image("intro/logo.jpg", width=260)
        except Exception:
            pass
        st.markdown(
            '<p class="intro-tagline">나만의 채색으로 채우는 시간</p>',
            unsafe_allow_html=True,
        )
        st.markdown(
            """
            <div class="home-welcome-card">
                <p class="home-welcome-title">작업실 그리다가</p>
                <p class="home-welcome-sub">오늘도 반가워요. 아래에서 사용자 유형을 선택해 주세요.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("원생용", use_container_width=True, key="entry_student"):
            st.session_state["entry_mode"] = "student"
            st.query_params["mode"] = "student"
            st.query_params.pop("owner_login_at", None)
            st.session_state["student_id_input"] = ""
            st.session_state["student_message"] = ""
            st.session_state["student_message_type"] = ""
            st.rerun()
        if st.button("선생님", use_container_width=True, key="entry_owner"):
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
                const shell = b.closest('div[data-testid="stButton"]');
                if (t.includes("원생용")) {
                  b.classList.add("entry-student-btn");
                  if (shell) shell.classList.add("entry-btn-shell");
                }
                if (t.includes("선생님")) {
                  b.classList.add("entry-teacher-btn");
                  if (shell) shell.classList.add("entry-btn-shell");
                }
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
    st.subheader("🎓 출석 하기")
    st.caption("ID를 입력하면 오늘 수업 1 회가 차감됩니다.")
    st.markdown(
        """
        <style>
        /* 원생 출석 화면에서는 버튼 패딩을 줄여 3열 키패드 고정 */
        div[data-testid="stButton"] > button {
            width: 100% !important;
            box-sizing: border-box !important;
            padding: 0.3rem 0.14rem !important;
            min-height: 107px !important;
            font-size: 1.57rem !important;
            font-weight: 700 !important;
        }
        /* Streamlit 모바일 자동 스택 방지: 키패드 3열 강제 유지 */
        div[data-testid="stHorizontalBlock"] {
            display: flex !important;
            flex-direction: row !important;
            flex-wrap: nowrap !important;
            gap: 0.25rem !important;
        }
        div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"],
        div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
            flex: 0 0 33.333% !important;
            min-width: 0 !important;
            max-width: 33.33% !important;
            width: 33.33% !important;
        }
        /* 세로 모드(좁은 폭)에서 추가 축소 */
        @media (max-width: 480px) {
            div[data-testid="stButton"] > button {
                padding: 0.21rem 0.05rem !important;
                min-height: 91px !important;
                font-size: 1.33rem !important;
                font-weight: 700 !important;
            }
            div[data-testid="stHorizontalBlock"] {
                gap: 0.14rem !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    current_id = st.session_state.get("student_id_input", "")
    st.markdown(
        f"<div style='border:1px solid #d8c3ac;border-radius:8px;padding:6px 10px;background:#fff8f0;font-weight:600;'>"
        f"{current_id if current_id else 'ID를 입력하세요'}</div>",
        unsafe_allow_html=True,
    )
    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
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

    action_col1, action_col2 = st.columns(2, gap="small")
    with action_col1:
        if st.button("✅ 확인", type="primary", use_container_width=True):
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
    with action_col2:
        if st.button("🛑 요청 취소", use_container_width=True, key="cancel_attendance_request"):
            student_id = st.session_state.get("student_id_input", "").strip()
            if not student_id:
                st.session_state["student_message"] = "취소하려면 ID를 먼저 입력해주세요."
                st.session_state["student_message_type"] = "error"
                st.rerun()
            ok, msg = cancel_pending_attendance_request(student_id)
            st.session_state["student_message"] = str(msg)
            st.session_state["student_message_type"] = "success" if ok else "error"
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
    oauth_ready = drive_oauth.oauth_google_drive_configured()
    if oauth_ready:
        # Google OAuth 완료 직후 자동으로 원장 세션 진입
        if drive_oauth.has_valid_session_credentials():
            st.session_state["owner_authenticated"] = True
            st.session_state["owner_auth_method"] = "google"
            if not st.session_state.get("owner_login_at"):
                st.session_state["owner_login_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            st.query_params["mode"] = "owner"
            st.query_params["owner_login_at"] = st.session_state["owner_login_at"]
            st.rerun()

        if drive_oauth.has_valid_session_credentials():
            if st.button("Google 계정으로 로그인하기", use_container_width=True, key="owner_google_login"):
                st.session_state["owner_authenticated"] = True
                st.session_state["owner_auth_method"] = "google"
                st.session_state["owner_login_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                st.query_params["mode"] = "owner"
                st.query_params["owner_login_at"] = st.session_state["owner_login_at"]
                st.rerun()
        else:
            try:
                cfg = drive_oauth._load_oauth_secrets()  # 내부 helper 재사용
                auth_url = drive_oauth.build_google_drive_authorization_url(cfg) if cfg else ""
            except Exception:
                auth_url = ""
            if auth_url:
                st.link_button("Google 계정으로 로그인하기", auth_url, use_container_width=True)
            else:
                st.error("Google OAuth 설정을 확인해 주세요.")

    owner_password = get_owner_password()
    if owner_password:
        with st.expander("비밀번호로 로그인(예비 수단)", expanded=not oauth_ready):
            with st.form("owner_login_form", clear_on_submit=True):
                pwd = st.text_input("비밀번호", type="password", placeholder="원장 비밀번호 입력")
                submitted = st.form_submit_button("로그인", use_container_width=True)
                if submitted:
                    if pwd == owner_password:
                        st.session_state["owner_authenticated"] = True
                        st.session_state["owner_auth_method"] = "password"
                        st.session_state["owner_login_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        st.query_params["mode"] = "owner"
                        st.query_params["owner_login_at"] = st.session_state["owner_login_at"]
                        st.rerun()
                    st.error("비밀번호가 올바르지 않습니다.")
    elif not oauth_ready:
        st.warning("원장 인증 수단이 없습니다. Google OAuth 또는 `owner_password` 설정이 필요합니다.")

    st.markdown("---")
    if st.button("⬅️ 처음으로", use_container_width=True, key="back_from_owner"):
        st.session_state["entry_mode"] = None
        st.session_state["intro_done"] = False
        st.session_state["owner_authenticated"] = False
        st.session_state["owner_auth_method"] = ""
        st.session_state["owner_login_at"] = ""
        st.query_params.pop("mode", None)
        st.query_params.pop("owner_login_at", None)
        st.query_params.pop("skip_intro", None)
        st.rerun()


def render_owner_menu():
    _t_owner = time.perf_counter()
    auto_backup_enabled = False
    try:
        if "AUTO_DAILY_BACKUP" in st.secrets:
            auto_backup_enabled = str(st.secrets["AUTO_DAILY_BACKUP"]).strip().lower() in ("1", "true", "yes", "on")
    except Exception:
        auto_backup_enabled = False
    if auto_backup_enabled and not st.session_state.get("_owner_daily_backup_checked_once"):
        try:
            from core.sheet_backup import maybe_run_daily_sheet_backup

            maybe_run_daily_sheet_backup()
        except Exception:
            pass
        st.session_state["_owner_daily_backup_checked_once"] = True

    # 메뉴 전환 시 lazy import 비용이 한 박자처럼 느껴지지 않도록, 원장 화면에서 1회만 선로딩
    if not st.session_state.get("_owner_feature_modules_preloaded"):
        try:
            import core.marketer  # noqa: F401
            import core.finance  # noqa: F401
            import core.curriculum  # noqa: F401
        except Exception:
            pass
        st.session_state["_owner_feature_modules_preloaded"] = True

    apply_owner_dashboard_style()
    render_owner_brand_header()

    # 새로고침 진입 시 승인 대기가 있으면 상단 확인창 표시
    if not st.session_state.get("owner_pending_prompt_closed", False):
        pending_df = get_pending_attendance_requests(limit=500, force_refresh=False)
        pending_count = 0 if pending_df is None else int(len(pending_df))
        if pending_count > 0:
            with st.container(border=True):
                st.warning(f"승인 대기 {pending_count}건이 있습니다. 승인하러 가시겠습니까?")
                p1, p2 = st.columns(2, gap="small")
                with p1:
                    if st.button("승인하러 가기", use_container_width=True, key="owner_pending_prompt_yes"):
                        st.session_state["owner_menu_index"] = 1
                        st.session_state["open_attendance_manager_once"] = True
                        st.session_state["owner_pending_prompt_closed"] = True
                        st.query_params["owner_menu_idx"] = "1"
                        st.rerun()
                with p2:
                    if st.button("아니요", use_container_width=True, key="owner_pending_prompt_no"):
                        st.session_state["owner_pending_prompt_closed"] = True
                        st.rerun()

    def render_dashboard_cards():
        _t_cards = time.perf_counter()
        perf_log("app.render_dashboard_cards", (time.perf_counter() - _t_cards) * 1000.0)

    # 주메뉴만 border 박스(높이 슬림). fragment는 박스 밖에서 돌려 테두리 안 빈 여백이 커지지 않게 함.
    with st.container(border=True, key="owner_menu_bar"):
        render_owner_menu_grid(
            st.session_state.get("owner_login_at", ""),
            active_idx=int(st.session_state.get("owner_menu_index", 0)),
        )
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

    with st.container(border=True):
        if selected_idx == 0:
            from core.marketer import run_marketing_ui

            run_marketing_ui()
        elif selected_idx == 1:
            run_student_ui()
        elif selected_idx == 2:
            from core.finance import run_finance_ui

            run_finance_ui()
        elif selected_idx == 3:
            from core.curriculum import run_curriculum_ui

            run_curriculum_ui()

    st.markdown("<br><br>", unsafe_allow_html=True)
    if st.button("로그아웃", use_container_width=True, key="owner_logout_bottom"):
        st.session_state["owner_authenticated"] = False
        st.session_state["owner_auth_method"] = ""
        st.session_state["entry_mode"] = None
        st.session_state["intro_done"] = False
        st.session_state["owner_login_at"] = ""
        st.query_params.pop("mode", None)
        st.query_params.pop("owner_login_at", None)
        st.query_params.pop("owner_menu_idx", None)
        st.query_params.pop("skip_intro", None)
        st.rerun()
    st.caption("Developed by 엔지니어 남편 v1.5")
    perf_log("app.render_owner_menu", (time.perf_counter() - _t_owner) * 1000.0)


if st.session_state.get('intro_done'):
    _t = time.perf_counter()
    init_entry_state()
    perf_log("boot.init_entry_state", (time.perf_counter() - _t) * 1000.0)
    _t = time.perf_counter()
    sync_owner_session_from_query()
    perf_log("boot.sync_owner_session", (time.perf_counter() - _t) * 1000.0)
    # F5 복원: owner 모드 + Google 세션 유효하면 원장 세션을 먼저 복구
    try:
        _t = time.perf_counter()
        if (
            str(st.query_params.get("mode", "")) == "owner"
            and drive_oauth.oauth_google_drive_configured()
            and drive_oauth.has_valid_session_credentials()
            and not st.session_state.get("owner_authenticated")
        ):
            st.session_state["owner_authenticated"] = True
            st.session_state["owner_auth_method"] = "google"
            if not st.session_state.get("owner_login_at"):
                st.session_state["owner_login_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            st.query_params["owner_login_at"] = st.session_state["owner_login_at"]
        perf_log("boot.owner_google_session_restore", (time.perf_counter() - _t) * 1000.0)
    except Exception:
        pass
    # 원장 세션 1시간 만료 처리
    if (
        st.session_state.get("owner_authenticated")
        and st.session_state.get("owner_auth_method") != "google"
        and not is_owner_session_valid()
    ):
        st.session_state["owner_authenticated"] = False
        st.session_state["owner_auth_method"] = ""
        st.session_state["owner_login_at"] = ""
        st.query_params.pop("owner_login_at", None)
        if st.session_state.get("entry_mode") == "owner":
            st.warning("원장 로그인 유지 시간이 만료되었습니다. 다시 로그인해주세요.")
    # Google 기반 원장 인증: OAuth 세션이 끊기면 다시 로그인
    if (
        st.session_state.get("owner_authenticated")
        and st.session_state.get("owner_auth_method") == "google"
        and drive_oauth.oauth_google_drive_configured()
        and not drive_oauth.has_valid_session_credentials()
    ):
        st.session_state["owner_authenticated"] = False
        st.session_state["owner_auth_method"] = ""
        st.session_state["owner_login_at"] = ""
        st.query_params.pop("owner_login_at", None)
        if st.session_state.get("entry_mode") == "owner":
            st.warning("Google 로그인 세션이 만료되었습니다. 다시 로그인해주세요.")

    # 표 전용 URL(?fullscreen=…)은 원장 모드로만 처리하고, 본문은 여기서 끝(st.stop)
    try:
        _fs_qp = str(st.query_params.get("fullscreen", "") or "").strip()
    except Exception:
        _fs_qp = ""
    if _fs_qp in ("schedule_month", "finance_expenses"):
        st.session_state["entry_mode"] = "owner"
        try:
            st.query_params["mode"] = "owner"
        except Exception:
            pass
    if try_render_fullscreen_tables():
        st.stop()

    mode = st.session_state.get("entry_mode")
    if mode is None:
        _t = time.perf_counter()
        render_intro_branch()
        perf_log("boot.render_intro_branch", (time.perf_counter() - _t) * 1000.0)
    elif mode == "student":
        st.query_params["mode"] = "student"
        _t = time.perf_counter()
        render_student_entry()
        perf_log("boot.render_student_entry", (time.perf_counter() - _t) * 1000.0)
    elif mode == "owner":
        st.query_params["mode"] = "owner"
        if st.session_state.get("owner_authenticated"):
            _t = time.perf_counter()
            render_owner_menu()
            perf_log("boot.render_owner_menu", (time.perf_counter() - _t) * 1000.0)
        else:
            _t = time.perf_counter()
            render_owner_auth()
            perf_log("boot.render_owner_auth", (time.perf_counter() - _t) * 1000.0)

    perf_log("boot.total", (time.perf_counter() - _t_boot0) * 1000.0)

# --- 4. 푸터 ---
if st.session_state.get('intro_done'):
    st.markdown("---")
    st.caption("© 2026 작업실 그리다가. All rights reserved.")

    if perf_enabled():
        with st.expander("⚡ 성능 로그(상위 10)"):
            top = perf_recent_top(10)
            if top:
                for i, row in enumerate(top, start=1):
                    st.caption(f"{i}. {row['label']} - {row['ms']:.1f}ms")
            else:
                st.caption("아직 수집된 로그가 없습니다.")