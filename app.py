"""
MLabs Transcription — Main Entry Point
"""

import streamlit as st
import sys
import os

# Make sure sub-packages are importable
sys.path.insert(0, os.path.dirname(__file__))

from database.db import get_project_transcriptions, get_user_projects, get_user_team, init_db
from utils.auth_ui import (
    get_active_team_id,
    get_current_user,
    hide_sidebar_for_logged_out,
    is_logged_in,
    render_login_form,
)
from utils.components import sidebar_navigation, render_duration_badge, render_status_badge

INVITE_ME_LINK = (
    "https://wa.me/50558601131?text=Please%20invite%20me%20to%20your%20transcription%20app,"
    "%20this%20is%20my%20email:"
)

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="MLabs Transcription",
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Init DB ───────────────────────────────────────────────────────────────────
init_db()

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main-title {
        font-size: 2.8rem;
        font-weight: 800;
        background: linear-gradient(135deg, #4CAF50, #2196F3);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0;
    }
    .subtitle {
        color: #888;
        font-size: 1.1rem;
        margin-top: 0;
    }
    .stat-card {
        background: #1e1e1e;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
        border: 1px solid #333;
    }
    .stat-number {
        font-size: 2.4rem;
        font-weight: 700;
        color: #4CAF50;
    }
    .stat-label {
        color: #888;
        font-size: 0.9rem;
    }
    div[data-testid="stForm"] {
        background: #1a1a1a;
        border-radius: 12px;
        padding: 20px;
        border: 1px solid #333;
    }
</style>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────

# ── Main Content ──────────────────────────────────────────────────────────────
if not is_logged_in():
    hide_sidebar_for_logged_out()

    # Hero section
    col1, col2 = st.columns([1.2, 1], gap="large")
    with col1:
        st.markdown('<p class="main-title">MLabs Transcription</p>', unsafe_allow_html=True)
        st.markdown('<p class="subtitle">Transcribe any audio — any length — any format</p>', unsafe_allow_html=True)
        st.markdown(
            "MLabs Transcription helps teams transcribe long-form audio with shared workspaces, "
            "permissioned access, and export-ready outputs."
        )
        st.caption("Made by MLabs")
        st.markdown("")

        features = [
            ("🎙️", "Multiple AI Models", "Whisper, ElevenLabs Scribe v2, Parakeet, Real-time"),
            ("📁", "Audio Format Support", "MP3, WAV, OPUS, M4A, FLAC, WebM, and more via FFmpeg"),
            ("⏱️", "Long Audio Sessions", "Process 1–5 hour recordings automatically via smart chunking"),
            ("🔑", "Your API Keys", "Bring your own keys — full control, no markups"),
            ("📤", "Flexible Export", "TXT, DOCX, SRT, VTT, JSON, CSV, and Markdown"),
            ("📂", "Project Management", "Organize transcriptions into projects"),
        ]
        for icon, title, desc in features:
            st.markdown(f"**{icon} {title}** — {desc}")

    with col2:
        st.markdown("### Welcome")
        st.caption("Sign in to access your team workspace.")
        st.link_button("Invite Me", INVITE_ME_LINK, use_container_width=True)
        render_login_form()

else:
    sidebar_navigation()
    # ── Dashboard ────────────────────────────────────────────────────────────
    user = get_current_user()
    active_team_id = get_active_team_id()
    active_team = get_user_team(user["id"], active_team_id) if active_team_id else None
    if not active_team:
        st.error("No active team is available for this account.")
        st.stop()

    active_team_name = active_team.get("team_name") or active_team.get("name") or "Team"
    st.markdown(f'<p class="main-title">Welcome, {user["username"]}!</p>', unsafe_allow_html=True)
    st.markdown(f'<p class="subtitle">{active_team_name} Dashboard</p>', unsafe_allow_html=True)
    st.markdown("")

    # Load user data
    projects = get_user_projects(user["id"], team_id=active_team_id)

    # Aggregate stats
    total_transcriptions = 0
    total_words = 0
    total_duration = 0
    for project in projects:
        txs = get_project_transcriptions(project["id"], acting_user_id=user["id"])
        total_transcriptions += len(txs)
        for tx in txs:
            total_words += tx.get("word_count") or 0
            total_duration += tx.get("duration_seconds") or 0

    # Stats row
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""<div class="stat-card">
            <div class="stat-number">{len(projects)}</div>
            <div class="stat-label">Projects</div></div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""<div class="stat-card">
            <div class="stat-number">{total_transcriptions}</div>
            <div class="stat-label">Transcriptions</div></div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""<div class="stat-card">
            <div class="stat-number">{total_words:,}</div>
            <div class="stat-label">Words Transcribed</div></div>""", unsafe_allow_html=True)
    with c4:
        dur_label = render_duration_badge(total_duration)
        st.markdown(f"""<div class="stat-card">
            <div class="stat-number" style="font-size:1.6rem;">{dur_label or "0s"}</div>
            <div class="stat-label">Audio Processed</div></div>""", unsafe_allow_html=True)

    st.markdown("---")

    # Quick Actions
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        if st.button("🎙️ New Transcription", use_container_width=True, type="primary"):
            st.switch_page("pages/transcribe.py")
    with col_b:
        if st.button("📁 Manage Projects", use_container_width=True):
            st.switch_page("pages/projects.py")
    with col_c:
        if st.button("⚙️ API Keys & Settings", use_container_width=True):
            st.switch_page("pages/settings.py")

    st.markdown("")

    # Recent transcriptions across all projects
    if total_transcriptions > 0:
        st.subheader("📜 Recent Activity")
        recent = []
        for project in projects:
            txs = get_project_transcriptions(project["id"], acting_user_id=user["id"])
            for tx in txs:
                tx["project_name"] = project["name"]
                recent.append(tx)
        recent.sort(key=lambda x: x["created_at"], reverse=True)
        recent = recent[:8]

        for tx in recent:
            with st.expander(
                f"{render_status_badge(tx['status'])}  {tx['original_filename']}  —  "
                f"📁 {tx['project_name']}  •  {render_duration_badge(tx.get('duration_seconds'))}"
            ):
                col1, col2 = st.columns([3, 1])
                with col1:
                    preview = (tx.get("transcript") or "")[:400]
                    st.text(preview + ("..." if len(tx.get("transcript") or "") > 400 else ""))
                with col2:
                    st.markdown(f"**Model:** {tx.get('model_used', 'N/A')}")
                    st.markdown(f"**Language:** {tx.get('language', 'N/A')}")
                    st.markdown(f"**Words:** {(tx.get('word_count') or 0):,}")
    else:
        st.info("No transcriptions yet. Start by creating a project and uploading an audio file!")


