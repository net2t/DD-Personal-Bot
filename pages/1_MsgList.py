"""
Page 1 – MsgList
Send personal messages to targets.
"""

import os
import sys
import streamlit as st
import pandas as pd
from dotenv import load_dotenv

load_dotenv(override=False)
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from main import Config, SheetsManager, Logger
from utils.ui_helpers import (
    load_custom_css, create_metric_card, create_glowing_container,
    create_status_badge, create_dashboard_header, create_filter_controls,
    apply_filters, create_glowing_button, create_data_table_with_style,
    create_info_card, create_stats_grid
)

# ── helpers ────────────────────────────────────────────────────────────────

def _make_logger():
    return Logger("streamlit_msglist")

@st.cache_resource(show_spinner=False)
def _sheets():
    log = _make_logger()
    sm = SheetsManager(log)
    if not sm.connect():
        return None, log
    return sm, log

def _load_df(sheets_mgr, sheet_id, sheet_name):
    ws = sheets_mgr.get_sheet(sheet_id, sheet_name, create_if_missing=True)
    if ws is None:
        return None, None
    rows = ws.get_all_values()
    if not rows:
        return pd.DataFrame(), ws
    headers = rows[0]
    data = rows[1:]
    df = pd.DataFrame(data, columns=headers)
    df.insert(0, "_row", range(2, 2 + len(df)))  # 1-based sheet row
    return df, ws

def _save_row(sheets_mgr, ws, df_row, original_df):
    """Write a single edited row back to the sheet."""
    row_num = int(df_row["_row"])
    headers = [c for c in original_df.columns if c != "_row"]
    for col_idx, col in enumerate(headers, start=1):
        val = str(df_row.get(col, ""))
        sheets_mgr.update_cell(ws, row_num, col_idx, val)

# ── UI ─────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="MsgList", page_icon="💬", layout="wide")

# Load custom CSS for professional styling
load_custom_css()

# Create dashboard header
create_dashboard_header(
    "💬 Message List Dashboard",
    "Manage and track your messaging campaigns"
)

sm, log = _sheets()
if sm is None:
    st.error("❌ Google Sheets connection failed. Check credentials.")
    st.stop()

sheet_id = Config.SHEET_ID
sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit" if sheet_id else ""
if sheet_url:
    st.markdown(f"📎 [Open in Google Sheets]({sheet_url})", unsafe_allow_html=False)

with st.spinner("Loading MsgList…"):
    df, ws = _load_df(sm, sheet_id, "MsgList")

if df is None:
    st.error("Could not load MsgList sheet.")
    st.stop()

if df.empty:
    create_info_card(
        "No Messages Found",
        "Your message list is empty. Add new targets below to get started with your messaging campaign.",
        icon="📭",
        color="#ffa726"
    )
else:
    # ── Summary Stats ─────────────────────────────────────────────────────
    stats = {
        "Total Targets": len(df),
        "Pending": len(df[df[status_col].str.lower().str.startswith("pending")] if status_col else []),
        "Completed": len(df[df[status_col].str.lower().isin(["done", "sent"])]) if status_col else 0
    }
    create_stats_grid(stats, columns=3)
    
    # ── Filter Controls ─────────────────────────────────────────────────────
    if status_col:
        filters = create_filter_controls(df, ["STATUS"])
        view = apply_filters(df, filters)
    else:
        view = df

    st.caption(f"Showing {len(view)} targets")

    # ── Editable Table ─────────────────────────────────────────────────────
    display_cols = [c for c in view.columns if c != "_row"]
    
    create_glowing_container(
        f"📝 **Edit Targets** - Modify message details and status",
        glow_color="#667eea"
    )
    
    edited = st.data_editor(
        view[display_cols],
        use_container_width=True,
        num_rows="dynamic",
        key="msglist_editor",
        column_config={
            "STATUS": st.column_config.SelectboxColumn(
                "STATUS",
                options=["pending", "Done", "Failed", "Skipped"],
                default="pending"
            )
        } if "STATUS" in view.columns else None
    )

    col1, col2 = st.columns([1, 5])
    with col1:
        if create_glowing_button("Save Changes", "save_msg", "💾", primary=True):
            with st.spinner("Saving…"):
                # Rebuild with _row column
                edited_with_row = edited.copy()
                edited_with_row.insert(0, "_row", view["_row"].values[:len(edited)])
                for _, row in edited_with_row.iterrows():
                    _save_row(sm, ws, row, df)
            create_success_animation("Changes saved successfully!")
            st.cache_resource.clear()
            st.rerun()
    with col2:
        if create_glowing_button("Refresh", "refresh_msg", "🔄"):
            st.cache_resource.clear()
            st.rerun()

create_gradient_header("➕ Add New Target", "1.5rem")

with st.form("add_msg"):
    create_glowing_container(
        "📝 **Target Information** - Fill in the details below",
        glow_color="#764ba2"
    )
    
    cols = st.columns(3)
    mode = cols[0].selectbox("MODE", ["nick", "url"])
    name = cols[1].text_input("NAME")
    nick = cols[2].text_input("NICK/URL")
    cols2 = st.columns(3)
    city = cols2[0].text_input("CITY")
    message = cols2[1].text_area("MESSAGE", height=80)
    status = cols2[2].selectbox("STATUS", ["pending", "Done", "Failed", "Skipped"])
    submitted = st.form_submit_button("Add Target", type="primary")
    if submitted:
        if not nick:
            st.warning("NICK/URL is required.")
        else:
            headers = [c for c in (df.columns if not df.empty else [])] or [
                "MODE","NAME","NICK/URL","CITY","POSTS","FOLLOWERS","Gender",
                "MESSAGE","STATUS","NOTES","RESULT URL"
            ]
            row_vals = {h: "" for h in headers}
            row_vals.update({"MODE": mode, "NAME": name, "NICK/URL": nick,
                             "CITY": city, "MESSAGE": message, "STATUS": status})
            with st.spinner("Adding target…"):
                sm.append_row(ws, [row_vals.get(h, "") for h in headers])
            create_success_animation("Target added successfully!")
            st.cache_resource.clear()
            st.rerun()
