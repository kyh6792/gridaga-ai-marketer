import streamlit as st
import pandas as pd
from datetime import datetime
import time
from core.perf import perf_log

def get_conn():
    _t0 = time.perf_counter()
    # DB_BACKEND=gsheets|supabase. Returns an object exposing read/update methods.
    from core.db_conn import DBConn

    key = "_singleton_db_conn"
    conn = st.session_state.get(key)
    if conn is None:
        conn = DBConn()
        st.session_state[key] = conn
        perf_log("db.get_conn.create", (time.perf_counter() - _t0) * 1000.0)
    else:
        perf_log("db.get_conn.cache_hit", (time.perf_counter() - _t0) * 1000.0)
    return conn


def reset_gsheets_connection():
    """시크릿 변경·연결 오류 후 수동으로 다시 붙일 때만 사용."""
    st.session_state.pop("_singleton_db_conn", None)


def get_sheet_url():
    """시트 접근용 URL/ID를 secrets에서 안전하게 가져옵니다."""
    try:
        if "GSHEETS_URL" in st.secrets:
            return st.secrets["GSHEETS_URL"]
        if "connections" in st.secrets and "google_drive" in st.secrets["connections"]:
            conn_cfg = st.secrets["connections"]["google_drive"]
            if "spreadsheet" in conn_cfg:
                return conn_cfg["spreadsheet"]
    except Exception:
        pass
    return ""


def get_prompt_worksheet():
    """프롬프트 워크시트명(기본: prompt)"""
    try:
        if "PROMPT_WORKSHEET" in st.secrets:
            return str(st.secrets["PROMPT_WORKSHEET"])
    except Exception:
        pass
    return "prompt"


def _read_prompt_sheet(conn, sheet_url, *, ttl=60, discover_fallbacks=True):
    """프롬프트 구조(category/prompt)를 가진 워크시트를 찾아 읽습니다."""
    configured_ws = get_prompt_worksheet()
    last_error = None

    try:
        df = conn.read(spreadsheet=sheet_url, worksheet=configured_ws, ttl=ttl)
        if isinstance(df, pd.DataFrame) and not df.empty:
            if "category" in df.columns and "prompt" in df.columns:
                return df, configured_ws
    except Exception as e:
        last_error = e

    if not discover_fallbacks:
        if last_error:
            raise last_error
        return pd.DataFrame(), None

    candidate_worksheets = [w for w in ("prompts", "Tab", "sheet1", "Sheet1") if w != configured_ws]
    for ws in candidate_worksheets:
        try:
            df = conn.read(spreadsheet=sheet_url, worksheet=ws, ttl=ttl)
            if isinstance(df, pd.DataFrame) and not df.empty:
                if "category" in df.columns and "prompt" in df.columns:
                    return df, ws
        except Exception as e:
            last_error = e

    try:
        df = conn.read(spreadsheet=sheet_url, ttl=ttl)
        if isinstance(df, pd.DataFrame) and "category" in df.columns and "prompt" in df.columns:
            return df, None
    except Exception as e:
        last_error = e

    if last_error:
        raise last_error
    return pd.DataFrame(), None


@st.cache_data(show_spinner=False, ttl=300)
def _cached_prompt_records(_backend: str, _worksheet: str, _sheet_url: str):
    """세션을 넘어 재사용되는 프롬프트 캐시(인스턴스 전역)."""
    conn = get_conn()
    # Supabase/gsheets 모두 DBConn.read를 통해 동일 인터페이스로 조회
    df = conn.read(worksheet=_worksheet, ttl=60)
    if isinstance(df, pd.DataFrame) and "category" in df.columns and "prompt" in df.columns:
        out = (
            df[["category", "prompt"]]
            .astype(str)
            .dropna(how="all")
            .to_dict(orient="records")
        )
        return out
    return []


def load_prompts_from_sheet(default_prompts):
    _t0 = time.perf_counter()
    try:
        conn = get_conn()
        backend = str(getattr(conn, "backend", "gsheets"))
        worksheet = get_prompt_worksheet()
        sheet_url = get_sheet_url()

        # 인스턴스 전역 캐시 우선(새 세션/F5에도 재사용)
        try:
            recs = _cached_prompt_records(backend, worksheet, sheet_url)
            if recs:
                out = {str(r.get("category", "")): str(r.get("prompt", "")) for r in recs if r.get("category")}
                if out:
                    perf_log("db.load_prompts.cached_records", (time.perf_counter() - _t0) * 1000.0)
                    return out
        except Exception:
            pass

        # Supabase path
        try:
            df = conn.read(worksheet=worksheet, ttl=60)
            if isinstance(df, pd.DataFrame) and 'category' in df.columns and 'prompt' in df.columns:
                return dict(zip(df['category'], df['prompt']))
        except Exception:
            pass

        if not sheet_url:
            return default_prompts

        df, _ = _read_prompt_sheet(conn, sheet_url)
        if 'category' in df.columns and 'prompt' in df.columns:
            out = dict(zip(df['category'], df['prompt']))
            perf_log("db.load_prompts.success", (time.perf_counter() - _t0) * 1000.0)
            return out
        return default_prompts
    except Exception as e:
        st.error(f"시트 로드 에러: {repr(e)}")
        perf_log("db.load_prompts.error", (time.perf_counter() - _t0) * 1000.0)
        return default_prompts

def save_prompt_to_sheet(category, new_prompt):
    _t0 = time.perf_counter()
    try:
        conn = get_conn()
        _cached_prompt_records.clear()
        # Supabase path: upsert single row
        try:
            df = pd.DataFrame([{"category": str(category), "prompt": str(new_prompt)}])
            conn.update(worksheet=get_prompt_worksheet(), data=df)
            perf_log("db.save_prompt.supabase", (time.perf_counter() - _t0) * 1000.0)
            return
        except Exception:
            pass

        sheet_url = get_sheet_url()
        if not sheet_url:
            st.error("시트 URL 설정을 찾을 수 없습니다.")
            return

        df, worksheet = _read_prompt_sheet(conn, sheet_url, ttl=0, discover_fallbacks=True)
        if df.empty:
            st.error("프롬프트 시트를 찾지 못했습니다. 시트 탭과 컬럼(category, prompt)을 확인해주세요.")
            return
        df.loc[df['category'] == category, 'prompt'] = new_prompt
        if worksheet:
            conn.update(spreadsheet=sheet_url, worksheet=worksheet, data=df)
        else:
            conn.update(spreadsheet=sheet_url, data=df)
        perf_log("db.save_prompt.gsheets", (time.perf_counter() - _t0) * 1000.0)
    except Exception as e:
        st.error(f"프롬프트 저장 에러: {repr(e)}")
        perf_log("db.save_prompt.error", (time.perf_counter() - _t0) * 1000.0)
    
def save_to_history(category, insta_text, blog_text, image_link=""): # image_link 인자 추가
    """마케팅 생성 결과를 구글 시트 'history' 탭에 누적 저장"""
    try:
        conn = get_conn()
        sheet_url = get_sheet_url()
        if not sheet_url:
            st.error("시트 URL 설정을 찾을 수 없습니다.")
            return False
        
        # 1. 기존 데이터 읽기 (없으면 빈 DF 생성)
        try:
            df_history = conn.read(spreadsheet=sheet_url, worksheet="history", ttl=0)
        except Exception:
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
        sheet_url = get_sheet_url()
        if not sheet_url:
            return pd.DataFrame()
        
        df = conn.read(spreadsheet=sheet_url, worksheet="history", ttl=60)
        return df.sort_values(by="date", ascending=False)
    except Exception:
        return pd.DataFrame()