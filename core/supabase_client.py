import streamlit as st
import time
from core.perf import perf_log

try:
    from supabase import Client, create_client
except Exception:  # pragma: no cover
    Client = object  # type: ignore
    create_client = None  # type: ignore


_SUPABASE_SESSION_KEY = "_singleton_supabase_client"


def supabase_enabled() -> bool:
    try:
        return str(st.secrets.get("DB_BACKEND", "gsheets")).strip().lower() == "supabase"
    except Exception:
        return False


def get_supabase_client() -> "Client | None":
    _t0 = time.perf_counter()
    client = st.session_state.get(_SUPABASE_SESSION_KEY)
    if client is not None:
        perf_log("db.supabase_client.cache_hit", (time.perf_counter() - _t0) * 1000.0)
        return client

    if create_client is None:
        perf_log("db.supabase_client.import_missing", (time.perf_counter() - _t0) * 1000.0)
        return None

    try:
        url = str(st.secrets.get("SUPABASE_URL", "")).strip()
        key = str(st.secrets.get("SUPABASE_SERVICE_ROLE_KEY", "")).strip()
    except Exception:
        perf_log("db.supabase_client.secrets_error", (time.perf_counter() - _t0) * 1000.0)
        return None

    if not url or not key:
        perf_log("db.supabase_client.missing_config", (time.perf_counter() - _t0) * 1000.0)
        return None

    try:
        client = create_client(url, key)
        st.session_state[_SUPABASE_SESSION_KEY] = client
        perf_log("db.supabase_client.create_client", (time.perf_counter() - _t0) * 1000.0)
        return client
    except Exception:
        perf_log("db.supabase_client.create_failed", (time.perf_counter() - _t0) * 1000.0)
        return None

