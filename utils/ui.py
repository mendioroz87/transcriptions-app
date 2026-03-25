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
        pass


def apply_theme_css() -> None:
    theme = get_resolved_theme()
    mobile = is_mobile_view()

    if theme == "dark":
        palette = {
            "bg": "#07101F",
            "bg_alt": "#0B1222",
            "surface": "#0F172A",
            "surface_alt": "#111C33",
            "card": "#101A2F",
            "border": "#24324A",
            "border_strong": "#314463",
            "text": "#E2E8F0",
            "muted": "#9FB0C7",
            "primary": "#60A5FA",
            "primary_strong": "#3B82F6",
            "primary_soft": "#12203A",
            "primary_ring": "rgba(96, 165, 250, 0.18)",
            "ambient_1": "rgba(96, 165, 250, 0.20)",
            "ambient_2": "rgba(45, 212, 191, 0.10)",
            "shadow": "rgba(2, 6, 23, 0.65)",
            "glow": "rgba(96, 165, 250, 0.48)",
            "success": "#22C55E",
            "warning": "#F59E0B",
            "danger": "#F87171",
        }
    else:
        palette = {
            "bg": "#F4F7FB",
            "bg_alt": "#EEF4FF",
            "surface": "#FFFFFF",
            "surface_alt": "#F8FBFF",
            "card": "#FFFFFF",
            "border": "#D8E2EE",
            "border_strong": "#BFD0E6",
            "text": "#0F172A",
            "muted": "#5B6B82",
            "primary": "#2563EB",
            "primary_strong": "#1D4ED8",
            "primary_soft": "#E9F1FF",
            "primary_ring": "rgba(37, 99, 235, 0.18)",
            "ambient_1": "rgba(37, 99, 235, 0.16)",
            "ambient_2": "rgba(14, 165, 233, 0.12)",
            "shadow": "rgba(15, 23, 42, 0.18)",
            "glow": "rgba(37, 99, 235, 0.42)",
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
                --mlabs-bg-alt: {palette['bg_alt']};
                --mlabs-surface: {palette['surface']};
                --mlabs-surface-alt: {palette['surface_alt']};
                --mlabs-card: {palette['card']};
                --mlabs-border: {palette['border']};
                --mlabs-border-strong: {palette['border_strong']};
                --mlabs-text: {palette['text']};
                --mlabs-muted: {palette['muted']};
                --mlabs-primary: {palette['primary']};
                --mlabs-primary-strong: {palette['primary_strong']};
                --mlabs-primary-soft: {palette['primary_soft']};
                --mlabs-primary-ring: {palette['primary_ring']};
                --mlabs-ambient-1: {palette['ambient_1']};
                --mlabs-ambient-2: {palette['ambient_2']};
                --mlabs-shadow: {palette['shadow']};
                --mlabs-glow: {palette['glow']};
                --mlabs-success: {palette['success']};
                --mlabs-warning: {palette['warning']};
                --mlabs-danger: {palette['danger']};
                --mlabs-radius: 22px;
            }}

            .stApp,
            [data-testid="stAppViewContainer"] {{
                background:
                    radial-gradient(circle at top left, var(--mlabs-ambient-1), transparent 34%),
                    radial-gradient(circle at top right, var(--mlabs-ambient-2), transparent 28%),
                    linear-gradient(180deg, var(--mlabs-bg) 0%, var(--mlabs-bg-alt) 100%);
                color: var(--mlabs-text);
            }}

            [data-testid="stHeader"] {{
                background: transparent;
            }}

            [data-testid="stMainBlockContainer"] {{
                padding-top: {page_padding_top};
                padding-left: {page_padding_x};
                padding-right: {page_padding_x};
                max-width: 1240px;
            }}

            [data-testid="stSidebar"] {{
                display: {sidebar_display};
                background: linear-gradient(180deg, var(--mlabs-surface) 0%, var(--mlabs-surface-alt) 100%);
                border-right: 1px solid var(--mlabs-border);
                box-shadow: 18px 0 42px -36px var(--mlabs-shadow);
            }}

            [data-testid="stSidebar"] * {{
                color: var(--mlabs-text);
            }}

            [data-testid="stSidebar"] [data-testid="stSidebarNav"] a {{
                border-radius: 14px;
                transition: background 0.16s ease, color 0.16s ease, transform 0.16s ease;
            }}

            [data-testid="stSidebar"] [data-testid="stSidebarNav"] a:hover,
            [data-testid="stSidebar"] [data-testid="stSidebarNav"] a[aria-current="page"] {{
                background: var(--mlabs-primary-soft);
                color: var(--mlabs-primary);
                transform: translateX(2px);
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
                box-shadow: 0 26px 50px -38px var(--mlabs-shadow);
            }}

            div[data-testid="stForm"] {{
                padding: 1rem;
            }}

            div[data-testid="stMetric"] {{
                padding: 0.95rem 1rem;
                background: linear-gradient(180deg, var(--mlabs-surface) 0%, var(--mlabs-surface-alt) 100%);
            }}

            div[data-testid="stMetricLabel"] p {{
                color: var(--mlabs-muted) !important;
                font-size: 0.74rem;
                font-weight: 700;
                letter-spacing: 0.05em;
                text-transform: uppercase;
            }}

            div[data-testid="stMetricValue"] {{
                color: var(--mlabs-text);
            }}

            h1, h2, h3, h4, h5, h6, p, span, label, li, div {{
                color: var(--mlabs-text);
            }}

            .stMarkdown a {{
                color: var(--mlabs-primary);
            }}

            small,
            .stCaption,
            [data-testid="stCaptionContainer"] p {{
                color: var(--mlabs-muted) !important;
            }}

            .stAlert {{
                border-radius: 16px;
                border: 1px solid var(--mlabs-border);
                box-shadow: 0 22px 44px -34px var(--mlabs-shadow);
            }}

            .stButton > button,
            .stFormSubmitButton > button,
            .stDownloadButton > button,
            .stLinkButton > a {{
                width: 100%;
                min-height: 2.95rem;
                border-radius: 16px;
                border: 1px solid var(--mlabs-border);
                padding: 0.72rem 1rem;
                font-weight: 600;
                letter-spacing: 0.01em;
                background: linear-gradient(180deg, var(--mlabs-surface-alt) 0%, var(--mlabs-surface) 100%);
                color: var(--mlabs-text) !important;
                box-shadow: 0 16px 30px -24px var(--mlabs-shadow);
                transition:
                    transform 0.14s ease,
                    box-shadow 0.14s ease,
                    border-color 0.14s ease,
                    background 0.14s ease,
                    color 0.14s ease;
            }}

            .stButton > button[kind*="primary"],
            .stFormSubmitButton > button[kind*="primary"],
            .stDownloadButton > button[kind*="primary"] {{
                background: linear-gradient(135deg, var(--mlabs-primary) 0%, var(--mlabs-primary-strong) 100%);
                color: #FFFFFF !important;
                border-color: transparent;
                box-shadow: 0 20px 36px -20px var(--mlabs-glow);
            }}

            .stButton > button:hover,
            .stFormSubmitButton > button:hover,
            .stDownloadButton > button:hover {{
                transform: translateY(-1px);
                border-color: var(--mlabs-border-strong);
                color: var(--mlabs-primary) !important;
                background: var(--mlabs-primary-soft);
                box-shadow: 0 22px 38px -24px var(--mlabs-shadow);
            }}

            .stButton > button[kind*="primary"]:hover,
            .stFormSubmitButton > button[kind*="primary"]:hover,
            .stDownloadButton > button[kind*="primary"]:hover {{
                color: #FFFFFF !important;
                border-color: transparent;
                background: linear-gradient(135deg, var(--mlabs-primary-strong) 0%, var(--mlabs-primary) 100%);
                box-shadow: 0 24px 40px -20px var(--mlabs-glow);
            }}

            .stLinkButton > a {{
                display: flex;
                align-items: center;
                justify-content: center;
                text-decoration: none;
            }}

            .stLinkButton > a:hover {{
                transform: translateY(-1px);
                border-color: var(--mlabs-border-strong);
                color: var(--mlabs-primary) !important;
                background: var(--mlabs-primary-soft);
                box-shadow: 0 22px 38px -24px var(--mlabs-shadow);
            }}

            .stButton > button:disabled,
            .stFormSubmitButton > button:disabled,
            .stDownloadButton > button:disabled {{
                background: var(--mlabs-surface-alt) !important;
                color: var(--mlabs-muted) !important;
                border-color: var(--mlabs-border) !important;
                box-shadow: none !important;
                transform: none !important;
                opacity: 0.72;
            }}

            div[data-baseweb="input"] > div,
            div[data-baseweb="base-input"] > div,
            div[data-baseweb="select"] > div,
            textarea,
            input {{
                background: var(--mlabs-surface) !important;
                color: var(--mlabs-text) !important;
                border: 1px solid var(--mlabs-border) !important;
                border-radius: 16px !important;
            }}

            div[data-baseweb="input"] > div:focus-within,
            div[data-baseweb="base-input"] > div:focus-within,
            div[data-baseweb="select"] > div:focus-within {{
                border-color: var(--mlabs-primary) !important;
                box-shadow: 0 0 0 4px var(--mlabs-primary-ring) !important;
            }}

            [data-testid="stTabs"] {{
                padding: 0.35rem;
                background: var(--mlabs-surface-alt);
            }}

            [data-testid="stTabs"] [role="tablist"] {{
                gap: 0.4rem;
            }}

            [data-testid="stTabs"] button {{
                border-radius: 12px;
            }}

            [data-testid="stTabs"] button[aria-selected="true"] {{
                background: var(--mlabs-surface);
                color: var(--mlabs-primary);
                box-shadow: 0 14px 28px -24px var(--mlabs-shadow);
            }}

            .mlabs-page-header {{
                background: linear-gradient(135deg, var(--mlabs-surface) 0%, var(--mlabs-surface-alt) 100%);
                border: 1px solid var(--mlabs-border);
                border-radius: 26px;
                padding: 1.15rem 1.35rem;
                margin-bottom: 1rem;
                display: flex;
                flex-wrap: wrap;
                gap: 1rem;
                align-items: flex-start;
                justify-content: space-between;
                box-shadow: 0 32px 56px -42px var(--mlabs-shadow);
            }}

            .mlabs-page-header h1 {{
                font-size: 2rem;
                line-height: 1.06;
                margin: 0;
                letter-spacing: -0.03em;
            }}

            .mlabs-page-header p {{
                margin: 0.45rem 0 0 0;
                color: var(--mlabs-muted);
                max-width: 42rem;
            }}

            .mlabs-page-chip-wrap {{
                display: flex;
                gap: 0.55rem;
                flex-wrap: wrap;
                justify-content: flex-end;
            }}

            .mlabs-chip {{
                background: var(--mlabs-primary-soft);
                color: var(--mlabs-primary);
                border: 1px solid var(--mlabs-border-strong);
                border-radius: 999px;
                padding: 0.45rem 0.8rem;
                font-size: 0.85rem;
                font-weight: 600;
            }}

            .mlabs-toolbar {{
                background: linear-gradient(180deg, var(--mlabs-primary-soft) 0%, var(--mlabs-surface) 100%);
                border: 1px solid var(--mlabs-border);
                border-radius: 20px;
                padding: 0.9rem 1rem;
                margin: 0.5rem 0 1rem 0;
            }}

            .mlabs-list-card {{
                background: linear-gradient(180deg, var(--mlabs-surface) 0%, var(--mlabs-surface-alt) 100%);
                border: 1px solid var(--mlabs-border);
                border-radius: 20px;
                padding: 0.95rem 1rem;
                margin-bottom: 0.7rem;
                box-shadow: 0 20px 38px -34px var(--mlabs-shadow);
            }}

            .mlabs-section-kicker {{
                color: var(--mlabs-primary);
                font-size: 0.76rem;
                font-weight: 700;
                letter-spacing: 0.08em;
                text-transform: uppercase;
                margin-bottom: 0.55rem;
            }}

            .mlabs-feature-stack {{
                display: flex;
                flex-direction: column;
                gap: 0.8rem;
            }}

            .mlabs-feature-item {{
                display: grid;
                grid-template-columns: 46px 1fr;
                gap: 0.85rem;
                align-items: start;
                padding: 0.95rem 1rem;
                border-radius: 20px;
                border: 1px solid var(--mlabs-border);
                background: linear-gradient(180deg, var(--mlabs-surface) 0%, var(--mlabs-surface-alt) 100%);
                box-shadow: 0 18px 32px -30px var(--mlabs-shadow);
            }}

            .mlabs-feature-icon {{
                width: 46px;
                height: 46px;
                border-radius: 14px;
                display: flex;
                align-items: center;
                justify-content: center;
                background: linear-gradient(135deg, var(--mlabs-primary-soft) 0%, var(--mlabs-surface) 100%);
                color: var(--mlabs-primary);
                font-size: 1rem;
                font-weight: 700;
            }}

            .mlabs-feature-body strong {{
                display: block;
                margin-bottom: 0.18rem;
            }}

            .mlabs-feature-body p {{
                margin: 0;
                color: var(--mlabs-muted);
            }}

            .mlabs-auth-panel {{
                background: linear-gradient(180deg, var(--mlabs-surface) 0%, var(--mlabs-surface-alt) 100%);
                border: 1px solid var(--mlabs-border);
                border-radius: 24px;
                padding: 1.1rem;
                box-shadow: 0 28px 48px -40px var(--mlabs-shadow);
            }}

            .mlabs-auth-panel h3 {{
                margin: 0;
            }}

            .mlabs-auth-panel p {{
                margin: 0.35rem 0 0 0;
                color: var(--mlabs-muted);
            }}

            @media (max-width: {MOBILE_BREAKPOINT}px) {{
                .mlabs-page-header {{
                    padding: 1rem;
                }}

                .mlabs-page-header h1 {{
                    font-size: 1.55rem;
                }}

                .mlabs-page-chip-wrap {{
                    justify-content: flex-start;
                }}

                .mlabs-feature-item {{
                    grid-template-columns: 40px 1fr;
                    padding: 0.9rem;
                }}

                .mlabs-feature-icon {{
                    width: 40px;
                    height: 40px;
                    border-radius: 12px;
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
    theme_label = f"Theme: {theme_mode}" if theme_mode != "System" else f"Theme: System / {resolved}"
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
