"""
Google Drive OAuth (사용자 계정) — 로컬·Streamlit Cloud 공통.

secrets.toml (로컬) / Cloud Secrets (배포) 예시:

[oauth_google_drive]
client_id = "....apps.googleusercontent.com"
client_secret = "GOCSPX-..."
# 로컬 테스트: GCP 콘솔에 동일 URI 등록
redirect_uri = "http://localhost:8501/"
# 배포 시: redirect_uri = "https://<앱이름>.streamlit.app/"
# (선택) state_signing_key = "임의 긴 문자열"  # 없으면 client_id+secret에서 유도

GCP: OAuth 동의 화면 + Drive API 활성화 + OAuth 클라이언트(웹 앱)에
위 redirect_uri를 그대로「승인된 리디렉션 URI」로 등록.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from string import ascii_letters, digits

import streamlit as st
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

_CREDS_KEY = "_google_drive_oauth_creds"
_DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]
# google_auth_oauthlib Flow와 동일한 PKCE 문자 집합 (RFC 7636)
_PKCE_CHARS = ascii_letters + digits + "-._~"


def _load_oauth_secrets():
    try:
        if "oauth_google_drive" not in st.secrets:
            return None
        s = st.secrets["oauth_google_drive"]
        cid = str(s.get("client_id", "")).strip()
        secret = str(s.get("client_secret", "")).strip()
        redir = str(s.get("redirect_uri", "")).strip()
        if cid and secret and redir:
            return {"client_id": cid, "client_secret": secret, "redirect_uri": redir}
    except Exception:
        pass
    return None


def oauth_google_drive_configured() -> bool:
    return _load_oauth_secrets() is not None


def _oauth_state_signing_key(cfg: dict) -> bytes:
    """세션 없이 state 검증용. Cloud에서 세션이 바뀌어도 동작."""
    try:
        s = st.secrets["oauth_google_drive"].get("state_signing_key")
        if s:
            return str(s).encode("utf-8")
    except Exception:
        pass
    raw = f"{cfg['client_id']}:{cfg['client_secret']}"
    return hashlib.sha256(raw.encode("utf-8")).digest()


def _new_pkce_code_verifier() -> str:
    """Flow.authorization_url과 동일 길이·문자 집합으로 PKCE verifier 생성."""
    return "".join(secrets.choice(_PKCE_CHARS) for _ in range(128))


def _create_signed_oauth_state(cfg: dict, payload: dict) -> str:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    b64 = base64.urlsafe_b64encode(body).decode("ascii").rstrip("=")
    sig = hmac.new(_oauth_state_signing_key(cfg), b64.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{b64}.{sig}"


def _verify_signed_oauth_state(cfg: dict, state: str, max_age_sec: int = 900) -> dict | None:
    if not state or "." not in state:
        return None
    try:
        b64, sig = state.rsplit(".", 1)
        want = hmac.new(_oauth_state_signing_key(cfg), b64.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(want, sig):
            return None
        pad = "=" * (-len(b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(b64 + pad))
        if int(time.time()) - int(payload["ts"]) > max_age_sec:
            return None
        if "cv" not in payload:
            return None
        return payload
    except Exception:
        return None


def _build_flow(
    cfg: dict,
    *,
    code_verifier: str | None = None,
    autogenerate_code_verifier: bool = True,
) -> Flow:
    client_config = {
        "web": {
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [cfg["redirect_uri"]],
        }
    }
    if code_verifier is not None:
        return Flow.from_client_config(
            client_config,
            _DRIVE_SCOPES,
            redirect_uri=cfg["redirect_uri"],
            code_verifier=code_verifier,
            autogenerate_code_verifier=False,
        )
    return Flow.from_client_config(
        client_config,
        _DRIVE_SCOPES,
        redirect_uri=cfg["redirect_uri"],
        autogenerate_code_verifier=autogenerate_code_verifier,
    )


def _creds_to_dict(creds: Credentials) -> dict:
    return {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri or "https://oauth2.googleapis.com/token",
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes or _DRIVE_SCOPES),
    }


def has_valid_session_credentials() -> bool:
    d = st.session_state.get(_CREDS_KEY)
    if not d:
        return False
    return bool(d.get("refresh_token") or d.get("token"))


def get_session_credentials() -> Credentials | None:
    d = st.session_state.get(_CREDS_KEY)
    if not d:
        return None
    try:
        creds = Credentials(
            token=d.get("token"),
            refresh_token=d.get("refresh_token"),
            token_uri=d.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=d.get("client_id"),
            client_secret=d.get("client_secret"),
            scopes=d.get("scopes") or _DRIVE_SCOPES,
        )
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            st.session_state[_CREDS_KEY] = _creds_to_dict(creds)
        return creds
    except Exception:
        return None


def disconnect_google_drive_oauth():
    st.session_state.pop(_CREDS_KEY, None)


def build_google_drive_authorization_url(cfg: dict) -> str:
    """Google 동의 화면 URL. 연결 버튼 한 번에 바로 이동할 때 사용."""
    cv = _new_pkce_code_verifier()
    pl = {
        "ts": int(time.time()),
        "n": secrets.token_hex(8),
        "cv": cv,
    }
    if st.session_state.get("owner_login_at") and st.session_state.get("entry_mode") == "owner":
        pl["ola"] = str(st.session_state["owner_login_at"])
        pl["omi"] = int(st.session_state.get("owner_menu_index", 0))
    signed_state = _create_signed_oauth_state(cfg, pl)
    flow = _build_flow(cfg, code_verifier=cv, autogenerate_code_verifier=False)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
        state=signed_state,
    )
    return auth_url


def _oauth_strip_callback_params():
    preserved = {}
    for k in list(st.query_params.keys()):
        if k not in ("code", "state", "scope"):
            preserved[k] = st.query_params[k]
    st.query_params.clear()
    for k, v in preserved.items():
        st.query_params[k] = v
    if st.session_state.get("intro_done") and "skip_intro" not in st.query_params:
        st.query_params["skip_intro"] = "1"


def _apply_oauth_return_navigation(payload: dict):
    """구글 리다이렉트 후 세션이 비어도 원장·마케팅으로 돌아가게 복원."""
    ola = payload.get("ola")
    if ola:
        st.session_state["entry_mode"] = "owner"
        st.session_state["owner_login_at"] = str(ola)
        st.session_state["owner_menu_index"] = int(payload.get("omi", 0))
        st.session_state["owner_authenticated"] = True
    st.session_state["intro_done"] = True


def try_finish_google_drive_oauth():
    """앱 진입 시 호출: ?code=&state= 이 있으면 토큰 교환 후 쿼리 정리·rerun."""
    cfg = _load_oauth_secrets()
    if not cfg:
        return

    raw_code = st.query_params.get("code")
    if not raw_code:
        return

    code = raw_code[0] if isinstance(raw_code, (list, tuple)) else raw_code
    if not code:
        return

    raw_state = st.query_params.get("state")
    state_url = raw_state[0] if isinstance(raw_state, (list, tuple)) else raw_state
    state_str = str(state_url or "").strip()
    payload = _verify_signed_oauth_state(cfg, state_str)
    if not payload:
        st.session_state["_oauth_drive_error"] = (
            "OAuth 연결이 만료되었거나 세션이 끊겼습니다. "
            "마케팅 화면에서 **연결**을 다시 눌러 주세요. (같은 브라우저 탭에서 완료하는 것이 안전합니다.)"
        )
        _oauth_strip_callback_params()
        st.rerun()
        return

    try:
        flow = _build_flow(cfg, code_verifier=payload["cv"], autogenerate_code_verifier=False)
        flow.fetch_token(code=code)
        st.session_state[_CREDS_KEY] = _creds_to_dict(flow.credentials)
        st.session_state["_oauth_drive_ok"] = True
        _apply_oauth_return_navigation(payload)
    except Exception as e:
        st.session_state["_oauth_drive_error"] = f"Google 토큰 교환 실패: {e}"

    _oauth_strip_callback_params()
    if payload.get("ola"):
        st.query_params["mode"] = "owner"
        st.query_params["owner_login_at"] = str(payload["ola"])
        st.query_params["owner_menu_idx"] = str(int(payload.get("omi", 0)))
    if st.session_state.get("intro_done") and "skip_intro" not in st.query_params:
        st.query_params["skip_intro"] = "1"
    st.rerun()


def render_google_drive_oauth_panel():
    """한 줄: 짧은 안내 + [연결] 링크(바로 Google) / [해제] 버튼."""
    if not oauth_google_drive_configured():
        return

    if st.session_state.pop("_oauth_drive_ok", None):
        if hasattr(st, "toast"):
            st.toast("Google 드라이브 연결 완료", icon="✅")
        else:
            st.caption("✅ Google 드라이브 연결 완료")

    err = st.session_state.pop("_oauth_drive_error", None)
    if err:
        st.error(err)

    cfg = _load_oauth_secrets()
    if not cfg:
        return

    connected = has_valid_session_credentials()
    if connected:
        c1, c2, c3 = st.columns([3.4, 0.55, 0.55], vertical_alignment="center")
    else:
        c1, c2 = st.columns([3.4, 0.75], vertical_alignment="center")
        c3 = None

    with c1:
        st.caption("**드라이브 자동 저장** · 문구만 쓸 땐 생략 · 이 탭 닫으면 다시 연결")
    with c2:
        if connected:
            st.caption("✓")
        else:
            auth_url = build_google_drive_authorization_url(cfg)
            try:
                st.link_button("연결", auth_url, use_container_width=True, type="secondary")
            except TypeError:
                st.link_button("연결", auth_url, use_container_width=True)
    if connected and c3 is not None:
        with c3:
            if st.button("해제", key="oauth_drive_disconnect", help="이 탭에서만 연동 해제"):
                disconnect_google_drive_oauth()
                st.rerun()
