from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import streamlit as st
import time
from streamlit_gsheets import GSheetsConnection
from core.perf import perf_log


def _db_backend() -> str:
    try:
        return str(st.secrets.get("DB_BACKEND", "gsheets")).strip().lower()
    except Exception:
        return "gsheets"


@dataclass(frozen=True)
class TableMap:
    table: str
    pk: str | None


_WS_MAP: dict[str, TableMap] = {
    "prompt": TableMap("prompts", "category"),
    "prompts": TableMap("prompts", "category"),
    "history": TableMap("marketing_history", None),
    "students": TableMap("students", "student_id"),
    "attendance_requests": TableMap("attendance_requests", "request_id"),
    "attendance_log": TableMap("attendance_log", None),
    "student_schedule": TableMap("student_schedule", "id"),
    "curriculum": TableMap("curriculum", "course_id"),
    "finance_transactions": TableMap("finance_transactions", "tx_id"),
    "finance_expenses": TableMap("finance_expenses", "ex_id"),
}


def _sb():
    from core.supabase_client import get_supabase_client

    c = get_supabase_client()
    if c is None:
        raise RuntimeError("Supabase client not configured. Check SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY.")
    return c


def _to_df(rows: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _legacy_from_supabase(worksheet: str, rows: list[dict[str, Any]]) -> pd.DataFrame:
    df = _to_df(rows)
    if df.empty:
        return df

    ws = str(worksheet)
    if ws in ("prompt", "prompts"):
        # prompts: category, prompt already
        return df[["category", "prompt"]].copy() if "category" in df.columns and "prompt" in df.columns else df

    if ws == "history":
        # marketing_history stores date_text column
        if "date_text" in df.columns and "date" not in df.columns:
            df = df.rename(columns={"date_text": "date"})
        cols = [c for c in ["date", "category", "instagram", "blog", "image_link"] if c in df.columns]
        return df[cols].copy() if cols else df

    if ws == "students":
        # Convert to legacy Korean headers used across app
        rename = {
            "student_id": "ID",
            "name": "이름",
            "phone": "연락처",
            "registered_date": "등록일",
            "course": "수강코스",
            "total_sessions": "총 횟수",
            "remaining_sessions": "잔여 횟수",
            "status": "상태",
            "memo": "메모",
        }
        df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
        ordered = ["ID", "이름", "연락처", "등록일", "수강코스", "총 횟수", "잔여 횟수", "상태", "메모"]
        for c in ordered:
            if c not in df.columns:
                df[c] = ""
        return df[ordered].copy()

    if ws == "attendance_requests":
        rename = {"time_text": "time"}
        df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
        ordered = ["request_id", "time", "student_id", "student_name", "status", "approved_time"]
        for c in ordered:
            if c not in df.columns:
                df[c] = ""
        return df[ordered].copy()

    if ws == "attendance_log":
        rename = {"time_text": "time"}
        df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
        ordered = ["time", "student_id", "student_name", "remain_count", "event"]
        for c in ordered:
            if c not in df.columns:
                df[c] = ""
        return df[ordered].copy()

    # schedule/curriculum/finance already use matching column names in code
    return df


def _supabase_from_legacy(worksheet: str, df: pd.DataFrame) -> list[dict[str, Any]]:
    if df is None:
        return []
    frame = df.copy()
    ws = str(worksheet)

    if ws in ("prompt", "prompts"):
        if "category" not in frame.columns or "prompt" not in frame.columns:
            return []
        frame = frame[["category", "prompt"]].copy()
        return frame.astype(object).where(pd.notna(frame), "").to_dict(orient="records")

    if ws == "history":
        # legacy has date
        if "date" in frame.columns and "date_text" not in frame.columns:
            frame = frame.rename(columns={"date": "date_text"})
        cols = [c for c in ["date_text", "category", "instagram", "blog", "image_link"] if c in frame.columns]
        if not cols:
            return []
        frame = frame[cols].copy()
        return frame.astype(object).where(pd.notna(frame), "").to_dict(orient="records")

    if ws == "students":
        rename = {
            "ID": "student_id",
            "이름": "name",
            "연락처": "phone",
            "등록일": "registered_date",
            "수강코스": "course",
            "총 횟수": "total_sessions",
            "잔여 횟수": "remaining_sessions",
            "상태": "status",
            "메모": "memo",
        }
        frame = frame.rename(columns={k: v for k, v in rename.items() if k in frame.columns})
        needed = [
            "student_id",
            "name",
            "phone",
            "registered_date",
            "course",
            "total_sessions",
            "remaining_sessions",
            "status",
            "memo",
        ]
        for c in needed:
            if c not in frame.columns:
                frame[c] = "" if c not in ("total_sessions", "remaining_sessions") else 0
        frame["total_sessions"] = pd.to_numeric(frame["total_sessions"], errors="coerce").fillna(0).astype(int)
        frame["remaining_sessions"] = pd.to_numeric(frame["remaining_sessions"], errors="coerce").fillna(0).astype(int)
        frame["student_id"] = frame["student_id"].astype(str).str.strip()
        frame = frame[frame["student_id"] != ""]
        return frame.astype(object).where(pd.notna(frame), "").to_dict(orient="records")

    if ws == "attendance_requests":
        if "time" in frame.columns and "time_text" not in frame.columns:
            frame = frame.rename(columns={"time": "time_text"})
        needed = ["request_id", "time_text", "student_id", "student_name", "status", "approved_time"]
        for c in needed:
            if c not in frame.columns:
                frame[c] = ""
        frame["request_id"] = frame["request_id"].astype(str).str.strip()
        frame = frame[frame["request_id"] != ""]
        return frame.astype(object).where(pd.notna(frame), "").to_dict(orient="records")

    if ws == "attendance_log":
        if "time" in frame.columns and "time_text" not in frame.columns:
            frame = frame.rename(columns={"time": "time_text"})
        needed = ["time_text", "student_id", "student_name", "remain_count", "event"]
        for c in needed:
            if c not in frame.columns:
                frame[c] = 0 if c == "remain_count" else ""
        frame["remain_count"] = pd.to_numeric(frame["remain_count"], errors="coerce").fillna(0).astype(int)
        return frame.astype(object).where(pd.notna(frame), "").to_dict(orient="records")

    # default passthrough for schedule/curriculum/finance
    return frame.astype(object).where(pd.notna(frame), "").to_dict(orient="records")


class DBConn:
    """Small adapter exposing read/update like GSheetsConnection."""

    def __init__(self):
        _t0 = time.perf_counter()
        self.backend = _db_backend()
        self._gs = None
        self._cache_ns = "_db_supabase_read_cache"
        perf_log(f"db.conn.init.{self.backend}", (time.perf_counter() - _t0) * 1000.0)

    def _cache_get(self, key: str, ttl: int):
        if ttl <= 0:
            return None
        store = st.session_state.get(self._cache_ns, {})
        hit = store.get(key)
        if not hit:
            return None
        ts = float(hit.get("ts", 0.0))
        if (time.time() - ts) > float(ttl):
            return None
        df = hit.get("df")
        return df.copy() if isinstance(df, pd.DataFrame) else None

    def _cache_set(self, key: str, df: pd.DataFrame):
        store = st.session_state.get(self._cache_ns)
        if not isinstance(store, dict):
            store = {}
        store[key] = {"ts": time.time(), "df": df.copy()}
        st.session_state[self._cache_ns] = store

    def _cache_clear(self):
        st.session_state.pop(self._cache_ns, None)

    def _gsheets(self):
        _t0 = time.perf_counter()
        if self._gs is None:
            self._gs = st.connection("google_drive", type=GSheetsConnection)
            perf_log("db.gsheets.connection.create", (time.perf_counter() - _t0) * 1000.0)
        else:
            perf_log("db.gsheets.connection.cache_hit", (time.perf_counter() - _t0) * 1000.0)
        return self._gs

    def read(self, *, worksheet: str | None = None, spreadsheet: str | None = None, ttl: int = 0, **kwargs):
        _t0 = time.perf_counter()
        if self.backend != "supabase":
            out = self._gsheets().read(worksheet=worksheet, spreadsheet=spreadsheet, ttl=ttl, **kwargs)
            perf_log(f"db.gsheets.read.{worksheet or 'none'}", (time.perf_counter() - _t0) * 1000.0)
            return out

        ws = str(worksheet or "").strip()
        if not ws:
            return pd.DataFrame()
        tm = _WS_MAP.get(ws)
        if tm is None:
            raise ValueError(f"Unknown worksheet mapping for Supabase: {ws}")

        cache_key = f"{tm.table}:{ws}"
        cached = self._cache_get(cache_key, int(ttl))
        if cached is not None:
            perf_log(f"db.supabase.read.cache_hit.{tm.table}", (time.perf_counter() - _t0) * 1000.0)
            return cached

        res = _sb().table(tm.table).select("*").execute()
        rows = list(res.data or [])
        out = _legacy_from_supabase(ws, rows)
        if int(ttl) > 0:
            self._cache_set(cache_key, out)
        perf_log(f"db.supabase.read.{tm.table}.rows={len(rows)}", (time.perf_counter() - _t0) * 1000.0)
        return out

    def update(self, *, worksheet: str | None = None, spreadsheet: str | None = None, data=None, **kwargs):
        _t0 = time.perf_counter()
        if self.backend != "supabase":
            out = self._gsheets().update(worksheet=worksheet, spreadsheet=spreadsheet, data=data, **kwargs)
            perf_log(f"db.gsheets.update.{worksheet or 'none'}", (time.perf_counter() - _t0) * 1000.0)
            return out

        ws = str(worksheet or "").strip()
        if not ws:
            return None
        tm = _WS_MAP.get(ws)
        if tm is None:
            raise ValueError(f"Unknown worksheet mapping for Supabase: {ws}")

        df = data if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
        payload = _supabase_from_legacy(ws, df)

        if tm.pk:
            # Replace-by-upsert (closest behavior to sheet overwrite)
            if payload:
                _sb().table(tm.table).upsert(payload).execute()
            self._cache_clear()
            perf_log(f"db.supabase.update.upsert.{tm.table}.rows={len(payload)}", (time.perf_counter() - _t0) * 1000.0)
            return None

        # Append-only tables: attendance_log, marketing_history
        if payload:
            _sb().table(tm.table).insert(payload).execute()
        self._cache_clear()
        perf_log(f"db.supabase.update.insert.{tm.table}.rows={len(payload)}", (time.perf_counter() - _t0) * 1000.0)
        return None

