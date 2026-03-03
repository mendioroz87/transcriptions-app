import streamlit as st
from transcription.engine import MODELS


def _safe_page_link(path: str, label: str) -> bool:
    """Render a page link only if it exists for the current entrypoint context."""
    try:
        st.sidebar.page_link(path, label=label)
        return True
    except Exception as exc:
        if exc.__class__.__name__ in {"StreamlitPageNotFoundError", "KeyError"}:
            return False
        raise


def render_model_selector(current_model: str = "whisper", key: str = "model_selector"):
    """Render a visual model selector card grid."""
    model_keys = list(MODELS.keys())
    cols = st.columns(len(model_keys))

    selected = current_model
    for i, (mkey, minfo) in enumerate(MODELS.items()):
        with cols[i]:
            is_selected = mkey == selected
            border_color = "#4CAF50" if is_selected else "#444"
            bg_color = "#1a3a1a" if is_selected else "#1e1e1e"
            st.markdown(
                f"""
                <div style="border: 2px solid {border_color}; border-radius: 10px;
                            padding: 12px; background: {bg_color}; text-align: center;
                            margin-bottom: 8px; min-height: 110px;">
                    <div style="font-size: 28px;">{minfo['icon']}</div>
                    <div style="font-weight: bold; font-size: 13px;">{minfo['label']}</div>
                    <div style="font-size: 11px; color: #aaa; margin-top: 4px;">{minfo['description']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    selected_model = st.selectbox(
        "Select transcription model",
        options=model_keys,
        format_func=lambda k: f"{MODELS[k]['icon']} {MODELS[k]['label']}",
        index=model_keys.index(current_model) if current_model in model_keys else 0,
        key=key,
    )
    return selected_model


def render_duration_badge(seconds: float) -> str:
    if not seconds:
        return ""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h}h {m}m {s}s"
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


def render_status_badge(status: str) -> str:
    default_color = "\u26AA"
    colors = {
        "completed": "\U0001F7E2",
        "processing": "\U0001F7E1",
        "pending": default_color,
        "error": "\U0001F534",
    }
    return f"{colors.get(status, default_color)} {status.capitalize()}"


def sidebar_navigation():
    """Render sidebar navigation and logout."""
    from database.db import get_user_teams
    from utils.auth_ui import (
        ensure_active_team,
        get_active_team_id,
        get_current_user,
        logout,
        set_active_team_id,
    )

    user = get_current_user()
    if user:
        ensure_active_team()
        teams = get_user_teams(user["id"])

        st.sidebar.markdown(f"### \U0001F464 {user['username']}")
        if teams:
            team_ids = [team["id"] for team in teams]
            team_map = {team["id"]: team for team in teams}
            active_team_id = get_active_team_id()
            if active_team_id not in team_map:
                active_team_id = team_ids[0]
                set_active_team_id(active_team_id)

            selected_team_id = st.sidebar.selectbox(
                "Active Team",
                options=team_ids,
                format_func=lambda tid: team_map[tid].get("team_name") or team_map[tid]["name"],
                index=team_ids.index(active_team_id),
            )
            if selected_team_id != active_team_id:
                set_active_team_id(selected_team_id)
                st.session_state.pop("current_project", None)
                st.rerun()

            active_team = team_map[selected_team_id]
            if active_team.get("is_owner"):
                role_label = "Owner"
            elif active_team.get("can_edit_team_api_keys"):
                role_label = "Team Key Manager"
            elif active_team.get("can_edit_personal_api_keys"):
                role_label = "Personal Key Manager"
            else:
                role_label = "Member"
            st.sidebar.caption(f"Role: {role_label}")

        st.sidebar.markdown("---")
        _safe_page_link("app.py", label="\U0001F3E0 Dashboard")
        _safe_page_link("pages/projects.py", label="\U0001F4C1 My Projects")
        _safe_page_link("pages/transcribe.py", label="\U0001F3A4 Transcribe")
        _safe_page_link("pages/history.py", label="\U0001F4DC History")
        _safe_page_link("pages/settings.py", label="\u2699\ufe0f Settings")
        st.sidebar.markdown("---")
        if st.sidebar.button("\U0001F6AA Logout", use_container_width=True):
            logout()
