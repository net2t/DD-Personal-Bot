"""
Main Dashboard Entry Point
Professional colorful dashboard with navigation and overview
"""

import os
import sys
import streamlit as st
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime

load_dotenv(override=False)
sys.path.insert(0, os.path.dirname(__file__))
from main import Config, SheetsManager, Logger
from utils.ui_helpers import (
    load_custom_css, create_metric_card, create_glowing_container,
    create_status_badge, create_dashboard_header, create_filter_controls,
    apply_filters, create_glowing_button, create_data_table_with_style,
    create_info_card, create_stats_grid, create_progress_ring, create_activity_chart,
    create_sidebar_navigation
)

def load_dashboard_data():
    """Load data from all sheets for dashboard overview"""
    log = Logger("dashboard")
    sm = SheetsManager(log)
    
    if not sm.connect():
        return None, None, None, None, log
    
    try:
        # Load data from all sheets
        msglist_df, _ = sm.get_sheet(Config.SHEET_ID, "MsgList", create_if_missing=False), None
        postqueue_df, _ = sm.get_sheet(Config.SHEET_ID, "PostQueue", create_if_missing=False), None
        inbox_df, _ = sm.get_sheet(Config.SHEET_ID, "Inbox", create_if_missing=False), None
        history_df, _ = sm.get_sheet(Config.SHEET_ID, "MsgHistory", create_if_missing=False), None
        
        # Convert to dataframes if sheets exist
        msglist_data = pd.DataFrame(msglist_df.get_all_values()[1:], columns=msglist_df.get_all_values()[0]) if msglist_df and msglist_df.get_all_values() else pd.DataFrame()
        postqueue_data = pd.DataFrame(postqueue_df.get_all_values()[1:], columns=postqueue_df.get_all_values()[0]) if postqueue_df and postqueue_df.get_all_values() else pd.DataFrame()
        inbox_data = pd.DataFrame(inbox_df.get_all_values()[1:], columns=inbox_df.get_all_values()[0]) if inbox_df and inbox_df.get_all_values() else pd.DataFrame()
        history_data = pd.DataFrame(history_df.get_all_values()[1:], columns=history_df.get_all_values()[0]) if history_df and history_df.get_all_values() else pd.DataFrame()
        
        return msglist_data, postqueue_data, inbox_data, history_data, log
        
    except Exception as e:
        log.error(f"Error loading dashboard data: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), log

def create_overview_stats(msglist_df, postqueue_df, inbox_df, history_df):
    """Create overview statistics for all modules"""
    stats = {
        "Message Targets": len(msglist_df),
        "Scheduled Posts": len(postqueue_df),
        "Inbox Messages": len(inbox_df),
        "Sent Messages": len(history_df)
    }
    
    # Add more detailed stats
    if not msglist_df.empty and "STATUS" in msglist_df.columns:
        pending = len(msglist_df[msglist_df["STATUS"].str.lower().str.startswith("pending", na=False)])
        stats["Pending Messages"] = pending
    
    if not postqueue_df.empty and "STATUS" in postqueue_df.columns:
        pending_posts = len(postqueue_df[postqueue_df["STATUS"].str.lower().str.startswith("pending", na=False)])
        stats["Pending Posts"] = pending_posts
    
    if not inbox_df.empty and "STATUS" in inbox_df.columns:
        pending_replies = len(inbox_df[inbox_df["STATUS"].str.lower().str.startswith("pending", na=False)])
        stats["Pending Replies"] = pending_replies
    
    if not history_df.empty and "STATUS" in history_df.columns:
        successful = len(history_df[history_df["STATUS"].str.lower().isin(["sent", "done", "posted"], na=False)])
        stats["Successful Messages"] = successful
    
    return stats

def create_recent_activity_table(msglist_df, postqueue_df, inbox_df, history_df):
    """Create a combined recent activity table"""
    activities = []
    
    # Add recent message targets
    if not msglist_df.empty and "TIMESTAMP" in msglist_df.columns:
        recent = msglist_df.nlargest(5, "TIMESTAMP") if pd.to_numeric(msglist_df["TIMESTAMP"], errors='coerce').notna().all() else msglist_df.tail(5)
        for _, row in recent.iterrows():
            activities.append({
                "Type": "Message Target",
                "Details": f"{row.get('NAME', 'N/A')} - {row.get('STATUS', 'N/A')}",
                "Time": row.get("TIMESTAMP", "N/A")
            })
    
    # Add recent posts
    if not postqueue_df.empty and "TIMESTAMP" in postqueue_df.columns:
        recent = postqueue_df.nlargest(5, "TIMESTAMP") if pd.to_numeric(postqueue_df["TIMESTAMP"], errors='coerce').notna().all() else postqueue_df.tail(5)
        for _, row in recent.iterrows():
            activities.append({
                "Type": "Post",
                "Details": f"{row.get('TITLE', 'N/A')} - {row.get('STATUS', 'N/A')}",
                "Time": row.get("TIMESTAMP", "N/A")
            })
    
    # Add recent inbox messages
    if not inbox_df.empty and "TIMESTAMP" in inbox_df.columns:
        recent = inbox_df.nlargest(5, "TIMESTAMP") if pd.to_numeric(inbox_df["TIMESTAMP"], errors='coerce').notna().all() else inbox_df.tail(5)
        for _, row in recent.iterrows():
            activities.append({
                "Type": "Inbox",
                "Details": f"{row.get('NAME', 'N/A')} - {row.get('STATUS', 'N/A')}",
                "Time": row.get("TIMESTAMP", "N/A")
            })
    
    return pd.DataFrame(activities)

def main():
    st.set_page_config(
        page_title="DD Bot Dashboard", 
        page_icon="🤖", 
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Load custom CSS
    load_custom_css()
    
    # Sidebar navigation
    st.sidebar.markdown("## 🤖 DD Bot Control Panel")
    
    # Navigation
    pages = ["Dashboard", "MsgList", "PostQueue", "InboxActivity", "MsgHistory"]
    selected_page = st.sidebar.selectbox(
        "Navigate to:",
        pages,
        format_func=lambda x: {
            "Dashboard": "🏠 Dashboard",
            "MsgList": "💬 Message List", 
            "PostQueue": "📤 Post Queue",
            "InboxActivity": "📥 Inbox & Activity",
            "MsgHistory": "📜 Message History"
        }.get(x, x)
    )
    
    # Quick actions
    st.sidebar.markdown("### 🚀 Quick Actions")
    if st.sidebar.button("🔄 Refresh All Data", type="primary"):
        st.cache_resource.clear()
        st.rerun()
    
    # Sheet info
    if Config.SHEET_ID:
        st.sidebar.markdown("### 📎 Quick Links")
        st.sidebar.markdown(
            f"[📊 Open Google Sheets](https://docs.google.com/spreadsheets/d/{Config.SHEET_ID}/edit)",
            unsafe_allow_html=True
        )
    
    # Main content
    if selected_page == "Dashboard":
        # Dashboard header
        create_dashboard_header(
            "🤖 DD Bot Dashboard",
            f"Welcome back! Here's your overview for {datetime.now().strftime('%B %d, %Y')}"
        )
        
        # Load data
        with st.spinner("Loading dashboard data..."):
            msglist_df, postqueue_df, inbox_df, history_df, log = load_dashboard_data()
        
        if msglist_df is None:
            st.error("❌ Failed to connect to Google Sheets")
            st.stop()
        
        # Overview statistics
        create_glowing_container(
            "📊 **System Overview** - Current status across all modules",
            glow_color="#667eea"
        )
        
        overview_stats = create_overview_stats(msglist_df, postqueue_df, inbox_df, history_df)
        create_stats_grid(overview_stats, columns=4)
        
        # Module status cards
        col1, col2 = st.columns(2)
        
        with col1:
            create_glowing_container(
                "💬 **Message Module** - Target management status",
                glow_color="#764ba2"
            )
            
            if not msglist_df.empty:
                msg_stats = {
                    "Total Targets": len(msglist_df),
                    "Pending": len(msglist_df[msglist_df["STATUS"].str.lower().str.startswith("pending", na=False)]) if "STATUS" in msglist_df.columns else 0,
                    "Completed": len(msglist_df[msglist_df["STATUS"].str.lower().isin(["done", "sent"], na=False)]) if "STATUS" in msglist_df.columns else 0
                }
                create_stats_grid(msg_stats, columns=3)
                
                if create_glowing_button("Manage Messages", "go_msglist", "💬", primary=True):
                    st.switch_page("pages/1_MsgList.py")
            else:
                create_info_card(
                    "No Message Data",
                    "Start by adding message targets to begin your campaigns.",
                    icon="📭",
                    color="#ffa726"
                )
        
        with col2:
            create_glowing_container(
                "📤 **Post Module** - Content scheduling status",
                glow_color="#f093fb"
            )
            
            if not postqueue_df.empty:
                post_stats = {
                    "Total Posts": len(postqueue_df),
                    "Pending": len(postqueue_df[postqueue_df["STATUS"].str.lower().str.startswith("pending", na=False)]) if "STATUS" in postqueue_df.columns else 0,
                    "Published": len(postqueue_df[postqueue_df["STATUS"].str.lower().isin(["done", "posted"], na=False)]) if "STATUS" in postqueue_df.columns else 0
                }
                create_stats_grid(post_stats, columns=3)
                
                if create_glowing_button("Manage Posts", "go_postqueue", "📤", primary=True):
                    st.switch_page("pages/2_PostQueue.py")
            else:
                create_info_card(
                    "No Post Data",
                    "Schedule your content to automate posting.",
                    icon="📭",
                    color="#ffa726"
                )
        
        # Inbox and History
        col3, col4 = st.columns(2)
        
        with col3:
            create_glowing_container(
                "📥 **Inbox Module** - Message monitoring status",
                glow_color="#667eea"
            )
            
            if not inbox_df.empty:
                inbox_stats = {
                    "Total Messages": len(inbox_df),
                    "Pending Replies": len(inbox_df[inbox_df["STATUS"].str.lower().str.startswith("pending", na=False)]) if "STATUS" in inbox_df.columns else 0,
                    "Replied": len(inbox_df[inbox_df["STATUS"].str.lower() == "sent"]) if "STATUS" in inbox_df.columns else 0
                }
                create_stats_grid(inbox_stats, columns=3)
                
                if create_glowing_button("Manage Inbox", "go_inbox", "📥", primary=True):
                    st.switch_page("pages/3_InboxActivity.py")
            else:
                create_info_card(
                    "No Inbox Data",
                    "Monitor and reply to incoming messages automatically.",
                    icon="📭",
                    color="#ffa726"
                )
        
        with col4:
            create_glowing_container(
                "📜 **History Module** - Performance tracking",
                glow_color="#764ba2"
            )
            
            if not history_df.empty:
                hist_stats = {
                    "Total Sent": len(history_df),
                    "Successful": len(history_df[history_df["STATUS"].str.lower().isin(["sent", "done", "posted"], na=False)]) if "STATUS" in history_df.columns else 0,
                    "Failed": len(history_df[history_df["STATUS"].str.lower() == "failed"]) if "STATUS" in history_df.columns else 0
                }
                create_stats_grid(hist_stats, columns=3)
                
                # Success rate
                if "STATUS" in history_df.columns and len(history_df) > 0:
                    success_rate = (hist_stats["Successful"] / hist_stats["Total Sent"]) * 100
                    create_progress_ring(
                        round(success_rate, 1),
                        "Success Rate",
                        "#66bb6a" if success_rate > 80 else "#ffa726" if success_rate > 50 else "#ef5350"
                    )
                
                if create_glowing_button("View History", "go_history", "📜", primary=True):
                    st.switch_page("pages/4_MsgHistory.py")
            else:
                create_info_card(
                    "No History Data",
                    "Your message history will appear here once you start sending messages.",
                    icon="📭",
                    color="#ffa726"
                )
        
        # Recent activity
        create_glowing_container(
            "⏰ **Recent Activity** - Latest updates across all modules",
            glow_color="#667eea"
        )
        
        recent_activity = create_recent_activity_table(msglist_df, postqueue_df, inbox_df, history_df)
        if not recent_activity.empty:
            st.dataframe(recent_activity, use_container_width=True)
        else:
            create_info_card(
                "No Recent Activity",
                "Start using the bot modules to see activity here.",
                icon="📭",
                color="#ffa726"
            )
        
        # System info
        create_glowing_container(
            "ℹ️ **System Information** - Bot configuration and status",
            glow_color="#764ba2"
        )
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Bot Version", "2.1.0")
        with col2:
            st.metric("Sheets Connected", "✅ Active" if Config.SHEET_ID else "❌ Not Configured")
        with col3:
            st.metric("Last Updated", datetime.now().strftime("%H:%M:%S"))
    
    else:
        # Navigate to selected page
        page_map = {
            "MsgList": "pages/1_MsgList.py",
            "PostQueue": "pages/2_PostQueue.py", 
            "InboxActivity": "pages/3_InboxActivity.py",
            "MsgHistory": "pages/4_MsgHistory.py"
        }
        
        if selected_page in page_map:
            st.switch_page(page_map[selected_page])

if __name__ == "__main__":
    main()
