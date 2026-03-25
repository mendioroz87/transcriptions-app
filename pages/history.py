"""
History Page - View, search, export, and remove transcriptions.
"""

import io
import os
import re
import sys
import zipfile

import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.db import (
    delete_transcription,
    delete_transcriptions_bulk,
    get_project_transcriptions,
    get_user_projects,
    get_user_team,
)
from exports.exporter import export_as_docx, export_as_markdown, export_as_txt
from utils.auth_ui import get_active_team_id, get_current_user, require_login
from utils.components import render_duration_badge, render_status_badge, sidebar_navigation
from utils.ui import init_ui, is_mobile_view, render_page_header


st.set_page_config(page_title="History - MLabs", page_icon="📜", layout="wide")
init_ui()
require_login()
sidebar_navigation(current="history")


def _selection_key(tx_id: int) -> str:
    return f"history_selected_{tx_id}"


def _details_key(tx_id: int) -> str:
    return f"history_details_open_{tx_id}"


def _safe_stem(filename: str, tx_id: int) -> str:
    stem = os.path.splitext(filename or f"transcription_{tx_id}")[0]
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._")
    return sanitized or f"transcription_{tx_id}"


def _meta_for_export(tx: dict) -> dict:
    return {
        "model_used": tx.get("model_used", ""),
        "language": tx.get("language", ""),
        "duration_seconds": tx.get("duration_seconds", 0),
        "word_count": tx.get("word_count", 0),
    }


def _build_bulk_export_zip(transcriptions: list[dict], export_format: str, include_summary: bool) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for tx in transcriptions:
            transcript = tx.get("transcript") or ""
            summary_text = tx.get("summary_text") or ""
            stem = f"{_safe_stem(tx.get('original_filename', ''), tx['id'])}_{tx['id']}"
            meta = _meta_for_export(tx)

            if export_format == "txt":
                payload = export_as_txt(
                    transcript,
                    stem,
                    summary_text=summary_text,
                    include_summary=include_summary,
                )
                archive.writestr(f"{stem}.txt", payload)
            elif export_format == "md":
                payload = export_as_markdown(
                    transcript,
                    stem,
                    meta,
                    summary_text=summary_text,
                    include_summary=include_summary,
                )
                archive.writestr(f"{stem}.md", payload)
            elif export_format == "docx":
                payload = export_as_docx(
                    transcript,
                    stem,
                    meta,
                    summary_text=summary_text,
                    include_summary=include_summary,
                )
                archive.writestr(f"{stem}.docx", payload)
            else:
                raise ValueError(f"Unsupported export format: {export_format}")

    buffer.seek(0)
    return buffer.getvalue()


def _set_visible_selection(transcriptions: list[dict], selected: bool) -> None:
    for tx in transcriptions:
        st.session_state[_selection_key(tx["id"])] = selected


def _selected_transcriptions(transcriptions: list[dict]) -> list[dict]:
    return [tx for tx in transcriptions if st.session_state.get(_selection_key(tx["id"]), False)]


def _render_bulk_toolbar(transcriptions: list[dict], user_id: int, mobile: bool) -> None:
    selected_items = _selected_transcriptions(transcriptions)
    visible_count = len(transcriptions)

    top_cols = st.columns(2 if mobile else 4)
    with top_cols[0]:
        if st.button("Select Visible", use_container_width=True, key="history_select_visible"):
            _set_visible_selection(transcriptions, True)
            st.rerun()
    with top_cols[1]:
        if st.button("Clear Selection", use_container_width=True, key="history_clear_visible"):
            _set_visible_selection(transcriptions, False)
            st.rerun()
    if not mobile:
        with top_cols[2]:
            st.caption(f"Visible: {visible_count}")
        with top_cols[3]:
            st.caption(f"Selected: {len(selected_items)}")

    if not selected_items:
        st.caption("Select one or more transcripts to enable bulk export or bulk delete.")
        return

    st.markdown(
        f"<div class='mlabs-toolbar'><strong>{len(selected_items)} selected</strong> · Bulk export now uses TXT, Markdown or DOCX zip bundles.</div>",
        unsafe_allow_html=True,
    )
    include_summary = st.checkbox(
        "Include summaries in bulk exports",
        value=any(bool(tx.get("summary_text")) for tx in selected_items),
        key="history_bulk_include_summary",
    )

    action_cols = st.columns(2 if mobile else 4)
    txt_zip = _build_bulk_export_zip(selected_items, "txt", include_summary)
    md_zip = _build_bulk_export_zip(selected_items, "md", include_summary)

    with action_cols[0]:
        st.download_button(
            "Download TXT ZIP",
            data=txt_zip,
            file_name="mlabs_history_txt.zip",
            mime="application/zip",
            use_container_width=True,
        )
    with action_cols[1]:
        st.download_button(
            "Download MD ZIP",
            data=md_zip,
            file_name="mlabs_history_markdown.zip",
            mime="application/zip",
            use_container_width=True,
        )

    docx_error = None
    try:
        docx_zip = _build_bulk_export_zip(selected_items, "docx", include_summary)
    except ImportError:
        docx_zip = None
        docx_error = "DOCX bulk export is unavailable because python-docx is not installed."

    if not mobile:
        with action_cols[2]:
            st.download_button(
                "Download DOCX ZIP",
                data=docx_zip or b"",
                file_name="mlabs_history_docx.zip",
                mime="application/zip",
                use_container_width=True,
                disabled=docx_zip is None,
            )
        with action_cols[3]:
            if st.button("Delete Selected", use_container_width=True, type="secondary"):
                deleted_count = delete_transcriptions_bulk([tx["id"] for tx in selected_items], acting_user_id=user_id)
                _set_visible_selection(transcriptions, False)
                st.warning(f"Deleted {deleted_count} transcription(s).")
                st.rerun()
    else:
        extra_cols = st.columns(2)
        with extra_cols[0]:
            st.download_button(
                "Download DOCX ZIP",
                data=docx_zip or b"",
                file_name="mlabs_history_docx.zip",
                mime="application/zip",
                use_container_width=True,
                disabled=docx_zip is None,
            )
        with extra_cols[1]:
            if st.button("Delete Selected", use_container_width=True, type="secondary"):
                deleted_count = delete_transcriptions_bulk([tx["id"] for tx in selected_items], acting_user_id=user_id)
                _set_visible_selection(transcriptions, False)
                st.warning(f"Deleted {deleted_count} transcription(s).")
                st.rerun()

    if docx_error:
        st.caption(docx_error)


def _render_export_panel(tx: dict) -> None:
    transcript = tx.get("transcript") or ""
    if not transcript:
        st.info("No transcript to export.")
        return

    summary_text = tx.get("summary_text") or ""
    include_summary = st.checkbox(
        "Include summary in export",
        value=bool(summary_text),
        disabled=not bool(summary_text),
        key=f"tx_export_include_summary_{tx['id']}",
    )
    file_stem = _safe_stem(tx["original_filename"], tx["id"])
    meta = _meta_for_export(tx)

    export_cols = st.columns(3)
    with export_cols[0]:
        st.download_button(
            "TXT",
            export_as_txt(
                transcript,
                file_stem,
                summary_text=summary_text,
                include_summary=include_summary,
            ),
            file_name=f"{file_stem}.txt",
            mime="text/plain",
            use_container_width=True,
            key=f"txt_{tx['id']}",
        )
    with export_cols[1]:
        st.download_button(
            "MD",
            export_as_markdown(
                transcript,
                file_stem,
                meta,
                summary_text=summary_text,
                include_summary=include_summary,
            ),
            file_name=f"{file_stem}.md",
            mime="text/markdown",
            use_container_width=True,
            key=f"md_{tx['id']}",
        )
    with export_cols[2]:
        try:
            docx_bytes = export_as_docx(
                transcript,
                file_stem,
                meta,
                summary_text=summary_text,
                include_summary=include_summary,
            )
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


def _render_details(tx: dict) -> None:
    transcript = tx.get("transcript") or ""
    summary_text = tx.get("summary_text") or ""

    with st.container(border=True):
        detail_tabs = st.tabs(["Transcript", "Export", "Metadata"])
        with detail_tabs[0]:
            if transcript:
                st.text_area(
                    "Transcript",
                    value=transcript,
                    height=250,
                    key=f"text_{tx['id']}",
                    label_visibility="collapsed",
                )
                if summary_text:
                    st.markdown("#### Summary")
                    st.text_area(
                        "Summary",
                        value=summary_text,
                        height=160,
                        key=f"summary_{tx['id']}",
                        label_visibility="collapsed",
                    )
            else:
                st.info("No transcript available yet.")
        with detail_tabs[1]:
            _render_export_panel(tx)
        with detail_tabs[2]:
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**File:** {tx['original_filename']}")
                st.markdown(f"**Project:** {tx['project_name']}")
                st.markdown(f"**Model:** {tx.get('model_used', 'N/A')}")
                st.markdown(f"**Language:** {tx.get('language', 'N/A')}")
            with col2:
                st.markdown(f"**Status:** {tx.get('status', 'N/A')}")
                st.markdown(f"**Duration:** {render_duration_badge(tx.get('duration_seconds')) or 'N/A'}")
                st.markdown(f"**Word Count:** {(tx.get('word_count') or 0):,}")
                st.markdown(f"**Created:** {(tx.get('created_at') or '')[:19]}")

            if st.button("Delete this transcription", key=f"del_{tx['id']}", type="secondary"):
                delete_transcription(tx["id"], acting_user_id=user["id"])
                st.warning("Transcription deleted.")
                st.rerun()


def _render_history_rows(transcriptions: list[dict], mobile: bool) -> None:
    for tx in transcriptions:
        open_now = st.session_state.get(_details_key(tx["id"]), False)
        with st.container(border=True):
            if mobile:
                top_cols = st.columns([0.5, 3.2, 1.4])
                with top_cols[0]:
                    st.checkbox("Select", key=_selection_key(tx["id"]), label_visibility="collapsed")
                with top_cols[1]:
                    st.markdown(f"**{tx['original_filename']}**")
                    st.caption(
                        f"{tx['project_name']} · {render_duration_badge(tx.get('duration_seconds')) or 'Duration n/a'} · "
                        f"{(tx.get('word_count') or 0):,} words"
                    )
                    st.caption(render_status_badge(tx["status"]))
                with top_cols[2]:
                    if st.button("Hide" if open_now else "Open", key=f"toggle_{tx['id']}", use_container_width=True):
                        st.session_state[_details_key(tx["id"])] = not open_now
                        st.rerun()
            else:
                cols = st.columns([0.5, 3.1, 1.8, 1.4, 1.2, 1.3])
                with cols[0]:
                    st.checkbox("Select", key=_selection_key(tx["id"]), label_visibility="collapsed")
                with cols[1]:
                    st.markdown(f"**{tx['original_filename']}**")
                    st.caption(tx["project_name"])
                with cols[2]:
                    st.caption(render_status_badge(tx["status"]))
                    st.caption(tx.get("language") or "Language n/a")
                with cols[3]:
                    st.caption(render_duration_badge(tx.get("duration_seconds")) or "Duration n/a")
                with cols[4]:
                    st.caption(f"{(tx.get('word_count') or 0):,} words")
                with cols[5]:
                    if st.button("Hide" if open_now else "Open", key=f"toggle_{tx['id']}", use_container_width=True):
                        st.session_state[_details_key(tx["id"])] = not open_now
                        st.rerun()
            if st.session_state.get(_details_key(tx["id"]), False):
                _render_details(tx)


user = get_current_user()
active_team_id = get_active_team_id()
active_team = get_user_team(user["id"], active_team_id) if active_team_id else None
if not active_team:
    st.error("No active team is available for this account.")
    st.stop()

team_name = active_team.get("team_name") or active_team.get("name") or "Team"
projects = get_user_projects(user["id"], team_id=active_team_id)
mobile = is_mobile_view()

render_page_header(
    "Transcription History",
    f"{team_name} review workspace with visible bulk actions and simplified export formats.",
)

if not projects:
    st.info("No projects yet.")
    st.stop()

filter_cols = st.columns(1 if mobile else 3)
with filter_cols[0]:
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
with filter_cols[1 if not mobile else 0]:
    status_filter = st.selectbox("Status", ["All", "completed", "processing", "error"])
if not mobile:
    with filter_cols[2]:
        search_query = st.text_input("Search transcripts", placeholder="Type to search...")
else:
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

if search_query.strip():
    q = search_query.lower().strip()
    all_transcriptions = [
        tx
        for tx in all_transcriptions
        if q in (tx.get("original_filename") or "").lower()
        or q in (tx.get("transcript") or "").lower()
    ]

st.caption(f"{len(all_transcriptions)} transcriptions match your filters.")

if not all_transcriptions:
    st.info("No transcriptions match your filters.")
else:
    _render_bulk_toolbar(all_transcriptions, user["id"], mobile)
    _render_history_rows(all_transcriptions, mobile)
