import streamlit as st
import streamlit.components.v1 as components
from google import genai
from PIL import Image, ImageOps
import io
import json
import re
import os
from datetime import datetime
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

import pandas as pd
from core.database import load_prompts_from_sheet, save_prompt_to_sheet, get_conn, get_history_data, save_to_history
from core.config import DEFAULT_PROMPTS, API_MODEL
from core import drive_oauth
from core.drive import display_drive_selector, get_drive_folder_id, upload_image_to_drive, upload_bytes_to_drive


def _render_copy_text_box(label: str, text: str, key: str):
    """코드블록 대신 줄바꿈되는 문구 박스."""
    t = str(text or "")
    line_count = max(4, min(16, len(t.splitlines()) + 2))
    st.text_area(
        label,
        value=t,
        key=key,
        height=24 * line_count + 20,
        help="내용 선택 후 복사해서 사용하세요.",
    )


def _render_copy_button(text: str, key: str, label: str = "📋 복사하기"):
    """클립보드 복사 버튼 (실패 시 안내)."""
    if st.button(label, key=key, use_container_width=True):
        payload = json.dumps(str(text or ""))
        components.html(
            f"""
            <script>
            (async () => {{
              try {{
                const txt = {payload};
                await navigator.clipboard.writeText(txt);
              }} catch (e) {{}}
            }})();
            </script>
            """,
            height=0,
        )
        st.toast("클립보드에 복사했어요.")


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
    current_prompts = load_prompts_from_sheet(DEFAULT_PROMPTS)
    category_options = list(current_prompts.keys())
    if "marketing_category" not in st.session_state and category_options:
        st.session_state["marketing_category"] = category_options[0]
    category = st.session_state.get("marketing_category", category_options[0] if category_options else "")

    # 2. 사진 업로드 영역 (카드형 레이아웃)
    with st.container(border=True):
        img_source = st.toggle("☁️ 구글 드라이브 사용", value=False)
        input_image = None
        final_image_link = ""
        auto_upload_after_generate = False
        original_upload = None

        if not img_source:
            has_folder = bool(get_drive_folder_id())
            oauth_on = drive_oauth.oauth_google_drive_configured()
            oauth_ok = drive_oauth.has_valid_session_credentials() if oauth_on else True

            # 업로드 전에 연결 상태를 먼저 확인할 수 있게 상단에 배치
            if oauth_on:
                st.caption("먼저 Google 드라이브 연결 상태를 확인하세요.")
                drive_oauth.render_google_drive_oauth_panel()
                oauth_ok = drive_oauth.has_valid_session_credentials()
                if not oauth_ok:
                    st.info("먼저 **연결**을 완료하면, 이미지 업로드 후 다시 불러올 필요가 줄어듭니다.")

            uploaded_file = st.file_uploader("📷 사진을 선택하세요", type=['jpg', 'jpeg', 'png'])
            if uploaded_file:
                original_upload = {
                    "bytes": uploaded_file.getvalue(),
                    "name": str(getattr(uploaded_file, "name", "") or "").strip(),
                    "mime_type": str(getattr(uploaded_file, "type", "") or "").strip() or "application/octet-stream",
                }
                # 휴대폰 사진 EXIF 방향값 반영 (회전/뒤집힘 방지)
                input_image = ImageOps.exif_transpose(Image.open(uploaded_file))
                st.image(input_image, use_container_width=True)
                can_upload = has_folder and oauth_ok if oauth_on else has_folder
                default_on = bool(can_upload and (oauth_ok if oauth_on else has_folder))
                auto_upload_after_generate = st.checkbox(
                    "문구 생성 후 이 사진을 구글 드라이브에 자동 업로드",
                    value=default_on,
                    disabled=not can_upload,
                    help="생성 직후 지정 폴더에 사진 업로드. OAuth면 옆 **연결**, 아니면 서비스 계정.",
                )
                if not has_folder:
                    st.caption("secrets에 `folder_id` 필요")
                elif oauth_on and not oauth_ok:
                    st.caption("자동 업로드 쓰려면 옆 **연결**")
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

    # 4. 생성할 문구 범위 + 생성 버튼
    if input_image:
        category = st.pills(
            "📍 어떤 사진인가요?",
            category_options,
            default=category_options[0] if category_options else "",
            key="marketing_category",
        )
        output_choice = st.segmented_control(
            "만들 문구",
            ["둘 다", "인스타만", "블로그만"],
            default="둘 다",
            help="한 종류만 선택하면 토큰·시간을 줄일 수 있습니다.",
        )
        if st.button("🚀 마케팅 문구 만들기", type="primary", use_container_width=True):
            mode = {"둘 다": "both", "인스타만": "instagram", "블로그만": "blog"}[output_choice]
            process_and_display_results(
                input_image,
                category,
                editable_instruction,
                special_request,
                final_image_link,
                auto_upload_after_generate=auto_upload_after_generate,
                output_mode=mode,
                original_upload=original_upload,
            )

# --- 내부 보조 함수 (가독성을 위해 분리) ---
def process_and_display_results(
    image,
    cat,
    instruction,
    request,
    link,
    *,
    auto_upload_after_generate=False,
    output_mode: str = "both",
    original_upload: dict | None = None,
):
    """output_mode: both | instagram | blog"""
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

            if output_mode == "both":
                json_line = '{"instagram":"...", "blog":"..."}'
                scope_hint = "instagram, blog 키를 모두 채워라."
            elif output_mode == "instagram":
                json_line = '{"instagram":"..."}'
                scope_hint = "instagram 키만 출력한다. blog 키는 넣지 마라."
            else:
                json_line = '{"blog":"..."}'
                scope_hint = "blog 키만 출력한다. instagram 키는 넣지 마라."

            prompt = (
                f"{instruction}\n\n"
                "아래 형식의 JSON만 출력해줘. 설명 문장 금지.\n"
                f"{json_line}\n"
                f"{scope_hint}\n\n"
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
            if output_mode == "both":
                if not insta_text or not blog_text:
                    st.error("AI 응답 형식이 올바르지 않습니다. 다시 시도해주세요.")
                    return
            elif output_mode == "instagram":
                if not insta_text:
                    st.error("인스타 문구를 받지 못했습니다. 다시 시도해주세요.")
                    return
                blog_text = ""
            else:
                if not blog_text:
                    st.error("블로그 문구를 받지 못했습니다. 다시 시도해주세요.")
                    return
                insta_text = ""
        except Exception as e:
            st.error(f"AI 생성 중 오류: {e}")
            return

    final_link = (link or "").strip()
    if not final_link and auto_upload_after_generate:
        folder_id = get_drive_folder_id()
        if folder_id:
            use_oauth = drive_oauth.oauth_google_drive_configured()
            user_creds = drive_oauth.get_session_credentials() if use_oauth else None
            if use_oauth and user_creds is None:
                st.warning("드라이브 연결 안 됨 — 업로드 생략")
            else:
                with st.spinner("☁️ 드라이브에 원본 사진 저장 중..."):
                    if original_upload and original_upload.get("bytes"):
                        original_name = str(original_upload.get("name", "")).strip()
                        if not original_name:
                            original_name = f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                        up = upload_bytes_to_drive(
                            data=original_upload.get("bytes", b""),
                            file_name=original_name,
                            folder_id=folder_id,
                            mime_type=str(original_upload.get("mime_type", "") or "application/octet-stream"),
                            add_anyone_reader=True,
                            user_credentials=user_creds if use_oauth else None,
                        )
                    else:
                        # 드라이브에서 고른 이미지 등 원본 bytes가 없을 때만 기존 JPG 변환 업로드 사용
                        up = upload_image_to_drive(
                            image,
                            folder_id,
                            cat,
                            user_credentials=user_creds if use_oauth else None,
                        )
                if up and up.get("link"):
                    final_link = str(up["link"]).strip()
                    st.caption(f"드라이브에 저장됨: {final_link}")
                elif up and up.get("id"):
                    st.caption(
                        "드라이브에는 올라갔으나 웹 링크를 가져오지 못했습니다. 드라이브에서 파일을 확인하세요."
                    )
    
    st.success("✅ 완성되었습니다!")
    render_key = datetime.now().strftime("%Y%m%d%H%M%S%f")
    if output_mode == "both":
        t1, t2 = st.tabs(["📸 인스타", "📝 블로그"])
        with t1:
            _render_copy_text_box("인스타 문구", insta_text, key=f"mk_out_insta_{render_key}")
            _render_copy_button(insta_text, key=f"mk_out_copy_insta_{render_key}")
            st.link_button("인스타그램 바로가기", "https://instagram.com", use_container_width=True)
        with t2:
            _render_copy_text_box("블로그 문구", blog_text, key=f"mk_out_blog_{render_key}")
            _render_copy_button(blog_text, key=f"mk_out_copy_blog_{render_key}")
            st.link_button("블로그 바로가기", "https://blog.naver.com", use_container_width=True)
    elif output_mode == "instagram":
        st.markdown("**📸 인스타**")
        _render_copy_text_box("인스타 문구", insta_text, key=f"mk_out_insta_{render_key}")
        _render_copy_button(insta_text, key=f"mk_out_copy_insta_{render_key}")
        st.link_button("인스타그램 바로가기", "https://instagram.com", use_container_width=True)
    else:
        st.markdown("**📝 블로그**")
        _render_copy_text_box("블로그 문구", blog_text, key=f"mk_out_blog_{render_key}")
        _render_copy_button(blog_text, key=f"mk_out_copy_blog_{render_key}")
        st.link_button("블로그 바로가기", "https://blog.naver.com", use_container_width=True)

    saved = save_to_history(cat, insta_text, blog_text, final_link)
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


def _normalize_history_image_link(raw) -> str | None:
    """시트 빈칸·0·NaN 제거 후 http 링크만."""
    try:
        if raw is None or (isinstance(raw, float) and pd.isna(raw)):
            return None
    except Exception:
        pass
    u = str(raw).strip()
    if not u or u.lower() in ("nan", "none", "0", "0.0"):
        return None
    if not u.startswith("http"):
        return None
    return u


def _drive_file_id_from_url(u: str) -> str | None:
    m = re.search(r"drive\.google\.com/file/d/([a-zA-Z0-9_-]+)", u)
    if m:
        return m.group(1)
    m = re.search(r"drive\.google\.com/open\?[^#]*\bid=([a-zA-Z0-9_-]+)", u)
    if m:
        return m.group(1)
    return None


def _history_fetch_image_for_preview(page_url: str) -> Image.Image | None:
    """URL을 받아 실제 이미지면 PIL Image로. HTML/오류면 None (st.image(URL) 깨짐 방지)."""
    fid = _drive_file_id_from_url(page_url)
    candidates = []
    if fid:
        candidates.append(f"https://drive.google.com/uc?export=download&id={fid}")
        candidates.append(f"https://drive.google.com/uc?export=view&id={fid}")
    else:
        candidates.append(page_url)

    for url in candidates:
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; GiridagaApp/1.0)"})
            with urlopen(req, timeout=12) as resp:
                data = resp.read()
            if not data or len(data) < 24:
                continue
            if data[:1] == b"<" or data[:4] in (b"\xef\xbb\xbf<", b"<!DO", b"<htm"):
                continue
            bio = io.BytesIO(data)
            img = Image.open(bio)
            img.load()
            if img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")
            return img
        except (URLError, HTTPError, OSError, ValueError, TypeError):
            continue
    return None


def _history_filter_today(df: pd.DataFrame) -> pd.DataFrame:
    """date 컬럼 기준 오늘(로컬 날짜) 행만."""
    if df is None or df.empty or "date" not in df.columns:
        return pd.DataFrame()
    today = datetime.now().strftime("%Y-%m-%d")
    d = df["date"].astype(str).str.strip().str[:10]
    return df.loc[d == today].copy()


def display_history_ui():
    st.subheader("📜 생성 히스토리")
    df = get_history_data()
    if df is None or df.empty:
        st.info("저장된 히스토리가 없습니다.")
        return

    df_today = _history_filter_today(df)
    if df_today.empty:
        st.info(f"오늘({datetime.now().strftime('%Y-%m-%d')}) 저장된 히스토리가 없습니다.")
        return

    total = len(df_today)
    today_str = datetime.now().strftime("%Y-%m-%d")
    st.caption(f"오늘({today_str}) · 총 {total}건")

    vis_key = f"marketing_history_visible_{today_str}"
    if vis_key not in st.session_state:
        st.session_state[vis_key] = 10

    requested = int(st.session_state[vis_key])
    n_show = min(requested, total)
    if requested > total:
        st.session_state[vis_key] = total

    chunk = df_today.iloc[:n_show]

    for _, row in chunk.iterrows():
        page_href = _normalize_history_image_link(row.get("image_link", ""))
        pil_img = _history_fetch_image_for_preview(page_href) if page_href else None

        with st.container(border=True):
            cap = f"{row.get('date', '')} | {row.get('category', '')}"
            if page_href:
                c_img, c_body = st.columns([0.32, 0.68], vertical_alignment="top")
                with c_img:
                    if pil_img is not None:
                        st.image(pil_img, use_container_width=True)
                    else:
                        st.markdown("##### 🖼️")
                        st.caption("미리보기 불가(권한·드라이브)")
                    st.link_button("원본", page_href, use_container_width=True)
                with c_body:
                    st.caption(cap)
                    st.markdown("**인스타**")
                    _render_copy_text_box(
                        "인스타 문구",
                        str(row.get("instagram", "")),
                        key=f"mk_hist_insta_{str(row.get('date', ''))}_{str(row.get('category', ''))}",
                    )
                    _render_copy_button(
                        str(row.get("instagram", "")),
                        key=f"mk_hist_copy_insta_{str(row.get('date', ''))}_{str(row.get('category', ''))}",
                    )
                    st.markdown("**블로그**")
                    _render_copy_text_box(
                        "블로그 문구",
                        str(row.get("blog", "")),
                        key=f"mk_hist_blog_{str(row.get('date', ''))}_{str(row.get('category', ''))}",
                    )
                    _render_copy_button(
                        str(row.get("blog", "")),
                        key=f"mk_hist_copy_blog_{str(row.get('date', ''))}_{str(row.get('category', ''))}",
                    )
            else:
                st.caption(cap)
                st.markdown("**인스타**")
                _render_copy_text_box(
                    "인스타 문구",
                    str(row.get("instagram", "")),
                    key=f"mk_hist_nolink_insta_{str(row.get('date', ''))}_{str(row.get('category', ''))}",
                )
                _render_copy_button(
                    str(row.get("instagram", "")),
                    key=f"mk_hist_nolink_copy_insta_{str(row.get('date', ''))}_{str(row.get('category', ''))}",
                )
                st.markdown("**블로그**")
                _render_copy_text_box(
                    "블로그 문구",
                    str(row.get("blog", "")),
                    key=f"mk_hist_nolink_blog_{str(row.get('date', ''))}_{str(row.get('category', ''))}",
                )
                _render_copy_button(
                    str(row.get("blog", "")),
                    key=f"mk_hist_nolink_copy_blog_{str(row.get('date', ''))}_{str(row.get('category', ''))}",
                )

    if n_show < total:
        more = min(10, total - n_show)
        if st.button(f"더보기 ({more}개)", key="marketing_history_more", use_container_width=True):
            st.session_state[vis_key] = n_show + 10
            st.rerun()