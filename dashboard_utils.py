import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import gspread
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials


def repo_root() -> Path:
    return Path(__file__).resolve().parent


def load_env() -> None:
    load_dotenv(dotenv_path=repo_root() / ".env", override=False)


def sanitize_headers(headers: List[str]) -> List[str]:
    cleaned: List[str] = []
    seen: Dict[str, int] = {}

    for i, h in enumerate(headers):
        base = str(h).strip()
        if not base:
            base = f"col_{i + 1}"

        count = seen.get(base, 0) + 1
        seen[base] = count

        if count == 1:
            cleaned.append(base)
        else:
            cleaned.append(f"{base}_{count}")

    return cleaned


@st.cache_resource(show_spinner=False)
def gs_client(credentials_file: str) -> gspread.Client:
    creds_path = Path(credentials_file)
    if not creds_path.is_absolute():
        creds_path = repo_root() / creds_path

    if not creds_path.exists():
        raise FileNotFoundError(f"Credentials file not found: {creds_path}")

    scope = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_file(str(creds_path), scopes=scope)
    return gspread.authorize(creds)


def open_workbook(sheet_id: str, credentials_file: str):
    client = gs_client(credentials_file)
    return client.open_by_key(sheet_id)


@st.cache_data(show_spinner=False, ttl=60)
def worksheet_to_df(sheet_id: str, ws_title: str, credentials_file: str) -> pd.DataFrame:
    wb = open_workbook(sheet_id, credentials_file)
    ws = wb.worksheet(ws_title)
    values = ws.get_all_values()
    if not values:
        return pd.DataFrame()

    headers = sanitize_headers(values[0])
    rows = values[1:]
    df = pd.DataFrame(rows, columns=headers)

    df.columns = [str(c).strip() for c in df.columns]
    for col in df.columns:
        df[col] = df[col].astype(str)

    return df


def find_col(df: pd.DataFrame, names: Iterable[str]) -> Optional[str]:
    lower = {c.strip().lower(): c for c in df.columns}
    for n in names:
        key = n.strip().lower()
        if key in lower:
            return lower[key]
    return None


def status_metrics(df: pd.DataFrame) -> Dict[str, int]:
    col = find_col(df, ["status"])
    if not col:
        return {}

    s = df[col].fillna("").astype(str).str.strip()
    total = int(len(s))
    pending = int((s.str.lower() == "pending").sum())
    done = int(s.str.lower().isin(["done", "success", "posted"]).sum())
    failed = int(s.str.lower().isin(["failed", "error"]).sum())
    other = total - pending - done - failed

    return {"total": total, "pending": pending, "done": done, "failed": failed, "other": other}


def parse_timestamp_series(df: pd.DataFrame) -> Tuple[Optional[str], Optional[pd.Series]]:
    col = find_col(df, ["timestamp", "time", "date"])
    if not col:
        return None, None

    parsed = pd.to_datetime(df[col], errors="coerce", utc=False)
    if parsed.notna().sum() == 0:
        return col, None

    return col, parsed


@dataclass
class FilterState:
    status_values: Optional[List[str]] = None
    search_text: str = ""
    date_range: Optional[Tuple[pd.Timestamp, pd.Timestamp]] = None


def apply_filters(df: pd.DataFrame, status_col: Optional[str], ts: Optional[pd.Series], fs: FilterState) -> pd.DataFrame:
    out = df.copy()

    if status_col and fs.status_values:
        s = out[status_col].fillna("").astype(str).str.strip()
        out = out[s.isin(fs.status_values)]

    if fs.search_text:
        q = fs.search_text.strip().lower()
        if q:
            mask = pd.Series(False, index=out.index)
            for c in out.columns:
                mask = mask | out[c].fillna("").astype(str).str.lower().str.contains(q, na=False)
            out = out[mask]

    if ts is not None and fs.date_range is not None:
        start, end = fs.date_range
        ts_sub = ts.reindex(out.index)
        end_inclusive = end + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
        mask = (ts_sub >= start) & (ts_sub <= end_inclusive)
        out = out[mask]

    return out


def normalize_table(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    non_empty_cols = [c for c in df.columns if not df[c].fillna("").astype(str).str.strip().eq("").all()]
    df = df[non_empty_cols]

    status_col = find_col(df, ["status"])
    first_cols: List[str] = []
    if status_col:
        first_cols.append(status_col)

    rest = [c for c in df.columns if c not in first_cols]
    return df[first_cols + rest]


def style_failed_rows(df: pd.DataFrame) -> Optional[pd.io.formats.style.Styler]:
    if df.empty:
        return None

    status_col = find_col(df, ["status"])
    if not status_col:
        return None

    def _row_style(row: pd.Series):
        v = str(row.get(status_col, "")).strip().lower()
        if v in {"failed", "error"}:
            return ["background-color: rgba(255,0,0,0.12)"] * len(row)
        return [""] * len(row)

    return df.style.apply(_row_style, axis=1)


def dataframe_download_button(df: pd.DataFrame, filename: str, label: str = "Download CSV") -> None:
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    st.download_button(label=label, data=csv_bytes, file_name=filename, mime="text/csv")


def require_config() -> Tuple[str, str]:
    load_env()
    sheet_id = os.getenv("DD_SHEET_ID", "").strip()
    credentials_file = os.getenv("CREDENTIALS_FILE", "credentials.json").strip()

    if not sheet_id:
        raise RuntimeError("Missing DD_SHEET_ID in .env")

    return sheet_id, credentials_file
