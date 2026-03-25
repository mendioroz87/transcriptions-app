import os
import sys

import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.db import (
    create_project,
    delete_project,
    delete_projects_bulk,
    get_project_transcriptions,
    get_user_projects,
    get_user_team,
    update_project,
)
from transcription.engine import MODELS
from utils.auth_ui import get_active_team_id, get_current_user, require_login
from utils.components import render_duration_badge, sidebar_navigation
from utils.ui import init_ui, is_mobile_view, render_page_header


st.set_page_config(page_title="Projects - MLabs", page_icon="📁", layout="wide")
init_ui()
require_login()
sidebar_navigation(current="projects")

user = get_current_user()
active_team_id = get_active_team_id()
active_team = get_user_team(user["id"], active_team_id) if active_team_id else None
if not active_team:
    st.error("No active team is available for this account.")
    st.stop()

team_name = active_team.get("team_name") or active_team.get("name") or "Team"
can_manage_any_key = bool(
    active_team.get("is_owner")
    or active_team.get("can_edit_personal_api_keys")
    or active_team.get("can_edit_team_api_keys")
)
mobile = is_mobile_view()

render_page_header(
    "Projects",
    f"{team_name} workspace with device-aware project management and simplified cards on mobile.",
)

with st.expander("Create New Project", expanded=False):
    with st.form("create_project_form"):
        p_name = st.text_input("Project Name *")
        p_desc = st.text_area("Description", placeholder="What is this project about?")

        model_keys = list(MODELS.keys())
        p_model = st.selectbox(
            "Default Transcription Model",
            options=model_keys,
            format_func=lambda key: f"{MODELS[key]['icon']} {MODELS[key]['label']}",
        )

        p_api_key = None
        if MODELS[p_model]["requires_api_key"]:
            if can_manage_any_key:
                p_api_key = st.text_input(
                    f"{MODELS[p_model]['api_key_label']} (optional)",
                    type="password",
                    help="Stored only for this project.",
                )
            else:
                st.caption("Your role cannot store project API keys.")

        submitted = st.form_submit_button("Create Project", type="primary", use_container_width=True)
        if submitted:
            if not p_name.strip():
                st.error("Project name is required.")
            else:
                create_project(
                    user["id"],
                    p_name.strip(),
                    p_desc.strip(),
                    p_model,
                    p_api_key or None,
                    team_id=active_team_id,
                )
                st.success(f"Project '{p_name}' created.")
                st.rerun()

projects = get_user_projects(user["id"], team_id=active_team_id)
search_query = st.text_input("Search projects", placeholder="Filter by name or description")
filtered_projects = projects
if search_query.strip():
    q = search_query.lower().strip()
    filtered_projects = [
        project
        for project in projects
        if q in (project.get("name") or "").lower() or q in (project.get("description") or "").lower()
    ]

if not filtered_projects:
    st.info("No projects match your current filters.")
else:
    for project in filtered_projects:
        transcriptions = get_project_transcriptions(project["id"], acting_user_id=user["id"])
        completed = [tx for tx in transcriptions if tx["status"] == "completed"]
        total_words = sum((tx.get("word_count") or 0) for tx in completed)
        total_dur = sum((tx.get("duration_seconds") or 0) for tx in completed)
        model_info = MODELS.get(project["model"], {})

        with st.container(border=True):
            if mobile:
                st.markdown(f"### {model_info.get('icon', '📁')} {project['name']}")
                if project.get("description"):
                    st.caption(project["description"])
                meta_cols = st.columns(3)
                with meta_cols[0]:
                    st.metric("Transcriptions", len(transcriptions))
                with meta_cols[1]:
                    st.metric("Words", f"{total_words:,}")
                with meta_cols[2]:
                    st.metric("Audio", render_duration_badge(total_dur) or "-")
                st.caption(
                    f"Model: {model_info.get('label', project['model'])} · Created: {project['created_at'][:10]}"
                )
                b1, b2 = st.columns(2)
                with b1:
                    if st.button("Transcribe", key=f"mobile_tx_{project['id']}", use_container_width=True, type="primary"):
                        st.session_state["current_project"] = project
                        st.switch_page("pages/transcribe.py")
                with b2:
                    if st.button("History", key=f"mobile_hist_{project['id']}", use_container_width=True):
                        st.session_state["current_project"] = project
                        st.switch_page("pages/history.py")
            else:
                col_info, col_stats, col_actions = st.columns([3, 2, 1.5])
                with col_info:
                    st.markdown(f"### {model_info.get('icon', '📁')} {project['name']}")
                    if project.get("description"):
                        st.caption(project["description"])
                    st.caption(
                        f"Model: {model_info.get('label', project['model'])} · Created: {project['created_at'][:10]}"
                    )
                with col_stats:
                    st.metric("Transcriptions", len(transcriptions))
                    st.metric("Total Words", f"{total_words:,}")
                    st.metric("Audio Processed", render_duration_badge(total_dur) or "-")
                with col_actions:
                    if st.button("Transcribe", key=f"tx_{project['id']}", use_container_width=True, type="primary"):
                        st.session_state["current_project"] = project
                        st.switch_page("pages/transcribe.py")
                    if st.button("History", key=f"hist_{project['id']}", use_container_width=True):
                        st.session_state["current_project"] = project
                        st.switch_page("pages/history.py")

            with st.popover("Edit Project", use_container_width=not mobile):
                with st.form(f"edit_{project['id']}"):
                    new_name = st.text_input("Name", value=project["name"])
                    new_desc = st.text_area("Description", value=project.get("description") or "")
                    model_keys = list(MODELS.keys())
                    new_model = st.selectbox(
                        "Model",
                        options=model_keys,
                        format_func=lambda key: f"{MODELS[key]['icon']} {MODELS[key]['label']}",
                        index=model_keys.index(project["model"]) if project["model"] in model_keys else 0,
                    )
                    if MODELS[new_model]["requires_api_key"]:
                        if can_manage_any_key:
                            new_key = st.text_input(
                                "API Key",
                                type="password",
                                value=project.get("api_key") or "",
                            )
                        else:
                            new_key = project.get("api_key") or None
                            st.caption("Your role cannot edit project API keys.")
                    else:
                        new_key = None

                    c1, c2 = st.columns(2)
                    with c1:
                        if st.form_submit_button("Save", use_container_width=True):
                            update_project(
                                project["id"],
                                new_name,
                                new_desc,
                                new_model,
                                new_key,
                                acting_user_id=user["id"],
                            )
                            st.success("Saved.")
                            st.rerun()
                    with c2:
                        if st.form_submit_button("Delete", use_container_width=True):
                            delete_project(project["id"], acting_user_id=user["id"])
                            st.warning("Project deleted.")
                            st.rerun()

            if transcriptions:
                st.caption("Recent files")
                for tx in transcriptions[:3]:
                    st.caption(
                        f"• {tx['original_filename']} · {render_duration_badge(tx.get('duration_seconds')) or 'Duration n/a'} · "
                        f"{(tx.get('word_count') or 0):,} words"
                    )

    with st.expander("Bulk Remove Projects", expanded=False):
        st.caption("Delete selected projects and every transcription inside them. This cannot be undone.")
        project_label_to_id = {
            f"{project['name']} (id={project['id']})": project["id"]
            for project in filtered_projects
        }
        selected_labels = st.multiselect(
            "Select projects to delete",
            options=list(project_label_to_id.keys()),
            key="bulk_delete_projects_select",
        )
        confirmed = st.checkbox(
            "I understand these deletions are permanent.",
            key="bulk_delete_projects_confirm",
        )
        if st.button(
            "Delete Selected Projects",
            type="secondary",
            use_container_width=True,
            disabled=not selected_labels or not confirmed,
            key="bulk_delete_projects_btn",
        ):
            selected_ids = [project_label_to_id[label] for label in selected_labels]
            deleted_count = delete_projects_bulk(selected_ids, acting_user_id=user["id"])
            if (
                "current_project" in st.session_state
                and st.session_state["current_project"]["id"] in selected_ids
            ):
                del st.session_state["current_project"]
            st.warning(f"Deleted {deleted_count} project(s).")
            st.rerun()
