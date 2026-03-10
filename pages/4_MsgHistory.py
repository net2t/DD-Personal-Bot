"""
Page 4 – MsgHistory
Read-only view of all sent messages.
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
    create_info_card, create_stats_grid, create_progress_ring
)


@st.cache_resource(show_spinner=False)
def _sheets():
    log = Logger("streamlit_history")
    sm = SheetsManager(log)
    if not sm.connect():
        return None, log
    return sm, log


st.set_page_config(page_title="MsgHistory", page_icon="📜", layout="wide")

# Load custom CSS for professional styling
load_custom_css()

# Create dashboard header
create_dashboard_header(
    "📜 Message History Dashboard",
    "View and analyze your messaging performance"
)

sm, log = _sheets()
if sm is None:
    st.error("❌ Sheets connection failed.")
    st.stop()

sheet_id = Config.SHEET_ID
if sheet_id:
    st.markdown(f"📎 [Open in Google Sheets](https://docs.google.com/spreadsheets/d/{sheet_id}/edit)")

with st.spinner("Loading MsgHistory…"):
    ws = sm.get_sheet(sheet_id, "MsgHistory", create_if_missing=True)
    rows = ws.get_all_values() if ws else []

if not rows or len(rows) <= 1:
    create_info_card(
        "No Message History",
        "No messages have been sent yet. Your message history will appear here once you start sending messages.",
        icon="📭",
        color="#ffa726"
    )
    st.stop()

df = pd.DataFrame(rows[1:], columns=rows[0])

# ── Summary Stats ─────────────────────────────────────────────────────
create_glowing_container(
    "📊 **Message Performance** - Overview of your messaging results",
    glow_color="#667eea"
)

stats = {
    "Total Sent": len(df),
    "Successful": int((df["STATUS"].str.lower().isin(["posted","done","sent"])).sum()) if "STATUS" in df.columns else 0,
    "Failed": int((df["STATUS"].str.lower() == "failed").sum()) if "STATUS" in df.columns else 0
}
create_stats_grid(stats, columns=3)

# Add success rate if we have data
if "STATUS" in df.columns and len(df) > 0:
    success_rate = (stats["Successful"] / stats["Total Sent"]) * 100
    col1, col2, col3 = st.columns(3)
    with col2:
        create_progress_ring(
            round(success_rate, 1),
            "Success Rate",
            "#66bb6a" if success_rate > 80 else "#ffa726" if success_rate > 50 else "#ef5350"
        )

# ── Filters ────────────────────────────────────────────────────────────────
create_glowing_container(
    "🔍 **History Filters** - Filter messages by user and status",
    glow_color="#764ba2"
)

c1, c2 = st.columns(2)
nick_opts = ["All"] + sorted(df["NICK"].dropna().unique().tolist()) if "NICK" in df.columns else ["All"]
nick_f = c1.selectbox("Filter NICK", nick_opts)
status_opts = ["All"] + sorted(df["STATUS"].dropna().unique().tolist()) if "STATUS" in df.columns else ["All"]
status_f = c2.selectbox("Filter STATUS", status_opts)

view = df.copy()
if nick_f != "All" and "NICK" in view.columns:
    view = view[view["NICK"] == nick_f]
if status_f != "All" and "STATUS" in view.columns:
    view = view[view["STATUS"] == status_f]

st.caption(f"{len(view)} records")

create_glowing_container(
    "📋 **Message History** - Detailed view of sent messages",
    glow_color="#667eea"
)

# Add status badges to the display
if "STATUS" in view.columns:
    display_df = view.copy()
    display_df["STATUS"] = display_df["STATUS"].apply(
        lambda x: create_status_badge(str(x)) if pd.notna(x) else ""
    )
    st.markdown(display_df.to_html(escape=False), unsafe_allow_html=True)
else:
    st.dataframe(view, use_container_width=True)

if create_glowing_button("Refresh History", "refresh_history", "🔄"):
    st.cache_resource.clear()
    st.rerun()
