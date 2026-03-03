"""
Settings page for API keys, team management, account settings, and system checks.
"""

import hashlib
import os
import sys

import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from audio.processor import check_ffmpeg
from database.db import (
    DB_PATH,
    PERMISSION_LEVELS,
    create_team,
    create_team_invitation,
    get_connection,
    get_team_api_keys,
    get_team_invitations,
    get_team_members,
    get_user_api_keys,
    get_user_team,
    remove_team_member,
    revoke_team_invitation,
    save_api_key,
    save_team_api_key,
    update_team_member_permissions,
)
from transcription.engine import MODELS
from utils.auth_ui import get_active_team_id, get_current_user, require_login, set_active_team_id
from utils.components import sidebar_navigation

st.set_page_config(page_title="Settings - MLabs", page_icon="S", layout="wide")
sidebar_navigation()
require_login()

user = get_current_user()
active_team_id = get_active_team_id()
active_team = get_user_team(user["id"], active_team_id) if active_team_id else None
if not active_team:
    st.error("No active team is available for this account.")
    st.stop()

team_name = active_team.get("team_name") or active_team.get("name") or "Team"
can_edit_personal_api_keys = bool(active_team.get("is_owner") or active_team.get("can_edit_personal_api_keys"))
can_edit_team_api_keys = bool(active_team.get("is_owner") or active_team.get("can_edit_team_api_keys"))
can_manage_members = bool(active_team.get("is_owner") or active_team.get("can_manage_members"))

user_api_keys = get_user_api_keys(user["id"])
team_api_keys = get_team_api_keys(active_team_id, acting_user_id=user["id"])

st.title("Settings")
st.caption(f"Active team: {team_name}. Manage API keys, team access, and account preferences.")
st.markdown("---")

tab_keys, tab_team, tab_account, tab_system = st.tabs(
    ["API Keys", "Team", "Account", "System Info"]
)

api_providers = [
    {
        "provider": "openai",
        "label": "OpenAI (Whisper)",
        "placeholder": "sk-...",
        "models": ["Whisper"],
    },
    {
        "provider": "elevenlabs",
        "label": "ElevenLabs (Scribe v2)",
        "placeholder": "xi-...",
        "models": ["Scribe v2"],
    },
]

permission_options = ["use_only", "own_key", "team_key"]


def permission_label(level: str) -> str:
    preset = PERMISSION_LEVELS.get(level, PERMISSION_LEVELS["own_key"])
    return preset["label"]


def member_role_label(member: dict) -> str:
    if member.get("is_owner"):
        return "Owner"
    return permission_label(member.get("permission_level", "own_key"))


with tab_keys:
    st.subheader("Personal API Keys")
    if not can_edit_personal_api_keys:
        st.info("Your role in this team cannot update personal API keys.")

    for provider_info in api_providers:
        with st.container(border=True):
            col_label, col_input, col_save = st.columns([1.6, 3, 1])
            with col_label:
                st.markdown(f"**{provider_info['label']}**")
                st.caption(", ".join(provider_info["models"]))

            with col_input:
                current_key = user_api_keys.get(provider_info["provider"], "")
                new_key = st.text_input(
                    "Personal API Key",
                    value=current_key,
                    type="password",
                    placeholder=provider_info["placeholder"],
                    key=f"personal_key_{provider_info['provider']}",
                    label_visibility="collapsed",
                )

            with col_save:
                if st.button(
                    "Save",
                    key=f"save_personal_{provider_info['provider']}",
                    type="primary",
                    use_container_width=True,
                    disabled=not can_edit_personal_api_keys,
                ):
                    if not new_key.strip():
                        st.error("Key cannot be empty.")
                    else:
                        save_api_key(user["id"], provider_info["provider"], new_key.strip())
                        st.success("Saved personal key.")
                        st.rerun()

    st.markdown("")
    st.subheader("Team API Keys")
    if not can_edit_team_api_keys:
        st.info("Your role in this team cannot update team API keys.")

    for provider_info in api_providers:
        with st.container(border=True):
            col_label, col_input, col_save = st.columns([1.6, 3, 1])
            with col_label:
                st.markdown(f"**{provider_info['label']}**")
                st.caption(f"Shared across {team_name}")

            with col_input:
                current_key = team_api_keys.get(provider_info["provider"], "")
                new_key = st.text_input(
                    "Team API Key",
                    value=current_key,
                    type="password",
                    placeholder=provider_info["placeholder"],
                    key=f"team_key_{provider_info['provider']}",
                    label_visibility="collapsed",
                )

            with col_save:
                if st.button(
                    "Save",
                    key=f"save_team_{provider_info['provider']}",
                    type="primary",
                    use_container_width=True,
                    disabled=not can_edit_team_api_keys,
                ):
                    if not new_key.strip():
                        st.error("Key cannot be empty.")
                    else:
                        ok, msg = save_team_api_key(
                            active_team_id,
                            user["id"],
                            provider_info["provider"],
                            new_key.strip(),
                        )
                        if ok:
                            st.success("Saved team key.")
                            st.rerun()
                        else:
                            st.error(msg)

with tab_team:
    st.subheader("Active Team")
    with st.container(border=True):
        st.markdown(f"**Team:** {team_name}")
        st.markdown(f"**Your Role:** {member_role_label(active_team)}")
        st.markdown(f"**Can manage members:** {'Yes' if can_manage_members else 'No'}")

    st.markdown("")
    st.subheader("Create Team")
    with st.form("create_team_form"):
        new_team_name = st.text_input("Team Name")
        if st.form_submit_button("Create Team", use_container_width=True):
            ok, msg, team_payload = create_team(user["id"], new_team_name.strip())
            if ok and team_payload:
                set_active_team_id(team_payload["id"])
                st.success(f"{msg} Switched to {team_payload.get('team_name') or team_payload.get('name')}.")
                st.rerun()
            else:
                st.error(msg)

    st.markdown("")
    st.subheader("Team Members")
    members = get_team_members(active_team_id, user["id"])
    if not members:
        st.info("No team members found.")
    else:
        for member in members:
            with st.container(border=True):
                col_info, col_actions = st.columns([2, 3])
                with col_info:
                    st.markdown(f"**{member['username']}**")
                    st.caption(member["email"])
                    st.caption(member_role_label(member))

                with col_actions:
                    if member.get("is_owner"):
                        st.caption("Owner permissions are fixed.")
                    elif can_manage_members:
                        member_permission = member.get("permission_level", "own_key")
                        selected_permission = st.selectbox(
                            f"Permissions for {member['username']}",
                            options=permission_options,
                            index=permission_options.index(member_permission)
                            if member_permission in permission_options
                            else 1,
                            format_func=permission_label,
                            key=f"perm_{member['user_id']}",
                        )
                        c1, c2 = st.columns(2)
                        with c1:
                            if st.button(
                                "Update",
                                key=f"perm_save_{member['user_id']}",
                                use_container_width=True,
                            ):
                                ok, msg = update_team_member_permissions(
                                    active_team_id,
                                    member["user_id"],
                                    user["id"],
                                    selected_permission,
                                )
                                if ok:
                                    st.success(msg)
                                    st.rerun()
                                else:
                                    st.error(msg)
                        with c2:
                            if st.button(
                                "Remove",
                                key=f"perm_remove_{member['user_id']}",
                                use_container_width=True,
                            ):
                                ok, msg = remove_team_member(
                                    active_team_id,
                                    member["user_id"],
                                    user["id"],
                                )
                                if ok:
                                    st.warning(msg)
                                    st.rerun()
                                else:
                                    st.error(msg)
                    else:
                        st.caption("You cannot edit member permissions.")

    st.markdown("")
    st.subheader("Invitations")
    if not can_manage_members:
        st.info("Your role in this team cannot send or revoke invites.")
    else:
        with st.form("invite_user_form"):
            invite_email = st.text_input("Invite Email")
            invite_permission = st.selectbox(
                "Invite Permission",
                options=permission_options,
                index=1,
                format_func=permission_label,
            )
            invite_days = st.number_input("Invite valid for (days)", min_value=1, max_value=30, value=7)
            submitted_invite = st.form_submit_button("Create Invite", use_container_width=True)
            if submitted_invite:
                ok, msg, invite_payload = create_team_invitation(
                    active_team_id,
                    user["id"],
                    invite_email.strip(),
                    permission_level=invite_permission,
                    days_valid=int(invite_days),
                )
                if ok and invite_payload:
                    st.success(msg)
                    st.code(invite_payload["invite_token"], language="text")
                    st.caption("Share this token privately with the invited user.")
                else:
                    st.error(msg)

    invites = get_team_invitations(active_team_id, user["id"]) if can_manage_members else []
    pending_invites = [
        invite
        for invite in invites
        if not invite.get("accepted_at") and not invite.get("revoked_at")
    ]
    if pending_invites:
        st.markdown("**Pending Invites**")
        for invite in pending_invites:
            with st.container(border=True):
                c1, c2 = st.columns([4, 1])
                with c1:
                    st.markdown(f"**{invite['email']}**")
                    st.caption(
                        f"{permission_label(invite.get('permission_level', 'own_key'))} | Expires: {invite['expires_at'][:19]}"
                    )
                    st.code(invite["invite_token"], language="text")
                with c2:
                    if st.button(
                        "Revoke",
                        key=f"revoke_invite_{invite['id']}",
                        use_container_width=True,
                        disabled=not can_manage_members,
                    ):
                        ok, msg = revoke_team_invitation(invite["id"], user["id"])
                        if ok:
                            st.warning(msg)
                            st.rerun()
                        else:
                            st.error(msg)

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
            conn = get_connection()
            user_row = conn.execute(
                "SELECT * FROM users WHERE id=? AND password_hash=?",
                (user["id"], hashlib.sha256(old_pw.encode()).hexdigest()),
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
                    (hashlib.sha256(new_pw.encode()).hexdigest(), user["id"]),
                )
                conn.commit()
                conn.close()
                st.success("Password updated successfully.")

with tab_system:
    st.subheader("System Status")

    ffmpeg_ok = check_ffmpeg()
    ffmpeg_status = "Installed & working" if ffmpeg_ok else "Not found"
    st.metric("FFmpeg", ffmpeg_status)

    st.markdown("---")
    st.markdown("### Available Models")
    for model_key, model_info in MODELS.items():
        col_model, col_status = st.columns([3, 1])
        with col_model:
            st.markdown(f"{model_info['icon']} **{model_info['label']}**")
            st.caption(model_info["description"])
        with col_status:
            if model_info["requires_api_key"]:
                provider_map = {"whisper": "openai", "elevenlabs_scribe_v2": "elevenlabs"}
                provider = provider_map.get(model_key, model_key)
                has_any_key = bool(user_api_keys.get(provider) or team_api_keys.get(provider))
                st.markdown("API Key: " + ("Available" if has_any_key else "Missing"))
            else:
                st.markdown("Local model")

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
            st.markdown(f"OK  **{label}** (`{pkg}`)")
        except ImportError:
            st.markdown(f"Missing  **{label}** (`pip install {pkg}`)")

    st.markdown("---")
    st.markdown(f"**Database:** `{os.path.abspath(DB_PATH)}`")
    st.markdown("**App Version:** 1.1.0")
    st.markdown("**By:** M Labs")
