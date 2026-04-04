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


@st.cache_data(show_spinner=False)
def _asset_css_bg_from_path(asset_path: str, fallback: str, max_kb: int = 0) -> str:
    """파일 경로 기반 CSS background(data URI) 생성. max_kb 초과 시 fallback."""
    try:
        p = Path(asset_path)
        if not p.exists():
            return fallback
        raw = p.read_bytes()
        if max_kb and len(raw) > int(max_kb) * 1024:
            # 너무 큰 배경 이미지는 첫 로딩 지연이 커서 그라데이션으로 대체
            return fallback
        ext = p.suffix.lower()
        if ext == ".webp":
            mime = "image/webp"
        elif ext in (".jpg", ".jpeg"):
            mime = "image/jpeg"
        elif ext == ".gif":
            mime = "image/gif"
        else:
            mime = "image/png"
        b64 = base64.b64encode(raw).decode("ascii")
        return f"url('data:{mime};base64,{b64}') center/cover no-repeat"
    except Exception:
        return fallback


def _asset_css_bg(asset_name: str, fallback: str, max_kb: int = 0) -> str:
    """assets 이미지를 CSS background 값으로 변환 (없으면 fallback)."""
    try:
        p = Path(__file__).resolve().parents[1] / "assets" / asset_name
        return _asset_css_bg_from_path(str(p), fallback, max_kb=max_kb)
    except Exception:
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
    canvas_bg = _asset_css_bg("canvas_bg.webp", "#FCF9F2")
    css = """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Nanum+Myeongjo:wght@400;700&display=swap');
        @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');

        /* 스크롤바 등장 시 가로 폭이 바뀌며 가운데 글씨가 좌우로 흔들리는 현상 완화 */
        html {
            scrollbar-gutter: stable;
        }
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

        /* 캔버스: fixed일 때 100%는 뷰포트 기준 — cover는 비율 맞추며 크게 잘라 ‘확대’처럼 보이는 경우가 많음 */
        html, body {
            min-height: 100vh !important;
            min-height: 100dvh !important;
            margin: 0 !important;
            background-color: #FCF9F2 !important;
            overflow-x: hidden !important;
            overscroll-behavior-x: none !important;
        }
        .stApp {
            background: __CANVAS_BG__ !important;
            background-attachment: fixed !important;
            background-size: 100% 100% !important;
            background-position: center center !important;
            background-repeat: no-repeat !important;
            min-height: 100vh !important;
            min-height: 100dvh !important;
            overflow-x: hidden !important;
        }
        [data-testid="stAppViewContainer"] {
            background: transparent !important;
            overflow-x: hidden !important;
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
        /* 인트로 하단 캐치프라이즈: 더 진하게, 자간 과하면 서브픽셀에서 흔들려 보일 수 있음 */
        p.intro-tagline {
            font-family: 'Nanum Myeongjo', 'Noto Serif KR', serif !important;
            text-align: center !important;
            color: #3D4F32 !important;
            font-size: 1.3rem !important;
            font-weight: 800 !important;
            line-height: 1.45 !important;
            margin: 0.75rem auto 0 auto !important;
            max-width: 28rem !important;
            width: 100% !important;
            box-sizing: border-box !important;
            letter-spacing: 0 !important;
            text-rendering: geometricPrecision;
            -webkit-font-smoothing: antialiased;
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
            p.intro-tagline {
                font-size: 1.15rem !important;
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
        # 기존에는 최소 3초로 강제되어 첫 진입(F5/URL) 체감 로딩이 길어짐
        duration = max(0.0, float(duration))
    except Exception:
        duration = 0.0

    # intro_done 키가 있어도 False면 다시 인트로 재생
    if not st.session_state.get('intro_done', False):
        intro_place = st.empty()
        with intro_place.container():
            try:
                intro_img = Image.open(image_path)
                iw = int(intro_img.size[0]) if intro_img.size else 480
                display_w = max(200, min(iw, 480))
                # 가운데 열 유지 + 이미지는 고정 width (use_container_width면 로드 후 폭이 바뀌며 아래 문장이 좌우로 흔들릴 수 있음)
                _, col2, _ = st.columns([1, 2, 1])
                with col2:
                    st.image(intro_img, width=display_w)
                    st.markdown(
                        '<p class="intro-tagline">나만의 채색으로 채우는 시간</p>',
                        unsafe_allow_html=True,
                    )
                
                if duration > 0:
                    time.sleep(duration)
                st.session_state['intro_done'] = True
                intro_place.empty()
            except Exception as e:
                st.session_state['intro_done'] = True


def apply_owner_dashboard_style():
    """원장 대시보드 전용 스타일"""
    canvas_bg = _asset_css_bg(
        "canvas_bg.webp",
        "linear-gradient(180deg, #E2CCB3 0%, #D6B693 100%)",
        max_kb=350,
    )
    title_bg = canvas_bg
    panel_bg = canvas_bg
    menu_btn1_bg = _asset_css_bg("butten1.png", "linear-gradient(120deg, #C09066 0%, #B47F57 55%, #A86E48 100%)")
    menu_btn2_bg = _asset_css_bg("butten2.png", "linear-gradient(120deg, #C09066 0%, #B47F57 55%, #A86E48 100%)")
    menu_btn3_bg = _asset_css_bg("butten3.png", "linear-gradient(120deg, #C09066 0%, #B47F57 55%, #A86E48 100%)")
    menu_btn4_bg = _asset_css_bg("butten4.png", "linear-gradient(120deg, #C09066 0%, #B47F57 55%, #A86E48 100%)")
    logout_btn_bg = _asset_css_bg("logout.png", "linear-gradient(120deg, #9E6B43 0%, #8E5F3D 58%, #7E5233 100%)")

    css = """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Nanum+Pen+Script&display=swap');
        @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;800&display=swap');
        @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
        @font-face {
            font-family: 'RIDIBatang';
            src: url('https://cdn.jsdelivr.net/gh/projectnoonnu/noonfonts_2101@1.1/RIDIBatang.woff') format('woff');
            font-weight: normal;
            font-style: normal;
            font-display: swap;
        }
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
            --atelier-text: #2F2218;
            --atelier-sub: #4B382A;
        }
        html, body, .stApp, [data-testid="stAppViewContainer"] {
            font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans KR', sans-serif !important;
        }
        /* 대시보드 본문 기본 Pretendard */
        [data-testid="stAppViewContainer"] .block-container {
            font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans KR', sans-serif !important;
            color: var(--atelier-text) !important;
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
        /* 본문 소제목(h4~h6): Pretendard 유지 */
        [data-testid="stMarkdownContainer"] h4,
        [data-testid="stMarkdownContainer"] h5,
        [data-testid="stMarkdownContainer"] h6 {
            font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans KR', sans-serif !important;
            letter-spacing: -0.01em;
            color: var(--atelier-text) !important;
            font-weight: 700 !important;
        }
        /* 상단 4메뉴로 연 화면의 st.header / st.subheader만 wood 큰 제목 (익스팬더·마크다운 제목은 제외) */
        [data-testid="stHeadingWithActionElements"] h1 {
            font-family: 'RIDIBatang', 'Nanum Myeongjo', 'Noto Serif KR', serif !important;
            color: #5C4338 !important;
            letter-spacing: -0.01em !important;
            font-weight: 800 !important;
            text-shadow: 0 1px 0 rgba(255, 250, 245, 0.14), 0 2px 5px rgba(28, 20, 14, 0.2) !important;
            font-size: 1.3rem !important;
            line-height: 1.3 !important;
        }
        [data-testid="stHeadingWithActionElements"] h2,
        [data-testid="stHeadingWithActionElements"] h3 {
            font-family: 'RIDIBatang', 'Nanum Myeongjo', 'Noto Serif KR', serif !important;
            color: #5C4338 !important;
            letter-spacing: -0.01em !important;
            font-weight: 800 !important;
            text-shadow: 0 1px 0 rgba(255, 250, 245, 0.14), 0 2px 5px rgba(28, 20, 14, 0.2) !important;
            font-size: 1.15rem !important;
            line-height: 1.35 !important;
        }
        /* Streamlit 아이콘 폰트는 유지 (arrow_right 문자열 노출 방지) */
        .material-symbols-rounded,
        .material-icons,
        [class*="material-symbols"] {
            font-family: 'Material Symbols Rounded', 'Material Icons' !important;
        }
        [data-testid="stExpander"] summary .material-symbols-rounded,
        [data-testid="stExpander"] summary [class*="material-symbols"],
        [data-testid="stExpander"] summary .material-icons {
            font-family: 'Material Symbols Rounded', 'Material Icons' !important;
            font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24 !important;
            font-weight: 400 !important;
            letter-spacing: normal !important;
            text-shadow: none !important;
            color: #5C4338 !important;
        }
        .sticky-owner-header {
            position: relative;
            top: auto;
            left: 0;
            right: 0;
            z-index: 1;
            background: transparent;
            padding: 0.06rem 0 0.2rem 0;
            margin-top: -0.18rem !important;
            margin-bottom: 0;
            border-bottom: none;
        }
        .sticky-owner-header.full-bleed {
            width: 100%;
            padding-left: 1rem;
            padding-right: 1rem;
            box-sizing: border-box;
        }
        .owner-header-spacer {
            height: 0;
            display: none;
        }
        .sticky-owner-header .header-inner {
            max-width: 760px;
            margin: 0 auto;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .header-left {
            min-width: 0;
            width: 100%;
            text-align: center;
        }
        @media (max-width: 900px) {
            .owner-header-spacer {
                height: 0;
            }
            .sticky-owner-header .header-inner {
                padding-right: 0;
            }
        }
        /* 캔버스: 뷰포트에 맞춰 가로·세로 꽉 참(cover 대신 100%로 과확대·잘림 완화) */
        html, body {
            min-height: 100vh !important;
            min-height: 100dvh !important;
            margin: 0 !important;
            background-color: #FCF9F2 !important;
            overflow-x: hidden !important;
            overscroll-behavior-x: none !important;
        }
        .stApp {
            background: __CANVAS_BG__ !important;
            background-attachment: fixed !important;
            background-size: 100% 100% !important;
            background-position: center center !important;
            background-repeat: no-repeat !important;
            min-height: 100vh !important;
            min-height: 100dvh !important;
            overflow-x: hidden !important;
        }
        [data-testid="stAppViewContainer"] {
            background: transparent !important;
            overflow-x: hidden !important;
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
        /* 원장 주메뉴 테두리: 헤더와 폭 맞춤, 패딩·높이 슬림, 살짝 아래로 */
        .st-key-owner_menu_bar[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-owner_menu_bar [data-testid="stVerticalBlockBorderWrapper"] {
            margin-top: 0.95rem !important;
            margin-left: auto !important;
            margin-right: auto !important;
            max-width: 760px !important;
            width: 100% !important;
            box-sizing: border-box !important;
            padding: 0.32rem 0.48rem 0.36rem 0.48rem !important;
            border-radius: 12px !important;
        }
        .st-key-owner_menu_bar [data-testid="stVerticalBlock"] {
            gap: 0.2rem !important;
        }
        /* 패널(익스팬더/탭/컨테이너): fixed 배경은 접힘/펼침 때 리페인트가 커져 끊김·잔상(고스팅)을 유발할 수 있음.
           캔버스(.stApp)만 fixed로 두고, 패널은 스크롤 배경 + 반투명 톤으로 안정화. */
        [data-testid="stExpander"],
        [data-testid="stTabs"] [data-baseweb="tab-panel"],
        [data-testid="stVerticalBlockBorderWrapper"] {
            background-attachment: scroll !important;
            background-size: auto !important;
            background-position: center center !important;
            background-repeat: repeat !important;
            /* GPU 레이어 분리로 잔상 완화(특히 Windows/Chrome에서) */
            transform: translateZ(0);
            backface-visibility: hidden;
            will-change: contents;
        }
        [data-testid="stExpander"] {
            background: rgba(232, 212, 190, 0.82) !important;
        }
        [data-testid="stTabs"] [data-baseweb="tab-panel"],
        [data-testid="stVerticalBlockBorderWrapper"] {
            background: rgba(232, 212, 190, 0.74) !important;
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
            font-family: 'RIDIBatang', 'Nanum Myeongjo', 'Noto Serif KR', serif !important;
            color: #5C4338 !important;
            letter-spacing: -0.01em !important;
            font-weight: 800 !important;
            text-shadow: 0 1px 0 rgba(255, 250, 245, 0.14), 0 1px 3px rgba(28, 20, 14, 0.12) !important;
        }
        [data-testid="stTabs"] button[role="tab"] {
            background: transparent !important;
            font-family: 'RIDIBatang', 'Nanum Myeongjo', 'Noto Serif KR', serif !important;
            color: #5C4338 !important;
            letter-spacing: -0.01em !important;
            font-weight: 800 !important;
            text-shadow: 0 1px 0 rgba(255, 250, 245, 0.14), 0 1px 3px rgba(28, 20, 14, 0.12) !important;
            border-radius: 10px !important;
            border: none !important;
        }
        [data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
            background: #8E6242 !important;
            font-family: 'RIDIBatang', 'Nanum Myeongjo', 'Noto Serif KR', serif !important;
            color: #FFF8F2 !important;
            letter-spacing: -0.01em !important;
            font-weight: 800 !important;
            text-shadow: 0 1px 2px rgba(24, 16, 10, 0.4) !important;
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
        /* 세그먼트: 슬라이딩 칩 트랙 (테마 primary 붉은색이 덮이지 않도록 배경·글자 명시) */
        [data-testid="stSegmentedControl"] {
            display: flex !important;
            align-items: stretch !important;
            gap: 3px !important;
            background: linear-gradient(180deg, rgba(255, 252, 248, 0.95) 0%, rgba(232, 218, 200, 0.55) 100%) !important;
            border: 1px solid rgba(110, 78, 52, 0.32) !important;
            border-radius: 999px !important;
            padding: 4px !important;
            box-shadow: inset 0 1px 3px rgba(48, 32, 20, 0.07), 0 1px 2px rgba(80, 55, 35, 0.06) !important;
        }
        [data-testid="stSegmentedControl"] button {
            flex: 1 1 0 !important;
            min-width: 0 !important;
            margin: 0 !important;
            background: transparent !important;
            background-color: transparent !important;
            border: 1px solid transparent !important;
            border-radius: 999px !important;
            font-family: 'RIDIBatang', 'Nanum Myeongjo', 'Noto Serif KR', serif !important;
            color: #4A3628 !important;
            letter-spacing: -0.02em !important;
            font-weight: 600 !important;
            font-size: 1.15rem !important;
            text-shadow: none !important;
            box-shadow: none !important;
            transition: background 0.2s ease, color 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease !important;
        }
        [data-testid="stSegmentedControl"] button:hover {
            background: rgba(255, 255, 255, 0.55) !important;
            background-color: rgba(255, 255, 255, 0.55) !important;
        }
        [data-testid="stSegmentedControl"] button[aria-pressed="true"],
        [data-testid="stSegmentedControl"] button[kind="primary"] {
            background: linear-gradient(168deg, #A67B52 0%, #7A4E34 48%, #5C3824 100%) !important;
            background-color: #6B4530 !important;
            border-color: rgba(36, 24, 16, 0.4) !important;
            color: #FFFDF9 !important;
            font-weight: 700 !important;
            box-shadow: 0 2px 12px rgba(48, 32, 22, 0.28), inset 0 1px 0 rgba(255, 236, 216, 0.25) !important;
            text-shadow: 0 1px 2px rgba(18, 10, 6, 0.45) !important;
        }
        [data-testid="stSegmentedControl"] button[aria-pressed="true"]:hover,
        [data-testid="stSegmentedControl"] button[kind="primary"]:hover {
            filter: brightness(1.03) !important;
        }
        [data-testid="stSegmentedControl"] button:focus {
            outline: none !important;
        }
        [data-testid="stSegmentedControl"] button:focus-visible {
            outline: 2px solid #B88962 !important;
            outline-offset: 2px !important;
        }
        [data-testid="stSegmentedControl"] button p,
        [data-testid="stSegmentedControl"] button span,
        [data-testid="stSegmentedControl"] button div {
            color: inherit !important;
        }
        [data-testid="stSegmentedControl"] button[aria-pressed="true"] p,
        [data-testid="stSegmentedControl"] button[aria-pressed="true"] span,
        [data-testid="stSegmentedControl"] button[aria-pressed="true"] div,
        [data-testid="stSegmentedControl"] button[kind="primary"] p,
        [data-testid="stSegmentedControl"] button[kind="primary"] span,
        [data-testid="stSegmentedControl"] button[kind="primary"] div {
            color: #FFFDF9 !important;
        }
        /* 익스팬더 안: 제목·세그먼트·라벨은 통일 전 크기·Pretendard (화면 대제목만 위 wood 규칙 유지) */
        [data-testid="stExpander"] summary,
        [data-testid="stExpander"] summary p {
            font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans KR', sans-serif !important;
            color: var(--atelier-text) !important;
            font-weight: 700 !important;
            font-size: 1.08rem !important;
            line-height: 1.35 !important;
            letter-spacing: -0.01em !important;
            text-shadow: none !important;
        }
        [data-testid="stExpander"] [data-testid="stWidgetLabel"] p {
            font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans KR', sans-serif !important;
            color: var(--atelier-text) !important;
            font-weight: 700 !important;
            font-size: 1.08rem !important;
            text-shadow: none !important;
        }
        [data-testid="stExpander"] [data-testid="stSegmentedControl"] button {
            font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans KR', sans-serif !important;
            font-size: 1.08rem !important;
            font-weight: 600 !important;
            color: #3D2E22 !important;
            letter-spacing: -0.02em !important;
            text-shadow: none !important;
            background: transparent !important;
            background-color: transparent !important;
            border-color: transparent !important;
            box-shadow: none !important;
        }
        [data-testid="stExpander"] [data-testid="stSegmentedControl"] button[aria-pressed="true"],
        [data-testid="stExpander"] [data-testid="stSegmentedControl"] button[kind="primary"] {
            font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans KR', sans-serif !important;
            font-size: 1.08rem !important;
            font-weight: 700 !important;
            color: #FFFDF9 !important;
            letter-spacing: -0.02em !important;
            text-shadow: 0 1px 2px rgba(18, 10, 6, 0.4) !important;
            background: linear-gradient(168deg, #A67B52 0%, #7A4E34 48%, #5C3824 100%) !important;
            background-color: #6B4530 !important;
            border-color: rgba(36, 24, 16, 0.4) !important;
            box-shadow: 0 2px 10px rgba(48, 32, 22, 0.22), inset 0 1px 0 rgba(255, 236, 216, 0.22) !important;
        }
        [data-testid="stExpander"] [data-testid="stSegmentedControl"] button[aria-pressed="true"] p,
        [data-testid="stExpander"] [data-testid="stSegmentedControl"] button[aria-pressed="true"] span,
        [data-testid="stExpander"] [data-testid="stSegmentedControl"] button[aria-pressed="true"] div,
        [data-testid="stExpander"] [data-testid="stSegmentedControl"] button[kind="primary"] p,
        [data-testid="stExpander"] [data-testid="stSegmentedControl"] button[kind="primary"] span,
        [data-testid="stExpander"] [data-testid="stSegmentedControl"] button[kind="primary"] div {
            color: #FFFDF9 !important;
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
        .wood-kicker-row {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0.45rem;
        }
        .wood-kicker {
            font-family: 'Playfair Display', serif !important;
            color: #FFF8F0;
            font-size: 1.02rem;
            letter-spacing: 0.09em;
            font-weight: 800;
            line-height: 1;
            margin-bottom: 0.01rem;
            text-transform: uppercase;
            text-shadow: 0 1px 3px rgba(30, 20, 14, 0.55), 0 0 1px rgba(30, 20, 14, 0.35);
        }
        .wood-signature-row {
            margin-top: 0.08rem;
            width: min(520px, calc(100vw - 2.4rem));
            margin-left: auto;
            margin-right: auto;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0;
        }
        .wood-signature-wrap {
            position: relative;
            width: auto;
            overflow: hidden;
            white-space: nowrap;
            margin-top: -0.01rem;
        }
        .wood-signature-text {
            display: inline-block;
            font-family: 'RIDIBatang', 'Nanum Myeongjo', 'Noto Serif KR', serif !important;
            color: #5C4338;
            font-size: clamp(2.48rem, 7vw, 2.95rem);
            line-height: 1.02;
            letter-spacing: -0.01em;
            font-weight: 800;
            text-shadow: 0 1px 0 rgba(255, 250, 245, 0.14), 0 2px 5px rgba(28, 20, 14, 0.2);
            white-space: nowrap;
            word-break: keep-all;
        }
        .wood-line {
            flex: 1 1 60px;
            max-width: 90px;
            min-width: 24px;
            height: 2px;
            border-radius: 999px;
            background: rgba(255, 248, 240, 0.92);
            box-shadow: 0 1px 2px rgba(30, 20, 14, 0.35);
        }
        .wood-line.left {
            transform-origin: right center;
            animation: lineGatherLeft 0.95s ease-out 0.15s 1 both;
        }
        .wood-line.right {
            transform-origin: left center;
            animation: lineGatherRight 0.95s ease-out 0.15s 1 both;
        }
        @keyframes lineGatherLeft {
            0% { transform: translateX(-28px) scaleX(0.12); opacity: 0.15; }
            100% { transform: translateX(0) scaleX(1); opacity: 1; }
        }
        @keyframes lineGatherRight {
            0% { transform: translateX(28px) scaleX(0.12); opacity: 0.15; }
            100% { transform: translateX(0) scaleX(1); opacity: 1; }
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
            color: #E0DCD8 !important;
            font-size: 1.08rem !important;
            display: flex !important;
            justify-content: center !important;
            align-items: center !important;
            padding: 0.62rem 0.55rem !important;
            border: none !important;
            background: __MENU_BTN1_BG__ !important;
            background-size: contain !important;
            background-position: center !important;
            background-repeat: no-repeat !important;
            box-shadow: none !important;
            transition: transform 120ms ease, filter 120ms ease, box-shadow 120ms ease !important;
        }
        div[data-testid="stButton"] > button.menu-btn1[kind="primary"] {
            background: __MENU_BTN1_BG__ !important;
            background-size: contain !important;
            background-position: center !important;
            background-repeat: no-repeat !important;
            border: none !important;
        }
        div[data-testid="stButton"] > button.menu-btn2 {
            color: #E0DCD8 !important;
            font-size: 1.08rem !important;
            display: flex !important;
            justify-content: center !important;
            align-items: center !important;
            padding: 0.62rem 0.55rem !important;
            border: none !important;
            background: __MENU_BTN2_BG__ !important;
            background-size: contain !important;
            background-position: center !important;
            background-repeat: no-repeat !important;
            box-shadow: none !important;
            transition: transform 120ms ease, filter 120ms ease, box-shadow 120ms ease !important;
        }
        div[data-testid="stButton"] > button.menu-btn2[kind="primary"] {
            background: __MENU_BTN2_BG__ !important;
            background-size: contain !important;
            background-position: center !important;
            background-repeat: no-repeat !important;
            border: none !important;
        }
        div[data-testid="stButton"] > button.menu-btn3 {
            color: #E0DCD8 !important;
            font-size: 1.08rem !important;
            display: flex !important;
            justify-content: center !important;
            align-items: center !important;
            padding: 0.62rem 0.55rem !important;
            border: none !important;
            background: __MENU_BTN3_BG__ !important;
            background-size: contain !important;
            background-position: center !important;
            background-repeat: no-repeat !important;
            box-shadow: none !important;
            transition: transform 120ms ease, filter 120ms ease, box-shadow 120ms ease !important;
        }
        div[data-testid="stButton"] > button.menu-btn3[kind="primary"] {
            background: __MENU_BTN3_BG__ !important;
            background-size: contain !important;
            background-position: center !important;
            background-repeat: no-repeat !important;
            border: none !important;
        }
        div[data-testid="stButton"] > button.menu-btn4 {
            color: #E0DCD8 !important;
            font-size: 1.08rem !important;
            display: flex !important;
            justify-content: center !important;
            align-items: center !important;
            padding: 0.62rem 0.55rem !important;
            border: none !important;
            background: __MENU_BTN4_BG__ !important;
            background-size: contain !important;
            background-position: center !important;
            background-repeat: no-repeat !important;
            box-shadow: none !important;
            transition: transform 120ms ease, filter 120ms ease, box-shadow 120ms ease !important;
        }
        div[data-testid="stButton"] > button.menu-btn4[kind="primary"] {
            background: __MENU_BTN4_BG__ !important;
            background-size: contain !important;
            background-position: center !important;
            background-repeat: no-repeat !important;
            border: none !important;
        }
        div[data-testid="stButton"] > button.menu-btn-logout {
            color: #FFFFFF !important;
            text-shadow: 0 1px 2px rgba(24, 16, 10, 0.45) !important;
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
        div[data-testid="stButton"] > button.menu-btn4 div {
            color: #E0DCD8 !important;
            font-size: 1.08rem !important;
            font-weight: 700 !important;
            text-shadow: 0 1px 2px rgba(24, 16, 10, 0.45) !important;
        }
        div[data-testid="stButton"] > button.menu-btn-logout p,
        div[data-testid="stButton"] > button.menu-btn-logout span,
        div[data-testid="stButton"] > button.menu-btn-logout div {
            color: #FFFFFF !important;
            font-weight: 700 !important;
            text-shadow: 0 1px 2px rgba(24, 16, 10, 0.45) !important;
        }
        .st-key-owner_logout_bottom div[data-testid="stButton"] > button,
        .st-key-owner_logout_bottom div[data-testid="stButton"] > button p,
        .st-key-owner_logout_bottom div[data-testid="stButton"] > button span,
        .st-key-owner_logout_bottom div[data-testid="stButton"] > button div {
            color: #FFFFFF !important;
            text-shadow: 0 1px 2px rgba(24, 16, 10, 0.45) !important;
        }
        /* 주메뉴: 열 비율만큼 버튼이 가로로 꽉 차게 */
        .st-key-owner-menu-slot-0,
        .st-key-owner-menu-slot-1,
        .st-key-owner-menu-slot-2,
        .st-key-owner-menu-slot-3 {
            width: 100% !important;
            max-width: 100% !important;
            min-width: 0 !important;
        }
        .st-key-owner-menu-slot-0 div[data-testid="stButton"],
        .st-key-owner-menu-slot-1 div[data-testid="stButton"],
        .st-key-owner-menu-slot-2 div[data-testid="stButton"],
        .st-key-owner-menu-slot-3 div[data-testid="stButton"] {
            width: 100% !important;
            max-width: 100% !important;
            min-width: 0 !important;
        }
        /* 주메뉴 버튼 고정 스타일: js가 실패해도 key 기반으로 유지 */
        .st-key-owner-menu-slot-0 div[data-testid="stButton"] > button,
        .st-key-owner-menu-slot-1 div[data-testid="stButton"] > button,
        .st-key-owner-menu-slot-2 div[data-testid="stButton"] > button,
        .st-key-owner-menu-slot-3 div[data-testid="stButton"] > button {
            color: #E0DCD8 !important;
            font-size: 1.1rem !important;
            display: flex !important;
            justify-content: center !important;
            align-items: center !important;
            padding: 0.4rem 0.39rem !important;
            border: none !important;
            box-shadow: none !important;
            transition: transform 120ms ease, filter 120ms ease, box-shadow 120ms ease !important;
            text-shadow: 0 1px 2px rgba(24, 16, 10, 0.45) !important;
            width: 100% !important;
            max-width: 100% !important;
            min-width: 0 !important;
            box-sizing: border-box !important;
            min-height: 2.59rem !important;
        }
        /* 가운데 정렬 (라벨 끝 공백은 Python 라벨 문자열로 조정) */
        .st-key-owner-menu-slot-0 div[data-testid="stButton"] > button > div,
        .st-key-owner-menu-slot-1 div[data-testid="stButton"] > button > div,
        .st-key-owner-menu-slot-2 div[data-testid="stButton"] > button > div,
        .st-key-owner-menu-slot-3 div[data-testid="stButton"] > button > div {
            display: flex !important;
            justify-content: center !important;
            align-items: center !important;
            width: 100% !important;
            margin: 0 !important;
        }
        .st-key-owner-menu-slot-0 div[data-testid="stButton"] > button { background: __MENU_BTN1_BG__ !important; background-size: contain !important; background-position: center !important; background-repeat: no-repeat !important; }
        .st-key-owner-menu-slot-1 div[data-testid="stButton"] > button { background: __MENU_BTN2_BG__ !important; background-size: contain !important; background-position: center !important; background-repeat: no-repeat !important; }
        .st-key-owner-menu-slot-2 div[data-testid="stButton"] > button { background: __MENU_BTN3_BG__ !important; background-size: contain !important; background-position: center !important; background-repeat: no-repeat !important; }
        .st-key-owner-menu-slot-3 div[data-testid="stButton"] > button { background: __MENU_BTN4_BG__ !important; background-size: contain !important; background-position: center !important; background-repeat: no-repeat !important; }
        .st-key-owner-menu-slot-0 div[data-testid="stButton"] > button[kind="primary"] { background: __MENU_BTN1_BG__ !important; background-size: contain !important; background-position: center !important; background-repeat: no-repeat !important; }
        .st-key-owner-menu-slot-1 div[data-testid="stButton"] > button[kind="primary"] { background: __MENU_BTN2_BG__ !important; background-size: contain !important; background-position: center !important; background-repeat: no-repeat !important; }
        .st-key-owner-menu-slot-2 div[data-testid="stButton"] > button[kind="primary"] { background: __MENU_BTN3_BG__ !important; background-size: contain !important; background-position: center !important; background-repeat: no-repeat !important; }
        .st-key-owner-menu-slot-3 div[data-testid="stButton"] > button[kind="primary"] { background: __MENU_BTN4_BG__ !important; background-size: contain !important; background-position: center !important; background-repeat: no-repeat !important; }
        .st-key-owner-menu-slot-0 div[data-testid="stButton"] > button p,
        .st-key-owner-menu-slot-0 div[data-testid="stButton"] > button span,
        .st-key-owner-menu-slot-0 div[data-testid="stButton"] > button div,
        .st-key-owner-menu-slot-1 div[data-testid="stButton"] > button p,
        .st-key-owner-menu-slot-1 div[data-testid="stButton"] > button span,
        .st-key-owner-menu-slot-1 div[data-testid="stButton"] > button div,
        .st-key-owner-menu-slot-2 div[data-testid="stButton"] > button p,
        .st-key-owner-menu-slot-2 div[data-testid="stButton"] > button span,
        .st-key-owner-menu-slot-2 div[data-testid="stButton"] > button div,
        .st-key-owner-menu-slot-3 div[data-testid="stButton"] > button p,
        .st-key-owner-menu-slot-3 div[data-testid="stButton"] > button span,
        .st-key-owner-menu-slot-3 div[data-testid="stButton"] > button div {
            color: #E0DCD8 !important;
            font-size: 1.1rem !important;
            font-weight: 700 !important;
            text-shadow: 0 1px 2px rgba(24, 16, 10, 0.45) !important;
        }
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
        /* 한 줄 4메뉴: 열 동일 비율 (구 JS가 50% 고정하던 문제 보완) */
        div[data-testid="stHorizontalBlock"]:has(.st-key-owner-menu-slot-0):has(.st-key-owner-menu-slot-3) {
            display: flex !important;
            flex-direction: row !important;
            flex-wrap: nowrap !important;
            align-items: center !important;
        }
        div[data-testid="stHorizontalBlock"]:has(.st-key-owner-menu-slot-0):has(.st-key-owner-menu-slot-3) > div[data-testid="stColumn"],
        div[data-testid="stHorizontalBlock"]:has(.st-key-owner-menu-slot-0):has(.st-key-owner-menu-slot-3) > div[data-testid="column"] {
            flex: 1 1 0% !important;
            min-width: 0 !important;
            max-width: none !important;
            width: auto !important;
            align-self: center !important;
        }
        div[data-testid="stHorizontalBlock"]:has(.st-key-owner-menu-slot-0):has(.st-key-owner-menu-slot-3) > div[data-testid="stColumn"] > div,
        div[data-testid="stHorizontalBlock"]:has(.st-key-owner-menu-slot-0):has(.st-key-owner-menu-slot-3) > div[data-testid="column"] > div {
            width: 100% !important;
            max-width: 100% !important;
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
                    <div class='wood-kicker-row' aria-hidden='true'>
                        <span class='wood-line left'></span>
                        <div class='wood-kicker'>STUDIO</div>
                        <span class='wood-line right'></span>
                    </div>
                    <div class='wood-signature-row' aria-hidden='true'>
                        <div class='wood-signature-wrap'>
                            <span class='wood-signature-text'>그리다가</span>
                        </div>
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
        ("회원관리", 0),
        ("재무", 1),
        ("커리큘럼", 2),
        ("마케팅", 3),
    ]

    row = st.columns(4, gap="small")
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

    for col, (label, idx) in zip(row, items):
        _menu_btn(col, label, idx)

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

          function applyBg(btn, bg, mainMenu) {
            if (!bg) return;
            btn.style.setProperty("background", bg, "important");
            btn.style.setProperty("background-size", mainMenu ? "contain" : "cover", "important");
            btn.style.setProperty("background-position", "center", "important");
            btn.style.setProperty("background-repeat", "no-repeat", "important");
            btn.style.setProperty("border", "none", "important");
            btn.style.setProperty("box-shadow", "none", "important");
            if (mainMenu) {
              btn.style.setProperty("color", "#E0DCD8", "important");
              btn.style.setProperty("font-size", "1.1rem", "important");
              btn.style.setProperty("text-shadow", "0 1px 2px rgba(24, 16, 10, 0.45)", "important");
              btn.style.setProperty("display", "flex", "important");
              btn.style.setProperty("justify-content", "center", "important");
              btn.style.setProperty("align-items", "center", "important");
              btn.style.setProperty("padding", "0.4rem 0.39rem", "important");
              btn.style.setProperty("width", "100%", "important");
              btn.style.setProperty("box-sizing", "border-box", "important");
              const wrap = btn.closest('div[data-testid="stButton"]');
              if (wrap) {
                wrap.style.setProperty("width", "100%", "important");
                wrap.style.setProperty("max-width", "100%", "important");
              }
            } else {
              btn.style.setProperty("color", "#FFFFFF", "important");
              btn.style.setProperty("text-shadow", "0 1px 2px rgba(24, 16, 10, 0.45)", "important");
            }
          }

          function applyMenuButtonClasses() {
            try {
              const btns = doc.querySelectorAll('div[data-testid="stButton"] > button');
              btns.forEach((b) => {
                const t = (b.innerText || "").trim();
                if (t.includes("마케팅")) applyBg(b, bgMap["마케팅"], true);
                if (t.includes("회원관리")) applyBg(b, bgMap["회원관리"], true);
                if (t.includes("재무")) applyBg(b, bgMap["재무"], true);
                if (t.includes("커리큘럼")) applyBg(b, bgMap["커리큘럼"], true);
                if (t.includes("로그아웃")) applyBg(b, bgMap["로그아웃"], false);
              });

              // 원장 주메뉴: 한 줄 4버튼은 동일 비율(25%씩). 예전 2×2(한 행에 2버튼)은 50%씩.
              const rows = doc.querySelectorAll('div[data-testid="stHorizontalBlock"]');
              rows.forEach((hb) => {
                const btns = hb.querySelectorAll('div[data-testid="stButton"] > button');
                if (!btns || btns.length < 2) return;
                const texts = Array.from(btns).map((b) => (b.innerText || "").trim());
                const hasM = texts.some((t) => t.includes("마케팅"));
                const hasU = texts.some((t) => t.includes("회원관리"));
                const hasF = texts.some((t) => t.includes("재무"));
                const hasC = texts.some((t) => t.includes("커리큘럼"));
                const isFullMenuRow = hasM && hasU && hasF && hasC && btns.length === 4;
                const isHalfMenuRow =
                  btns.length === 2 &&
                  ((hasM && hasU) || (hasF && hasC));
                if (!isFullMenuRow && !isHalfMenuRow) return;
                hb.style.setProperty("display", "flex", "important");
                hb.style.setProperty("flex-direction", "row", "important");
                hb.style.setProperty("flex-wrap", "nowrap", "important");
                hb.style.setProperty("align-items", "center", "important");
                hb.style.setProperty("gap", "0.5rem", "important");
                if (isFullMenuRow) {
                  Array.from(hb.children).forEach((c) => {
                    c.style.setProperty("flex", "1 1 0%", "important");
                    c.style.setProperty("min-width", "0", "important");
                    c.style.setProperty("max-width", "none", "important");
                    c.style.setProperty("width", "auto", "important");
                    c.style.setProperty("align-self", "center", "important");
                    const inner = c.querySelector('[class*="st-key-owner-menu-slot"]');
                    if (inner) {
                      inner.style.setProperty("width", "100%", "important");
                      inner.style.setProperty("max-width", "100%", "important");
                    }
                  });
                } else {
                  Array.from(hb.children).forEach((c) => {
                    c.style.setProperty("width", "50%", "important");
                    c.style.setProperty("max-width", "50%", "important");
                    c.style.setProperty("min-width", "0", "important");
                    c.style.setProperty("flex", "0 0 50%", "important");
                  });
                }
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