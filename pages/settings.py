"""
Settings Page — Manage API keys, account info, preferences.
"""

import streamlit as st
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.db import save_api_key, get_user_api_keys, get_connection
from utils.auth_ui import require_login, get_current_user
from utils.components import sidebar_navigation
from audio.processor import check_ffmpeg
from transcription.engine import MODELS

st.set_page_config(page_title="Settings — MLabs", page_icon="⚙️", layout="wide")
sidebar_navigation()
require_login()

user = get_current_user()
user_api_keys = get_user_api_keys(user["id"])

st.title("⚙️ Settings")
st.caption("Manage your API keys, account info, and app preferences.")
st.markdown("---")

tab_keys, tab_account, tab_system = st.tabs(["🔑 API Keys", "👤 Account", "🖥️ System Info"])

# ── API Keys Tab ──────────────────────────────────────────────────────────────
with tab_keys:
    st.subheader("Global API Keys")
    st.markdown(
        "Save your API keys here and they'll be available across all projects. "
        "Keys are stored securely in your local database."
    )
    st.markdown("")

    api_providers = [
        {"provider": "openai", "label": "OpenAI (Whisper)", "icon": "🤖",
         "placeholder": "sk-...", "models": ["Whisper"]},
        {"provider": "elevenlabs", "label": "ElevenLabs (Scribe v2)", "icon": "🎙️",
         "placeholder": "xi-...", "models": ["Scribe v2"]},
    ]

    for provider_info in api_providers:
        with st.container(border=True):
            col_label, col_input, col_save = st.columns([1.5, 3, 1])
            with col_label:
                st.markdown(f"**{provider_info['icon']} {provider_info['label']}**")
                st.caption(", ".join(provider_info["models"]))

            with col_input:
                current_key = user_api_keys.get(provider_info["provider"], "")
                new_key = st.text_input(
                    "API Key",
                    value=current_key,
                    type="password",
                    placeholder=provider_info["placeholder"],
                    key=f"key_{provider_info['provider']}",
                    label_visibility="collapsed",
                )

            with col_save:
                if st.button("Save", key=f"save_{provider_info['provider']}",
                             use_container_width=True, type="primary"):
                    if new_key.strip():
                        save_api_key(user["id"], provider_info["provider"], new_key.strip())
                        st.success("✅ Saved!")
                    else:
                        st.error("Key cannot be empty.")

    st.markdown("")
    st.info(
        "💡 **Tip:** API keys saved here are used as defaults. You can also override them "
        "per-project or per-transcription session."
    )

# ── Account Tab ───────────────────────────────────────────────────────────────
with tab_account:
    st.subheader("Account Information")

    with st.container(border=True):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**Username:** {user['username']}")
            st.markdown(f"**Email:** {user['email']}")
            st.markdown(f"**Member since:** {user.get('created_at', '')[:10]}")

    st.markdown("")
    st.subheader("Change Password")
    with st.form("change_password"):
        old_pw = st.text_input("Current Password", type="password")
        new_pw = st.text_input("New Password", type="password")
        confirm_pw = st.text_input("Confirm New Password", type="password")
        if st.form_submit_button("Update Password", use_container_width=True):
            import hashlib
            conn = get_connection()
            user_row = conn.execute(
                "SELECT * FROM users WHERE id=? AND password_hash=?",
                (user["id"], hashlib.sha256(old_pw.encode()).hexdigest())
            ).fetchone()
            conn.close()

            if not user_row:
                st.error("Current password is incorrect.")
            elif new_pw != confirm_pw:
                st.error("Passwords do not match.")
            elif len(new_pw) < 6:
                st.error("Password must be at least 6 characters.")
            else:
                conn = get_connection()
                conn.execute(
                    "UPDATE users SET password_hash=? WHERE id=?",
                    (hashlib.sha256(new_pw.encode()).hexdigest(), user["id"])
                )
                conn.commit()
                conn.close()
                st.success("✅ Password updated successfully!")

# ── System Info Tab ───────────────────────────────────────────────────────────
with tab_system:
    st.subheader("System Status")

    # FFmpeg
    ffmpeg_ok = check_ffmpeg()
    ffmpeg_status = "✅ Installed & working" if ffmpeg_ok else "❌ Not found"
    st.metric("FFmpeg", ffmpeg_status)

    # Available models
    st.markdown("---")
    st.markdown("### Available Models")
    for mkey, minfo in MODELS.items():
        col_m, col_s = st.columns([3, 1])
        with col_m:
            st.markdown(f"{minfo['icon']} **{minfo['label']}**")
            st.caption(minfo["description"])
        with col_s:
            if minfo["requires_api_key"]:
                provider_map = {"whisper": "openai", "elevenlabs_scribe_v2": "elevenlabs"}
                prov = provider_map.get(mkey, mkey)
                has_key = bool(user_api_keys.get(prov))
                st.markdown("🔑 API Key: " + ("✅" if has_key else "❌"))
            else:
                st.markdown("🖥️ Local model")

    # Python packages check
    st.markdown("---")
    st.markdown("### Package Status")
    packages = [
        ("openai", "OpenAI Whisper API"),
        ("faster_whisper", "Faster-Whisper (Local)"),
        ("nemo", "NVIDIA NeMo / Parakeet"),
        ("docx", "python-docx (DOCX export)"),
        ("requests", "Requests (HTTP client)"),
    ]
    for pkg, label in packages:
        try:
            __import__(pkg)
            st.markdown(f"✅ **{label}** (`{pkg}`)")
        except ImportError:
            st.markdown(f"❌ **{label}** (`pip install {pkg}`) — not installed")

    # DB location
    st.markdown("---")
    from database.db import DB_PATH
    st.markdown(f"**Database:** `{os.path.abspath(DB_PATH)}`")
    st.markdown(f"**App Version:** 1.0.0")
    st.markdown(f"**By:** M Labs")
