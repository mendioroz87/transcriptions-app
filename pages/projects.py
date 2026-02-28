import streamlit as st
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.db import (
    get_user_projects, create_project, update_project,
    delete_project, get_project_transcriptions
)
from transcription.engine import MODELS
from utils.auth_ui import require_login, get_current_user
from utils.components import sidebar_navigation, render_status_badge, render_duration_badge

st.set_page_config(page_title="Projects — MLabs", page_icon="📁", layout="wide")
sidebar_navigation()
require_login()

user = get_current_user()

st.title("📁 My Projects")
st.caption("Organize your transcriptions into projects. Each project can use a different AI model.")
st.markdown("---")

# ── Create New Project ────────────────────────────────────────────────────────
with st.expander("➕ Create New Project", expanded=False):
    with st.form("create_project_form"):
        p_name = st.text_input("Project Name *")
        p_desc = st.text_area("Description", placeholder="What is this project about?")

        model_keys = list(MODELS.keys())
        p_model = st.selectbox(
            "Default Transcription Model",
            options=model_keys,
            format_func=lambda k: f"{MODELS[k]['icon']} {MODELS[k]['label']}",
        )

        api_key_needed = MODELS[p_model]["requires_api_key"]
        p_api_key = None
        if api_key_needed:
            p_api_key = st.text_input(
                f"🔑 {MODELS[p_model]['api_key_label']} (optional — can set globally in Settings)",
                type="password",
                help="This key will be stored only for this project.",
            )

        submitted = st.form_submit_button("Create Project", type="primary", use_container_width=True)
        if submitted:
            if not p_name.strip():
                st.error("Project name is required.")
            else:
                create_project(user["id"], p_name.strip(), p_desc.strip(), p_model, p_api_key or None)
                st.success(f"✅ Project '{p_name}' created!")
                st.rerun()

st.markdown("")

# ── List Projects ─────────────────────────────────────────────────────────────
projects = get_user_projects(user["id"])

if not projects:
    st.info("No projects yet. Create your first project above!")
else:
    for project in projects:
        transcriptions = get_project_transcriptions(project["id"])
        completed = [t for t in transcriptions if t["status"] == "completed"]
        total_words = sum(t.get("word_count") or 0 for t in completed)
        total_dur = sum(t.get("duration_seconds") or 0 for t in completed)

        model_info = MODELS.get(project["model"], {})
        with st.container(border=True):
            col_info, col_stats, col_actions = st.columns([3, 2, 1.5])

            with col_info:
                st.markdown(f"### {model_info.get('icon', '📁')} {project['name']}")
                if project.get("description"):
                    st.caption(project["description"])
                st.caption(f"Model: **{model_info.get('label', project['model'])}** · Created: {project['created_at'][:10]}")

            with col_stats:
                st.metric("Transcriptions", len(transcriptions))
                st.metric("Total Words", f"{total_words:,}")
                st.metric("Audio Processed", render_duration_badge(total_dur) or "—")

            with col_actions:
                if st.button("🎙️ Transcribe", key=f"tx_{project['id']}", use_container_width=True, type="primary"):
                    st.session_state["current_project"] = project
                    st.switch_page("pages/transcribe.py")

                if st.button("📜 History", key=f"hist_{project['id']}", use_container_width=True):
                    st.session_state["current_project"] = project
                    st.switch_page("pages/history.py")

                with st.popover("⚙️ Edit", use_container_width=True):
                    with st.form(f"edit_{project['id']}"):
                        new_name = st.text_input("Name", value=project["name"])
                        new_desc = st.text_area("Description", value=project.get("description") or "")
                        model_keys = list(MODELS.keys())
                        new_model = st.selectbox(
                            "Model",
                            options=model_keys,
                            format_func=lambda k: f"{MODELS[k]['icon']} {MODELS[k]['label']}",
                            index=model_keys.index(project["model"]) if project["model"] in model_keys else 0,
                        )
                        if MODELS[new_model]["requires_api_key"]:
                            new_key = st.text_input("API Key", type="password",
                                                     value=project.get("api_key") or "")
                        else:
                            new_key = None

                        c1, c2 = st.columns(2)
                        with c1:
                            if st.form_submit_button("Save", use_container_width=True):
                                update_project(project["id"], new_name, new_desc, new_model, new_key)
                                st.success("Saved!")
                                st.rerun()
                        with c2:
                            if st.form_submit_button("🗑️ Delete", use_container_width=True):
                                delete_project(project["id"])
                                st.warning("Project deleted.")
                                st.rerun()

            # Show recent transcriptions within the project card
            if transcriptions:
                st.markdown("")
                recent = transcriptions[:3]
                for tx in recent:
                    st.markdown(
                        f"&nbsp;&nbsp;{render_status_badge(tx['status'])} "
                        f"**{tx['original_filename']}** — "
                        f"{render_duration_badge(tx.get('duration_seconds'))} · "
                        f"{tx.get('word_count') or 0:,} words"
                    )
