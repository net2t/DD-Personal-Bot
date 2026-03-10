"""
Page 3 – Inbox & Activity
View inbox conversations, compose replies, and track activity log.
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
    create_info_card, create_stats_grid, create_activity_chart
)


@st.cache_resource(show_spinner=False)
def _sheets():
    log = Logger("streamlit_inbox")
    sm = SheetsManager(log)
    if not sm.connect():
        return None, log
    return sm, log


def _load(sm, sheet_id, name, create=True):
    ws = sm.get_sheet(sheet_id, name, create_if_missing=create)
    if ws is None:
        return None, None
    rows = ws.get_all_values()
    if not rows or len(rows) <= 1:
        return pd.DataFrame(), ws
    df = pd.DataFrame(rows[1:], columns=rows[0])
    df.insert(0, "_row", range(2, 2 + len(df)))
    return df, ws


def _save_row(sm, ws, df_row, original_df):
    row_num = int(df_row["_row"])
    headers = [c for c in original_df.columns if c != "_row"]
    for i, col in enumerate(headers, 1):
        sm.update_cell(ws, row_num, i, str(df_row.get(col, "")))


# ── UI ─────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Inbox & Activity", page_icon="📥", layout="wide")

# Load custom CSS for professional styling
load_custom_css()

# Create dashboard header
create_dashboard_header(
    "📥 Inbox & Activity Dashboard",
    "Monitor conversations and track system activity"
)

sm, log = _sheets()
if sm is None:
    st.error("❌ Sheets connection failed.")
    st.stop()

sheet_id = Config.SHEET_ID
if sheet_id:
    st.markdown(f"📎 [Open in Google Sheets](https://docs.google.com/spreadsheets/d/{sheet_id}/edit)")

tab_inbox, tab_activity, tab_conv = st.tabs(["📨 Inbox / Replies", "📊 Activity Log", "💬 Conversation Log"])

# ── Tab 1: Inbox ───────────────────────────────────────────────────────────
with tab_inbox:
    with st.spinner("Loading Inbox…"):
        # Try multiple sheet name variants
        inbox_df, inbox_ws = None, None
        for sheet_name in ["Inbox", "InboxQueue", "Inbox & Activity"]:
            inbox_df, inbox_ws = _load(sm, sheet_id, sheet_name, create=False)
            if inbox_df is not None:
                break
        if inbox_df is None:
            inbox_df, inbox_ws = _load(sm, sheet_id, "Inbox", create=True)

    if inbox_df is None:
        st.error("Could not load Inbox sheet.")
    elif inbox_df.empty:
        create_info_card(
            "No Inbox Messages",
            "Your inbox is empty. Run `python main.py --mode inbox` to fetch messages from your account.",
            icon="📭",
            color="#ffa726"
        )
    else:
        # Summary metrics
        status_col = "STATUS" if "STATUS" in inbox_df.columns else None
        
        create_glowing_container(
            "📊 **Inbox Overview** - Message statistics and status",
            glow_color="#667eea"
        )
        
        stats = {
            "Total Conversations": len(inbox_df),
            "Pending Replies": int((inbox_df[status_col].str.lower().str.startswith("pending")).sum()) if status_col else 0,
            "Sent Replies": int((inbox_df[status_col].str.lower() == "sent").sum()) if status_col else 0
        }
        create_stats_grid(stats, columns=3)

        # Filter
        if status_col:
            filters = create_filter_controls(inbox_df, ["STATUS"])
            view = apply_filters(inbox_df, filters)
        else:
            view = inbox_df

        st.caption(f"{len(view)} conversations")
        
        create_glowing_container(
            "💬 **Message Management** - Review and reply to conversations",
            glow_color="#764ba2"
        )
        display_cols = [c for c in view.columns if c != "_row"]
        edited = st.data_editor(
            view[display_cols],
            use_container_width=True,
            num_rows="dynamic",
            key="inbox_editor",
            column_config={
                "MY_REPLY": st.column_config.TextColumn("MY_REPLY (type reply here)", width="large"),
                "STATUS": st.column_config.SelectboxColumn(
                    "STATUS",
                    options=["pending", "sent", "Done", "Skipped", "Failed"],
                ),
            }
        )

        c1, c2 = st.columns([1, 5])
        with c1:
            if create_glowing_button("Save Replies", "save_inbox", "💾", primary=True):
                with st.spinner("Saving…"):
                    ew = edited.copy()
                    ew.insert(0, "_row", view["_row"].values[:len(edited)])
                    for _, row in ew.iterrows():
                        _save_row(sm, inbox_ws, row, inbox_df)
                create_success_animation("Replies saved successfully!")
                st.cache_resource.clear()
                st.rerun()
        with c2:
            if create_glowing_button("Refresh", "refresh_inbox", "🔄"):
                st.cache_resource.clear()
                st.rerun()

    create_gradient_header("➕ Add Inbox Entry Manually", "1.2rem")
    
    with st.form("add_inbox"):
        create_glowing_container(
            "📝 **Manual Entry** - Add conversation details manually",
            glow_color="#f093fb"
        )
        
        cols = st.columns(3)
        nick = cols[0].text_input("NICK")
        name = cols[1].text_input("NAME")
        last_msg = cols[2].text_input("LAST_MSG")
        cols2 = st.columns(3)
        reply = cols2[0].text_area("MY_REPLY", height=80)
        status = cols2[1].selectbox("STATUS", ["pending", "sent", "Done", "Skipped"])
        notes = cols2[2].text_input("NOTES")
        sub = st.form_submit_button("Add Entry", type="primary")
        if sub and nick:
            from datetime import datetime
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            row_vals = [nick, name, last_msg, reply, status, ts, notes, ""]
            with st.spinner("Adding entry…"):
                sm.append_row(inbox_ws, row_vals)
            create_success_animation("Entry added successfully!")
            st.cache_resource.clear()
            st.rerun()

# ── Tab 2: Activity Log ────────────────────────────────────────────────────
with tab_activity:
    with st.spinner("Loading Activity Log…"):
        logs_df, logs_ws = _load(sm, sheet_id, "Logs", create=True)

    if logs_df is None:
        st.error("Could not load Logs sheet.")
    elif logs_df.empty:
        create_info_card(
            "No Activity Logged",
            "No system activity has been recorded yet. The activity log will show bot operations and events.",
            icon="📭",
            color="#ffa726"
        )
    else:
        # Filters
        create_glowing_container(
            "🔍 **Activity Filters** - Filter system logs by mode and status",
            glow_color="#667eea"
        )
        
        c1, c2, c3 = st.columns(3)
        mode_opts = ["All"] + sorted(logs_df["MODE"].dropna().unique().tolist()) if "MODE" in logs_df.columns else ["All"]
        status_opts = ["All"] + sorted(logs_df["STATUS"].dropna().unique().tolist()) if "STATUS" in logs_df.columns else ["All"]
        mode_f = c1.selectbox("Filter MODE", mode_opts, key="log_mode")
        status_f = c2.selectbox("Filter STATUS", status_opts, key="log_status")
        limit = c3.number_input("Max rows", min_value=10, max_value=1000, value=100, step=10)

        view = logs_df.copy()
        if mode_f != "All" and "MODE" in view.columns:
            view = view[view["MODE"] == mode_f]
        if status_f != "All" and "STATUS" in view.columns:
            view = view[view["STATUS"] == status_f]
        view = view.tail(int(limit))

        st.caption(f"Showing last {len(view)} entries")
        display_cols = [c for c in view.columns if c != "_row"]
        st.dataframe(view[display_cols], use_container_width=True)

        if create_glowing_button("Refresh Logs", "refresh_logs", "🔄"):
            st.cache_resource.clear()
            st.rerun()

# ── Tab 3: Conversation Log ────────────────────────────────────────────────
with tab_conv:
    with st.spinner("Loading Conversation Log…"):
        conv_df, conv_ws = _load(sm, sheet_id, "ConversationLog", create=True)

    if conv_df is None:
        st.error("Could not load ConversationLog.")
    elif conv_df.empty:
        create_info_card(
            "No Conversations Logged",
            "No conversation history has been recorded yet. This log will track all message exchanges.",
            icon="📭",
            color="#ffa726"
        )
    else:
        nick_opts = ["All"]
        if "NICK" in conv_df.columns:
            nick_opts += sorted(conv_df["NICK"].dropna().unique().tolist())
        
        create_glowing_container(
            "💬 **Conversation Filters** - View chat history by user",
            glow_color="#764ba2"
        )
        
        nick_f = st.selectbox("Filter by NICK", nick_opts, key="conv_nick")
        view = conv_df if nick_f == "All" else conv_df[conv_df["NICK"] == nick_f]
        view = view.tail(200)

        # Format as chat view
        display_cols = [c for c in view.columns if c != "_row"]
        st.dataframe(view[display_cols], use_container_width=True)

        if create_glowing_button("Refresh Conversations", "refresh_conv", "🔄"):
            st.cache_resource.clear()
            st.rerun()
