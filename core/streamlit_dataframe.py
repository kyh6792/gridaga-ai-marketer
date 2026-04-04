"""Streamlit data_editor / Arrow dtype 호환."""

from __future__ import annotations

import pandas as pd


def dataframe_for_data_editor(df: pd.DataFrame) -> pd.DataFrame:
    """PyArrow·StringDtype 등으로 TextColumn에 int가 섞일 때 나는 오류 완화."""
    if df is None or df.empty:
        return df
    # tolist()로 numpy 스칼라 → Python int/str 등으로 풀어 Arrow-backed 열 제거
    return pd.DataFrame({c: df[c].tolist() for c in df.columns})
