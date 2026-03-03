"""
Transcription Page - Upload audio, select model, run transcription.
"""

import os
import sys
import tempfile

import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from audio.processor import (  # noqa: E402
    SUPPORTED_EXTENSIONS,
    check_ffmpeg,
    get_audio_info,
    process_uploaded_file,
)
from database.db import (  # noqa: E402
    create_transcription,
    get_team_api_keys,
    get_user_api_keys,
    get_user_team,
    get_user_projects,
    update_transcription,
)
from transcription.engine import MODELS, TranscriptionUserError, check_model_requirements, transcribe  # noqa: E402
from utils.auth_ui import get_active_team_id, get_current_user, require_login  # noqa: E402
from utils.components import render_duration_badge, sidebar_navigation  # noqa: E402


st.set_page_config(page_title="Transcribe - MLabs", page_icon="T", layout="wide")
require_login()
sidebar_navigation()

user = get_current_user()
active_team_id = get_active_team_id()
active_team = get_user_team(user["id"], active_team_id) if active_team_id else None
if not active_team:
    st.error("No active team is available for this account.")
    st.stop()

team_name = active_team.get("team_name") or active_team.get("name") or "Team"
user_api_keys = get_user_api_keys(user["id"])
team_api_keys = get_team_api_keys(active_team_id, acting_user_id=user["id"])
projects = get_user_projects(user["id"], team_id=active_team_id)

st.title("New Transcription")
st.caption(f"Team: {team_name}. Upload audio and transcribe it with your selected model.")

if not check_ffmpeg():
    st.error(
        "FFmpeg not found. Audio conversion will fail without it.\n\n"
        "Install FFmpeg:\n"
        "- Ubuntu/Debian: `sudo apt install ffmpeg`\n"
        "- macOS: `brew install ffmpeg`\n"
        "- Windows: Download from https://ffmpeg.org/download.html"
    )

if not projects:
    st.warning("You do not have any projects yet. Create one first.")
    if st.button("Create a Project"):
        st.switch_page("pages/projects.py")
    st.stop()

st.markdown("---")

col_config, col_upload = st.columns([1, 1.5], gap="large")

with col_config:
    st.subheader("Configuration")

    project_options = {p["id"]: p for p in projects}
    default_pid = None
    if "current_project" in st.session_state:
        default_pid = st.session_state["current_project"]["id"]

    project_ids = list(project_options.keys())
    default_idx = project_ids.index(default_pid) if default_pid in project_ids else 0

    selected_pid = st.selectbox(
        "Project",
        options=project_ids,
        format_func=lambda pid: project_options[pid]["name"],
        index=default_idx,
    )
    selected_project = project_options[selected_pid]

    model_keys = list(MODELS.keys())
    current_model = selected_project.get("model", "whisper")
    current_idx = model_keys.index(current_model) if current_model in model_keys else 0

    selected_model = st.selectbox(
        "Transcription Model",
        options=model_keys,
        format_func=lambda key: f"{MODELS[key]['icon']} {MODELS[key]['label']}",
        index=current_idx,
        help="Select the AI model to use for this transcription.",
    )
    model_info = MODELS[selected_model]
    st.caption(f"_{model_info['description']}_")

    api_key = None
    if model_info["requires_api_key"]:
        provider_map = {
            "whisper": "openai",
            "elevenlabs_scribe_v2": "elevenlabs",
        }
        provider = provider_map.get(selected_model, selected_model)
        team_key = team_api_keys.get(provider) or ""
        user_key = user_api_keys.get(provider) or ""
        project_key = selected_project.get("api_key") or ""

        key_source_labels = []
        if team_key:
            key_source_labels.append("Team key")
        if user_key:
            key_source_labels.append("My key")
        if project_key:
            key_source_labels.append("Project key")
        key_source_labels.append("Custom key")

        default_source = "Custom key"
        if team_key:
            default_source = "Team key"
        elif user_key:
            default_source = "My key"
        elif project_key:
            default_source = "Project key"

        selected_source = st.selectbox(
            "API Key Source",
            options=key_source_labels,
            index=key_source_labels.index(default_source),
            help="Choose whether to use the active team key, your personal key, project key, or a one-off key.",
        )

        if selected_source == "Team key":
            api_key = team_key
        elif selected_source == "My key":
            api_key = user_key
        elif selected_source == "Project key":
            api_key = project_key
        else:
            api_key = st.text_input(
                model_info["api_key_label"],
                value="",
                type="password",
                help="This key is used for this run only unless saved in Settings.",
            )

        if not api_key:
            st.warning(f"An API key is required for {model_info['label']}.")

    language = st.selectbox(
        "Language (optional)",
        options=["Auto-detect", "en", "es", "fr", "de", "pt", "it", "zh", "ja", "ar", "ru"],
        help="Keep Auto-detect unless you know the language.",
    )
    language_code = None if language == "Auto-detect" else language

    st.info(
        "Long audio is split into 10-minute chunks and stitched after transcription."
    )

    model_ready, model_error = check_model_requirements(selected_model, api_key=api_key)
    if not model_ready:
        st.error(f"Model is not ready: {model_error}")

with col_upload:
    st.subheader("Upload Audio")

    ext_list = ", ".join(sorted(SUPPORTED_EXTENSIONS))
    st.caption(f"Supported formats: {ext_list}")

    uploaded_file = st.file_uploader(
        "Drag and drop or browse",
        type=[ext.lstrip(".") for ext in SUPPORTED_EXTENSIONS],
        label_visibility="collapsed",
    )

    if uploaded_file:
        st.success(f"Loaded: {uploaded_file.name} ({uploaded_file.size / (1024*1024):.1f} MB)")

        with st.spinner("Analyzing audio..."):
            tmp_dir = tempfile.mkdtemp()
            ext = os.path.splitext(uploaded_file.name)[1]
            raw_path = os.path.join(tmp_dir, f"preview{ext}")
            with open(raw_path, "wb") as file_obj:
                file_obj.write(uploaded_file.getbuffer())
            info = get_audio_info(raw_path)

        col_d, col_s, col_c = st.columns(3)
        with col_d:
            st.metric("Duration", render_duration_badge(info.get("duration", 0)) or "?")
        with col_s:
            st.metric("File Size", f"{info.get('size_mb', 0)} MB")
        with col_c:
            st.metric("Codec", str(info.get("codec", "?")).upper())

        dur = info.get("duration", 0)
        if dur > 3600:
            chunks_est = max(1, int(dur // 600))
            st.info(
                f"This file is {render_duration_badge(dur)} long and will use about {chunks_est} chunks."
            )

        st.markdown("")
        can_transcribe = ((not model_info["requires_api_key"]) or bool(api_key)) and model_ready

        if st.button("Start Transcription", type="primary", use_container_width=True, disabled=not can_transcribe):
            progress_bar = st.progress(0, text="Preparing...")
            result_area = st.container()

            def update_progress(pct: int, msg: str):
                progress_bar.progress(pct / 100, text=msg)

            try:
                update_progress(3, "Converting audio via FFmpeg...")
                wav_path, _audio_info = process_uploaded_file(uploaded_file, tmp_dir)

                tid = create_transcription(
                    project_id=selected_pid,
                    filename=os.path.basename(wav_path),
                    original_filename=uploaded_file.name,
                    model_used=selected_model,
                    acting_user_id=user["id"],
                )

                result = transcribe(
                    audio_path=wav_path,
                    model=selected_model,
                    api_key=api_key,
                    language=language_code,
                    progress_callback=update_progress,
                )

                update_transcription(
                    tid=tid,
                    transcript=result["text"],
                    status="completed",
                    duration=result.get("duration"),
                    word_count=result.get("word_count"),
                    language=result.get("language"),
                )

                progress_bar.progress(1.0, text="Transcription complete")

                with result_area:
                    st.success(
                        f"Transcription complete: {result['word_count']:,} words, "
                        f"language {result['language']}, chunks {result['chunks_processed']}"
                    )
                    st.text_area("Transcript", value=result["text"], height=300)

                    st.markdown("Download transcript:")
                    dc1, dc2, dc3 = st.columns(3)
                    with dc1:
                        st.download_button(
                            "TXT",
                            result["text"].encode(),
                            file_name=f"{uploaded_file.name}.txt",
                            mime="text/plain",
                            use_container_width=True,
                        )
                    with dc2:
                        import json

                        st.download_button(
                            "JSON",
                            json.dumps(result, indent=2).encode(),
                            file_name=f"{uploaded_file.name}.json",
                            mime="application/json",
                            use_container_width=True,
                        )
                    with dc3:
                        if st.button("Full Export Options", use_container_width=True):
                            st.session_state["current_project"] = selected_project
                            st.switch_page("pages/history.py")

            except Exception as exc:
                if "tid" in locals():
                    update_transcription(tid, transcript="", status="error")
                progress_bar.empty()
                st.error(f"Transcription failed: {exc}")
                if not isinstance(exc, TranscriptionUserError):
                    st.exception(exc)
