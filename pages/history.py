"""
History Page — View, search, and export past transcriptions.
"""

import streamlit as st
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.db import (
    get_user_projects, get_project_transcriptions, get_transcription, delete_transcription
)
from exports.exporter import (
    export_as_txt, export_as_json, export_as_markdown,
    export_as_docx, export_as_csv
)
from utils.auth_ui import require_login, get_current_user
from utils.components import sidebar_navigation, render_status_badge, render_duration_badge

st.set_page_config(page_title="History — MLabs", page_icon="📜", layout="wide")
sidebar_navigation()
require_login()

user = get_current_user()
projects = get_user_projects(user["id"])

st.title("📜 Transcription History")
st.caption("Browse, search, and export all your past transcriptions.")
st.markdown("---")

if not projects:
    st.info("No projects yet.")
    st.stop()

# ── Filters ───────────────────────────────────────────────────────────────────
col_f1, col_f2, col_f3 = st.columns(3)

with col_f1:
    project_map = {"All Projects": None}
    project_map.update({p["name"]: p["id"] for p in projects})

    # Pre-select from session state if set
    default_proj_name = "All Projects"
    if "current_project" in st.session_state:
        cp = st.session_state["current_project"]
        if cp["name"] in project_map:
            default_proj_name = cp["name"]

    selected_proj_name = st.selectbox("Filter by Project", list(project_map.keys()),
                                       index=list(project_map.keys()).index(default_proj_name))

with col_f2:
    status_filter = st.selectbox("Status", ["All", "completed", "processing", "error"])

with col_f3:
    search_query = st.text_input("🔍 Search transcripts", placeholder="Type to search...")

# ── Load Transcriptions ───────────────────────────────────────────────────────
all_transcriptions = []
for project in projects:
    if project_map[selected_proj_name] and project["id"] != project_map[selected_proj_name]:
        continue
    txs = get_project_transcriptions(project["id"])
    for tx in txs:
        tx["project_name"] = project["name"]
        all_transcriptions.append(tx)

all_transcriptions.sort(key=lambda x: x["created_at"], reverse=True)

# Apply filters
if status_filter != "All":
    all_transcriptions = [t for t in all_transcriptions if t["status"] == status_filter]

if search_query:
    q = search_query.lower()
    all_transcriptions = [
        t for t in all_transcriptions
        if q in (t.get("original_filename") or "").lower()
        or q in (t.get("transcript") or "").lower()
    ]

# ── Bulk Export ───────────────────────────────────────────────────────────────
if all_transcriptions:
    with st.expander(f"📦 Bulk Export ({len(all_transcriptions)} records)"):
        st.download_button(
            "⬇️ Export all as CSV",
            data=export_as_csv(all_transcriptions),
            file_name="mlabs_transcriptions.csv",
            mime="text/csv",
            use_container_width=True,
        )

st.markdown(f"**{len(all_transcriptions)} transcriptions found**")
st.markdown("")

# ── Transcription Cards ───────────────────────────────────────────────────────
if not all_transcriptions:
    st.info("No transcriptions match your filters.")
else:
    for tx in all_transcriptions:
        label = (
            f"{render_status_badge(tx['status'])}  {tx['original_filename']}"
            f"  —  📁 {tx['project_name']}"
            f"  •  ⏱️ {render_duration_badge(tx.get('duration_seconds')) or '?'}"
            f"  •  📝 {tx.get('word_count') or 0:,} words"
            f"  •  🌐 {tx.get('language') or '?'}"
        )

        with st.expander(label):
            tab_text, tab_export, tab_meta = st.tabs(["📄 Transcript", "⬇️ Export", "ℹ️ Metadata"])

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

                    fname = os.path.splitext(tx["original_filename"])[0]
                    meta = {
                        "model_used": tx.get("model_used", ""),
                        "language": tx.get("language", ""),
                        "duration_seconds": tx.get("duration_seconds", 0),
                        "word_count": tx.get("word_count", 0),
                    }

                    with ec1:
                        st.download_button(
                            "📄 TXT", export_as_txt(transcript, fname),
                            file_name=f"{fname}.txt", mime="text/plain",
                            use_container_width=True, key=f"txt_{tx['id']}"
                        )
                    with ec2:
                        st.download_button(
                            "🗂️ JSON", export_as_json(tx),
                            file_name=f"{fname}.json", mime="application/json",
                            use_container_width=True, key=f"json_{tx['id']}"
                        )
                    with ec3:
                        st.download_button(
                            "📝 MD", export_as_markdown(transcript, fname, meta),
                            file_name=f"{fname}.md", mime="text/markdown",
                            use_container_width=True, key=f"md_{tx['id']}"
                        )
                    with ec4:
                        try:
                            docx_bytes = export_as_docx(transcript, fname, meta)
                            st.download_button(
                                "📃 DOCX", docx_bytes,
                                file_name=f"{fname}.docx",
                                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                use_container_width=True, key=f"docx_{tx['id']}"
                            )
                        except ImportError:
                            st.caption("DOCX: install python-docx")
                    with ec5:
                        st.download_button(
                            "🗃️ CSV", export_as_csv([tx]),
                            file_name=f"{fname}.csv", mime="text/csv",
                            use_container_width=True, key=f"csv_{tx['id']}"
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
                    st.markdown(f"**Word Count:** {tx.get('word_count') or 0:,}")
                    st.markdown(f"**Created:** {(tx.get('created_at') or '')[:19]}")

                st.markdown("")
                if st.button("🗑️ Delete this transcription", key=f"del_{tx['id']}",
                              type="secondary"):
                    delete_transcription(tx["id"])
                    st.warning("Transcription deleted.")
                    st.rerun()
