"""
MLabs Transcription — Main Entry Point
"""

import os
import sys

import streamlit as st

# Make sure sub-packages are importable
sys.path.insert(0, os.path.dirname(__file__))

from database.db import get_project_transcriptions, get_user_projects, get_user_team, init_db
from utils.auth_ui import (
    get_active_team_id,
    get_current_user,
    hide_sidebar_for_logged_out,
    is_logged_in,
    render_pending_invitations_panel,
    render_login_form,
)
from utils.components import render_duration_badge, render_status_badge, sidebar_navigation
from utils.ui import init_ui, is_mobile_view, render_page_header

INVITE_ME_LINK = (
    "https://wa.me/50558601131?text=Please%20invite%20me%20to%20your%20transcription%20app,"
    "%20this%20is%20my%20email:"
)

st.set_page_config(
    page_title="MLabs Transcription",
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()
init_ui()


def render_logged_out_hero() -> None:
    hide_sidebar_for_logged_out()
    mobile = is_mobile_view()

    render_page_header(
        "MLabs Transcription",
        "Transcribe any audio, collaborate with your team, and export polished outputs.",
    )

    features = [
        ("🎙️", "Multiple AI Models", "Whisper, ElevenLabs Scribe v2, Parakeet, Faster-Whisper"),
        ("📁", "Wide Audio Support", "MP3, WAV, OPUS, M4A, FLAC, WebM and more via FFmpeg"),
        ("⏱️", "Long Audio Sessions", "Process 1–5 hour recordings with automatic chunking"),
        ("🔑", "Flexible Keys", "Use team keys, personal keys, or one-off project keys"),
        ("📤", "Export Ready", "TXT, Markdown and DOCX outputs for clean handoff"),
        ("👥", "Team Workspace", "Shared projects, permissions, invitations and activity history"),
    ]

    if mobile:
        with st.container(border=True):
            st.markdown("### Welcome")
            st.caption("Sign in to access your team workspace.")
            st.link_button("Invite Me", INVITE_ME_LINK, use_container_width=True)
            render_login_form()

        st.markdown("### Why teams use it")
        for icon, title, desc in features:
            with st.container(border=True):
                st.markdown(f"**{icon} {title}**")
                st.caption(desc)
        return

    col1, col2 = st.columns([1.3, 1], gap="large")
    with col1:
        st.markdown("### Why teams use it")
        for icon, title, desc in features:
            with st.container(border=True):
                st.markdown(f"**{icon} {title}**")
                st.caption(desc)
    with col2:
        with st.container(border=True):
            st.markdown("### Welcome")
            st.caption("Sign in to access your team workspace.")
            st.link_button("Invite Me", INVITE_ME_LINK, use_container_width=True)
            render_login_form()


def _render_stats(projects: list[dict], user_id: int) -> None:
    total_transcriptions = 0
    total_words = 0
    total_duration = 0
    completed_count = 0
    processing_count = 0

    for project in projects:
        txs = get_project_transcriptions(project["id"], acting_user_id=user_id)
        total_transcriptions += len(txs)
        for tx in txs:
            total_words += tx.get("word_count") or 0
            total_duration += tx.get("duration_seconds") or 0
            if tx.get("status") == "completed":
                completed_count += 1
            elif tx.get("status") == "processing":
                processing_count += 1

    metric_items = [
        ("Projects", len(projects)),
        ("Transcriptions", total_transcriptions),
        ("Completed", completed_count),
        ("In Progress", processing_count),
        ("Words", f"{total_words:,}"),
        ("Audio", render_duration_badge(total_duration) or "0s"),
    ]

    mobile = is_mobile_view()
    if mobile:
        for idx in range(0, len(metric_items), 2):
            cols = st.columns(2)
            for col, item in zip(cols, metric_items[idx: idx + 2]):
                label, value = item
                with col:
                    with st.container(border=True):
                        st.metric(label, value)
        return

    cols = st.columns(6)
    for col, item in zip(cols, metric_items):
        label, value = item
        with col:
            with st.container(border=True):
                st.metric(label, value)


def _render_quick_actions() -> None:
    actions = [
        ("🎙️ New Transcription", "pages/transcribe.py", True),
        ("📁 Manage Projects", "pages/projects.py", False),
        ("⚙️ Settings", "pages/settings.py", False),
    ]
    mobile = is_mobile_view()
    if mobile:
        for label, target, primary in actions:
            if st.button(label, use_container_width=True, type="primary" if primary else "secondary"):
                st.switch_page(target)
        return

    cols = st.columns(3)
    for col, (label, target, primary) in zip(cols, actions):
        with col:
            if st.button(label, use_container_width=True, type="primary" if primary else "secondary"):
                st.switch_page(target)


def _render_recent_activity(projects: list[dict], user_id: int) -> None:
    recent = []
    for project in projects:
        txs = get_project_transcriptions(project["id"], acting_user_id=user_id)
        for tx in txs:
            tx["project_name"] = project["name"]
            recent.append(tx)
    recent.sort(key=lambda item: item["created_at"], reverse=True)
    recent = recent[:8]

    if not recent:
        st.info("No transcriptions yet. Start by creating a project and uploading an audio file.")
        return

    st.markdown("### Recent Activity")
    for tx in recent:
        with st.container(border=True):
            st.markdown(
                f"**{tx['original_filename']}** · {render_status_badge(tx['status'])} · "
                f"📁 {tx['project_name']} · {render_duration_badge(tx.get('duration_seconds')) or 'Duration n/a'}"
            )
            meta_cols = st.columns(3)
            with meta_cols[0]:
                st.caption(f"Model: {tx.get('model_used', 'N/A')}")
            with meta_cols[1]:
                st.caption(f"Language: {tx.get('language', 'N/A')}")
            with meta_cols[2]:
                st.caption(f"Words: {(tx.get('word_count') or 0):,}")
            preview = (tx.get("transcript") or "")[:360]
            st.caption(preview + ("..." if len(tx.get("transcript") or "") > 360 else ""))


if not is_logged_in():
    render_logged_out_hero()
else:
    sidebar_navigation(current="overview")
    pending_invite_count = render_pending_invitations_panel()
    user = get_current_user()
    active_team_id = get_active_team_id()
    active_team = get_user_team(user["id"], active_team_id) if active_team_id else None
    if not active_team:
        if pending_invite_count:
            st.info("Accept one of your pending invitations above to activate a team workspace.")
        else:
            st.error("No active team is available for this account.")
        st.stop()

    active_team_name = active_team.get("team_name") or active_team.get("name") or "Team"
    render_page_header(
        f"Welcome, {user['username']}",
        f"{active_team_name} dashboard with responsive layouts for desktop and mobile.",
    )

    projects = get_user_projects(user["id"], team_id=active_team_id)
    _render_stats(projects, user["id"])
    st.markdown("### Quick Actions")
    _render_quick_actions()
    _render_recent_activity(projects, user["id"])
