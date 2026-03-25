from __future__ import annotations

from html import escape

import streamlit as st
import streamlit.components.v1 as components

MOBILE_BREAKPOINT = 820
VALID_THEME_MODES = {"light", "dark", "system"}


def _query_param_value(name: str, default: str = "") -> str:
    raw = st.query_params.get(name, default)
    if isinstance(raw, list):
        raw = raw[0] if raw else default
    return str(raw or default)


def inject_client_context() -> None:
    """Detect device width and system theme in the browser and persist them in query params."""
    components.html(
        f"""
        <script>
        (() => {{
            const parentWindow = window.parent;
            if (!parentWindow || !parentWindow.location) return;

            const params = new URLSearchParams(parentWindow.location.search);
            const nextDevice = parentWindow.matchMedia('(max-width: {MOBILE_BREAKPOINT}px)').matches
                ? 'mobile'
                : 'desktop';
            const nextSystemTheme = parentWindow.matchMedia('(prefers-color-scheme: dark)').matches
                ? 'dark'
                : 'light';

            let changed = false;
            if (params.get('device') !== nextDevice) {{
                params.set('device', nextDevice);
                changed = true;
            }}
            if (params.get('system_theme') !== nextSystemTheme) {{
                params.set('system_theme', nextSystemTheme);
                changed = true;
            }}

            if (changed) {{
                const nextUrl = `${{parentWindow.location.pathname}}?${{params.toString()}}`;
                parentWindow.location.replace(nextUrl);
            }}
        }})();
        </script>
        """,
        height=0,
    )


def get_device_type() -> str:
    return "mobile" if _query_param_value("device", "desktop").lower() == "mobile" else "desktop"


def is_mobile_view() -> bool:
    return get_device_type() == "mobile"


def get_theme_mode() -> str:
    current = _query_param_value("theme_mode", st.session_state.get("ui_theme_mode", "system")).lower()
    if current not in VALID_THEME_MODES:
        current = "system"
    st.session_state["ui_theme_mode"] = current
    return current


def get_system_theme() -> str:
    return "dark" if _query_param_value("system_theme", "light").lower() == "dark" else "light"


def get_resolved_theme() -> str:
    theme_mode = get_theme_mode()
    if theme_mode == "system":
        return get_system_theme()
    return theme_mode


def set_theme_mode(theme_mode: str) -> None:
    next_mode = theme_mode.lower().strip()
    if next_mode not in VALID_THEME_MODES:
        next_mode = "system"
    st.session_state["ui_theme_mode"] = next_mode
    try:
        st.query_params["theme_mode"] = next_mode
    except Exception:
        # Some Streamlit runtimes expose query params as a read-only view.
        pass


def apply_theme_css() -> None:
    theme = get_resolved_theme()
    mobile = is_mobile_view()

    if theme == "dark":
        palette = {
            "bg": "#0F172A",
            "surface": "#111827",
            "card": "#1E293B",
            "border": "#334155",
            "text": "#E2E8F0",
            "muted": "#94A3B8",
            "primary": "#60A5FA",
            "primary_soft": "#172554",
            "success": "#22C55E",
            "warning": "#F59E0B",
            "danger": "#F87171",
        }
    else:
        palette = {
            "bg": "#F8FAFC",
            "surface": "#FFFFFF",
            "card": "#FFFFFF",
            "border": "#E2E8F0",
            "text": "#0F172A",
            "muted": "#475569",
            "primary": "#2563EB",
            "primary_soft": "#EFF6FF",
            "success": "#16A34A",
            "warning": "#D97706",
            "danger": "#DC2626",
        }

    sidebar_display = "none" if mobile else "block"
    page_padding_top = "1.2rem" if mobile else "1.8rem"
    page_padding_x = "0.8rem" if mobile else "1.25rem"

    st.markdown(
        f"""
        <style>
            :root {{
                --mlabs-bg: {palette['bg']};
                --mlabs-surface: {palette['surface']};
                --mlabs-card: {palette['card']};
                --mlabs-border: {palette['border']};
                --mlabs-text: {palette['text']};
                --mlabs-muted: {palette['muted']};
                --mlabs-primary: {palette['primary']};
                --mlabs-primary-soft: {palette['primary_soft']};
                --mlabs-success: {palette['success']};
                --mlabs-warning: {palette['warning']};
                --mlabs-danger: {palette['danger']};
                --mlabs-radius: 18px;
            }}

            .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {{
                background: var(--mlabs-bg);
                color: var(--mlabs-text);
            }}

            [data-testid="stMainBlockContainer"] {{
                padding-top: {page_padding_top};
                padding-left: {page_padding_x};
                padding-right: {page_padding_x};
                max-width: 1200px;
            }}

            [data-testid="stSidebar"] {{
                display: {sidebar_display};
                background: var(--mlabs-surface);
                border-right: 1px solid var(--mlabs-border);
            }}

            [data-testid="stSidebar"] * {{
                color: var(--mlabs-text);
            }}

            [data-testid="stVerticalBlockBorderWrapper"],
            div[data-testid="stForm"],
            div[data-testid="stExpander"],
            div[data-testid="stMetric"],
            [data-testid="stPopover"] > div,
            [data-testid="stTabs"] {{
                background: var(--mlabs-card);
                border: 1px solid var(--mlabs-border);
                border-radius: var(--mlabs-radius);
            }}

            div[data-testid="stForm"] {{
                padding: 1rem;
            }}

            div[data-testid="stMetric"] {{
                padding: 0.8rem 1rem;
            }}

            div[data-testid="stMetricValue"] {{
                color: var(--mlabs-text);
            }}

            h1, h2, h3, h4, h5, h6, p, span, label, li, div {{
                color: var(--mlabs-text);
            }}

            small, .stCaption, [data-testid="stCaptionContainer"] p {{
                color: var(--mlabs-muted) !important;
            }}

            .stAlert {{
                border-radius: 16px;
            }}

            .stButton > button,
            .stDownloadButton > button,
            [data-testid="baseButton-secondary"],
            [data-testid="baseButton-primary"] {{
                border-radius: 14px;
                border: 1px solid var(--mlabs-border);
                min-height: 2.7rem;
                font-weight: 600;
            }}

            .stButton > button[kind="primary"],
            .stDownloadButton > button[kind="primary"] {{
                background: var(--mlabs-primary);
                color: #ffffff;
                border-color: var(--mlabs-primary);
            }}

            .stButton > button:hover,
            .stDownloadButton > button:hover {{
                border-color: var(--mlabs-primary);
                color: var(--mlabs-primary);
            }}

            .stButton > button[kind="primary"]:hover,
            .stDownloadButton > button[kind="primary"]:hover {{
                color: #ffffff;
            }}

            div[data-baseweb="input"] > div,
            div[data-baseweb="select"] > div,
            textarea,
            input {{
                background: var(--mlabs-surface) !important;
                color: var(--mlabs-text) !important;
                border-color: var(--mlabs-border) !important;
                border-radius: 14px !important;
            }}

            [data-testid="stTabs"] button {{
                border-radius: 12px;
            }}

            [data-testid="stTabs"] button[aria-selected="true"] {{
                color: var(--mlabs-primary);
            }}

            .mlabs-page-header {{
                background: var(--mlabs-surface);
                border: 1px solid var(--mlabs-border);
                border-radius: 22px;
                padding: 1rem 1.2rem;
                margin-bottom: 1rem;
                display: flex;
                flex-wrap: wrap;
                gap: 0.8rem;
                align-items: flex-start;
                justify-content: space-between;
            }}

            .mlabs-page-header h1 {{
                font-size: 1.9rem;
                line-height: 1.1;
                margin: 0;
            }}

            .mlabs-page-header p {{
                margin: 0.35rem 0 0 0;
                color: var(--mlabs-muted);
            }}

            .mlabs-page-chip-wrap {{
                display: flex;
                gap: 0.5rem;
                flex-wrap: wrap;
                justify-content: flex-end;
            }}

            .mlabs-chip {{
                background: var(--mlabs-primary-soft);
                color: var(--mlabs-primary);
                border: 1px solid var(--mlabs-border);
                border-radius: 999px;
                padding: 0.4rem 0.7rem;
                font-size: 0.85rem;
                font-weight: 600;
            }}

            .mlabs-toolbar {{
                background: var(--mlabs-primary-soft);
                border: 1px solid var(--mlabs-border);
                border-radius: 18px;
                padding: 0.9rem 1rem;
                margin: 0.5rem 0 1rem 0;
            }}

            .mlabs-list-card {{
                background: var(--mlabs-surface);
                border: 1px solid var(--mlabs-border);
                border-radius: 18px;
                padding: 0.85rem 1rem;
                margin-bottom: 0.7rem;
            }}

            @media (max-width: {MOBILE_BREAKPOINT}px) {{
                .mlabs-page-header {{
                    padding: 0.95rem 1rem;
                }}
                .mlabs-page-header h1 {{
                    font-size: 1.55rem;
                }}
                .mlabs-page-chip-wrap {{
                    justify-content: flex-start;
                }}
                [data-testid="stMainBlockContainer"] {{
                    padding-bottom: 6rem;
                }}
            }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def init_ui() -> None:
    inject_client_context()
    apply_theme_css()


def render_page_header(title: str, caption: str) -> None:
    device_label = "Mobile view" if is_mobile_view() else "Desktop view"
    theme_mode = get_theme_mode().capitalize()
    resolved = get_resolved_theme().capitalize()
    theme_label = f"Theme: {theme_mode}" if theme_mode != "System" else f"Theme: System · {resolved}"
    st.markdown(
        f"""
        <div class="mlabs-page-header">
            <div>
                <h1>{escape(title)}</h1>
                <p>{escape(caption)}</p>
            </div>
            <div class="mlabs-page-chip-wrap">
                <span class="mlabs-chip">{escape(device_label)}</span>
                <span class="mlabs-chip">{escape(theme_label)}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
