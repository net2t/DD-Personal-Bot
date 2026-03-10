"""
UI Helper Functions for Professional Dashboard
Provides reusable components for colorful, glowing UI elements
"""

import streamlit as st
import pandas as pd
from typing import List, Dict, Any, Optional
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime

def load_custom_css():
    """Load custom CSS for dashboard styling"""
    css_file = "styles/dashboard.css"
    try:
        with open(css_file, "r") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        pass  # CSS file not found, use default styling

def create_metric_card(title: str, value: str, delta: Optional[str] = None, 
                      color: str = "blue", icon: str = "📊") -> None:
    """Create a styled metric card with glow effect"""
    col1, col2 = st.columns([1, 4])
    with col1:
        st.markdown(f"<div style='font-size: 2rem; text-align: center;'>{icon}</div>", 
                   unsafe_allow_html=True)
    with col2:
        if delta:
            st.metric(title, value, delta)
        else:
            st.metric(title, value)

def create_glowing_container(content: str, glow_color: str = "#667eea") -> None:
    """Create a container with glow effect"""
    st.markdown(f"""
    <div style="
        background: rgba(255, 255, 255, 0.1);
        backdrop-filter: blur(10px);
        border-radius: 15px;
        border: 1px solid rgba(255, 255, 255, 0.2);
        box-shadow: 0 4px 20px rgba(102, 126, 234, 0.3);
        padding: 1.5rem;
        margin: 1rem 0;
    ">
        {content}
    </div>
    """, unsafe_allow_html=True)

def create_status_badge(status: str, color_map: Dict[str, str] = None) -> str:
    """Create a colored status badge"""
    if color_map is None:
        color_map = {
            "pending": "#ffa726",
            "done": "#66bb6a",
            "failed": "#ef5350",
            "sent": "#42a5f5",
            "skipped": "#9e9e9e",
            "repeating": "#ab47bc"
        }
    
    color = color_map.get(status.lower(), "#9e9e9e")
    return f"""
    <span style="
        background: {color};
        color: white;
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-size: 0.875rem;
        font-weight: 600;
        display: inline-block;
    ">{status.upper()}</span>
    """

def create_progress_ring(percentage: float, title: str, color: str = "#667eea") -> None:
    """Create a circular progress indicator"""
    fig = go.Figure(data=[go.Pie(
        values=[percentage, 100 - percentage],
        hole=0.7,
        showlegend=False,
        textinfo='none',
        marker=dict(colors=[color, '#f0f0f0'])
    )])
    
    fig.add_annotation(
        text=f"{percentage}%",
        x=0.5, y=0.5,
        font_size=20,
        showarrow=False
    )
    
    fig.update_layout(
        title=dict(text=title, x=0.5, font=dict(size=14)),
        height=200,
        margin=dict(l=0, r=0, t=40, b=0)
    )
    
    st.plotly_chart(fig, use_container_width=True)

def create_gradient_header(text: str, size: str = "2rem") -> None:
    """Create a gradient header text"""
    st.markdown(f"""
    <h1 style="
        background: linear-gradient(90deg, #667eea, #764ba2, #f093fb);
        background-size: 200% auto;
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: {size};
        font-weight: 700;
        text-align: center;
        margin: 1rem 0;
        animation: shine 3s linear infinite;
    ">{text}</h1>
    """, unsafe_allow_html=True)

def create_info_card(title: str, content: str, icon: str = "ℹ️", 
                    color: str = "#667eea") -> None:
    """Create an information card with icon"""
    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, rgba(102, 126, 234, 0.1), rgba(118, 75, 162, 0.1));
        backdrop-filter: blur(10px);
        border-radius: 15px;
        border: 1px solid rgba(102, 126, 234, 0.3);
        padding: 1.5rem;
        margin: 1rem 0;
        box-shadow: 0 4px 20px rgba(102, 126, 234, 0.2);
    ">
        <div style="display: flex; align-items: center; margin-bottom: 1rem;">
            <span style="font-size: 1.5rem; margin-right: 1rem;">{icon}</span>
            <h3 style="margin: 0; color: {color}; font-weight: 600;">{title}</h3>
        </div>
        <div style="color: #333; line-height: 1.6;">{content}</div>
    </div>
    """, unsafe_allow_html=True)

def create_stats_grid(stats: Dict[str, Any], columns: int = 3) -> None:
    """Create a grid of statistics"""
    cols = st.columns(columns)
    for i, (key, value) in enumerate(stats.items()):
        with cols[i % columns]:
            create_metric_card(
                title=key.replace("_", " ").title(),
                value=str(value),
                icon="📊"
            )

def create_activity_chart(data: pd.DataFrame, date_col: str, value_col: str, 
                         title: str = "Activity Chart") -> None:
    """Create an activity line chart with gradient"""
    fig = px.line(data, x=date_col, y=value_col, title=title)
    
    fig.update_traces(
        line=dict(width=3, color='#667eea'),
        fill='tonexty',
        fillcolor='rgba(102, 126, 234, 0.1)'
    )
    
    fig.update_layout(
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#333'),
        title_font=dict(size=16, color='#667eea'),
        showlegend=False
    )
    
    st.plotly_chart(fig, use_container_width=True)

def create_filter_controls(data: pd.DataFrame, filters: List[str]) -> Dict[str, str]:
    """Create styled filter controls"""
    filter_values = {}
    
    with st.expander("🔍 Filters", expanded=True):
        cols = st.columns(len(filters))
        
        for i, filter_col in enumerate(filters):
            with cols[i]:
                if filter_col in data.columns:
                    options = ["All"] + sorted(data[filter_col].dropna().unique().tolist())
                    selected = st.selectbox(
                        f"Filter by {filter_col}",
                        options,
                        key=f"filter_{filter_col}"
                    )
                    filter_values[filter_col] = selected
    
    return filter_values

def apply_filters(data: pd.DataFrame, filters: Dict[str, str]) -> pd.DataFrame:
    """Apply filters to dataframe"""
    filtered_data = data.copy()
    
    for col, value in filters.items():
        if value != "All" and col in filtered_data.columns:
            filtered_data = filtered_data[filtered_data[col] == value]
    
    return filtered_data

def create_glowing_button(text: str, key: str, icon: str = "🚀", 
                         primary: bool = False) -> bool:
    """Create a glowing button with icon"""
    button_type = "primary" if primary else "secondary"
    
    # Add icon to text
    display_text = f"{icon} {text}"
    
    return st.button(display_text, key=key, type=button_type)

def create_success_animation(message: str) -> None:
    """Create a success message with animation"""
    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, #00b09b, #96c93d);
        color: white;
        padding: 1.5rem;
        border-radius: 15px;
        text-align: center;
        font-weight: 600;
        box-shadow: 0 4px 20px rgba(0, 176, 155, 0.3);
        animation: pulse 2s infinite;
    ">
        ✅ {message}
    </div>
    """, unsafe_allow_html=True)

def create_loading_animation(message: str = "Loading...") -> None:
    """Create a custom loading animation"""
    st.markdown(f"""
    <div style="
        text-align: center;
        padding: 2rem;
        color: #667eea;
        font-weight: 600;
    ">
        <div style="
            display: inline-block;
            width: 40px;
            height: 40px;
            border: 4px solid rgba(102, 126, 234, 0.3);
            border-top: 4px solid #667eea;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin-right: 1rem;
        "></div>
        {message}
    </div>
    <style>
    @keyframes spin {{
        0% {{ transform: rotate(0deg); }}
        100% {{ transform: rotate(360deg); }}
    }}
    </style>
    """, unsafe_allow_html=True)

def create_dashboard_header(title: str, subtitle: str = "") -> None:
    """Create a professional dashboard header"""
    st.markdown(f"""
    <div style="
        text-align: center;
        padding: 2rem 0;
        background: linear-gradient(135deg, rgba(102, 126, 234, 0.1), rgba(118, 75, 162, 0.1));
        border-radius: 20px;
        margin-bottom: 2rem;
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.2);
    ">
        <h1 style="
            background: linear-gradient(90deg, #667eea, #764ba2, #f093fb);
            background-size: 200% auto;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-size: 2.5rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
            animation: shine 3s linear infinite;
        ">{title}</h1>
        {f'<p style="color: #666; font-size: 1.1rem;">{subtitle}</p>' if subtitle else ''}
    </div>
    """, unsafe_allow_html=True)

def create_data_table_with_style(df: pd.DataFrame, height: int = 400) -> None:
    """Create a styled data table"""
    # Add status badges if STATUS column exists
    if "STATUS" in df.columns:
        df_display = df.copy()
        df_display["STATUS"] = df_display["STATUS"].apply(
            lambda x: create_status_badge(str(x)) if pd.notna(x) else ""
        )
        st.markdown(df_display.to_html(escape=False), unsafe_allow_html=True)
    else:
        st.dataframe(df, use_container_width=True, height=height)

def create_sidebar_navigation(current_page: str, pages: List[str]) -> str:
    """Create sidebar navigation"""
    st.sidebar.markdown("## 🧭 Navigation")
    
    selected_page = None
    for page in pages:
        icon = {
            "MsgList": "💬",
            "PostQueue": "📤", 
            "InboxActivity": "📥",
            "MsgHistory": "📜"
        }.get(page, "📄")
        
        if st.sidebar.button(f"{icon} {page}", key=f"nav_{page}"):
            selected_page = page
    
    return selected_page or current_page
