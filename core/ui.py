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