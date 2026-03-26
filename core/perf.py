import os
from collections import deque

import streamlit as st

_PERF_LOG_KEY = "_perf_logs"
_PERF_MAX = 200


def perf_enabled() -> bool:
    """성능 계측 on/off. secrets.PERF_DEBUG=true 또는 env PERF_DEBUG=1."""
    try:
        if "PERF_DEBUG" in st.secrets:
            v = str(st.secrets["PERF_DEBUG"]).strip().lower()
            return v in ("1", "true", "yes", "on")
    except Exception:
        pass
    return str(os.getenv("PERF_DEBUG", "")).strip().lower() in ("1", "true", "yes", "on")


def perf_log(label: str, elapsed_ms: float):
    if not perf_enabled():
        return
    dq = st.session_state.get(_PERF_LOG_KEY)
    if dq is None:
        dq = deque(maxlen=_PERF_MAX)
        st.session_state[_PERF_LOG_KEY] = dq
    dq.append({"label": str(label), "ms": float(elapsed_ms)})


def perf_recent_top(n: int = 10):
    dq = st.session_state.get(_PERF_LOG_KEY)
    if not dq:
        return []
    rows = list(dq)
    rows.sort(key=lambda x: x.get("ms", 0.0), reverse=True)
    return rows[:n]
