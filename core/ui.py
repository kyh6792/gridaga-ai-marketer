import streamlit as st
import time
from PIL import Image
# core/ui_style.py (또는 ui.py)

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
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Nanum+Myeongjo:wght@400;700&family=Nanum+Gothic:wght@400;700&display=swap');

        /* 전체 기본 폰트 */
        html, body, [class*="css"], .stApp {
            font-family: 'Nanum Gothic', sans-serif;
            color: #4A4A4A;
        }

        /* 제목/헤더 명조체 */
        h1, h2, h3, .stHeader, [data-testid="stHeader"] {
            font-family: 'Nanum Myeongjo', serif !important;
            color: #4A4A4A !important;
        }

        /* 배경색 */
        .stApp {
            background-color: #FCF9F2;
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
    """, unsafe_allow_html=True)


    
def display_intro(image_path, duration=2.5):
    """인트로 화면 표시 및 스타일 주입"""
    # 1. 스타일 먼저 적용
    set_custom_style()
    
    if 'intro_done' not in st.session_state:
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
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Nanum+Myeongjo:wght@700&family=Nanum+Gothic:wght@400;700&display=swap');
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
        .sticky-owner-header {
            position: sticky;
            top: 0;
            z-index: 999;
            background: linear-gradient(180deg, #7A5638 0%, #8D6747 42%, #B18A68 100%);
            padding: 0.9rem 0 1.05rem 0;
            margin-bottom: 0;
            border-bottom: 1px solid #8A674A;
        }
        .sticky-owner-header.full-bleed {
            width: 100vw;
            margin-left: calc(50% - 50vw);
            margin-right: calc(50% - 50vw);
            margin-top: -0.6rem;
            padding-left: 1rem;
            padding-right: 1rem;
            box-sizing: border-box;
        }
        .sticky-owner-header .header-inner {
            max-width: 760px;
            margin: 0 auto;
        }
        .stApp {
            background: linear-gradient(180deg, #E2CCB3 0%, #D6B693 100%) !important;
        }
        [data-testid="stAppViewContainer"] {
            background: linear-gradient(180deg, #E2CCB3 0%, #D6B693 100%) !important;
        }
        .block-container {
            padding-top: 0 !important;
            padding-left: 0.45rem !important;
            padding-right: 0.45rem !important;
            max-width: 980px !important;
        }
        .stExpander {
            margin-top: 0 !important;
            padding-top: 0 !important;
        }
        [data-testid="stExpander"] {
            margin-top: 0 !important;
        }
        .wood-kicker {
            font-family: 'Nanum Gothic', sans-serif !important;
            color: #E9DCCF;
            font-size: 0.68rem;
            letter-spacing: 0.28em;
            font-weight: 700;
            line-height: 1;
            margin-bottom: 0.12rem;
            text-transform: uppercase;
        }
        .wood-title-main {
            font-weight: 700;
            color: #FFFFFF;
            font-size: 2.18rem;
            line-height: 1.05;
            margin-bottom: 0;
            letter-spacing: 0.012em;
            font-family: 'Nanum Myeongjo', serif !important;
            text-shadow: 0 1px 2px rgba(40, 28, 20, 0.35);
        }
        .wood-brush {
            margin-top: 0.28rem;
            width: 142px;
            height: 6px;
            border-radius: 999px;
            background: linear-gradient(90deg, #E8C49A 0%, #E0AD90 50%, #D59578 100%);
            opacity: 0.88;
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
        }
        .menu-card.active {
            border: 2px solid #F5D8A8;
            box-shadow: 0 0 0 2px rgba(245, 216, 168, 0.35), 0 4px 12px rgba(60, 41, 25, 0.32);
            transform: translateY(-1px);
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
        """,
        unsafe_allow_html=True,
    )


def render_owner_brand_header():
    st.markdown(
        """
        <div class='sticky-owner-header full-bleed'>
            <div class='header-inner'>
                <div class='wood-kicker'>STUDIO</div>
                <div class='wood-title-main'>그리다가</div>
                <div class='wood-brush'></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_owner_menu_grid(owner_login_at, active_idx=None):
    del owner_login_at  # 버튼 기반 전환으로 링크 쿼리 조합은 더 이상 사용하지 않음.

    items = [
        ("📢 마케팅", 0),
        ("👥 원생관리", 1),
        ("💰 재무", 2),
        ("📚 커리큘럼", 3),
    ]

    row1 = st.columns(2)
    row2 = st.columns(2)

    def _menu_btn(col, label, idx):
        # active_idx만 쓰면 버튼 처리보다 먼저 잡혀 한 박자 늦을 수 있어, 항상 최신 session 기준
        cur = int(st.session_state.get("owner_menu_index", active_idx if active_idx is not None else 0))
        is_active = cur == idx
        with col:
            if st.button(
                label,
                key=f"owner_menu_btn_{idx}",
                use_container_width=True,
                type="primary" if is_active else "secondary",
            ):
                st.session_state["owner_menu_index"] = idx
                st.query_params["owner_menu_idx"] = str(idx)

    _menu_btn(row1[0], items[0][0], items[0][1])
    _menu_btn(row1[1], items[1][0], items[1][1])
    _menu_btn(row2[0], items[2][0], items[2][1])
    _menu_btn(row2[1], items[3][0], items[3][1])