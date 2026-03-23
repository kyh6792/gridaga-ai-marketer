import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
import io
import os
import re # 정규표현식 import 확인
from PIL import Image
from datetime import datetime

def get_gdrive_service():
    """서비스 계정 인증 및 드라이브 서비스 빌드 (Read/Write 권한)"""
    # secrets.toml 계층 구조에 맞춤
    creds_dict = st.secrets["connections"]["google_auth"]
    creds = service_account.Credentials.from_service_account_info(creds_dict)
    
    # [변경] 권한 스코프를 Read/Write로 변경
    scoped_creds = creds.with_scopes(['https://www.googleapis.com/auth/drive'])
    
    return build('drive', 'v3', credentials=scoped_creds)


def upload_image_to_drive(pil_image, folder_id, category):
    """PIL 이미지를 구글 드라이브에 업로드하고 링크 반환 (WinError 32 방어)"""
    service = get_gdrive_service()
    
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
        
def get_drive_image_list(folder_id):
    """특정 폴더 내의 이미지 파일 목록(이름, ID) 가져오기"""
    service = get_gdrive_service()
    query = f"'{folder_id}' in parents and mimeType contains 'image/' and trashed = false"
    
    results = service.files().list(
        q=query, 
        pageSize=20, # 최신 20개만
        fields="files(id, name, createdTime)",
        orderBy="createdTime desc"
    ).execute()
    
    return results.get('files', [])

def download_drive_image(file_id):
    """파일 ID로 이미지를 다운로드하여 PIL Image로 변환"""
    service = get_gdrive_service()
    request = service.files().get_media(fileId=file_id)
    
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
        
    fh.seek(0)
    return Image.open(fh)