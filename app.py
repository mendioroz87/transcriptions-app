"""
MLabs Transcription - Main Entry Point
"""

from html import escape
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


def _render_feature_stack(features: list[tuple[str, str, str]]) -> None:
    items_html = "".join(
        f"""
        <div class="mlabs-feature-item">
            <div class="mlabs-feature-icon">{escape(icon)}</div>
            <div class="mlabs-feature-body">
                <strong>{escape(title)}</strong>
                <p>{escape(desc)}</p>
            </div>
        </div>
        """
        for icon, title, desc in features
    )
    st.markdown(
        f"""
        <div class="mlabs-section-kicker">Team Workflow</div>
        <div class="mlabs-feature-stack">{items_html}</div>
        """,
        unsafe_allow_html=True,
    )


def render_logged_out_hero() -> None:
    hide_sidebar_for_logged_out()
    mobile = is_mobile_view()

    render_page_header(
        "MLabs Transcription",
        "Transcribe long-form audio, manage shared projects, and keep the invited team active from the first sign-in.",
    )

    features = [
        ("AI", "Multiple AI models", "Whisper, ElevenLabs Scribe v2, Parakeet, and Faster-Whisper."),
        ("AV", "Wide audio support", "MP3, WAV, OPUS, M4A, FLAC, WebM, and FFmpeg conversion."),
        ("LX", "Long recordings", "Chunk and process one to five hour sessions without manual splitting."),
        ("KEY", "Flexible key sources", "Use shared team keys, personal keys, project keys, or one-off keys."),
        ("TXT", "Clean exports", "TXT, Markdown, and DOCX outputs ready for handoff."),
        ("TEAM", "Shared workspace", "Members, invitations, settings, and project history in one place."),
    ]

    if mobile:
        st.markdown("### Welcome")
        st.caption("Sign in with the invited Gmail address or use your local account.")
        st.link_button("Request Invite", INVITE_ME_LINK, use_container_width=True)
        render_login_form()
        st.markdown("")
        _render_feature_stack(features)
        return

    col1, col2 = st.columns([1.2, 0.9], gap="large")
    with col1:
        st.markdown("### Why teams use it")
        st.caption("Designed for shared transcription work rather than single-user uploads.")
        _render_feature_stack(features)
    with col2:
        st.markdown(
            """
            <div class="mlabs-auth-panel">
                <div class="mlabs-section-kicker">Access</div>
                <h3>Welcome</h3>
                <p>Sign in with the invited Gmail address or use your local password to enter the workspace.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("")
        st.link_button("Request Invite", INVITE_ME_LINK, use_container_width=True)
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
            for col, item in zip(cols, metric_items[idx : idx + 2]):
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
        ("New Transcription", "pages/transcribe.py", True),
        ("Manage Projects", "pages/projects.py", False),
        ("Settings", "pages/settings.py", False),
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
                f"**{tx['original_filename']}** | {render_status_badge(tx['status'])} | "
                f"{tx['project_name']} | {render_duration_badge(tx.get('duration_seconds')) or 'Duration n/a'}"
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
            st.info("Accept one of your remaining invitations above to activate a team workspace.")
        else:
            st.error("No active team is available for this account.")
        st.stop()

    active_team_name = active_team.get("team_name") or active_team.get("name") or "Team"
    render_page_header(
        f"Welcome, {user['username']}",
        f"{active_team_name} dashboard with shared stats, recent work, and team-aware navigation.",
    )

    projects = get_user_projects(user["id"], team_id=active_team_id)
    _render_stats(projects, user["id"])
    st.markdown("### Quick Actions")
    _render_quick_actions()
    _render_recent_activity(projects, user["id"])
