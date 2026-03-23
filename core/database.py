import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime

def get_conn():
    """구글 시트 연결 객체 생성 (섹션 이름 매칭)"""
    # secrets.toml의 [connections.google_auth]를 찾아갑니다.
    return st.connection("google_auth", type=GSheetsConnection)

def load_prompts_from_sheet(default_prompts):
    try:
        conn = get_conn()
        # [수정] secrets 계층 구조에 맞춰 URL 참조
        sheet_url = st.secrets["connections"]["google_auth"]["spreadsheet"]
        
        df = conn.read(spreadsheet=sheet_url, ttl=0)
        if 'category' in df.columns and 'prompt' in df.columns:
            return dict(zip(df['category'], df['prompt']))
        return default_prompts
    except Exception as e:
        st.error(f"시트 로드 에러: {e}")
        return default_prompts

def save_prompt_to_sheet(category, new_prompt):
    try:
        conn = get_conn()
        sheet_url = st.secrets["connections"]["google_auth"]["spreadsheet"]
        
        df = conn.read(spreadsheet=sheet_url, ttl=0)
        df.loc[df['category'] == category, 'prompt'] = new_prompt
        conn.update(spreadsheet=sheet_url, data=df)
        st.cache_data.clear()
    except Exception as e:
        st.error(f"프롬프트 저장 에러: {e}")
    
def save_to_history(category, insta_text, blog_text, image_link=""): # image_link 인자 추가
    """마케팅 생성 결과를 구글 시트 'history' 탭에 누적 저장"""
    try:
        conn = get_conn()
        sheet_url = st.secrets["connections"]["google_auth"]["spreadsheet"]
        
        # 1. 기존 데이터 읽기 (없으면 빈 DF 생성)
        try:
            df_history = conn.read(spreadsheet=sheet_url, worksheet="history", ttl=0)
        except:
            # 시트 헤더에 image_link가 있는지 확인 필요
            df_history = pd.DataFrame(columns=["date", "category", "instagram", "blog", "image_link"])
        
        # 2. 새 레코드 생성 (image_link 추가)
        new_row = pd.DataFrame([{
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "category": category,
            "instagram": str(insta_text),
            "blog": str(blog_text),
            "image_link": str(image_link) # 링크 저장
        }])
        
        # 3. 데이터 합치기 및 업데이트
        updated_df = pd.concat([df_history, new_row], ignore_index=True)
        conn.update(spreadsheet=sheet_url, worksheet="history", data=updated_df)
        return True
    except Exception as e:
        st.error(f"히스토리 저장 실패: {e}")
        return False

def get_history_data():
    """히스토리 탭의 전체 데이터를 가져옴 (최신순)"""
    try:
        conn = get_conn()
        # [수정] URL 참조 경로 변경
        sheet_url = st.secrets["connections"]["google_auth"]["spreadsheet"]
        
        df = conn.read(spreadsheet=sheet_url, worksheet="history", ttl=0)
        return df.sort_values(by="date", ascending=False)
    except:
        return pd.DataFrame()