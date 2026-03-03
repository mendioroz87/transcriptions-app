"""
History Page - View, search, export, and remove transcriptions.
"""

import os
import sys

import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.db import (  # noqa: E402
    delete_transcription,
    delete_transcriptions_bulk,
    get_project_transcriptions,
    get_user_team,
    get_user_projects,
)
from exports.exporter import (  # noqa: E402
    export_as_csv,
    export_as_docx,
    export_as_json,
    export_as_markdown,
    export_as_txt,
)
from utils.auth_ui import get_active_team_id, get_current_user, require_login  # noqa: E402
from utils.components import render_duration_badge, render_status_badge, sidebar_navigation  # noqa: E402


st.set_page_config(page_title="History - MLabs", page_icon="H", layout="wide")
sidebar_navigation()
require_login()

user = get_current_user()
active_team_id = get_active_team_id()
active_team = get_user_team(user["id"], active_team_id) if active_team_id else None
if not active_team:
    st.error("No active team is available for this account.")
    st.stop()

team_name = active_team.get("team_name") or active_team.get("name") or "Team"
projects = get_user_projects(user["id"], team_id=active_team_id)

st.title("Transcription History")
st.caption(f"Team: {team_name}. Browse, search, export, and remove transcriptions.")
st.markdown("---")

if not projects:
    st.info("No projects yet.")
    st.stop()

col_f1, col_f2, col_f3 = st.columns(3)

with col_f1:
    project_map = {"All Projects": None}
    project_map.update({project["name"]: project["id"] for project in projects})

    default_proj_name = "All Projects"
    if "current_project" in st.session_state:
        current_project = st.session_state["current_project"]
        if current_project["name"] in project_map:
            default_proj_name = current_project["name"]

    selected_proj_name = st.selectbox(
        "Filter by Project",
        list(project_map.keys()),
        index=list(project_map.keys()).index(default_proj_name),
    )

with col_f2:
    status_filter = st.selectbox("Status", ["All", "completed", "processing", "error"])

with col_f3:
    search_query = st.text_input("Search transcripts", placeholder="Type to search...")

all_transcriptions = []
for project in projects:
    selected_project_id = project_map[selected_proj_name]
    if selected_project_id and project["id"] != selected_project_id:
        continue

    for transcription in get_project_transcriptions(project["id"], acting_user_id=user["id"]):
        transcription["project_name"] = project["name"]
        all_transcriptions.append(transcription)

all_transcriptions.sort(key=lambda tx: tx["created_at"], reverse=True)

if status_filter != "All":
    all_transcriptions = [tx for tx in all_transcriptions if tx["status"] == status_filter]

if search_query:
    q = search_query.lower()
    all_transcriptions = [
        tx
        for tx in all_transcriptions
        if q in (tx.get("original_filename") or "").lower()
        or q in (tx.get("transcript") or "").lower()
    ]

if all_transcriptions:
    with st.expander(f"Bulk Export ({len(all_transcriptions)} records)"):
        st.download_button(
            "Export all as CSV",
            data=export_as_csv(all_transcriptions),
            file_name="mlabs_transcriptions.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with st.expander(f"Bulk Remove ({len(all_transcriptions)} records)", expanded=False):
        st.caption("Delete selected transcriptions from the filtered list. This cannot be undone.")
        tx_label_to_id = {
            f"{tx['original_filename']} | {tx.get('created_at', '')[:19]} | id={tx['id']}": tx["id"]
            for tx in all_transcriptions
        }
        selected_labels = st.multiselect(
            "Select transcriptions to delete",
            options=list(tx_label_to_id.keys()),
            key="bulk_delete_transcriptions_select",
        )
        confirmed = st.checkbox(
            "I understand these deletions are permanent.",
            key="bulk_delete_transcriptions_confirm",
        )

        if st.button(
            "Delete Selected Transcriptions",
            type="secondary",
            use_container_width=True,
            disabled=not selected_labels or not confirmed,
            key="bulk_delete_transcriptions_btn",
        ):
            selected_ids = [tx_label_to_id[label] for label in selected_labels]
            deleted_count = delete_transcriptions_bulk(selected_ids, acting_user_id=user["id"])
            st.warning(f"Deleted {deleted_count} transcription(s).")
            st.rerun()

st.markdown(f"**{len(all_transcriptions)} transcriptions found**")
st.markdown("")

if not all_transcriptions:
    st.info("No transcriptions match your filters.")
else:
    for tx in all_transcriptions:
        label = (
            f"{render_status_badge(tx['status'])}  {tx['original_filename']}"
            f"  |  {tx['project_name']}"
            f"  |  {render_duration_badge(tx.get('duration_seconds')) or '?'}"
            f"  |  {(tx.get('word_count') or 0):,} words"
            f"  |  {tx.get('language') or '?'}"
        )

        with st.expander(label):
            tab_text, tab_export, tab_meta = st.tabs(["Transcript", "Export", "Metadata"])

            transcript = tx.get("transcript") or ""

            with tab_text:
                if transcript:
                    st.text_area(
                        "Transcript",
                        value=transcript,
                        height=250,
                        key=f"text_{tx['id']}",
                        label_visibility="collapsed",
                    )
                else:
                    st.info("No transcript available yet.")

            with tab_export:
                if transcript:
                    st.markdown("**Choose export format:**")
                    ec1, ec2, ec3, ec4, ec5 = st.columns(5)

                    file_stem = os.path.splitext(tx["original_filename"])[0]
                    meta = {
                        "model_used": tx.get("model_used", ""),
                        "language": tx.get("language", ""),
                        "duration_seconds": tx.get("duration_seconds", 0),
                        "word_count": tx.get("word_count", 0),
                    }

                    with ec1:
                        st.download_button(
                            "TXT",
                            export_as_txt(transcript, file_stem),
                            file_name=f"{file_stem}.txt",
                            mime="text/plain",
                            use_container_width=True,
                            key=f"txt_{tx['id']}",
                        )
                    with ec2:
                        st.download_button(
                            "JSON",
                            export_as_json(tx),
                            file_name=f"{file_stem}.json",
                            mime="application/json",
                            use_container_width=True,
                            key=f"json_{tx['id']}",
                        )
                    with ec3:
                        st.download_button(
                            "MD",
                            export_as_markdown(transcript, file_stem, meta),
                            file_name=f"{file_stem}.md",
                            mime="text/markdown",
                            use_container_width=True,
                            key=f"md_{tx['id']}",
                        )
                    with ec4:
                        try:
                            docx_bytes = export_as_docx(transcript, file_stem, meta)
                            st.download_button(
                                "DOCX",
                                docx_bytes,
                                file_name=f"{file_stem}.docx",
                                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                use_container_width=True,
                                key=f"docx_{tx['id']}",
                            )
                        except ImportError:
                            st.caption("DOCX unavailable (install python-docx).")
                    with ec5:
                        st.download_button(
                            "CSV",
                            export_as_csv([tx]),
                            file_name=f"{file_stem}.csv",
                            mime="text/csv",
                            use_container_width=True,
                            key=f"csv_{tx['id']}",
                        )
                else:
                    st.info("No transcript to export.")

            with tab_meta:
                col_m1, col_m2 = st.columns(2)
                with col_m1:
                    st.markdown(f"**File:** {tx['original_filename']}")
                    st.markdown(f"**Project:** {tx['project_name']}")
                    st.markdown(f"**Model:** {tx.get('model_used', 'N/A')}")
                    st.markdown(f"**Language:** {tx.get('language', 'N/A')}")
                with col_m2:
                    st.markdown(f"**Status:** {tx.get('status', 'N/A')}")
                    st.markdown(f"**Duration:** {render_duration_badge(tx.get('duration_seconds'))}")
                    st.markdown(f"**Word Count:** {(tx.get('word_count') or 0):,}")
                    st.markdown(f"**Created:** {(tx.get('created_at') or '')[:19]}")

                st.markdown("")
                if st.button("Delete this transcription", key=f"del_{tx['id']}", type="secondary"):
                    delete_transcription(tx["id"], acting_user_id=user["id"])
                    st.warning("Transcription deleted.")
                    st.rerun()
