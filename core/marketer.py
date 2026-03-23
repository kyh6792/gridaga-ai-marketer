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

def run_marketing_ui():
    # 1. 시트에서 기본 프롬프트 로드
    current_prompts = load_prompts_from_sheet(DEFAULT_PROMPTS)
    display_categories = list(current_prompts.keys()) + ["📜 히스토리"]

    category = st.radio(
        "🏷️ 지금 어떤 사진을 올리시나요?", 
        display_categories, 
        horizontal=True,
        key="marketing_radio_widget"
    )

    st.markdown("---")

    # ==========================================
    # 분기 1: [📜 히스토리] 모드
    # ==========================================
    if category == "📜 히스토리":
        st.subheader("지난 마케팅 생성 기록")
        hist_df = get_history_data()
        
        if not hist_df.empty:
            # 날짜순 정렬 (최신순)
            hist_df = hist_df.sort_values(by='date', ascending=False)
            hist_df['display_name'] = hist_df['date'] + " [" + hist_df['category'] + "]"
            selected_record = st.selectbox("다시 볼 기록을 선택하세요", hist_df['display_name'])
            
            record_detail = hist_df[hist_df['display_name'] == selected_record].iloc[0]
            
            st.info(f"📅 생성일: {record_detail['date']}  |  🏷️ 카테고리: {record_detail['category']}")
            
          # [수정] 저장된 이미지 링크가 '진짜 문자열'인지 확인하는 로직 추가
            img_link = record_detail.get('image_link', "")
            
            # pd.isna는 판다스에서 빈 값(NaN)인지 체크해줍니다.
            if isinstance(img_link, str) and img_link.strip() != "":
                col1, col2 = st.columns([1, 2])
                with col1:
                    st.link_button("🖼️ 원본 사진 보기", img_link, use_container_width=True)
                with col2:
                    st.caption("구글 드라이브에 저장된 원본 사진 링크입니다.")
            else:
                st.caption("📌 이 기록에는 연결된 원본 사진이 없습니다.")
            
            tab1, tab2 = st.tabs(["📸 인스타그램", "✍️ 네이버 블로그"])
            with tab1:
                st.code(record_detail['instagram'], language="text")
                st.link_button("🚀 인스타그램 열기", "https://www.instagram.com/", use_container_width=True)
            with tab2:
                st.text_area("과거 블로그 내용", value=record_detail['blog'], height=350)
            
            if st.button("🔄 기록 새로고침", use_container_width=True):
                st.rerun()
        else:
            st.info("아직 저장된 히스토리가 없습니다.")
        return 

    # ==========================================
    # 분기 2: [생성 모드]
    # ==========================================
    
    img_source = st.radio(
        "📸 사진을 어디서 가져올까요?",
        ["📱 내 폰에서 올리기", "☁️ 구글 드라이브에서 선택"],
        horizontal=True,
        key="img_source_selector"
    )

    input_image = None
    final_image_link = "" 

    if img_source == "📱 내 폰에서 올리기":
        uploaded_file = st.file_uploader("사진을 선택해주세요.", type=['jpg', 'jpeg', 'png'], key="file_scanner")
        if uploaded_file:
            input_image = Image.open(uploaded_file)
            st.image(input_image, caption="내 폰에서 선택 완료", use_container_width=True)
            # 폰 사진은 '생성하기' 클릭 시 세션 초기화 방지를 위해 폰트 보존

    else: # 구글 드라이브 모드
        folder_id = st.secrets["google_drive"]["folder_id"]
        with st.spinner("드라이브에서 사진 목록을 불러오는 중..."):
            files = get_drive_image_list(folder_id)
        
        if files:
            file_names = [f['name'] for f in files]
            selected_name = st.selectbox("어떤 사진을 분석할까요?", file_names)
            
            selected_file = next(f for f in files if f['name'] == selected_name)
            selected_file_id = selected_file['id']
            
            if st.button("🖼️ 사진 불러오기", use_container_width=True):
                st.session_state['drive_img'] = download_drive_image(selected_file_id)
                st.session_state['last_image_link'] = selected_file.get('webViewLink', '')
            
            if 'drive_img' in st.session_state:
                input_image = st.session_state['drive_img']
                # 드라이브 사진인 경우 기존 링크를 최종 링크 후보로 설정
                final_image_link = st.session_state.get('last_image_link', '')
                st.image(input_image, caption="드라이브에서 불러온 사진", use_container_width=True)
        else:
            st.warning("드라이브 폴더가 비어있거나 권한이 없습니다.")

    # 3. 프롬프트 수정 익스팬더 (기본 스타일 설정)
    with st.expander("⚙️ 기본 문구 스타일 수정하기"):
        st.caption("💡 모든 사진에 공통으로 적용될 말투나 형식을 저장하려면 여기에 적으세요.")
        editable_instruction = st.text_area(
            "마케팅 팀장 지침", 
            value=current_prompts.get(category, ""), 
            height=150,
            key=f"text_area_{category}"
        )
        if st.button("💾 이 스타일을 시트에 영구 저장"):
            save_prompt_to_sheet(category, editable_instruction)
            st.success("시트에 저장되었습니다!")

    st.markdown("---")

    # 4. [신규] 이번 사진만 특별히 요청하기
    st.subheader("📝 이번 사진에만 특별히 요청하기")
    special_request = st.text_input(
        label="예: 아이의 표정을 강조해줘, 태그에 #여름방학 넣어줘 등",
        placeholder="이 사진에만 추가하고 싶은 내용을 적어주세요.",
        key="special_request_input"
    )
    st.caption("⚠️ 항상 적용하고 싶은 규칙은 위 '기본 문구 스타일 수정하기'에 넣고 저장하세요.")

    # 5. 분석 및 생성
    if input_image:
        if st.button("✨ 마케팅 문구 생성하기", type="primary", use_container_width=True):
            with st.spinner("그리다가 AI가 사진을 분석하고 기록하는 중입니다..."):
                try:
                    # 폰 사진 업로드 스킵 로직 (기존 동일)
                    if img_source == "📱 내 폰에서 올리기":
                        final_image_link = ""
                    else:
                        final_image_link = st.session_state.get('last_image_link', '')

                    # Gemini AI 호출
                    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
                    
                    # [수정] 유저가 입력한 특별 요청사항을 프롬프트에 합칩니다.
                    user_prompt = f"""
                    이 사진을 분석해서 인스타그램과 블로그 마케팅 문구를 JSON 형식으로 작성해줘.
                    
                    [특별 요청 사항]
                    {special_request if special_request else "없음 (기본 지침에 충실할 것)"}
                    
                    [출력 형식 가이드]
                    - 결과물에 JSON 구조({{...}})는 절대 노출하지 말고 내용만 보여줄 것.
                    - 문단 나누기와 줄 바꿈을 적극 활용할 것.
                    """
                    
                    response = client.models.generate_content(
                        model=API_MODEL, 
                        config={
                            'system_instruction': editable_instruction,
                            'response_mime_type': 'application/json'
                        },
                        contents=[user_prompt, input_image]
                    )
                    
                    res_data = json.loads(response.text)
                    insta_part = res_data.get("instagram", "")
                    blog_part = res_data.get("blog", "")

                    # 히스토리 저장
                    save_to_history(category, insta_part, blog_part, final_image_link)

                    st.success("분석 완료! 기록되었습니다.")
                    
                    # 결과 출력 (st.code 활용하여 복사 버튼 제공)
                    tab1, tab2 = st.tabs(["📸 인스타그램", "✍️ 네이버 블로그"])
                    with tab1:
                        st.code(insta_part, language="text")
                        st.link_button("🚀 인스타그램 열기", "https://www.instagram.com/studio_gridaga", use_container_width=True)
                    with tab2:
                        st.code(blog_part, language="text")
                        st.link_button("📝 네이버 블로그 글쓰기", "https://blog.naver.com/postwrite", use_container_width=True)

                except Exception as e:
                    st.error(f"분석 중 에러 발생: {e}")