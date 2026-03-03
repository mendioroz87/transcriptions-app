import streamlit as st
from database.db import authenticate_user, create_user, reset_user_password


def is_logged_in() -> bool:
    return st.session_state.get("user") is not None


def get_current_user() -> dict:
    return st.session_state.get("user")


def login(username_or_email: str, password: str) -> bool:
    user = authenticate_user(username_or_email, password)
    if user:
        st.session_state["user"] = user
        return True
    return False


def logout():
    for key in ["user", "current_project"]:
        if key in st.session_state:
            del st.session_state[key]
    st.rerun()


def require_login():
    """Call at the top of any page that requires authentication."""
    if not is_logged_in():
        st.warning("Please log in to access this page.")
        st.stop()


def render_login_form():
    """Render sign-in, registration, and password-reset forms."""
    tab1, tab2, tab3 = st.tabs(["Sign In", "Create Account", "Reset Password"])

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
        with st.form("register_form"):
            username = st.text_input("Username")
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            confirm = st.text_input("Confirm Password", type="password")
            submitted = st.form_submit_button("Create Account", use_container_width=True)
            if submitted:
                if password != confirm:
                    st.error("Passwords do not match.")
                elif len(password) < 6:
                    st.error("Password must be at least 6 characters.")
                else:
                    success, msg = create_user(username, email, password)
                    if success:
                        st.success(msg + " Please sign in.")
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
