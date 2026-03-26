import streamlit as st
import streamlit.components.v1 as components
import time
import base64
import json
from pathlib import Path
from PIL import Image
# core/ui_style.py (또는 ui.py)

# 신·구 Streamlit 모두: Running / 토스트형 스크립트 알림 / Deploy 등 (앱의 st.toast도 같이 숨겨질 수 있음)
STREAMLIT_CHROME_HIDE_CSS = """
/* 구버전: 상단 Running 배지 */
[data-testid="stStatusWidget"],
div[data-testid="stStatusWidget"] {
    display: none !important;
    visibility: hidden !important;
    height: 0 !important;
    overflow: hidden !important;
}
/* 신버전: 스크립트/캐시 알림이 토스트 영역으로 옮겨진 경우 */
[data-testid="toastContainer"],
[data-testid="stToast"],
#toast-container {
    display: none !important;
    visibility: hidden !important;
}
/* Streamlit Cloud */
[data-testid="stDeployButton"] {
    display: none !important;
}
/* 헤더 장식 줄 진행바 */
[data-testid="stDecoration"] [role="progressbar"] {
    opacity: 0 !important;
    height: 0 !important;
}
"""


def inject_global_streamlit_chrome_hide():
    """상단 Running…·토스트형 알림·Deploy 등 기본 크롬 UI 숨김. (스크립트는 그대로 실행됨)"""
    st.markdown(
        f"<style>{STREAMLIT_CHROME_HIDE_CSS}</style>",
        unsafe_allow_html=True,
    )


def _asset_css_bg(asset_name: str, fallback: str) -> str:
    """assets 이미지를 CSS background 값으로 변환 (없으면 fallback)."""
    try:
        p = Path(__file__).resolve().parents[1] / "assets" / asset_name
        if p.exists():
            b64 = base64.b64encode(p.read_bytes()).decode("ascii")
            return f"url('data:image/png;base64,{b64}') center/cover no-repeat"
    except Exception:
        pass
    return fallback


@st.cache_data(show_spinner=False)
def _menu_brush_slices():
    """주메뉴용 붓터치 이미지 4개를 source 이미지에서 자동 분할."""
    try:
        root = Path(__file__).resolve().parents[1] / "assets"
        src = root / "brush_strokes_source.png"
        if not src.exists():
            src = root / "brush_strokes.png"
        if not src.exists():
            return []

        img = Image.open(src).convert("RGBA")
        w, h = img.size

        # 원본(6줄 내외)에서 4개를 선택해 사용
        bands = 6
        band_h = max(1, h // bands)
        pick = [0, 1, 3, 5]
        out = []
        x0, x1 = int(w * 0.10), int(w * 0.90)
        for i in pick:
            y0 = int(i * band_h + band_h * 0.15)
            y1 = int((i + 1) * band_h - band_h * 0.15)
            y0 = max(0, min(y0, h - 1))
            y1 = max(y0 + 1, min(y1, h))
            out.append(img.crop((x0, y0, x1, y1)))
        return out
    except Exception:
        return []


def apply_custom_style():
    """Streamlit의 기본 헤더, 푸터, 메뉴를 숨기는 커스텀 CSS"""
    hide_st_style = """
                <style>
                #MainMenu {visibility: hidden;}
                footer {visibility: hidden;}
                header {visibility: hidden;}
                /* 모바일에서 상단 여백이 너무 많을 때 조절 */
                .block-container {
                    padding-top: 2rem;
                    padding-bottom: 0rem;
                }
                </style>
                """
    st.markdown(hide_st_style, unsafe_allow_html=True) 
    
def set_custom_style():
    apply_custom_style()
    """화실 전용 감성 테마 CSS 주입"""
    canvas_bg = _asset_css_bg("canvas_bg.png", "#FCF9F2")
    css = """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Nanum+Myeongjo:wght@400;700&display=swap');
        @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');

        /* 전체 기본 폰트 */
        html, body, [class*="css"], .stApp {
            font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans KR', sans-serif !important;
            color: #4A4A4A;
        }

        /* 일반 제목/헤더도 Pretendard로 통일 (브랜드 타이틀만 별도 클래스에서 오버라이드) */
        h1, h2, h3, .stHeader, [data-testid="stHeader"] {
            font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans KR', sans-serif !important;
            color: #4A4A4A !important;
        }

        /* 배경색 */
        .stApp {
            background: __CANVAS_BG__;
        }
        [data-testid="stAppViewContainer"] {
            background: __CANVAS_BG__;
        }

        /* 인트로 전용 클래스 */
        .intro-text {
            font-family: 'Nanum Myeongjo', serif;
            text-align: center;
            color: #8E9775;
            font-size: 1.4rem;
            font-weight: 700;
            margin-top: 15px;
            letter-spacing: 0.05rem;
        }

        /* 버튼 커스텀 */
        div.stButton > button {
            background-color: #8E9775 !important;
            color: white !important;
            border-radius: 12px !important;
            border: none !important;
            padding: 0.6rem 1.5rem !important;
            transition: all 0.3s ease;
        }
        div.stButton > button:hover {
            background-color: #6D7756 !important;
            transform: translateY(-2px);
            box-shadow: 0 4px 10px rgba(0,0,0,0.1);
        }

        /* 사이드바 & 컨테이너 곡률 */
        [data-testid="stSidebar"] { background-color: #F1EDE4 !important; }
        .stTabs, .stExpander {
            background-color: white !important;
            border-radius: 15px !important;
            border: 1px solid #E8E2D6 !important;
        }
        .stTextArea textarea { border-radius: 10px !important; }
        
        /* --- 기존 CSS 하단에 추가 --- */

        /* 모바일 전용 반응형 스타일 (화면 너비 768px 이하일 때) */
        @media (max-width: 768px) {
            /* 1. 메인 타이틀(h1) 크기 대폭 축소 */
            h1 {
                font-size: 1.5rem !important; /* 기존보다 훨씬 작게 */
                margin-bottom: 0.5rem !important;
            }
            
            /* 2. 부서 이름(h2) 및 섹션 헤더 크기 조정 */
            h2 {
                font-size: 1.2rem !important;
            }
            
            h3 {
                font-size: 1.0rem !important;
            }

            /* 3. 사이드바 라디오 버튼 텍스트 크기 */
            [data-testid="stSidebar"] .stRadio label {
                font-size: 0.9rem !important;
            }

            /* 4. 인트로 텍스트 크기 조정 */
            .intro-text {
                font-size: 1.1rem !important;
            }
       
        }
         </style>
    """
    st.markdown(css.replace("__CANVAS_BG__", canvas_bg), unsafe_allow_html=True)


    
def display_intro(image_path, duration=2.5):
    """인트로 화면 표시 및 스타일 주입"""
    # 1. 스타일 먼저 적용
    set_custom_style()
    try:
        duration = max(3.0, float(duration))
    except Exception:
        duration = 3.0

    # intro_done 키가 있어도 False면 다시 인트로 재생
    if not st.session_state.get('intro_done', False):
        intro_place = st.empty()
        with intro_place.container():
            try:
                intro_img = Image.open(image_path)
                _, col2, _ = st.columns([1, 2, 1])
                with col2:
                    st.image(intro_img, use_container_width=True)
                    # 인트로 문구도 CSS로 꾸민 스타일 적용 가능
                    st.markdown("<p style='text-align: center; color: #8E9775; font-size: 1.2rem; font-weight: bold;'>나만의 색으로 채우는 시간</p>", unsafe_allow_html=True)
                
                time.sleep(duration)
                st.session_state['intro_done'] = True
                intro_place.empty()
            except Exception as e:
                st.session_state['intro_done'] = True


def apply_owner_dashboard_style():
    """원장 대시보드 전용 스타일"""
    title_bg = _asset_css_bg(
        "title_back.png",
        "linear-gradient(180deg, #7A5638 0%, #8D6747 42%, #B18A68 100%)",
    )
    canvas_bg = _asset_css_bg("canvas_bg.png", "linear-gradient(180deg, #E2CCB3 0%, #D6B693 100%)")
    panel_bg = _asset_css_bg("canvas_bg2.png", "#E8D4BE")
    menu_btn1_bg = _asset_css_bg("butten1.png", "linear-gradient(120deg, #C09066 0%, #B47F57 55%, #A86E48 100%)")
    menu_btn2_bg = _asset_css_bg("butten2.png", "linear-gradient(120deg, #C09066 0%, #B47F57 55%, #A86E48 100%)")
    menu_btn3_bg = _asset_css_bg("butten3.png", "linear-gradient(120deg, #C09066 0%, #B47F57 55%, #A86E48 100%)")
    menu_btn4_bg = _asset_css_bg("butten4.png", "linear-gradient(120deg, #C09066 0%, #B47F57 55%, #A86E48 100%)")
    logout_btn_bg = _asset_css_bg("logout.png", "linear-gradient(120deg, #9E6B43 0%, #8E5F3D 58%, #7E5233 100%)")

    css = """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Nanum+Pen+Script&display=swap');
        @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
        /* Streamlit 기본 상단 UI 숨김 */
        #MainMenu { visibility: hidden !important; }
        header { visibility: hidden !important; height: 0 !important; }
        footer { visibility: hidden !important; height: 0 !important; }
        [data-testid="stHeader"] { display: none !important; }
        [data-testid="stToolbar"] { display: none !important; }
        [data-testid="stDecoration"] { display: none !important; }
        :root {
            --atelier-bg: #E2CCB3;
            --atelier-card: #D8BA99;
            --atelier-border: #9D744F;
            --atelier-text: #4A3526;
            --atelier-sub: #5F4736;
        }
        html, body, .stApp, [data-testid="stAppViewContainer"] {
            font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans KR', sans-serif !important;
        }
        /* 대시보드 본문 기본 Pretendard */
        [data-testid="stAppViewContainer"] .block-container {
            font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans KR', sans-serif !important;
        }
        /* 메뉴/입력/버튼/탭 텍스트는 Pretendard 강제 */
        [data-testid="stButton"] > button,
        [data-testid="stExpander"] summary,
        [data-testid="stTabs"] button,
        [data-testid="stTextInput"] input,
        [data-testid="stTextArea"] textarea,
        [data-testid="stSelectbox"] *,
        [data-testid="stRadio"] *,
        [data-testid="stCheckbox"] *,
        [data-testid="stMarkdownContainer"],
        [data-testid="stCaptionContainer"] {
            font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans KR', sans-serif !important;
        }
        /* 주메뉴 클릭 후 나오는 본문 제목(승인 하기/최근 처리/각 화면 헤더) */
        [data-testid="stHeadingWithActionElements"],
        [data-testid="stHeadingWithActionElements"] *,
        [data-testid="stMarkdownContainer"] h1,
        [data-testid="stMarkdownContainer"] h2,
        [data-testid="stMarkdownContainer"] h3,
        [data-testid="stMarkdownContainer"] h4,
        [data-testid="stMarkdownContainer"] h5,
        [data-testid="stMarkdownContainer"] h6 {
            font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans KR', sans-serif !important;
            letter-spacing: -0.01em;
        }
        /* Streamlit 아이콘 폰트는 유지 (arrow_right 문자열 노출 방지) */
        .material-symbols-rounded,
        .material-icons,
        [class*="material-symbols"] {
            font-family: 'Material Symbols Rounded', 'Material Icons' !important;
        }
        .sticky-owner-header {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            z-index: 1000;
            background: __TITLE_BG__;
            padding: 0.42rem 0 0.5rem 0;
            margin-bottom: 0;
            border-bottom: 1px solid #8A674A;
        }
        .sticky-owner-header.full-bleed {
            width: 100vw;
            padding-left: 1rem;
            padding-right: 1rem;
            box-sizing: border-box;
        }
        .owner-header-spacer {
            height: 70px;
        }
        .sticky-owner-header .header-inner {
            max-width: 760px;
            margin: 0 auto;
            display: flex;
            align-items: flex-start;
            justify-content: flex-start;
        }
        .header-left {
            min-width: 0;
            width: 100%;
        }
        @media (max-width: 900px) {
            .owner-header-spacer {
                height: 62px;
            }
            .sticky-owner-header .header-inner {
                padding-right: 0;
            }
        }
        .stApp {
            background: __CANVAS_BG__ !important;
        }
        [data-testid="stAppViewContainer"] {
            background: __CANVAS_BG__ !important;
        }
        .block-container {
            padding-top: 0 !important;
            padding-left: 0.45rem !important;
            padding-right: 0.45rem !important;
            max-width: 980px !important;
        }
        /* 원장 메인: 좁은 화면에서 좌(대시보드·4메뉴) / 우(본문 창) 가로 2열 → 세로 스택 */
        @media (max-width: 900px) {
            div[data-testid="stElementContainer"]:has(span.owner-main-split-anchor)
                + div[data-testid="stElementContainer"] [data-testid="stHorizontalBlock"] {
                flex-direction: column !important;
                align-items: stretch !important;
                gap: 0.75rem !important;
            }
            div[data-testid="stElementContainer"]:has(span.owner-main-split-anchor)
                + div[data-testid="stElementContainer"] [data-testid="stHorizontalBlock"] > div {
                width: 100% !important;
                min-width: 0 !important;
                max-width: 100% !important;
            }
        }
        .stExpander {
            margin-top: 0 !important;
            padding-top: 0 !important;
        }
        [data-testid="stExpander"] {
            margin-top: 0 !important;
            background: __PANEL_BG__ !important;
            border: 1px solid #B78F6A !important;
            border-radius: 14px !important;
            box-shadow: 0 2px 8px rgba(90, 66, 45, 0.10);
        }
        [data-testid="stExpander"] details {
            background: transparent !important;
        }
        [data-testid="stExpander"] summary {
            background: rgba(216, 186, 153, 0.45) !important;
            border-radius: 12px !important;
            padding: 0.2rem 0.55rem !important;
        }
        /* 원생관리/커리큘럼 본문(탭 패널 + border 컨테이너)도 canvas_bg2 적용 */
        [data-testid="stTabs"] [data-baseweb="tab-panel"] {
            background: __PANEL_BG__ !important;
            border: 1px solid #B78F6A !important;
            border-radius: 14px !important;
            padding: 0.45rem 0.55rem !important;
        }
        [data-testid="stVerticalBlockBorderWrapper"] {
            background: __PANEL_BG__ !important;
            border-color: #B78F6A !important;
            border-radius: 14px !important;
        }
        /* 재무 등 하단 st.tabs — 기본 흰 박스 대신 대시보드 톤 */
        [data-testid="stTabs"] {
            background: #E8D4BE !important;
            border: 1px solid #B78F6A !important;
            border-radius: 14px !important;
            padding: 0.4rem 0.5rem 0.65rem !important;
        }
        [data-testid="stTabs"] [role="tablist"] {
            background: #D8BA99 !important;
            border-radius: 12px !important;
            padding: 5px !important;
            gap: 6px !important;
            border: none !important;
        }
        [data-testid="stTabs"] [role="tablist"] button,
        [data-testid="stTabs"] [role="tablist"] p {
            color: #4A3526 !important;
        }
        [data-testid="stTabs"] button[role="tab"] {
            background: transparent !important;
            color: #4A3526 !important;
            border-radius: 10px !important;
            border: none !important;
        }
        [data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
            background: #8E6242 !important;
            color: #FFF8F2 !important;
        }
        [data-testid="stTabs"] button[role="tab"][aria-selected="true"] p,
        [data-testid="stTabs"] button[role="tab"][aria-selected="true"] span,
        [data-testid="stTabs"] button[role="tab"][aria-selected="true"] div {
            color: #FFF8F2 !important;
        }
        [data-testid="stTabs"] [data-baseweb="tab-list"] {
            background: #D8BA99 !important;
            border-radius: 12px !important;
            gap: 6px !important;
        }
        [data-testid="stTabs"] [data-baseweb="tab-highlight"] {
            background: #8E6242 !important;
        }
        [data-testid="stTabs"] [data-baseweb="tab-border"] {
            background: #E8D4BE !important;
        }
        /* segmented / pills 선택 대비 강화 (선택이 더 눈에 띄게) */
        [data-testid="stSegmentedControl"] {
            background: rgba(216, 186, 153, 0.42) !important;
            border: 1px solid #B78F6A !important;
            border-radius: 12px !important;
            padding: 4px !important;
        }
        [data-testid="stSegmentedControl"] button {
            background: #F6EFE4 !important;
            color: #4A3526 !important;
            border-radius: 10px !important;
            border: 1px solid #D8BA99 !important;
            font-weight: 600 !important;
            transition: all 120ms ease !important;
        }
        [data-testid="stSegmentedControl"] button[aria-pressed="true"] {
            background: #8E6242 !important;
            color: #FFF8F2 !important;
            border: 1px solid #6F4C33 !important;
            box-shadow: 0 2px 8px rgba(60, 41, 25, 0.22) !important;
            font-weight: 700 !important;
        }
        [data-testid="stSegmentedControl"] button p,
        [data-testid="stSegmentedControl"] button span,
        [data-testid="stSegmentedControl"] button div {
            color: inherit !important;
        }
        [data-testid="stPills"] button {
            background: #F6EFE4 !important;
            color: #4A3526 !important;
            border: 1px solid #D8BA99 !important;
            border-radius: 999px !important;
            font-weight: 600 !important;
        }
        [data-testid="stPills"] button[aria-selected="true"],
        [data-testid="stPills"] button[aria-pressed="true"] {
            background: #8E6242 !important;
            color: #FFF8F2 !important;
            border: 1px solid #6F4C33 !important;
            box-shadow: 0 2px 8px rgba(60, 41, 25, 0.20) !important;
            font-weight: 700 !important;
        }
        [data-testid="stPills"] button p,
        [data-testid="stPills"] button span,
        [data-testid="stPills"] button div {
            color: inherit !important;
        }
        .wood-kicker {
            font-family: 'Nanum Gothic', sans-serif !important;
            color: #E9DCCF;
            font-size: 0.62rem;
            letter-spacing: 0.28em;
            font-weight: 700;
            line-height: 1;
            margin-bottom: 0.05rem;
            text-transform: uppercase;
        }
        .wood-signature-row {
            margin-top: 0.02rem;
            margin-left: 1.15rem;
            width: 230px;
            max-width: calc(100vw - 3.2rem);
        }
        .wood-signature-wrap {
            position: relative;
            width: 210px;
            overflow: hidden;
            white-space: nowrap;
            margin-top: -0.04rem;
        }
        .wood-signature-text {
            display: inline-block;
            font-family: 'Nanum Myeongjo', serif !important;
            color: #F8E4CC;
            font-size: 2.68rem;
            line-height: 1;
            letter-spacing: 0.015em;
            text-shadow: 0 1px 1px rgba(40, 28, 20, 0.35);
            clip-path: inset(0 100% 0 0);
            animation: woodSignReveal 2.2s ease-in-out 1 forwards;
            white-space: nowrap;
            word-break: keep-all;
        }
        .wood-brush-anim {
            margin-top: 0.15rem;
            width: 210px;
            height: 6px;
            border-radius: 999px;
            background: linear-gradient(90deg, #E8C49A 0%, #E0AD90 50%, #D59578 100%);
            opacity: 1;
            transform-origin: left center;
            transform: scaleX(0);
            animation: woodBrushReveal 1.1s ease-out 0.95s 1 forwards;
        }
        .wood-signature-pen {
            position: absolute;
            top: 50%;
            left: 0;
            width: 3px;
            height: 1.95rem;
            transform: translateY(-48%);
            border-radius: 99px;
            background: rgba(255, 231, 205, 0.85);
            box-shadow: 0 0 6px rgba(255, 220, 175, 0.55);
            animation: woodSignPen 2.2s ease-in-out 1 forwards;
        }
        @keyframes woodSignReveal {
            0%, 22% { clip-path: inset(0 100% 0 0); opacity: 0.2; }
            78% { clip-path: inset(0 0% 0 0); opacity: 1; }
            100% { clip-path: inset(0 0% 0 0); opacity: 1; }
        }
        @keyframes woodSignPen {
            0%, 22% { left: 0%; opacity: 0; }
            30% { opacity: 0.95; }
            78% { left: 98%; opacity: 0.95; }
            100% { left: 98%; opacity: 0; }
        }
        @keyframes woodBrushReveal {
            0% { transform: scaleX(0); opacity: 0.2; }
            100% { transform: scaleX(1); opacity: 1; }
        }
        /* 기본 버튼은 과하게 키우지 않음 */
        div[data-testid="stButton"] > button {
            min-height: 44px !important;
            border-radius: 12px !important;
            font-size: 0.95rem !important;
            font-weight: 700 !important;
            padding: 0.45rem 0.35rem !important;
            background: #C79E76 !important;
            color: var(--atelier-text) !important;
            border: 1px solid var(--atelier-border) !important;
            box-shadow: 0 2px 6px rgba(121, 101, 80, 0.10);
        }
        div[data-testid="stButton"] > button:hover {
            background: #B98A62 !important;
        }
        div[data-testid="stButton"] > button.menu-btn1 {
            color: #4A3526 !important;
            border: none !important;
            background: __MENU_BTN1_BG__ !important;
            background-size: cover !important;
            background-position: center !important;
            background-repeat: no-repeat !important;
            box-shadow: none !important;
            transition: transform 120ms ease, filter 120ms ease, box-shadow 120ms ease !important;
        }
        div[data-testid="stButton"] > button.menu-btn1[kind="primary"] {
            background: __MENU_BTN1_BG__ !important;
            background-size: cover !important;
            background-position: center !important;
            background-repeat: no-repeat !important;
            border: none !important;
        }
        div[data-testid="stButton"] > button.menu-btn2 {
            color: #4A3526 !important;
            border: none !important;
            background: __MENU_BTN2_BG__ !important;
            background-size: cover !important;
            background-position: center !important;
            background-repeat: no-repeat !important;
            box-shadow: none !important;
            transition: transform 120ms ease, filter 120ms ease, box-shadow 120ms ease !important;
        }
        div[data-testid="stButton"] > button.menu-btn2[kind="primary"] {
            background: __MENU_BTN2_BG__ !important;
            background-size: cover !important;
            background-position: center !important;
            background-repeat: no-repeat !important;
            border: none !important;
        }
        div[data-testid="stButton"] > button.menu-btn3 {
            color: #4A3526 !important;
            border: none !important;
            background: __MENU_BTN3_BG__ !important;
            background-size: cover !important;
            background-position: center !important;
            background-repeat: no-repeat !important;
            box-shadow: none !important;
            transition: transform 120ms ease, filter 120ms ease, box-shadow 120ms ease !important;
        }
        div[data-testid="stButton"] > button.menu-btn3[kind="primary"] {
            background: __MENU_BTN3_BG__ !important;
            background-size: cover !important;
            background-position: center !important;
            background-repeat: no-repeat !important;
            border: none !important;
        }
        div[data-testid="stButton"] > button.menu-btn4 {
            color: #4A3526 !important;
            border: none !important;
            background: __MENU_BTN4_BG__ !important;
            background-size: cover !important;
            background-position: center !important;
            background-repeat: no-repeat !important;
            box-shadow: none !important;
            transition: transform 120ms ease, filter 120ms ease, box-shadow 120ms ease !important;
        }
        div[data-testid="stButton"] > button.menu-btn4[kind="primary"] {
            background: __MENU_BTN4_BG__ !important;
            background-size: cover !important;
            background-position: center !important;
            background-repeat: no-repeat !important;
            border: none !important;
        }
        div[data-testid="stButton"] > button.menu-btn-logout {
            color: #4A3526 !important;
            border: none !important;
            background: __LOGOUT_BTN_BG__ !important;
            background-size: cover !important;
            background-position: center !important;
            background-repeat: no-repeat !important;
            box-shadow: none !important;
            transition: transform 120ms ease, filter 120ms ease, box-shadow 120ms ease !important;
        }
        div[data-testid="stButton"] > button.menu-btn1:hover,
        div[data-testid="stButton"] > button.menu-btn2:hover,
        div[data-testid="stButton"] > button.menu-btn3:hover,
        div[data-testid="stButton"] > button.menu-btn4:hover,
        div[data-testid="stButton"] > button.menu-btn-logout:hover {
            filter: brightness(1.04) saturate(1.03) !important;
        }
        div[data-testid="stButton"] > button.menu-btn1:active,
        div[data-testid="stButton"] > button.menu-btn2:active,
        div[data-testid="stButton"] > button.menu-btn3:active,
        div[data-testid="stButton"] > button.menu-btn4:active,
        div[data-testid="stButton"] > button.menu-btn-logout:active {
            transform: translateY(2px) scale(0.988) !important;
            filter: brightness(0.92) saturate(0.95) !important;
            box-shadow: inset 0 2px 8px rgba(52, 35, 23, 0.28) !important;
        }
        div[data-testid="stButton"] > button.menu-btn1 p,
        div[data-testid="stButton"] > button.menu-btn1 span,
        div[data-testid="stButton"] > button.menu-btn1 div,
        div[data-testid="stButton"] > button.menu-btn2 p,
        div[data-testid="stButton"] > button.menu-btn2 span,
        div[data-testid="stButton"] > button.menu-btn2 div,
        div[data-testid="stButton"] > button.menu-btn3 p,
        div[data-testid="stButton"] > button.menu-btn3 span,
        div[data-testid="stButton"] > button.menu-btn3 div,
        div[data-testid="stButton"] > button.menu-btn4 p,
        div[data-testid="stButton"] > button.menu-btn4 span,
        div[data-testid="stButton"] > button.menu-btn4 div,
        div[data-testid="stButton"] > button.menu-btn-logout p,
        div[data-testid="stButton"] > button.menu-btn-logout span,
        div[data-testid="stButton"] > button.menu-btn-logout div {
            color: #4A3526 !important;
            font-weight: 700 !important;
        }
        /* 주메뉴 버튼 고정 스타일: js가 실패해도 key 기반으로 유지 */
        .st-key-owner-menu-slot-0 div[data-testid="stButton"] > button,
        .st-key-owner-menu-slot-1 div[data-testid="stButton"] > button,
        .st-key-owner-menu-slot-2 div[data-testid="stButton"] > button,
        .st-key-owner-menu-slot-3 div[data-testid="stButton"] > button {
            color: #4A3526 !important;
            border: none !important;
            box-shadow: none !important;
            transition: transform 120ms ease, filter 120ms ease, box-shadow 120ms ease !important;
        }
        .st-key-owner-menu-slot-0 div[data-testid="stButton"] > button { background: __MENU_BTN1_BG__ !important; background-size: cover !important; background-position: center !important; background-repeat: no-repeat !important; }
        .st-key-owner-menu-slot-1 div[data-testid="stButton"] > button { background: __MENU_BTN2_BG__ !important; background-size: cover !important; background-position: center !important; background-repeat: no-repeat !important; }
        .st-key-owner-menu-slot-2 div[data-testid="stButton"] > button { background: __MENU_BTN3_BG__ !important; background-size: cover !important; background-position: center !important; background-repeat: no-repeat !important; }
        .st-key-owner-menu-slot-3 div[data-testid="stButton"] > button { background: __MENU_BTN4_BG__ !important; background-size: cover !important; background-position: center !important; background-repeat: no-repeat !important; }
        .st-key-owner-menu-slot-0 div[data-testid="stButton"] > button[kind="primary"] { background: __MENU_BTN1_BG__ !important; }
        .st-key-owner-menu-slot-1 div[data-testid="stButton"] > button[kind="primary"] { background: __MENU_BTN2_BG__ !important; }
        .st-key-owner-menu-slot-2 div[data-testid="stButton"] > button[kind="primary"] { background: __MENU_BTN3_BG__ !important; }
        .st-key-owner-menu-slot-3 div[data-testid="stButton"] > button[kind="primary"] { background: __MENU_BTN4_BG__ !important; }
        .st-key-owner-menu-slot-0 div[data-testid="stButton"] > button:hover,
        .st-key-owner-menu-slot-1 div[data-testid="stButton"] > button:hover,
        .st-key-owner-menu-slot-2 div[data-testid="stButton"] > button:hover,
        .st-key-owner-menu-slot-3 div[data-testid="stButton"] > button:hover {
            filter: brightness(1.08) saturate(1.05) !important;
        }
        .st-key-owner-menu-slot-0 div[data-testid="stButton"] > button:active,
        .st-key-owner-menu-slot-1 div[data-testid="stButton"] > button:active,
        .st-key-owner-menu-slot-2 div[data-testid="stButton"] > button:active,
        .st-key-owner-menu-slot-3 div[data-testid="stButton"] > button:active {
            transform: translateY(4px) scale(0.975) !important;
            filter: brightness(0.78) saturate(0.9) contrast(1.04) !important;
            box-shadow: inset 0 4px 12px rgba(46, 30, 18, 0.42), 0 0 0 rgba(0,0,0,0) !important;
        }
        .menu-brush-img {
            margin: 0.02rem 0 0.15rem 0;
            opacity: 0.95;
        }
        .menu-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            margin-bottom: 16px;
        }
        .menu-card-link {
            text-decoration: none !important;
            display: block;
        }
        .menu-card {
            height: 96px;
            border-radius: 14px;
            border: 1px solid #B78F6A;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 1.05rem;
            color: #FFFFFF;
            text-shadow: 0 1px 2px rgba(32, 23, 16, 0.35);
            box-shadow: 0 2px 8px rgba(90, 66, 45, 0.15);
            background:
                radial-gradient(120% 100% at 10% 10%, rgba(255,255,255,0.18) 0%, rgba(255,255,255,0) 52%),
                linear-gradient(120deg, #C09066 0%, #B47F57 55%, #A86E48 100%);
            clip-path: polygon(3% 8%, 14% 2%, 86% 4%, 97% 11%, 98% 86%, 88% 97%, 10% 98%, 2% 90%);
        }
        .menu-card.active {
            border: 2px solid #F5D8A8;
            box-shadow: 0 0 0 2px rgba(245, 216, 168, 0.35), 0 4px 12px rgba(60, 41, 25, 0.32);
            transform: translateY(-1px);
            background:
                radial-gradient(120% 100% at 10% 10%, rgba(255,255,255,0.25) 0%, rgba(255,255,255,0) 52%),
                linear-gradient(120deg, #9E6B43 0%, #8E5F3D 58%, #7E5233 100%);
        }
        /* 재무 4칸 등: 제목 + 흰색 숫자를 카드 안에 세로 배치 */
        .menu-card-inner {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 6px;
            text-align: center;
            padding: 6px 4px;
            width: 100%;
        }
        .menu-card-metric {
            font-size: 1.05rem;
            font-weight: 800;
            color: #FFFFFF !important;
            letter-spacing: -0.02em;
            line-height: 1.15;
            text-shadow: 0 1px 2px rgba(32, 23, 16, 0.4);
        }
        </style>
        """
    st.markdown(
        css.replace("__TITLE_BG__", title_bg)
        .replace("__CANVAS_BG__", canvas_bg)
        .replace("__PANEL_BG__", panel_bg)
        .replace("__MENU_BTN1_BG__", menu_btn1_bg)
        .replace("__MENU_BTN2_BG__", menu_btn2_bg)
        .replace("__MENU_BTN3_BG__", menu_btn3_bg)
        .replace("__MENU_BTN4_BG__", menu_btn4_bg)
        .replace("__LOGOUT_BTN_BG__", logout_btn_bg),
        unsafe_allow_html=True,
    )


def render_owner_brand_header():
    st.markdown(
        """
        <div id='owner-brand-refresh-target' class='sticky-owner-header full-bleed'
             role='button'
             tabindex='0'
             title='새로고침'
             style='cursor:pointer;'
             onclick='try{(window.parent||window).location.reload();}catch(e){window.location.reload();}'
             onkeydown='if(event.key==="Enter"||event.key===" "){event.preventDefault();try{(window.parent||window).location.reload();}catch(e){window.location.reload();}}'>
            <div class='header-inner'>
                <div class='header-left'>
                    <div class='wood-kicker'>STUDIO</div>
                    <div class='wood-signature-row' aria-hidden='true'>
                        <div class='wood-signature-wrap'>
                            <span class='wood-signature-text'>그리다가</span>
                            <span class='wood-signature-pen'></span>
                        </div>
                        <div class='wood-brush-anim'></div>
                    </div>
                </div>
            </div>
        </div>
        <div class='owner-header-spacer' aria-hidden='true'></div>
        """,
        unsafe_allow_html=True,
    )
    components.html(
        """
        <script>
        (function () {
          const doc = (window.parent && window.parent.document) ? window.parent.document : document;
          const win = (window.parent && window.parent.location) ? window.parent : window;
          function hardRefresh() {
            try {
              const u = new URL(win.location.href);
              u.searchParams.set("_rf", String(Date.now()));
              win.location.href = u.toString();
            } catch (e) {
              try { win.location.reload(); } catch (_) {}
            }
          }
          function bind() {
            try {
              const el = doc.querySelector("#owner-brand-refresh-target");
              if (!el) return;
              if (el.dataset.refreshBound === "1") return;
              el.dataset.refreshBound = "1";
              el.addEventListener("click", function (e) {
                e.preventDefault();
                hardRefresh();
              }, true);
              el.addEventListener("keydown", function (e) {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  hardRefresh();
                }
              }, true);
            } catch (e) {}
          }
          bind();
          setTimeout(bind, 80);
          setTimeout(bind, 300);
        })();
        </script>
        """,
        height=0,
    )


def render_owner_menu_grid(owner_login_at, active_idx=None):
    del owner_login_at  # 버튼 기반 전환으로 링크 쿼리 조합은 사용하지 않음.
    items = [
        ("📢 마케팅", 0),
        ("👥 회원관리", 1),
        ("💰 재무", 2),
        ("📚 커리큘럼", 3),
    ]

    row1 = st.columns(2)
    row2 = st.columns(2)
    def _menu_btn(col, label, idx):
        cur = int(st.session_state.get("owner_menu_index", active_idx if active_idx is not None else 0))
        is_active = cur == idx
        with col:
            with st.container(key=f"owner-menu-slot-{idx}"):
                if st.button(
                    label,
                    key=f"owner_menu_btn_{idx}",
                    use_container_width=True,
                    type="primary" if is_active else "secondary",
                ):
                    st.session_state["owner_menu_index"] = idx
                    st.query_params["owner_menu_idx"] = str(idx)
                    # 버튼 클릭 시 Streamlit이 이미 1회 rerun 하므로 여기서 또 호출하면 매 클릭마다 2배 실행됨

    _menu_btn(row1[0], items[0][0], items[0][1])
    _menu_btn(row1[1], items[1][0], items[1][1])
    _menu_btn(row2[0], items[2][0], items[2][1])
    _menu_btn(row2[1], items[3][0], items[3][1])

    bg_map = {
        "마케팅": _asset_css_bg("butten1.png", "linear-gradient(120deg, #C09066 0%, #B47F57 55%, #A86E48 100%)"),
        "회원관리": _asset_css_bg("butten2.png", "linear-gradient(120deg, #C09066 0%, #B47F57 55%, #A86E48 100%)"),
        "재무": _asset_css_bg("butten3.png", "linear-gradient(120deg, #C09066 0%, #B47F57 55%, #A86E48 100%)"),
        "커리큘럼": _asset_css_bg("butten4.png", "linear-gradient(120deg, #C09066 0%, #B47F57 55%, #A86E48 100%)"),
        "로그아웃": _asset_css_bg("logout.png", "linear-gradient(120deg, #9E6B43 0%, #8E5F3D 58%, #7E5233 100%)"),
    }
    bg_map_js = json.dumps(bg_map, ensure_ascii=False)

    # st.button은 클래스 지정이 안 되므로, 마케팅 버튼 텍스트 기준으로 클래스 부여
    js = """
        <script>
        (function () {
          const doc = window.parent && window.parent.document ? window.parent.document : document;
          const bgMap = __BG_MAP_JS__;

          function applyBg(btn, bg) {
            if (!bg) return;
            btn.style.setProperty("background", bg, "important");
            btn.style.setProperty("background-size", "cover", "important");
            btn.style.setProperty("background-position", "center", "important");
            btn.style.setProperty("background-repeat", "no-repeat", "important");
            btn.style.setProperty("border", "none", "important");
            btn.style.setProperty("box-shadow", "none", "important");
            btn.style.setProperty("color", "#4A3526", "important");
          }

          function applyMenuButtonClasses() {
            try {
              const btns = doc.querySelectorAll('div[data-testid="stButton"] > button');
              btns.forEach((b) => {
                const t = (b.innerText || "").trim();
                if (t.includes("마케팅")) applyBg(b, bgMap["마케팅"]);
                if (t.includes("회원관리")) applyBg(b, bgMap["회원관리"]);
                if (t.includes("재무")) applyBg(b, bgMap["재무"]);
                if (t.includes("커리큘럼")) applyBg(b, bgMap["커리큘럼"]);
                if (t.includes("로그아웃")) applyBg(b, bgMap["로그아웃"]);
              });

              // 상단 4메뉴(2행) 모바일 자동 스택 방지: 항상 2x2 유지
              const rows = doc.querySelectorAll('div[data-testid="stHorizontalBlock"]');
              rows.forEach((hb) => {
                const btns = hb.querySelectorAll('div[data-testid="stButton"] > button');
                if (!btns || btns.length < 2) return;
                const texts = Array.from(btns).map((b) => (b.innerText || "").trim());
                const isMenuRow =
                  (texts.some((t) => t.includes("마케팅")) && texts.some((t) => t.includes("회원관리"))) ||
                  (texts.some((t) => t.includes("재무")) && texts.some((t) => t.includes("커리큘럼")));
                if (!isMenuRow) return;
                hb.style.setProperty("display", "flex", "important");
                hb.style.setProperty("flex-direction", "row", "important");
                hb.style.setProperty("flex-wrap", "nowrap", "important");
                hb.style.setProperty("gap", "0.5rem", "important");
                Array.from(hb.children).forEach((c) => {
                  c.style.setProperty("width", "50%", "important");
                  c.style.setProperty("max-width", "50%", "important");
                  c.style.setProperty("min-width", "0", "important");
                  c.style.setProperty("flex", "0 0 50%", "important");
                });
              });
            } catch (e) {}
          }

          applyMenuButtonClasses();
          setTimeout(applyMenuButtonClasses, 60);
          setTimeout(applyMenuButtonClasses, 250);
          setTimeout(applyMenuButtonClasses, 600);

          try {
            const observer = new MutationObserver(() => applyMenuButtonClasses());
            const root =
              doc.querySelector('section[data-testid="stAppViewContainer"]') || doc.body;
            observer.observe(root, { childList: true, subtree: true });
            setTimeout(() => observer.disconnect(), 12000);
          } catch (e) {}
        })();
        </script>
    """
    components.html(js.replace("__BG_MAP_JS__", bg_map_js), height=0)