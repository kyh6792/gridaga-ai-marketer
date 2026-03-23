import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
import io
import os
import re # 정규표현식 import 확인
from PIL import Image
from datetime import datetime
from googleapiclient.discovery import build
from google.oauth2 import service_account

# [핵심] 구글 서비스 연결 객체를 만드는 함수
def get_drive_service():
    """인증 정보를 사용하여 구글 드라이브 서비스 객체 생성"""
    creds_info = st.secrets["google_drive"] # secrets.toml의 정보 사용
    creds = service_account.Credentials.from_service_account_info(creds_info)
    # 구글 드라이브 API 버전 3 사용
    return build('drive', 'v3', credentials=creds)

def get_drive_image_list(folder_id):
    """파일 목록을 가져올 때 'service' 객체를 호출하여 사용"""
    try:
        # [수정] 위에서 만든 함수를 통해 'service' 열쇠를 가져옵니다.
        service = get_drive_service()
        
        results = service.files().list(
            q=f"'{folder_id}' in parents and trashed = false and mimeType contains 'image/'",
            fields="files(id, name, thumbnailLink, webViewLink, mimeType)",
            pageSize=50
        ).execute()
        return results.get('files', [])
    except Exception as e:
        st.error(f"드라이브 목록 로드 실패: {e}")
        return []

def upload_image_to_drive(pil_image, folder_id, category):
    """PIL 이미지를 구글 드라이브에 업로드하고 링크 반환 (WinError 32 방어)"""
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

        # 4. [추가 조치] 업로드 성공 후 권한 전파 (옵션)
        # 만약 위 설정으로도 안 된다면, 아래 코드를 통해 '누구나' 볼 수 있게 잠시 엽니다.
        service.permissions().create(
         fileId=file.get('id'),
         body={'type': 'anyone', 'role': 'reader'},
         supportsAllDrives=True
        ).execute()
        
        return {
            'id': file.get('id'),
            'link': file.get('webViewLink')
        }
        
    except Exception as e:
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

        # [수정] HEIC 파일일 경우를 대비해 아까 만든 안전한 오픈 함수를 쓰면 더 좋습니다.
        # 일단은 기본 Image.open으로 테스트해보세요.
        return Image.open(fh)
        
    except Exception as e:
        st.error(f"❌ 드라이브 사진 다운로드 중 에러: {e}")
        return None
        
        
        
def display_drive_selector():
    """구글 드라이브 썸네일 갤러리 (개수 조절 기능 추가)"""
    folder_id = st.secrets.get("google_drive", {}).get("folder_id")
    
    with st.spinner("☁️ 드라이브에서 작품 목록을 가져오고 있습니다..."):
        files = get_drive_image_list(folder_id)

    if not files:
        st.warning("⚠️ 드라이브 폴더가 비어있거나 사진을 찾을 수 없습니다.")
        return None, ""

    # [핵심] 제목과 설정 컨트롤러를 한 줄에 나란히 배치
    header_col1, header_col2 = st.columns([2, 1], vertical_alignment="bottom")
    with header_col1:
        st.markdown("### 🖼️ 분석할 작품을 선택하세요")
    with header_col2:
        # 사용자가 원하는 열(Column) 개수를 선택 (기본값: 4개)
        num_cols = st.selectbox("한 줄에 몇 개씩 볼까요?", [2, 3, 4, 5, 6], index=2)

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
                if thumb_url:
                    # 사진이 작아지므로 해상도는 s400 정도로 유지해도 충분합니다.
                    high_res_thumb = thumb_url.replace("=s220", "=s400")
                    st.image(high_res_thumb, use_container_width=True)
                else:
                    st.image("https://via.placeholder.com/400x400?text=No+Img", use_container_width=True)
                
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
    
