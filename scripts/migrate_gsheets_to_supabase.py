from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from supabase import create_client


def _spreadsheet_id_from_url(url: str) -> str:
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", str(url or ""))
    return m.group(1) if m else ""


def _read_toml(path: Path) -> dict[str, Any]:
    # Python 3.11+: tomllib. Fallback to tomli if needed.
    try:
        import tomllib  # type: ignore
    except Exception:  # pragma: no cover
        import tomli as tomllib  # type: ignore
    return tomllib.loads(path.read_text(encoding="utf-8"))


@dataclass
class Secrets:
    gsheets_url: str
    sa_info: dict[str, Any]
    supabase_url: str
    supabase_service_role_key: str


def load_secrets(secrets_path: Path) -> Secrets:
    if not secrets_path.exists():
        raise FileNotFoundError(f"Missing secrets file: {secrets_path}")
    s = _read_toml(secrets_path)

    gsheets_url = str(s.get("GSHEETS_URL", "")).strip()
    if not gsheets_url:
        # also allow connections.google_drive.spreadsheet
        gsheets_url = (
            str(s.get("connections", {}).get("google_drive", {}).get("spreadsheet", "")).strip()
        )

    conn_cfg = s.get("connections", {}).get("google_drive", {})
    if not isinstance(conn_cfg, dict):
        conn_cfg = {}

    supabase_url = str(s.get("SUPABASE_URL", "")).strip()
    supabase_key = str(s.get("SUPABASE_SERVICE_ROLE_KEY", "")).strip()

    if not gsheets_url:
        raise ValueError(f"GSHEETS_URL not found in {secrets_path.name}")
    if not supabase_url or not supabase_key:
        raise ValueError(f"SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not found in {secrets_path.name}")

    # streamlit-gsheets-connection stores service account fields under [connections.google_drive]
    sa_info = {
        "type": conn_cfg.get("type", "service_account"),
        "project_id": conn_cfg.get("project_id", ""),
        "private_key_id": conn_cfg.get("private_key_id", ""),
        "private_key": conn_cfg.get("private_key", ""),
        "client_email": conn_cfg.get("client_email", ""),
        "client_id": conn_cfg.get("client_id", ""),
        "auth_uri": conn_cfg.get("auth_uri", "https://accounts.google.com/o/oauth2/auth"),
        "token_uri": conn_cfg.get("token_uri", "https://oauth2.googleapis.com/token"),
        "auth_provider_x509_cert_url": conn_cfg.get(
            "auth_provider_x509_cert_url", "https://www.googleapis.com/oauth2/v1/certs"
        ),
        "client_x509_cert_url": conn_cfg.get("client_x509_cert_url", ""),
        "universe_domain": conn_cfg.get("universe_domain", "googleapis.com"),
    }

    if not sa_info.get("private_key") or not sa_info.get("client_email"):
        raise ValueError(f"Service account fields are missing in [connections.google_drive] {secrets_path.name}")

    return Secrets(
        gsheets_url=gsheets_url,
        sa_info=sa_info,
        supabase_url=supabase_url,
        supabase_service_role_key=supabase_key,
    )


def get_sheets_service(sa_info: dict[str, Any]):
    creds = Credentials.from_service_account_info(
        sa_info,
        scopes=("https://www.googleapis.com/auth/spreadsheets.readonly",),
    )
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def read_worksheet_df(svc, spreadsheet_id: str, worksheet: str) -> pd.DataFrame:
    res = (
        svc.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=f"{worksheet}!A:ZZ")
        .execute()
    )
    rows = res.get("values", [])
    if not rows:
        return pd.DataFrame()
    headers = [str(x) for x in rows[0]]
    body = rows[1:]
    width = len(headers)
    normalized = []
    for r in body:
        row = list(r[:width]) + [""] * max(0, width - len(r))
        normalized.append(row)
    return pd.DataFrame(normalized, columns=headers)


def _chunks(items: list[dict[str, Any]], size: int = 500):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _to_int(v: Any) -> int:
    try:
        if v is None:
            return 0
        if isinstance(v, (int, float)):
            return int(v)
        txt = str(v)
        nums = re.sub(r"[^0-9-]", "", txt)
        return int(nums) if nums not in ("", "-") else 0
    except Exception:
        return 0


def _reset_supabase(sb):
    # Delete rows (avoid duplicates). Order: child/append tables first.
    # PostgREST requires a filter for delete, so use always-true filters.
    sb.table("attendance_log").delete().gt("id", 0).execute()
    sb.table("marketing_history").delete().gt("id", 0).execute()

    sb.table("attendance_requests").delete().neq("request_id", "").execute()
    sb.table("student_schedule").delete().neq("id", "").execute()
    sb.table("finance_transactions").delete().neq("tx_id", "").execute()
    sb.table("finance_expenses").delete().neq("ex_id", "").execute()
    sb.table("curriculum").delete().neq("course_id", "").execute()
    sb.table("students").delete().neq("student_id", "").execute()
    sb.table("prompts").delete().neq("category", "").execute()


def migrate(*, secrets_file: str, reset: bool = False):
    root = Path(__file__).resolve().parents[1]
    sec = load_secrets((root / secrets_file).resolve())
    spreadsheet_id = _spreadsheet_id_from_url(sec.gsheets_url)
    if not spreadsheet_id:
        raise ValueError("Could not parse spreadsheet id from GSHEETS_URL")

    svc = get_sheets_service(sec.sa_info)
    sb = create_client(sec.supabase_url, sec.supabase_service_role_key)

    if reset:
        print("[reset] clearing existing Supabase tables...")
        _reset_supabase(sb)
        print("[reset] done.")

    plan: list[tuple[str, str]] = [
        ("prompt", "prompts"),
        ("prompts", "prompts"),
        ("history", "marketing_history"),
        ("students", "students"),
        ("attendance_requests", "attendance_requests"),
        ("attendance_log", "attendance_log"),
        ("student_schedule", "student_schedule"),
        ("curriculum", "curriculum"),
        ("finance_transactions", "finance_transactions"),
        ("finance_expenses", "finance_expenses"),
    ]

    for ws, table in plan:
        try:
            df = read_worksheet_df(svc, spreadsheet_id, ws)
        except HttpError as e:
            # Worksheet might not exist (400: Unable to parse range).
            msg = str(e)
            if "Unable to parse range" in msg or "400" in msg:
                print(f"[skip] {ws}: worksheet not found")
                continue
            raise
        if df is None or df.empty:
            print(f"[skip] {ws}: empty")
            continue

        # Normalize by target table
        rows: list[dict[str, Any]] = []

        if table == "prompts":
            if "category" not in df.columns or "prompt" not in df.columns:
                print(f"[skip] {ws}: missing category/prompt columns")
                continue
            for _, r in df.iterrows():
                cat = str(r.get("category", "")).strip()
                if not cat:
                    continue
                rows.append({"category": cat, "prompt": str(r.get("prompt", "") or "")})
            if not rows:
                print(f"[skip] {ws}: no valid rows")
                continue
            # upsert on PK
            for ch in _chunks(rows, 500):
                sb.table("prompts").upsert(ch).execute()
            print(f"[ok] {ws} -> {table}: {len(rows)}")
            continue

        if table == "marketing_history":
            for _, r in df.iterrows():
                rows.append(
                    {
                        "date_text": str(r.get("date", "") or ""),
                        "category": str(r.get("category", "") or ""),
                        "instagram": str(r.get("instagram", "") or ""),
                        "blog": str(r.get("blog", "") or ""),
                        "image_link": str(r.get("image_link", "") or ""),
                    }
                )
            for ch in _chunks(rows, 500):
                sb.table("marketing_history").insert(ch).execute()
            print(f"[ok] {ws} -> {table}: {len(rows)}")
            continue

        if table == "students":
            # Sheet columns (Korean): ["ID","이름","연락처","등록일","수강코스","총 횟수","잔여 횟수","상태","메모"]
            for _, r in df.iterrows():
                sid = str(r.get("ID", "")).strip()
                if not sid:
                    continue
                rows.append(
                    {
                        "student_id": sid,
                        "name": str(r.get("이름", "") or ""),
                        "phone": str(r.get("연락처", "") or ""),
                        "registered_date": str(r.get("등록일", "") or ""),
                        "course": str(r.get("수강코스", "") or ""),
                        "total_sessions": _to_int(r.get("총 횟수", 0)),
                        "remaining_sessions": _to_int(r.get("잔여 횟수", 0)),
                        "status": str(r.get("상태", "") or ""),
                        "memo": str(r.get("메모", "") or ""),
                    }
                )
            for ch in _chunks(rows, 500):
                sb.table("students").upsert(ch).execute()
            print(f"[ok] {ws} -> {table}: {len(rows)}")
            continue

        if table == "attendance_requests":
            for _, r in df.iterrows():
                rid = str(r.get("request_id", "")).strip()
                if not rid:
                    continue
                rows.append(
                    {
                        "request_id": rid,
                        "time_text": str(r.get("time", "") or ""),
                        "student_id": str(r.get("student_id", "") or ""),
                        "student_name": str(r.get("student_name", "") or ""),
                        "status": str(r.get("status", "") or ""),
                        "approved_time": str(r.get("approved_time", "") or ""),
                    }
                )
            for ch in _chunks(rows, 500):
                sb.table("attendance_requests").upsert(ch).execute()
            print(f"[ok] {ws} -> {table}: {len(rows)}")
            continue

        if table == "attendance_log":
            for _, r in df.iterrows():
                # no natural PK; insert as append-only
                rows.append(
                    {
                        "time_text": str(r.get("time", "") or ""),
                        "student_id": str(r.get("student_id", "") or ""),
                        "student_name": str(r.get("student_name", "") or ""),
                        "remain_count": _to_int(r.get("remain_count", 0)),
                        "event": str(r.get("event", "") or ""),
                    }
                )
            for ch in _chunks(rows, 500):
                sb.table("attendance_log").insert(ch).execute()
            print(f"[ok] {ws} -> {table}: {len(rows)}")
            continue

        if table == "student_schedule":
            for _, r in df.iterrows():
                sid = str(r.get("id", "")).strip()
                if not sid:
                    continue
                rows.append(
                    {
                        "id": sid,
                        "student_id": str(r.get("student_id", "") or ""),
                        "student_name": str(r.get("student_name", "") or ""),
                        "weekday": str(r.get("weekday", "") or ""),
                        "time_slot": str(r.get("time_slot", "") or ""),
                        "start_date": str(r.get("start_date", "") or ""),
                        "end_date": str(r.get("end_date", "") or ""),
                        "memo": str(r.get("memo", "") or ""),
                        "created_at": str(r.get("created_at", "") or ""),
                    }
                )
            for ch in _chunks(rows, 500):
                sb.table("student_schedule").upsert(ch).execute()
            print(f"[ok] {ws} -> {table}: {len(rows)}")
            continue

        if table == "curriculum":
            for _, r in df.iterrows():
                cid = str(r.get("course_id", "")).strip()
                if not cid:
                    continue
                rows.append(
                    {
                        "course_id": cid,
                        "course_name": str(r.get("course_name", "") or ""),
                        "sessions": _to_int(r.get("sessions", 0)),
                        "amount": _to_int(r.get("amount", 0)),
                        "description": str(r.get("description", "") or ""),
                        "created_at": str(r.get("created_at", "") or ""),
                        "sort_order": _to_int(r.get("sort_order", 9999)),
                    }
                )
            for ch in _chunks(rows, 500):
                sb.table("curriculum").upsert(ch).execute()
            print(f"[ok] {ws} -> {table}: {len(rows)}")
            continue

        if table == "finance_transactions":
            for _, r in df.iterrows():
                tx_id = str(r.get("tx_id", "")).strip()
                if not tx_id:
                    continue
                rows.append(
                    {
                        "tx_id": tx_id,
                        "date": str(r.get("date", "") or ""),
                        "year_month": str(r.get("year_month", "") or ""),
                        "year_week": str(r.get("year_week", "") or ""),
                        "student_id": str(r.get("student_id", "") or ""),
                        "student_name": str(r.get("student_name", "") or ""),
                        "course": str(r.get("course", "") or ""),
                        "event_type": str(r.get("event_type", "") or ""),
                        "amount": _to_int(r.get("amount", 0)),
                        "base_amount": _to_int(r.get("base_amount", 0)),
                        "discount_type": str(r.get("discount_type", "") or ""),
                        "discount_value": _to_int(r.get("discount_value", 0)),
                        "discount_amount": _to_int(r.get("discount_amount", 0)),
                        "event_name": str(r.get("event_name", "") or ""),
                        "note": str(r.get("note", "") or ""),
                    }
                )
            for ch in _chunks(rows, 500):
                sb.table("finance_transactions").upsert(ch).execute()
            print(f"[ok] {ws} -> {table}: {len(rows)}")
            continue

        if table == "finance_expenses":
            for _, r in df.iterrows():
                ex_id = str(r.get("ex_id", "")).strip()
                if not ex_id:
                    continue
                rows.append(
                    {
                        "ex_id": ex_id,
                        "date": str(r.get("date", "") or ""),
                        "year_month": str(r.get("year_month", "") or ""),
                        "category": str(r.get("category", "") or ""),
                        "item": str(r.get("item", "") or ""),
                        "amount": _to_int(r.get("amount", 0)),
                        "note": str(r.get("note", "") or ""),
                    }
                )
            for ch in _chunks(rows, 500):
                sb.table("finance_expenses").upsert(ch).execute()
            print(f"[ok] {ws} -> {table}: {len(rows)}")
            continue

        print(f"[skip] {ws}: unknown mapping")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--secrets-file",
        default=".streamlit/secrets.local.toml",
        help="Path (relative to repo root) to Streamlit secrets toml to read.",
    )
    ap.add_argument(
        "--reset",
        action="store_true",
        help="Clear target Supabase tables before importing (recommended when re-running).",
    )
    args = ap.parse_args()
    migrate(secrets_file=args.secrets_file, reset=bool(args.reset))

