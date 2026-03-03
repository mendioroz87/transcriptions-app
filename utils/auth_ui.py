import streamlit as st

from database.db import (
    accept_team_invitation,
    authenticate_user,
    get_user_default_team_id,
    get_user_team,
    get_user_teams,
    reset_user_password,
)


def is_logged_in() -> bool:
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
    user = get_current_user()
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
        ensure_active_team()
        return True
    return False


def logout():
    for key in ["user", "current_project", "active_team_id"]:
        if key in st.session_state:
            del st.session_state[key]
    st.rerun()


def require_login():
    """Call at the top of any page that requires authentication."""
    if not is_logged_in():
        hide_sidebar_for_logged_out()
        st.warning("Please log in to access this page.")
        st.stop()
    ensure_active_team()


def render_login_form():
    """Render sign-in, invite acceptance, and password-reset forms."""
    tab1, tab2, tab3 = st.tabs(["Sign In", "Accept Invite", "Reset Password"])

    with tab1:
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
        st.caption("New accounts can only be created from a valid invite token.")
        with st.form("accept_invite_form"):
            token = st.text_input("Invite Token")
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            username = st.text_input("Username (required only if this email has no account)")
            submitted = st.form_submit_button("Accept Invite", use_container_width=True)
            if submitted:
                if not token.strip():
                    st.error("Invite token is required.")
                elif not email.strip():
                    st.error("Email is required.")
                elif not password:
                    st.error("Password is required.")
                else:
                    success, msg, payload = accept_team_invitation(
                        invite_token=token.strip(),
                        email=email.strip(),
                        password=password,
                        username=username.strip() or None,
                    )
                    if success:
                        st.session_state["user"] = payload["user"]
                        set_active_team_id(payload["team_id"])
                        st.session_state.pop("current_project", None)

                        team = get_user_team(payload["user"]["id"], payload["team_id"])
                        team_name = team["team_name"] if team else "team"
                        st.success(f"{msg} Joined {team_name}.")
                        st.rerun()
                    else:
                        st.error(msg)

    with tab3:
        with st.form("reset_password_form"):
            identifier = st.text_input("Username or Email")
            email = st.text_input("Registered Email")
            new_password = st.text_input("New Password", type="password")
            confirm = st.text_input("Confirm New Password", type="password")
            submitted = st.form_submit_button("Reset Password", use_container_width=True)
            if submitted:
                if not identifier.strip() or not email.strip():
                    st.error("Username/email and registered email are required.")
                elif new_password != confirm:
                    st.error("Passwords do not match.")
                elif len(new_password) < 6:
                    st.error("Password must be at least 6 characters.")
                else:
                    success, msg = reset_user_password(
                        identifier.strip(),
                        email.strip(),
                        new_password,
                    )
                    if success:
                        st.success(msg)
                    else:
                        st.error(msg)
