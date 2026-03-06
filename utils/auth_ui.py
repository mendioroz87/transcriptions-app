import re
import time

import streamlit as st

from database.db import (
    accept_pending_team_invitation,
    authenticate_user,
    complete_password_reset,
    create_password_reset_request,
    get_pending_invitations_for_email,
    get_user_default_team_id,
    get_user_teams,
    resolve_google_user_login,
    revoke_password_reset_token,
    validate_password_reset_token,
)
from utils.email_sender import send_password_reset_email

GOOGLE_PROVIDER_NAME = "google"
VALID_GOOGLE_ISSUERS = {"https://accounts.google.com", "accounts.google.com"}


def _clear_local_session():
    for key in ["user", "current_project", "active_team_id", "auth_provider"]:
        st.session_state.pop(key, None)


def _get_query_param(name: str) -> str:
    return str(st.query_params.get(name, "") or "").strip()


def _set_query_param(name: str, value: str):
    st.query_params[name] = value


def _clear_query_param(name: str):
    try:
        if name in st.query_params:
            del st.query_params[name]
    except Exception:
        pass


def _consume_query_param(name: str) -> str:
    value = _get_query_param(name)
    if value:
        _clear_query_param(name)
    return value


def _get_streamlit_user():
    return getattr(st, "user", None)


def _oidc_supported() -> bool:
    return hasattr(st, "login") and hasattr(st, "logout") and _get_streamlit_user() is not None


def _get_secret_section(name: str):
    try:
        section = st.secrets.get(name)
    except Exception:
        return {}
    return section or {}


def google_login_available() -> bool:
    if not _oidc_supported():
        return False
    auth_section = _get_secret_section("auth")
    provider_section = auth_section.get(GOOGLE_PROVIDER_NAME) if hasattr(auth_section, "get") else {}
    return bool(
        auth_section.get("redirect_uri")
        and auth_section.get("cookie_secret")
        and provider_section
        and provider_section.get("client_id")
        and provider_section.get("client_secret")
        and provider_section.get("server_metadata_url")
    )


def _streamlit_user_logged_in() -> bool:
    user = _get_streamlit_user()
    return bool(getattr(user, "is_logged_in", False))


def _get_streamlit_user_claims() -> dict:
    user = _get_streamlit_user()
    if user is None:
        return {}

    to_dict = getattr(user, "to_dict", None)
    if callable(to_dict):
        try:
            return dict(to_dict())
        except Exception:
            pass

    claims = {}
    try:
        claims.update(dict(user))
    except Exception:
        pass

    for key in [
        "sub",
        "email",
        "name",
        "preferred_username",
        "email_verified",
        "iss",
        "aud",
        "exp",
    ]:
        value = getattr(user, key, None)
        if value is not None:
            claims[key] = value
    return claims


def _claim_is_true(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes"}


def _get_expected_google_client_id() -> str:
    auth_section = _get_secret_section("auth")
    provider_section = auth_section.get(GOOGLE_PROVIDER_NAME) if hasattr(auth_section, "get") else {}
    return str(provider_section.get("client_id", "") or "").strip()


def _validate_google_claims(claims: dict) -> str | None:
    issuer = str(claims.get("iss", "") or "").strip()
    if issuer not in VALID_GOOGLE_ISSUERS:
        return "Google authentication failed because the identity issuer is invalid."

    subject = str(claims.get("sub", "") or "").strip()
    if not subject:
        return "Google authentication failed because the Google subject claim is missing."

    email = str(claims.get("email", "") or "").strip().lower()
    if not email or not email.endswith("@gmail.com"):
        return "Only @gmail.com accounts can sign in with Google."

    if not _claim_is_true(claims.get("email_verified")):
        return "Google authentication failed because the Gmail address is not verified."

    exp_value = claims.get("exp")
    try:
        exp_timestamp = int(float(exp_value))
    except (TypeError, ValueError):
        return "Google authentication failed because the session expiration is missing."
    if exp_timestamp <= int(time.time()):
        return "Your Google session has expired. Please sign in again."

    expected_client_id = _get_expected_google_client_id()
    aud_value = claims.get("aud")
    if expected_client_id and aud_value:
        audiences = aud_value if isinstance(aud_value, list) else [aud_value]
        normalized_audiences = {str(item).strip() for item in audiences}
        if expected_client_id not in normalized_audiences:
            return "Google authentication failed because the audience claim is invalid."

    return None


def _normalize_username_candidate(value: str) -> str:
    candidate = re.sub(r"[^A-Za-z0-9_.-]+", "", (value or "").strip())
    return candidate or "member"


def _sync_google_session():
    if not google_login_available() or not _streamlit_user_logged_in():
        return st.session_state.get("user")

    claims = _get_streamlit_user_claims()
    validation_error = _validate_google_claims(claims)
    if validation_error:
        _clear_local_session()
        _set_query_param("auth_error", validation_error)
        st.logout()
        return None

    preferred_username = _normalize_username_candidate(
        str(claims.get("preferred_username") or "").split("@")[0]
        or str(claims.get("email", "") or "").split("@")[0]
    )
    ok, msg, user = resolve_google_user_login(
        provider_subject=str(claims.get("sub", "")).strip(),
        email=str(claims.get("email", "")).strip(),
        preferred_username=preferred_username,
    )
    if not ok or not user:
        _clear_local_session()
        _set_query_param("auth_error", msg or "Unable to sign in with Google.")
        st.logout()
        return None

    st.session_state["user"] = user
    st.session_state["auth_provider"] = GOOGLE_PROVIDER_NAME
    ensure_active_team()
    return user


def is_logged_in() -> bool:
    _sync_google_session()
    return st.session_state.get("user") is not None


def get_current_user() -> dict:
    return st.session_state.get("user")


def get_active_team_id():
    return st.session_state.get("active_team_id")


def set_active_team_id(team_id: int | None):
    if team_id is None:
        st.session_state.pop("active_team_id", None)
    else:
        st.session_state["active_team_id"] = team_id


def ensure_active_team():
    user = st.session_state.get("user")
    if not user:
        return None

    teams = get_user_teams(user["id"])
    if not teams:
        set_active_team_id(None)
        return None

    current_team_id = get_active_team_id()
    team_ids = [team["id"] for team in teams]
    if current_team_id in team_ids:
        return current_team_id

    default_team_id = get_user_default_team_id(user["id"]) or team_ids[0]
    set_active_team_id(default_team_id)
    return default_team_id


def hide_sidebar_for_logged_out():
    st.markdown(
        """
        <style>
            section[data-testid="stSidebar"] {display: none !important;}
            [data-testid="stSidebarNav"] {display: none !important;}
            [data-testid="collapsedControl"] {display: none !important;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def login(username_or_email: str, password: str) -> bool:
    user = authenticate_user(username_or_email, password)
    if user:
        st.session_state["user"] = user
        st.session_state["auth_provider"] = "local"
        ensure_active_team()
        return True
    return False


def logout():
    had_google_session = _streamlit_user_logged_in()
    _clear_local_session()
    if had_google_session:
        st.logout()
    else:
        st.rerun()


def require_login():
    """Call at the top of any page that requires authentication."""
    _sync_google_session()
    if st.session_state.get("user") is None:
        hide_sidebar_for_logged_out()
        st.warning("Please log in to access this page.")
        st.stop()
    ensure_active_team()


def _render_google_login_button(key: str, *, primary: bool = False):
    label = "Continue with Google"
    if not google_login_available():
        st.info("Google sign-in is not configured yet. Add the OIDC secrets to Streamlit Cloud first.")
        return

    if st.button(label, key=key, use_container_width=True, type="primary" if primary else "secondary"):
        st.login(provider=GOOGLE_PROVIDER_NAME)


def _render_query_messages():
    error_message = _consume_query_param("auth_error")
    if error_message:
        st.error(error_message)

    success_message = _consume_query_param("auth_success")
    if success_message:
        st.success(success_message)


def _render_password_reset_request():
    with st.form("reset_password_request_form"):
        identifier = st.text_input("Username or Email")
        submitted = st.form_submit_button("Send Reset Email", use_container_width=True)
        if submitted:
            ok, msg, payload = create_password_reset_request(identifier.strip())
            if not ok:
                st.error(msg)
                return

            if not payload:
                st.success("If an account matches that identifier, a reset email will be sent.")
                return

            email_ok, email_msg = send_password_reset_email(
                recipient_email=payload["email"],
                username=payload.get("username") or payload["email"],
                reset_token=payload["token"],
                expires_at=payload["expires_at"],
            )
            if email_ok:
                st.success("Password reset email sent. Check your inbox.")
            else:
                revoke_password_reset_token(payload["token"])
                st.error(f"Password reset email could not be sent: {email_msg}")


def _render_password_reset_completion(reset_token: str):
    is_valid, msg, payload = validate_password_reset_token(reset_token)
    if not is_valid or not payload:
        st.error(msg)
        if st.button("Request a new reset link", key="reset_link_request_new", use_container_width=True):
            _clear_query_param("reset")
            st.rerun()
        return

    st.info(f"Resetting password for `{payload['user_email']}`.")
    with st.form("reset_password_complete_form"):
        new_password = st.text_input("New Password", type="password")
        confirm = st.text_input("Confirm New Password", type="password")
        submitted = st.form_submit_button("Update Password", use_container_width=True)
        if submitted:
            if new_password != confirm:
                st.error("Passwords do not match.")
            elif len(new_password) < 6:
                st.error("Password must be at least 6 characters.")
            else:
                ok, response = complete_password_reset(reset_token, new_password)
                if ok:
                    _clear_query_param("reset")
                    _set_query_param("auth_success", response)
                    st.rerun()
                else:
                    st.error(response)


def render_pending_invitations_panel():
    user = get_current_user()
    if not user:
        return 0

    pending_invites = get_pending_invitations_for_email(user.get("email"))
    if not pending_invites:
        return 0

    st.markdown("### Pending Invitations")
    st.caption("This Gmail account has invitations waiting. Join each team explicitly.")

    for invite in pending_invites:
        permission_label = {
            "team_key": "Team Key Manager",
            "own_key": "Personal Key Manager",
            "use_only": "Member",
        }.get(invite.get("permission_level"), "Member")
        with st.container(border=True):
            col_info, col_action = st.columns([3, 1])
            with col_info:
                st.markdown(f"**{invite['team_name']}**")
                st.caption(
                    f"Invited by {invite['invited_by_username']} · Access: {permission_label} · Expires: {invite['expires_at'][:19]}"
                )
            with col_action:
                if st.button("Join Team", key=f"accept_pending_invite_{invite['id']}", use_container_width=True):
                    ok, msg, payload = accept_pending_team_invitation(invite["id"], user["id"])
                    if ok and payload:
                        set_active_team_id(payload["team_id"])
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
    return len(pending_invites)


def render_login_form():
    """Render sign-in, invite guidance, and password reset forms."""
    _render_query_messages()
    reset_token = _get_query_param("reset")
    tab1, tab2, tab3 = st.tabs(["Sign In", "Invitations", "Reset Password"])

    with tab1:
        st.markdown("#### Google Sign-In")
        st.caption("Use the Gmail address that was invited to the app.")
        _render_google_login_button("google_login_sign_in", primary=True)
        st.markdown("")
        st.caption("Or sign in with your existing local password.")
        with st.form("login_form"):
            identifier = st.text_input("Username or Email")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign In", use_container_width=True)
            if submitted:
                if login(identifier, password):
                    st.success("Welcome back!")
                    st.rerun()
                else:
                    st.error("Invalid credentials. Please try again.")

    with tab2:
        st.caption("Invitations are accepted after you sign in with the invited Gmail account.")
        if _get_query_param("invite"):
            st.info(
                "This invite token is now informational only. Sign in with the invited Gmail account and the app will list your pending invitations."
            )
        _render_google_login_button("google_login_invites")
        st.markdown("")
        st.caption("Existing local users can also sign in with their password and accept pending invites from the dashboard.")

    with tab3:
        if reset_token:
            _render_password_reset_completion(reset_token)
        else:
            st.caption("Request a reset link by username or email.")
            _render_password_reset_request()
