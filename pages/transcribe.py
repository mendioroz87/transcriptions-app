"""
Transcription Page - Upload audio, select model, run transcription.
"""

import os
import sys
import tempfile
import mimetypes

import streamlit as st
import streamlit.components.v1 as components

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
from exports.exporter import export_as_json, export_as_txt  # noqa: E402
from transcription.engine import (  # noqa: E402
    DEFAULT_SUMMARY_PROMPT,
    MODELS,
    TranscriptionUserError,
    check_model_requirements,
    summarize_transcript_with_openai,
    transcribe,
)
from utils.auth_ui import get_active_team_id, get_current_user, require_login  # noqa: E402
from utils.components import render_duration_badge, sidebar_navigation  # noqa: E402


def render_audio_preview_player(audio_path: str, original_filename: str, key_prefix: str):
    """Render an audio preview player with explicit playback speed and volume controls."""
    mime_type = mimetypes.guess_type(original_filename)[0] or "audio/wav"
    st.audio(audio_path, format=mime_type)

    col_speed, col_volume = st.columns(2)
    with col_speed:
        playback_speed = st.select_slider(
            "Speed",
            options=[0.5, 0.75, 1.0, 1.25, 1.5, 2.0],
            value=1.0,
            key=f"{key_prefix}_speed",
        )
    with col_volume:
        volume_percent = st.slider(
            "Volume",
            min_value=0,
            max_value=100,
            value=100,
            step=5,
            key=f"{key_prefix}_volume",
        )

    # Apply controls to audio elements rendered by Streamlit.
    components.html(
        f"""
        <script>
        const speed = {float(playback_speed)};
        const volume = {float(volume_percent) / 100.0};
        const applyPlaybackSettings = () => {{
            const players = window.parent.document.querySelectorAll("audio");
            players.forEach((player) => {{
                player.playbackRate = speed;
                player.volume = Math.max(0, Math.min(volume, 1));
            }});
        }};
        applyPlaybackSettings();
        setTimeout(applyPlaybackSettings, 200);
        setTimeout(applyPlaybackSettings, 900);
        </script>
        """,
        height=0,
    )


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

    st.markdown("")
    summary_requested = st.checkbox(
        "Generate transcript summary (OpenAI, low reasoning)",
        value=False,
        help="Uses your OpenAI key and the default MLabs summary prompt.",
    )
    summary_api_key = None
    summary_prompt_template = DEFAULT_SUMMARY_PROMPT
    if summary_requested:
        summary_team_key = team_api_keys.get("openai") or ""
        summary_user_key = user_api_keys.get("openai") or ""
        summary_project_key = selected_project.get("api_key") if selected_model == "whisper" else ""

        summary_sources = []
        if summary_team_key:
            summary_sources.append("Team OpenAI key")
        if summary_user_key:
            summary_sources.append("My OpenAI key")
        if summary_project_key:
            summary_sources.append("Project key")
        summary_sources.append("Custom OpenAI key")

        default_summary_source = "Custom OpenAI key"
        if summary_team_key:
            default_summary_source = "Team OpenAI key"
        elif summary_user_key:
            default_summary_source = "My OpenAI key"
        elif summary_project_key:
            default_summary_source = "Project key"

        selected_summary_source = st.selectbox(
            "Summary Key Source",
            options=summary_sources,
            index=summary_sources.index(default_summary_source),
        )

        if selected_summary_source == "Team OpenAI key":
            summary_api_key = summary_team_key
        elif selected_summary_source == "My OpenAI key":
            summary_api_key = summary_user_key
        elif selected_summary_source == "Project key":
            summary_api_key = summary_project_key
        else:
            summary_api_key = st.text_input(
                "OpenAI API Key (for summary)",
                value="",
                type="password",
                help="Required only when summary is enabled.",
            )

        with st.expander("Summary Prompt", expanded=False):
            st.text_area(
                "Prompt Template",
                value=summary_prompt_template,
                height=320,
                disabled=True,
                help="Default summary prompt currently in use.",
            )

        if not summary_api_key:
            st.warning("Summary requires a valid OpenAI API key.")

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
        can_transcribe = (
            ((not model_info["requires_api_key"]) or bool(api_key))
            and model_ready
            and ((not summary_requested) or bool(summary_api_key))
        )
        playback_container = st.container(border=True)
        with playback_container:
            st.caption("Preview audio")
            player_key_prefix = f"preview_{selected_pid}_{uploaded_file.name}_{uploaded_file.size}"
            render_audio_preview_player(
                audio_path=raw_path,
                original_filename=uploaded_file.name,
                key_prefix=player_key_prefix,
            )

            st.markdown("")
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

                    summary_result = None
                    summary_error = None
                    if summary_requested:
                        update_progress(98, "Generating summary with OpenAI...")
                        try:
                            summary_result = summarize_transcript_with_openai(
                                transcript=result["text"],
                                api_key=summary_api_key,
                                transcript_language=result.get("language"),
                                prompt_template=summary_prompt_template,
                            )
                        except Exception as summary_exc:
                            summary_error = str(summary_exc)

                    summary_text_value = summary_result["summary"] if summary_result else None
                    update_transcription(
                        tid=tid,
                        transcript=result["text"],
                        status="completed",
                        duration=result.get("duration"),
                        word_count=result.get("word_count"),
                        language=result.get("language"),
                        summary_text=summary_text_value,
                    )

                    progress_bar.progress(1.0, text="Transcription complete")

                    with result_area:
                        st.success(
                            f"Transcription complete: {result['word_count']:,} words, "
                            f"language {result['language']}, chunks {result['chunks_processed']}"
                        )
                        st.text_area("Transcript", value=result["text"], height=300)
                        if summary_requested:
                            st.markdown("### Summary")
                            if summary_result:
                                st.caption(f"Generated with {summary_result['model_used']} (low reasoning mode).")
                                st.text_area("Summary", value=summary_result["summary"], height=260)
                            else:
                                st.warning(f"Summary could not be generated: {summary_error}")

                        st.markdown("Download options:")
                        col_export_checks = st.columns(2)
                        with col_export_checks[0]:
                            export_transcript_only = st.checkbox(
                                "Export transcription only",
                                value=True,
                                key=f"tx_only_export_{tid}",
                            )
                        with col_export_checks[1]:
                            export_transcript_and_summary = st.checkbox(
                                "Export transcription + summary",
                                value=bool(summary_result),
                                disabled=not bool(summary_result),
                                key=f"tx_plus_summary_export_{tid}",
                            )

                        include_summary_in_exports = export_transcript_and_summary and bool(summary_result)
                        if not export_transcript_only and not export_transcript_and_summary:
                            st.warning("Select at least one export mode.")

                        dc1, dc2, dc3 = st.columns(3)
                        with dc1:
                            st.download_button(
                                "TXT",
                                export_as_txt(
                                    result["text"],
                                    title=uploaded_file.name,
                                    summary_text=summary_text_value or "",
                                    include_summary=include_summary_in_exports,
                                ),
                                file_name=f"{uploaded_file.name}.txt",
                                mime="text/plain",
                                use_container_width=True,
                                disabled=not (export_transcript_only or export_transcript_and_summary),
                            )
                        with dc2:
                            result_for_export = dict(result)
                            if summary_result:
                                result_for_export["summary"] = summary_result["summary"]
                                result_for_export["summary_model"] = summary_result["model_used"]

                            st.download_button(
                                "JSON",
                                export_as_json(
                                    result_for_export,
                                    include_summary=include_summary_in_exports,
                                ),
                                file_name=f"{uploaded_file.name}.json",
                                mime="application/json",
                                use_container_width=True,
                                disabled=not (export_transcript_only or export_transcript_and_summary),
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
