import io
import os
import re
from datetime import datetime

import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload, MediaIoBaseUpload
from PIL import Image, ImageOps

_HEIF_ENABLED = False
try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
    _HEIF_ENABLED = True
except Exception:
    _HEIF_ENABLED = False

# 시트 연결용 [connections.google_drive]에 들어 있는 앱 전용 키 (서비스 계정 JSON 아님)
_DRIVE_SECRETS_APP_KEYS = frozenset({"folder_id", "spreadsheet", "backup_folder_id"})

# Drive API 호출에 명시적 스코프 (미지정 시 insufficientPermissions 403이 나는 경우가 있음)
_DRIVE_SCOPES = ("https://www.googleapis.com/auth/drive",)


def _raw_drive_secrets():
    """Streamlit 표준 [connections.google_drive] 또는 레거시 최상위 [google_drive]."""
    try:
        if "connections" in st.secrets and "google_drive" in st.secrets["connections"]:
            return dict(st.secrets["connections"]["google_drive"])
    except Exception:
        pass
    try:
        if "google_drive" in st.secrets:
            return dict(st.secrets["google_drive"])
    except Exception:
        pass
    return None


def _service_account_info_dict():
    """Google Credentials.from_service_account_info()용 dict (folder_id 등 제외)."""
    raw = _raw_drive_secrets()
    if not raw:
        return None
    return {k: v for k, v in raw.items() if k not in _DRIVE_SECRETS_APP_KEYS}


def get_drive_folder_id():
    """마케팅 업로드·갤러리용 드라이브 폴더 ID (secrets의 connections.google_drive.folder_id)."""
    raw = _raw_drive_secrets()
    if not raw:
        return None
    fid = raw.get("folder_id")
    return str(fid).strip() if fid else None


def get_backup_folder_id():
    """일일 시트 백업 업로드 폴더. `backup_folder_id` 없으면 `folder_id`와 동일."""
    raw = _raw_drive_secrets()
    if not raw:
        return None
    fid = raw.get("backup_folder_id") or raw.get("folder_id")
    return str(fid).strip() if fid else None


def get_service_account_credentials(scopes: tuple[str, ...] | None = None):
    """서비스 계정 Credentials. scopes 미지정 시 Drive 전용."""
    creds_info = _service_account_info_dict()
    if not creds_info:
        return None
    s = list(scopes) if scopes is not None else list(_DRIVE_SCOPES)
    return service_account.Credentials.from_service_account_info(creds_info, scopes=s)


# [핵심] 구글 서비스 연결 객체를 만드는 함수
def get_drive_service():
    """인증 정보를 사용하여 구글 드라이브 서비스 객체 생성"""
    creds = get_service_account_credentials()
    if not creds:
        raise KeyError(
            'google_drive: secrets에 [connections.google_drive] 블록(또는 google_drive)을 설정해주세요.'
        )
    return build("drive", "v3", credentials=creds)


def upload_bytes_to_drive(
    data: bytes,
    file_name: str,
    folder_id: str,
    mime_type: str = "application/octet-stream",
    *,
    add_anyone_reader: bool = False,
    user_credentials=None,
) -> dict | None:
    """바이너리를 드라이브 폴더에 업로드. 실패 시 None.

    user_credentials: OAuth Credentials 시 본인 드라이브 업로드(개인 folder_id).
    """
    try:
        if user_credentials is not None:
            service = build("drive", "v3", credentials=user_credentials)
        else:
            service = get_drive_service()
        media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime_type, resumable=True)
        body = {"name": file_name, "parents": [folder_id]}
        file = service.files().create(
            body=body,
            media_body=media,
            fields="id, webViewLink",
            supportsAllDrives=True,
            ignoreDefaultVisibility=True,
        ).execute()
        if add_anyone_reader:
            try:
                service.permissions().create(
                    fileId=file.get("id"),
                    body={"type": "anyone", "role": "reader"},
                    supportsAllDrives=True,
                ).execute()
            except Exception:
                pass
        return {"id": file.get("id"), "link": file.get("webViewLink")}
    except Exception:
        return None

def get_drive_image_list(folder_id):
    """파일 목록을 가져올 때 'service' 객체를 호출하여 사용"""
    try:
        # [수정] 위에서 만든 함수를 통해 'service' 열쇠를 가져옵니다.
        service = get_drive_service()
        
        results = service.files().list(
            q=f"'{folder_id}' in parents and trashed = false and mimeType contains 'image/'",
            fields="files(id, name, thumbnailLink, webViewLink, mimeType, modifiedTime)",
            orderBy="modifiedTime desc,name_natural",
            pageSize=300,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        return results.get('files', [])
    except Exception as e:
        st.error(f"드라이브 목록 로드 실패: {e}")
        return []

def upload_image_to_drive(pil_image, folder_id, category, user_credentials=None):
    """PIL 이미지를 구글 드라이브에 업로드하고 링크 반환 (WinError 32 방어).

    user_credentials: google.oauth2.credentials.Credentials (OAuth). None이면 서비스 계정.
    """
    if pil_image.mode in ("RGBA", "P", "LA"):
        pil_image = pil_image.convert("RGB")

    if user_credentials is not None:
        service = build("drive", "v3", credentials=user_credentials)
    else:
        service = get_drive_service()
    
    # 1. 파일명 정제 (특수문자 제거)
    time_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_category = re.sub(r'[^\w\s]', '', category).replace(" ", "_")
    file_name = f"gridaga_{time_str}_{safe_category}.jpg"
    
    # 임시 파일 경로 설정
    temp_path = os.path.join(os.getcwd(), file_name)
    media = None # 미디어 객체 초기화
    
    try:
        # PIL 이미지를 로컬에 임시 저장
        pil_image.save(temp_path, format='JPEG')
        
        # 2. 메타데이터 및 미디어 정의
        file_metadata = {
            'name': file_name,
            'parents': [folder_id]
        }
        
        # 미디어 업로드 객체 생성
        media = MediaFileUpload(temp_path, mimetype='image/jpeg', resumable=True)
        
# 3. [핵심 수정] supportsAllDrives와 인자 추가
        # 서비스 계정이 개인이 아닌 '공유된 공간'에 자원을 쓴다는 것을 명시합니다.
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink',
            supportsAllDrives=True,       # 모든 드라이브 지원 권한 사용
            ignoreDefaultVisibility=True  # 기본 가시성 설정 무시 (소유권 이슈 방지)
        ).execute()

        # 조직(Workspace) 정책으로 "링크가 있는 모든 사용자" 공개가 막히면 403 — 업로드 자체는 성공한 상태
        try:
            service.permissions().create(
                fileId=file.get("id"),
                body={"type": "anyone", "role": "reader"},
                supportsAllDrives=True,
            ).execute()
        except Exception as perm_err:
            st.warning(
                "파일은 업로드되었으나 '누구나 보기' 공개는 조직 정책 등으로 설정되지 않았습니다. "
                f"({perm_err})"
            )

        return {
            'id': file.get('id'),
            'link': file.get('webViewLink')
        }
        
    except Exception as e:
        err_txt = str(e)
        is_sa_quota = user_credentials is None and (
            "Service Accounts do not have storage quota" in err_txt
            or "storageQuotaExceeded" in err_txt
        )
        if is_sa_quota and (not isinstance(e, HttpError) or e.resp.status == 403):
            st.error(
                "서비스 계정은 **개인 드라이브(내 드라이브) 용량**을 쓸 수 없습니다. "
                "폴더를 공유해도 이 오류가 날 수 있습니다.\n\n"
                "**가능한 해결:**\n"
                "1. **Google Workspace 공유 드라이브**를 만들고, 그 안에 폴더를 두고 `folder_id`를 그 폴더로 지정한 뒤, "
                "서비스 계정을 해당 **공유 드라이브 멤버**(콘텐츠 관리자 등)로 추가\n"
                "2. 또는 **OAuth**(본인 구글 로그인)로 업로드하도록 앱을 바꾸기\n"
                "3. Workspace라면 **도메인 전체 위임**으로 특정 사용자로 위장 업로드(관리자 설정 필요)"
            )
        else:
            st.error(f"드라이브 업로드 중 오류 발생: {e}")
        return None
        
    finally:
        # 4. [핵심] 파일 잠금 해제 및 임시 파일 삭제
        # 미디어 객체가 열려있다면 명시적으로 닫아줍니다.
        if media is not None and hasattr(media, '_fd') and media._fd is not None:
            media._fd.close()
            
        # 잠금이 해제된 후 파일을 삭제합니다.
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError as ce:
                # 가끔 OS 수준에서 지연이 생길 수 있으므로 경고만 표시
                print(f"임시 파일 삭제 실패 (지연): {ce}")
        

def download_drive_image(file_id):
    try:
        service = get_drive_service() # 오타 수정 확인!
        request = service.files().get_media(fileId=file_id)
        
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            
        # [핵심] 데이터를 다 받았으면 바늘을 맨 앞으로(0번지) 돌려줘야 합니다!
        fh.seek(0)
        
        # 데이터를 제대로 받았는지 크기 체크 (엔지니어의 방어 코드)
        if fh.getbuffer().nbytes == 0:
            st.error("⚠️ 드라이브에서 사진 데이터를 가져오지 못했습니다. (0바이트)")
            return None

        raw = fh.getvalue()
        head = raw[:64]
        low_head = head.lower()
        # 권한/링크 문제 시 HTML이 내려오는 경우
        if low_head.startswith(b"<") or b"<!doctype" in low_head or b"<html" in low_head:
            st.error("⚠️ 드라이브 응답이 이미지가 아닙니다. 파일 권한/형식을 확인해주세요.")
            return None
        # iPhone HEIC(HEIF) 시그니처: ftpyheic/ftypheif 등
        if len(raw) > 12 and raw[4:8] == b"ftyp" and raw[8:12] in (
            b"heic",
            b"heix",
            b"hevc",
            b"hevx",
            b"mif1",
            b"msf1",
        ):
            if not _HEIF_ENABLED:
                st.error(
                    "⚠️ HEIC/HEIF 형식입니다. 서버에 `pillow-heif`가 필요합니다. "
                    "설치 전에는 JPG/PNG로 변환해 업로드해주세요."
                )
                return None

        img = Image.open(io.BytesIO(raw))
        img.load()
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        return img
        
    except Exception as e:
        msg = str(e)
        if "cannot identify image file" in msg:
            st.error(
                "❌ 이미지 형식을 열 수 없습니다. "
                "아이폰 HEIC/HEIF 파일이거나 손상 파일일 수 있습니다.\n"
                "→ JPG/PNG로 변환해서 다시 시도해주세요."
            )
        else:
            st.error(f"❌ 드라이브 사진 다운로드 중 에러: {e}")
        return None


@st.cache_data(show_spinner=False, ttl=600)
def _get_drive_preview_image(file_id: str):
    """갤러리용 미리보기 이미지를 안정적으로 로드(품질/비율 유지)."""
    img = download_drive_image(file_id)
    if img is None:
        return None
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass
    if img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")
    # 목록 렌더링 부담을 줄이기 위해 긴 변 기준으로 축소
    try:
        img.thumbnail((960, 960))
    except Exception:
        pass
    return img


def display_drive_selector():
    """구글 드라이브 썸네일 갤러리 (개수 조절 기능 추가)"""
    raw = _raw_drive_secrets()
    folder_id = (raw or {}).get("folder_id")
    if not folder_id:
        st.error(
            "드라이브 폴더 ID가 없습니다. secrets의 `[connections.google_drive]`에 `folder_id`를 넣어주세요."
        )
        return None, ""

    with st.spinner("☁️ 드라이브에서 작품 목록을 가져오고 있습니다..."):
        files = get_drive_image_list(folder_id)

    if not files:
        st.warning("⚠️ 드라이브 폴더가 비어있거나 사진을 찾을 수 없습니다.")
        return None, ""

    # HEIC/HEIF 등 PIL 미리보기 불가 가능성이 큰 파일 안내
    heic_like = []
    for f in files:
        n = str(f.get("name", "")).lower()
        m = str(f.get("mimeType", "")).lower()
        if n.endswith((".heic", ".heif")) or "heic" in m or "heif" in m:
            heic_like.append(f.get("name", ""))
    if heic_like and not _HEIF_ENABLED:
        st.info(
            "현재 HEIC/HEIF 미리보기가 완전 지원되지 않아 일부 파일에서 오류가 날 수 있습니다. "
            "가능하면 JPG/PNG를 사용해주세요."
        )

    st.markdown("### 🖼️ 분석할 작품을 선택하세요")
    num_cols = 3

    ctrl1, ctrl2 = st.columns([2, 1], vertical_alignment="bottom")
    with ctrl1:
        query = st.text_input("파일명 검색", placeholder="예: 원데이, 2026-03, 아이폰")
    with ctrl2:
        per_page = st.selectbox("페이지당", [12, 24, 48], index=1)

    q = (query or "").strip().lower()
    if q:
        files = [f for f in files if q in str(f.get("name", "")).lower()]

    if not files:
        st.info("검색 결과가 없습니다.")
        return None, ""

    total = len(files)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = st.number_input("페이지", min_value=1, max_value=total_pages, value=1, step=1)
    page = int(page)
    start = (page - 1) * per_page
    end = min(start + per_page, total)
    files = files[start:end]
    st.caption(f"총 {total}개 중 {start + 1}-{end} 표시")

    st.divider() # 시각적 구분선 추가
    
    # 선택한 숫자(num_cols)만큼 화면을 쪼갭니다.
    cols = st.columns(num_cols)
    
    for idx, file in enumerate(files):
        thumb_url = file.get('thumbnailLink')
        file_name = file.get('name')
        file_id = file.get('id')
        view_link = file.get('webViewLink', '')
        
        # 선택된 개수(num_cols)에 맞춰 순서대로 배치
        with cols[idx % num_cols]:
            with st.container(border=True):
                preview_img = _get_drive_preview_image(file_id) if file_id else None
                if preview_img is not None:
                    st.image(preview_img, width=170)
                elif thumb_url:
                    high_res_thumb = thumb_url.replace("=s220", "=s800")
                    st.image(high_res_thumb, width=170)
                else:
                    st.image("https://via.placeholder.com/400x400?text=No+Img", width=170)
                
                short_name = file_name[:10] + "..." if len(file_name) > 10 else file_name
                st.caption(short_name)
                
                # 버튼 크기도 화면 비율에 맞춰 자동으로 작아집니다
                if st.button("✅ 선택", key=f"btn_{file_id}", use_container_width=True):
                    with st.spinner("사진 데이터 다운로드 중..."):
                        st.session_state['drive_img'] = download_drive_image(file_id)
                        st.session_state['last_image_link'] = view_link
                        st.toast(f"'{short_name}' 선택 완료!")
                        st.rerun()

    if 'drive_img' in st.session_state:
        st.success("✅ 현재 선택된 사진이 AI 분석 대기 중입니다.")
        return st.session_state['drive_img'], st.session_state.get('last_image_link', '')
    
    return None, ""
    
