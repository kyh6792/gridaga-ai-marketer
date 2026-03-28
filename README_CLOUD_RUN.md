## Cloud Run 배포(권장)

이 저장소는 Streamlit 앱입니다. Cloud Run에서는 컨테이너로 실행하며, **`.streamlit/secrets.toml`은 이미지에 포함하지 않고**
GCP **Secret Manager** 또는 Cloud Run 환경변수로 주입하는 것을 권장합니다.

> 중요: 로컬/대화/로그 등에 `secrets.toml`이 노출되었다면 **즉시 키를 로테이션**하세요.

### 1) 선행 조건

- GCP 프로젝트
- 결제/시트/드라이브에 접근할 **서비스 계정**(또는 기존 서비스 계정)
- (선택) Google OAuth 사용 시 OAuth Client (client_id / client_secret)
- Cloud Run, Artifact Registry, Secret Manager API 활성화

### 2) Secret Manager에 `secrets.toml` 저장

Streamlit은 기본적으로 아래 위치의 secrets 파일을 읽습니다.

- `/root/.streamlit/secrets.toml`

Cloud Run에서 Secret Manager를 **파일로 마운트**하면 기존 코드(`st.secrets[...]`)를 거의 그대로 유지할 수 있습니다.

예시(로컬에서 gcloud 사용):

```bash
gcloud secrets create streamlit-secrets --data-file=.streamlit/secrets.toml
```

이미 존재하면:

```bash
gcloud secrets versions add streamlit-secrets --data-file=.streamlit/secrets.toml
```

### 3) Cloud Run 배포(Cloud Build로 빌드)

```bash
gcloud run deploy giridaga-marketer \
  --source . \
  --region asia-northeast3 \
  --allow-unauthenticated \
  --memory 1024Mi \
  --cpu 1 \
  --set-env-vars "STREAMLIT_SERVER_HEADLESS=true" \
  --update-secrets "/root/.streamlit/secrets.toml=streamlit-secrets:latest"
```

#### 운영 팁

- **콜드스타트가 싫으면** `--min-instances=1` (대신 고정비 발생)
- 트래픽이 적으면 기본값(0) 권장

### 4) 웹훅(토스플레이스)까지 붙일 계획이라면

- Streamlit 앱을 Cloud Run에 그대로 두고,
- 웹훅 전용 엔드포인트(FastAPI)도 Cloud Run에 같이 두거나(멀티서비스),
- 하나의 서비스에 같이 넣고 라우팅 처리할 수도 있습니다(권장: 분리).

