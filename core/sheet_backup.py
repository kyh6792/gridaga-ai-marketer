"""
스프레드시트 일일 백업 → 같은 Drive 폴더에 .json.gz 업로드.

- secrets `[connections.google_drive]` 에 `backup_folder_id` 선택(없으면 `folder_id` 사용).
- 같은 스프레드시트에 `__backup_meta` 탭: key/value 로 `last_backup_date` = YYYY-MM-DD
- 앱 세션당 1회 자동 시도 + 푸터「백업하기」로 수동 실행 가능.

서비스 계정이 해당 폴더에 업로드 가능해야 함(공유 드라이브 등).
"""

from __future__ import annotations

import gzip
import json
import re
from datetime import datetime

import pandas as pd
import streamlit as st
from googleapiclient.discovery import build

from core.database import get_conn, get_sheet_url
from core.drive import get_backup_folder_id, get_service_account_credentials, upload_bytes_to_drive


def _oauth_creds_for_drive_upload():
    """마케팅에서 Google 드라이브 OAuth 연결돼 있으면 그 계정으로 업로드."""
    try:
        from core import drive_oauth

        if drive_oauth.oauth_google_drive_configured() and drive_oauth.has_valid_session_credentials():
            return drive_oauth.get_session_credentials()
    except Exception:
        pass
    return None

_META_WS = "__backup_meta"
_SCOPES = (
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets.readonly",
)


def _spreadsheet_id_from_url(url: str) -> str:
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", str(url))
    return m.group(1) if m else ""


def _sheets_range_for_tab(title: str) -> str:
    t = str(title)
    if re.match(r"^[A-Za-z0-9_]+$", t):
        return t
    return "'" + t.replace("'", "''") + "'"


def _get_sheets_api():
    creds = get_service_account_credentials(_SCOPES)
    if not creds:
        return None
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def _export_all_tabs(spreadsheet_id: str) -> dict:
    svc = _get_sheets_api()
    if not svc:
        return {}
    meta = (
        svc.spreadsheets()
        .get(spreadsheetId=spreadsheet_id, fields="sheets(properties/title)")
        .execute()
    )
    titles = [s["properties"]["title"] for s in meta.get("sheets", [])]
    out: dict[str, list] = {}
    for title in titles:
        if title == _META_WS:
            continue
        rng = _sheets_range_for_tab(title)
        res = (
            svc.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=rng)
            .execute()
        )
        out[title] = res.get("values", [])
    return out


def _needs_backup_today(conn, sheet_url: str, today: str) -> bool:
    try:
        df = conn.read(spreadsheet=sheet_url, worksheet=_META_WS, ttl=0)
    except Exception:
        return True
    if df is None or df.empty:
        return True
    if "key" not in df.columns or "value" not in df.columns:
        return True
    m = df[df["key"].astype(str) == "last_backup_date"]
    if m.empty:
        return True
    val = str(m.iloc[0]["value"]).strip()[:10]
    return val != today


def _write_backup_meta(conn, sheet_url: str, today: str):
    df = pd.DataFrame([{"key": "last_backup_date", "value": today}])
    conn.update(spreadsheet=sheet_url, worksheet=_META_WS, data=df)


def _perform_sheet_backup(
    conn,
    spreadsheet_id: str,
    sheet_url: str,
    folder_id: str,
    today: str,
    *,
    update_meta: bool,
    user_credentials=None,
) -> tuple[bool, str]:
    """백업 실행. (성공 여부, 메시지 또는 파일명)."""
    try:
        tabs = _export_all_tabs(spreadsheet_id)
        payload = {
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "spreadsheet_id": spreadsheet_id,
            "tabs": tabs,
        }
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        gz = gzip.compress(raw)
        fname = f"gridaga_sheet_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json.gz"
        up = upload_bytes_to_drive(
            gz,
            fname,
            folder_id,
            mime_type="application/gzip",
            add_anyone_reader=False,
            user_credentials=user_credentials,
        )
        if not up:
            if user_credentials is None:
                return (
                    False,
                    "Drive 업로드 실패. 서비스 계정은 개인 드라이브에 올리지 못합니다. "
                    "마케팅에서 Google 연결 후 다시 시도하거나, 공유 드라이브의 `folder_id`를 쓰세요.",
                )
            return False, "Drive 업로드 실패(`folder_id`가 본인 드라이브 안 폴더인지 확인)"
        if update_meta:
            _write_backup_meta(conn, sheet_url, today)
        return True, fname
    except Exception as e:
        return False, str(e)


def run_sheet_backup_now() -> tuple[bool, str]:
    """수동 백업(메타의 '오늘 백업 여부'와 무관하게 항상 시도)."""
    folder_id = get_backup_folder_id()
    sheet_url = get_sheet_url()
    if not folder_id:
        return False, "Drive 폴더 ID(`folder_id` 또는 `backup_folder_id`)가 없습니다."
    if not sheet_url:
        return False, "시트 URL(`GSHEETS_URL` / connections)이 없습니다."
    spreadsheet_id = _spreadsheet_id_from_url(sheet_url)
    if not spreadsheet_id:
        return False, "스프레드시트 ID를 URL에서 읽지 못했습니다."
    try:
        conn = get_conn()
    except Exception as e:
        return False, f"시트 연결 실패: {e}"
    today = datetime.now().strftime("%Y-%m-%d")
    oauth = _oauth_creds_for_drive_upload()
    return _perform_sheet_backup(
        conn,
        spreadsheet_id,
        sheet_url,
        folder_id,
        today,
        update_meta=True,
        user_credentials=oauth,
    )


def maybe_run_daily_sheet_backup():
    """첫 로드 시 하루 1회: 메타 확인 후 gzip JSON 백업."""
    if st.session_state.get("_sheet_daily_backup_done"):
        return

    folder_id = get_backup_folder_id()
    sheet_url = get_sheet_url()
    if not folder_id or not sheet_url:
        st.session_state["_sheet_daily_backup_done"] = True
        return

    spreadsheet_id = _spreadsheet_id_from_url(sheet_url)
    if not spreadsheet_id:
        st.session_state["_sheet_daily_backup_done"] = True
        return

    today = datetime.now().strftime("%Y-%m-%d")

    try:
        conn = get_conn()
    except Exception:
        st.session_state["_sheet_daily_backup_done"] = True
        return

    if not _needs_backup_today(conn, sheet_url, today):
        st.session_state["_sheet_daily_backup_done"] = True
        return

    try:
        oauth = _oauth_creds_for_drive_upload()
        _perform_sheet_backup(
            conn,
            spreadsheet_id,
            sheet_url,
            folder_id,
            today,
            update_meta=True,
            user_credentials=oauth,
        )
    except Exception:
        pass
    finally:
        st.session_state["_sheet_daily_backup_done"] = True
