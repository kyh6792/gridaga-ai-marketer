import streamlit as st
from google import genai
from PIL import Image
import json
import re
import os
from datetime import datetime
import pandas as pd
from core.database import load_prompts_from_sheet, save_prompt_to_sheet, get_conn, get_history_data, save_to_history
from core.config import DEFAULT_PROMPTS, API_MODEL
from core.drive import get_drive_image_list, download_drive_image, upload_image_to_drive
from core.drive import display_drive_selector

def run_marketing_ui():
    # 1. 상단 메뉴 (히스토리 분리)
    menu = st.segmented_control(
        "마케팅 메뉴",
        ["✨ 문구 생성", "📜 히스토리"],
        default="✨ 문구 생성",
        label_visibility="collapsed",
    )
    st.markdown("---")

    # [📜 히스토리 모드]
    if menu == "📜 히스토리":
        display_history_ui() # 코드가 길어지므로 별도 함수로 빼는 것을 추천
        return

    # [✨ 생성 모드] 
    # 카테고리 선택 (심플하게)
    current_prompts = load_prompts_from_sheet(DEFAULT_PROMPTS)
    category = st.pills("📍 어떤 사진인가요?", list(current_prompts.keys()), default=list(current_prompts.keys())[0])

    # 2. 사진 업로드 영역 (카드형 레이아웃)
    with st.container(border=True):
        img_source = st.toggle("☁️ 구글 드라이브 사용", value=False)
        input_image = None
        final_image_link = ""

        if not img_source:
            uploaded_file = st.file_uploader("📷 사진을 선택하세요", type=['jpg', 'jpeg', 'png'])
            if uploaded_file:
                input_image = Image.open(uploaded_file)
                st.image(input_image, use_container_width=True)
        else:
            # 드라이브 로직 (간소화)
            input_image, final_image_link = display_drive_selector() # 함수화 추천

    # 3. 요청 사항 (익스팬더로 숨겨서 깔끔하게)
    with st.expander("📝 특별 요청 또는 스타일 수정"):
        special_request = st.text_input("이번 사진에만 적용할 내용", placeholder="예: 해시태그에 #여름방학 추가")
        editable_instruction = st.text_area("기본 AI 지침", value=current_prompts.get(category, ""), height=100)
        if st.button("💾 기본 스타일로 저장"):
            save_prompt_to_sheet(category, editable_instruction)
            st.success("저장 완료!")

    # 4. 생성 버튼 (가장 강조)
    if input_image:
        if st.button("🚀 마케팅 문구 만들기", type="primary", use_container_width=True):
            process_and_display_results(input_image, category, editable_instruction, special_request, final_image_link)

# --- 내부 보조 함수 (가독성을 위해 분리) ---
def process_and_display_results(image, cat, instruction, request, link):
    with st.status("🎨 AI가 작성 중...", expanded=False):
        try:
            api_key = ""
            if "GEMINI_API_KEY" in st.secrets:
                api_key = str(st.secrets["GEMINI_API_KEY"])
            if not api_key and "gemini" in st.secrets and "api_key" in st.secrets["gemini"]:
                api_key = str(st.secrets["gemini"]["api_key"])
            if not api_key:
                st.error("GEMINI_API_KEY가 설정되지 않았습니다.")
                return

            prompt = (
                f"{instruction}\n\n"
                "아래 형식의 JSON만 출력해줘. 설명 문장 금지.\n"
                '{"instagram":"...", "blog":"..."}\n\n'
                f"[카테고리]\n{cat}\n\n"
                f"[추가 요청]\n{request if request else '없음'}"
            )

            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=API_MODEL,
                contents=[prompt, image]
            )
            raw_text = (response.text or "").strip()
            if not raw_text:
                st.error("AI 응답이 비어 있습니다. 잠시 후 다시 시도해주세요.")
                return

            res_data = _parse_marketing_json(raw_text)
            insta_text = str(res_data.get("instagram", "")).strip()
            blog_text = str(res_data.get("blog", "")).strip()
            if not insta_text or not blog_text:
                st.error("AI 응답 형식이 올바르지 않습니다. 다시 시도해주세요.")
                return
        except Exception as e:
            st.error(f"AI 생성 중 오류: {e}")
            return
    
    st.success("✅ 완성되었습니다!")
    t1, t2 = st.tabs(["📸 인스타", "📝 블로그"])
    with t1:
        st.code(insta_text, language="text")
        st.link_button("인스타그램 바로가기", "https://instagram.com", use_container_width=True)
    with t2:
        st.code(blog_text, language="text")
        st.link_button("블로그 바로가기", "https://blog.naver.com", use_container_width=True)

    saved = save_to_history(cat, insta_text, blog_text, link)
    if saved:
        st.caption("히스토리에 저장되었습니다.")


def _parse_marketing_json(text):
    """Gemini 응답에서 JSON 블록을 안전하게 파싱"""
    cleaned = text.strip()
    # ```json ... ``` 형태 대응
    cleaned = re.sub(r"^```json\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^```\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        return json.loads(cleaned)
    except Exception:
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return {}
        try:
            return json.loads(m.group(0))
        except Exception:
            return {}


def display_history_ui():
    st.subheader("📜 생성 히스토리")
    df = get_history_data()
    if df is None or df.empty:
        st.info("저장된 히스토리가 없습니다.")
        return

    for _, row in df.head(30).iterrows():
        with st.container(border=True):
            st.caption(f"{row.get('date', '')} | {row.get('category', '')}")
            st.markdown("**인스타**")
            st.code(str(row.get("instagram", "")), language="text")
            st.markdown("**블로그**")
            st.code(str(row.get("blog", "")), language="text")