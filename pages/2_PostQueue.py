"""
Page 2 – PostQueue
Manage posts (text / image) ready to be published.
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
    create_info_card, create_stats_grid, create_progress_ring, create_activity_chart
)


@st.cache_resource(show_spinner=False)
def _sheets():
    log = Logger("streamlit_postqueue")
    sm = SheetsManager(log)
    if not sm.connect():
        return None, log
    return sm, log


def _load_df(sm, sheet_id, name):
    ws = sm.get_sheet(sheet_id, name, create_if_missing=True)
    if ws is None:
        return None, None
    rows = ws.get_all_values()
    if not rows:
        return pd.DataFrame(), ws
    df = pd.DataFrame(rows[1:], columns=rows[0])
    df.insert(0, "_row", range(2, 2 + len(df)))
    return df, ws


def _save_row(sm, ws, df_row, original_df):
    row_num = int(df_row["_row"])
    headers = [c for c in original_df.columns if c != "_row"]
    for i, col in enumerate(headers, 1):
        sm.update_cell(ws, row_num, i, str(df_row.get(col, "")))


def _normalize_status(value: str) -> str:
    v = (value or "").strip()
    if not v:
        return ""
    vv = v.lower()
    if vv.startswith("pending"):
        return "Pending"
    if vv.startswith("done"):
        return "Done"
    if vv.startswith("failed"):
        return "Failed"
    if vv.startswith("repeating"):
        return "Repeating"
    if vv.startswith("skipped"):
        return "Skipped"
    return " ".join([w.capitalize() for w in vv.split() if w])


# ── UI ─────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="PostQueue", page_icon="📤", layout="wide")

# Load custom CSS for professional styling
load_custom_css()

# Create dashboard header
create_dashboard_header(
    "📤 Post Queue Dashboard",
    "Manage your content posting schedule and media"
)

sm, log = _sheets()
if sm is None:
    st.error("❌ Sheets connection failed.")
    st.stop()

sheet_id = Config.SHEET_ID
if sheet_id:
    st.markdown(f"📎 [Open in Google Sheets](https://docs.google.com/spreadsheets/d/{sheet_id}/edit)")

with st.spinner("Loading PostQueue…"):
    df, ws = _load_df(sm, sheet_id, "PostQueue")

if df is None:
    st.error("Could not load PostQueue.")
    st.stop()

if df.empty:
    create_info_card(
        "No Posts Scheduled",
        "Your post queue is empty. Add new content below to schedule your posts.",
        icon="📭",
        color="#ffa726"
    )
else:
    # ── Summary Stats ─────────────────────────────────────────────────────
    status_col = "STATUS" if "STATUS" in df.columns else None
    type_col = "TYPE" if "TYPE" in df.columns else None
    
    stats = {
        "Total Posts": len(df),
        "Pending": len(df[df[status_col].str.lower().str.startswith("pending")] if status_col else []),
        "Published": len(df[df[status_col].str.lower().isin(["done", "posted"])]) if status_col else 0
    }
    create_stats_grid(stats, columns=3)
    
    # Add type distribution if available
    if type_col:
        type_counts = df[type_col].value_counts()
        col1, col2 = st.columns(2)
        with col1:
            if "image" in type_counts:
                create_progress_ring(
                    (type_counts.get("image", 0) / len(df) * 100),
                    "Image Posts",
                    "#667eea"
                )
        with col2:
            if "text" in type_counts:
                create_progress_ring(
                    (type_counts.get("text", 0) / len(df) * 100),
                    "Text Posts",
                    "#764ba2"
                )
    
    # ── Filter Controls ─────────────────────────────────────────────────────
    filter_cols = []
    if status_col:
        filter_cols.append("STATUS")
    if type_col:
        filter_cols.append("TYPE")
    
    if filter_cols:
        filters = create_filter_controls(df, filter_cols)
        view = apply_filters(df, filters)
    else:
        view = df

    st.caption(f"Showing {len(view)} posts")
    create_glowing_container(
        f"📝 **Edit Posts** - Modify post content and scheduling",
        glow_color="#667eea"
    )
    
    display_cols = [c for c in view.columns if c != "_row"]
    edited = st.data_editor(view[display_cols], use_container_width=True,
                             num_rows="dynamic", key="postqueue_editor",
                             column_config={
                                 "STATUS": st.column_config.SelectboxColumn(
                                     "STATUS",
                                     options=["Pending", "Done", "Failed", "Skipped", "Repeating"],
                                     default="Pending"
                                 ),
                                 "TYPE": st.column_config.SelectboxColumn(
                                     "TYPE",
                                     options=["image", "text"],
                                     default="image"
                                 )
                             } if "STATUS" in view.columns else None)

    c1, c2 = st.columns([1, 5])
    with c1:
        if create_glowing_button("Save Changes", "save_post", "💾", primary=True):
            with st.spinner("Saving…"):
                ew = edited.copy()
                ew.insert(0, "_row", view["_row"].values[:len(edited)])
                for _, row in ew.iterrows():
                    _save_row(sm, ws, row, df)
            create_success_animation("Changes saved successfully!")
            st.cache_resource.clear()
            st.rerun()
    with c2:
        if create_glowing_button("Refresh", "refresh_post", "🔄"):
            st.cache_resource.clear()
            st.rerun()

create_gradient_header("➕ Add New Post", "1.5rem")

with st.form("add_post"):
    create_glowing_container(
        "📝 **Post Details** - Configure your content for publishing",
        glow_color="#764ba2"
    )
    
    c = st.columns(3)
    ptype = c[0].selectbox("TYPE", ["image", "text"])
    status = c[1].selectbox("STATUS", ["Pending", "Done", "Failed", "Skipped", "Repeating"])
    title = c[2].text_input("TITLE")
    c2 = st.columns(2)
    image_path = c2[0].text_input("IMGLink / URL")
    title_ur = c2[1].text_input("URDU / Caption")
    tags = st.text_input("TAGS (comma separated)")
    sub = st.form_submit_button("Add Post", type="primary")
    if sub:
        rows = ws.get_all_values() if ws else []
        headers = rows[0] if rows else [
            "STATUS", "TITLE", "URDU", "IMGLink", "TYPE",
            "POSTL", "TIMESTAMP", "NOTES", "SIGNATURE"
        ]
        rv = {h: "" for h in headers}
        # Backward-compatible writes if sheet still has legacy header names.
        rv.update({"STATUS": _normalize_status(status), "TITLE": title, "TYPE": ptype, "TAGS": tags})
        if "URDU" in headers:
            rv["URDU"] = title_ur
        elif "TITLE_UR" in headers:
            rv["TITLE_UR"] = title_ur

        if "IMGLink" in headers:
            rv["IMGLink"] = image_path
        elif "IMAGE_PATH" in headers:
            rv["IMAGE_PATH"] = image_path
        with st.spinner("Adding post…"):
            sm.append_row(ws, [rv.get(h, "") for h in headers])
        create_success_animation("Post added successfully!")
        st.cache_resource.clear()
        st.rerun()
