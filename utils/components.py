import streamlit as st

from transcription.engine import MODELS
from utils.ui import is_mobile_view


NAV_ITEMS = [
    ("overview", "app.py", "🏠 Overview"),
    ("projects", "pages/projects.py", "📁 Projects"),
    ("transcribe", "pages/transcribe.py", "🎙️ Transcribe"),
    ("history", "pages/history.py", "📜 History"),
    ("settings", "pages/settings.py", "⚙️ Settings"),
]


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
    default_color = "⚪"
    colors = {
        "completed": "🟢",
        "processing": "🟡",
        "pending": default_color,
        "error": "🔴",
    }
    return f"{colors.get(status, default_color)} {status.capitalize()}"


def _role_label(active_team: dict) -> str:
    if active_team.get("is_owner"):
        return "Owner"
    if active_team.get("can_edit_team_api_keys"):
        return "Team Key Manager"
    if active_team.get("can_edit_personal_api_keys"):
        return "Personal Key Manager"
    return "Member"


def _render_mobile_navigation(user: dict, teams: list[dict], current: str) -> None:
    from utils.auth_ui import get_active_team_id, logout, set_active_team_id

    with st.container(border=True):
        top_left, top_right = st.columns([1.8, 1])
        with top_left:
            st.markdown(f"**{user['username']}**")
            st.caption(user.get("email", ""))
        with top_right:
            if st.button("Logout", key="mobile_logout_btn", use_container_width=True):
                logout()

        if teams:
            team_ids = [team["id"] for team in teams]
            team_map = {team["id"]: team for team in teams}
            active_team_id = get_active_team_id()
            if active_team_id not in team_map:
                active_team_id = team_ids[0]
                set_active_team_id(active_team_id)
            selected_team_id = st.selectbox(
                "Active Team",
                options=team_ids,
                format_func=lambda tid: team_map[tid].get("team_name") or team_map[tid]["name"],
                index=team_ids.index(active_team_id),
                key="mobile_active_team_selector",
            )
            active_team = team_map[selected_team_id]
            st.caption(f"Role: {_role_label(active_team)}")
            if selected_team_id != active_team_id:
                set_active_team_id(selected_team_id)
                st.session_state.pop("current_project", None)
                st.rerun()

        row1 = st.columns(2)
        for col, item in zip(row1, NAV_ITEMS[:2]):
            item_key, item_path, item_label = item
            with col:
                if st.button(
                    item_label,
                    key=f"mobile_nav_{item_key}",
                    use_container_width=True,
                    type="primary" if item_key == current else "secondary",
                ):
                    st.switch_page(item_path)

        row2 = st.columns(3)
        for col, item in zip(row2, NAV_ITEMS[2:]):
            item_key, item_path, item_label = item
            with col:
                if st.button(
                    item_label,
                    key=f"mobile_nav_{item_key}",
                    use_container_width=True,
                    type="primary" if item_key == current else "secondary",
                ):
                    st.switch_page(item_path)


def sidebar_navigation(current: str = "overview"):
    """Render desktop sidebar or mobile top navigation based on the detected device."""
    from database.db import get_user_teams
    from utils.auth_ui import (
        ensure_active_team,
        get_active_team_id,
        get_current_user,
        logout,
        set_active_team_id,
    )

    user = get_current_user()
    if not user:
        return

    ensure_active_team()
    teams = get_user_teams(user["id"])
    if is_mobile_view():
        _render_mobile_navigation(user, teams, current)
        return

    st.sidebar.markdown(f"### 👤 {user['username']}")
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
        st.sidebar.caption(f"Role: {_role_label(active_team)}")

    st.sidebar.markdown("---")
    for item_key, item_path, item_label in NAV_ITEMS:
        label = f"➡️ {item_label}" if item_key == current else item_label
        _safe_page_link(item_path, label=label)
    st.sidebar.markdown("---")
    if st.sidebar.button("🚪 Logout", use_container_width=True):
        logout()
