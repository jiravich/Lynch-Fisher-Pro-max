"""Minimalist institutional design system, CSS overrides, HTML components, and Plotly builders.

Aesthetic: Linear / Koyfin / Stripe / Swiss editorial typography.
Strict anti-AI design rules: zero emojis, zero glowing shadows, zero glassmorphism,
zero neon gradients, crisp 1px hairlines, and tabular-nums monospace figures.
"""

from __future__ import annotations

import html as _html_lib
from typing import Any
from urllib.parse import quote_plus

import plotly.graph_objects as go
import streamlit as st

PALETTE: dict[str, str] = {
    "bg": "#0A0C0F",
    "surface": "#111419",
    "hover": "#161B22",
    "hairline": "#1F242D",
    "chart_grid": "#1A1F26",
    "text_primary": "#F1F5F9",
    "text_muted": "#8B949E",
    "emerald": "#10B981",
    "amber": "#D97706",
    "crimson": "#EF4444",
    "hurdle": "#30363D",
}

FONT_UI = "'IBM Plex Sans Thai', -apple-system, BlinkMacSystemFont, sans-serif"
FONT_MONO = "'IBM Plex Mono', 'JetBrains Mono', ui-monospace, monospace"

PLOTLY_CONFIG: dict[str, Any] = {
    "displayModeBar": False,
    "responsive": True,
    "scrollZoom": False,
}

# Crisp 1.5px stroke monochrome SVG icons (zero emojis).
SVG_ICONS: dict[str, str] = {
    "alert": (
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="12" cy="12" r="9"></circle>'
        '<line x1="12" y1="8" x2="12" y2="12"></line>'
        '<line x1="12" y1="16" x2="12.01" y2="16"></line>'
        "</svg>"
    ),
    "warning": (
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>'
        '<line x1="12" y1="9" x2="12" y2="13"></line>'
        '<line x1="12" y1="17" x2="12.01" y2="17"></line>'
        "</svg>"
    ),
    "external_link": (
        '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>'
        '<polyline points="15 3 21 3 21 9"></polyline>'
        '<line x1="10" y1="14" x2="21" y2="3"></line>'
        "</svg>"
    ),
    "bookmark": (
        '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path>'
        "</svg>"
    ),
    "check": (
        '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">'
        '<polyline points="20 6 9 17 4 12"></polyline>'
        "</svg>"
    ),
    "sliders": (
        '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">'
        '<line x1="4" y1="21" x2="4" y2="14"></line>'
        '<line x1="4" y1="10" x2="4" y2="3"></line>'
        '<line x1="12" y1="21" x2="12" y2="12"></line>'
        '<line x1="12" y1="8" x2="12" y2="3"></line>'
        '<line x1="20" y1="21" x2="20" y2="16"></line>'
        '<line x1="20" y1="12" x2="20" y2="3"></line>'
        '<line x1="1" y1="14" x2="7" y2="14"></line>'
        '<line x1="9" y1="8" x2="15" y2="8"></line>'
        '<line x1="17" y1="16" x2="23" y2="16"></line>'
        "</svg>"
    ),
}


def _html(block: str) -> str:
    """Strip leading indentation so Markdown never treats multiline HTML as code."""
    return "\n".join(line.lstrip() for line in block.splitlines()).strip()


def _esc(val: Any) -> str:
    return _html_lib.escape(str(val or ""))


def signal_color(signal: str) -> str:
    if signal == "green":
        return PALETTE["emerald"]
    if signal == "amber":
        return PALETTE["amber"]
    if signal == "red":
        return PALETTE["crimson"]
    return PALETTE["text_muted"]


def format_metric_value(value: float | None, fmt_type: str) -> str:
    if value is None:
        return "N/A"
    if fmt_type == "percent":
        return f"{value * 100:.1f}%"
    if fmt_type == "spread_pct":
        return f"{value * 100:+.1f}%"
    if fmt_type == "consistency":
        return f"{value * 100:.0f}%"
    if fmt_type == "pp_per_year":
        return f"{value:+.2f} pp/yr"
    if fmt_type == "ratio_x":
        return f"{value:.2f}x"
    return f"{value:.2f}"


def format_threshold_value(value: float, fmt_type: str) -> str:
    if fmt_type in {"percent", "spread_pct", "consistency"}:
        return f"{value * 100:.0f}%"
    if fmt_type == "pp_per_year":
        return f"{value:+.1f} pp"
    if fmt_type == "ratio_x":
        return f"{value:.2f}x"
    return f"{value:.2f}"


def inject_theme_css() -> None:
    """Inject obsidian institutional CSS overrides and Google Fonts."""
    css = _html(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans+Thai:wght@400;500;600&display=swap');

        :root {{
            --bg-canvas: {PALETTE['bg']};
            --bg-surface: {PALETTE['surface']};
            --bg-hover: {PALETTE['hover']};
            --border-hairline: {PALETTE['hairline']};
            --text-primary: {PALETTE['text_primary']};
            --text-muted: {PALETTE['text_muted']};
            --emerald: {PALETTE['emerald']};
            --amber: {PALETTE['amber']};
            --crimson: {PALETTE['crimson']};
        }}

        /* Hide default Streamlit branding, decoration bar, menu, and footer */
        #MainMenu,
        footer,
        [data-testid="stDecoration"],
        [data-testid="stToolbar"],
        [data-testid="stStatusWidget"],
        .stAppDeployButton {{
            display: none !important;
            visibility: hidden !important;
        }}

        header[data-testid="stHeader"] {{
            background: transparent !important;
            height: 2.25rem !important;
            border: none !important;
        }}

        /* Canvas and global typography */
        html, body, .stApp, [data-testid="stAppViewContainer"] {{
            background-color: var(--bg-canvas) !important;
            color: var(--text-primary) !important;
            font-family: {FONT_UI} !important;
            -webkit-font-smoothing: antialiased;
        }}

        .block-container {{
            max-width: 1360px !important;
            padding: 1.1rem 2rem 3rem 2rem !important;
        }}

        /* Global shadow kill & flat hairline discipline */
        *, *::before, *::after {{
            box-shadow: none !important;
        }}

        /* Enforce tabular monospace numbers across inputs, metrics, tables, and numeric classes */
        .mono, .num, .hero-num, .metric-val, .peer-table td.num, .peer-table th.num,
        [data-testid="stMetricValue"], [data-testid="stMetricDelta"] {{
            font-family: {FONT_MONO} !important;
            font-variant-numeric: tabular-nums !important;
            font-feature-settings: "tnum" 1 !important;
        }}

        /* Sidebar styling */
        section[data-testid="stSidebar"] {{
            background-color: var(--bg-canvas) !important;
            border-right: 1px solid var(--border-hairline) !important;
        }}
        section[data-testid="stSidebar"] > div {{
            padding-top: 1.25rem !important;
        }}

        /* Keep multi-column editorial blocks top-aligned cleanly */
        [data-testid="stHorizontalBlock"] {{
            align-items: flex-start;
        }}

        /* Inputs, Selectboxes, Textareas */
        .stTextInput input, .stTextArea textarea {{
            background-color: var(--bg-surface) !important;
            color: var(--text-primary) !important;
            border: 1px solid var(--border-hairline) !important;
            border-radius: 6px !important;
            font-size: 0.875rem !important;
        }}
        .stTextInput input {{
            font-family: {FONT_MONO} !important;
            font-variant-numeric: tabular-nums !important;
        }}
        .stTextInput input:focus, .stTextArea textarea:focus {{
            border-color: #3B4454 !important;
            outline: none !important;
        }}
        div[data-baseweb="select"] > div {{
            background-color: var(--bg-surface) !important;
            border: 1px solid var(--border-hairline) !important;
            border-radius: 6px !important;
            color: var(--text-primary) !important;
            font-size: 0.85rem !important;
        }}

        /* Minimalist flat buttons (including form submit primary buttons) */
        .stButton > button,
        .stFormSubmitButton > button {{
            background-color: var(--bg-surface) !important;
            color: var(--text-primary) !important;
            border: 1px solid var(--border-hairline) !important;
            border-radius: 6px !important;
            font-family: {FONT_UI} !important;
            font-size: 0.82rem !important;
            font-weight: 500 !important;
            padding: 0.38rem 0.75rem !important;
            transition: background-color 120ms ease, border-color 120ms ease;
        }}
        .stButton > button:hover,
        .stFormSubmitButton > button:hover {{
            background-color: var(--bg-hover) !important;
            border-color: #303846 !important;
        }}
        .stButton > button[kind="primary"],
        .stFormSubmitButton > button[kind="primary"],
        .stFormSubmitButton > button[kind="primaryFormSubmit"],
        button[data-testid="stBaseButton-primary"],
        button[data-testid="stBaseButton-primaryFormSubmit"] {{
            background-color: #F1F5F9 !important;
            color: #0A0C0F !important;
            border-color: #F1F5F9 !important;
            font-weight: 600 !important;
        }}
        .stButton > button[kind="primary"] *,
        .stFormSubmitButton > button[kind="primary"] *,
        .stFormSubmitButton > button[kind="primaryFormSubmit"] *,
        button[data-testid="stBaseButton-primary"] *,
        button[data-testid="stBaseButton-primaryFormSubmit"] * {{
            color: #0A0C0F !important;
        }}
        .stButton > button[kind="primary"]:hover,
        .stFormSubmitButton > button[kind="primary"]:hover,
        .stFormSubmitButton > button[kind="primaryFormSubmit"]:hover,
        button[data-testid="stBaseButton-primary"]:hover,
        button[data-testid="stBaseButton-primaryFormSubmit"]:hover {{
            background-color: #E2E8F0 !important;
            color: #0A0C0F !important;
        }}

        /* Ultra-clean circular ? popover trigger buttons (no chevron) */
        [data-testid="stPopover"] {{
            display: flex;
            justify-content: flex-end;
            padding-top: 0.42rem;
        }}
        [data-testid="stPopover"] button {{
            width: 22px !important;
            min-width: 22px !important;
            max-width: 22px !important;
            height: 22px !important;
            min-height: 22px !important;
            padding: 0 !important;
            border-radius: 999px !important;
            background: transparent !important;
            border: 1px solid var(--border-hairline) !important;
            color: var(--text-muted) !important;
            font-family: {FONT_MONO} !important;
            font-size: 11px !important;
            font-weight: 500 !important;
            line-height: 1 !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            gap: 0 !important;
        }}
        [data-testid="stPopover"] button:hover {{
            background: var(--bg-hover) !important;
            color: var(--text-primary) !important;
            border-color: #384152 !important;
        }}
        [data-testid="stPopover"] button svg,
        [data-testid="stPopover"] button [data-testid="stIconMaterial"],
        [data-testid="stPopover"] button span[class*="Icon"] {{
            display: none !important;
            width: 0 !important;
            height: 0 !important;
            overflow: hidden !important;
        }}
        div[data-testid="stPopoverBody"] {{
            background-color: var(--bg-surface) !important;
            border: 1px solid var(--border-hairline) !important;
            border-radius: 8px !important;
            color: var(--text-primary) !important;
            max-width: 340px !important;
        }}

        /* Hairline micro-drawer expanders */
        [data-testid="stExpander"] {{
            background: transparent !important;
            border: none !important;
            border-top: 1px solid var(--border-hairline) !important;
            border-radius: 0 !important;
            margin-top: 0.35rem !important;
        }}
        [data-testid="stExpander"] details {{
            border: none !important;
            background: transparent !important;
        }}
        [data-testid="stExpander"] summary {{
            padding: 0.45rem 0 !important;
            color: var(--text-muted) !important;
            font-size: 0.78rem !important;
        }}
        [data-testid="stExpander"] summary:hover {{
            color: var(--text-primary) !important;
        }}

        /* Linear-style hairline tabs */
        .stTabs [data-baseweb="tab-list"] {{
            gap: 1.25rem;
            border-bottom: 1px solid var(--border-hairline);
            background: transparent !important;
        }}
        .stTabs [data-baseweb="tab"] {{
            background: transparent !important;
            color: var(--text-muted) !important;
            padding: 0.45rem 0 !important;
            font-size: 0.82rem !important;
            font-weight: 500 !important;
            border-bottom: 2px solid transparent !important;
        }}
        .stTabs [aria-selected="true"] {{
            color: var(--text-primary) !important;
            border-bottom: 2px solid var(--text-primary) !important;
        }}
        .stTabs [data-baseweb="tab-highlight"],
        .stTabs [data-baseweb="tab-border"] {{
            display: none !important;
        }}

        /* Segmented / Radio compactness for Fisher 0/1/2 scoring */
        [data-testid="stRadio"] > div {{
            gap: 0.5rem !important;
        }}
        [data-testid="stSegmentedControl"] {{
            background: transparent !important;
        }}

        /* Custom Editorial Component Classes */
        .sidebar-brand {{
            padding-bottom: 0.9rem;
            margin-bottom: 0.9rem;
            border-bottom: 1px solid var(--border-hairline);
        }}
        .sidebar-brand-title {{
            font-family: {FONT_MONO};
            font-size: 0.82rem;
            font-weight: 600;
            letter-spacing: 0.08em;
            color: var(--text-primary);
        }}
        .sidebar-brand-sub {{
            font-size: 0.72rem;
            color: var(--text-muted);
            margin-top: 2px;
        }}

        .hero-bar {{
            display: flex;
            flex-wrap: wrap;
            justify-content: space-between;
            align-items: center;
            gap: 1rem;
            padding: 0.25rem 0 0.95rem 0;
            border-bottom: 1px solid var(--border-hairline);
        }}
        .hero-left {{
            display: flex;
            flex-direction: column;
            gap: 0.28rem;
            flex: 1 1 280px;
            min-width: 260px;
        }}
        .hero-identity {{
            display: flex;
            align-items: baseline;
            flex-wrap: wrap;
            gap: 0.6rem;
        }}
        .hero-ticker {{
            font-family: {FONT_MONO};
            font-size: 1.55rem;
            font-weight: 600;
            letter-spacing: -0.02em;
            color: var(--text-primary);
            line-height: 1.1;
        }}
        .hero-name {{
            font-size: 0.92rem;
            font-weight: 500;
            color: var(--text-primary);
        }}
        .hero-meta {{
            font-size: 0.76rem;
            color: var(--text-muted);
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 0.42rem;
        }}
        .hero-price-row {{
            display: flex;
            align-items: baseline;
            gap: 0.65rem;
            margin-top: 0.1rem;
        }}
        .hero-price {{
            font-family: {FONT_MONO};
            font-variant-numeric: tabular-nums;
            font-size: 1.38rem;
            font-weight: 600;
            color: var(--text-primary);
        }}
        .hero-change {{
            font-family: {FONT_MONO};
            font-variant-numeric: tabular-nums;
            font-size: 0.82rem;
            font-weight: 500;
        }}
        .hero-right {{
            display: flex;
            align-items: stretch;
            flex-wrap: nowrap;
            flex: 0 0 auto;
            gap: 0;
        }}
        .hero-kpi {{
            padding: 0.1rem 1.0rem;
            border-left: 1px solid var(--border-hairline);
            display: flex;
            flex-direction: column;
            justify-content: center;
            gap: 0.18rem;
            white-space: nowrap;
        }}
        .hero-kpi:first-child {{
            border-left: none;
            padding-left: 0;
        }}
        .hero-kpi:last-child {{
            padding-right: 0;
        }}
        .hero-kpi-label {{
            font-size: 0.7rem;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: var(--text-muted);
        }}
        .hero-kpi-val {{
            font-family: {FONT_MONO};
            font-variant-numeric: tabular-nums;
            font-size: 1.25rem;
            font-weight: 600;
            line-height: 1.15;
        }}
        .hero-kpi-sub {{
            font-family: {FONT_MONO};
            font-variant-numeric: tabular-nums;
            font-size: 0.72rem;
            color: var(--text-muted);
        }}

        .pill-badge {{
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.18rem 0.55rem;
            border: 1px solid var(--border-hairline);
            border-radius: 4px;
            background: var(--bg-surface);
            font-size: 0.76rem;
            font-weight: 500;
            color: var(--text-primary);
            white-space: nowrap;
        }}
        .pill-subtle {{
            display: inline-flex;
            align-items: center;
            padding: 0.12rem 0.42rem;
            border: 1px solid var(--border-hairline);
            border-radius: 4px;
            font-family: {FONT_MONO};
            font-size: 0.68rem;
            color: var(--text-muted);
            white-space: nowrap;
        }}

        .alert-strip {{
            display: flex;
            flex-direction: column;
            gap: 0.35rem;
            margin-top: 0.7rem;
        }}
        .alert-item {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.75rem;
            padding: 0.48rem 0.85rem;
            border-radius: 0 4px 4px 0;
            font-size: 0.8rem;
        }}
        .alert-hard {{
            background: rgba(239, 68, 68, 0.06);
            border-left: 3px solid var(--crimson);
            border-top: 1px solid rgba(239, 68, 68, 0.16);
            border-right: 1px solid rgba(239, 68, 68, 0.16);
            border-bottom: 1px solid rgba(239, 68, 68, 0.16);
        }}
        .alert-warning {{
            background: rgba(217, 119, 6, 0.06);
            border-left: 3px solid var(--amber);
            border-top: 1px solid rgba(217, 119, 6, 0.18);
            border-right: 1px solid rgba(217, 119, 6, 0.18);
            border-bottom: 1px solid rgba(217, 119, 6, 0.18);
        }}
        .alert-left {{
            display: flex;
            align-items: center;
            gap: 0.55rem;
            flex-wrap: wrap;
        }}

        .sec-header {{
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            gap: 0.75rem;
            padding: 1.15rem 0 0.45rem 0;
            margin-bottom: 0.65rem;
            border-bottom: 1px solid var(--border-hairline);
        }}
        .sec-title {{
            font-size: 0.92rem;
            font-weight: 600;
            color: var(--text-primary);
            letter-spacing: 0.01em;
            white-space: nowrap;
        }}
        .sec-sub {{
            font-size: 0.76rem;
            color: var(--text-muted);
            margin-left: 0.45rem;
            font-weight: 400;
        }}
        .sec-right {{
            display: inline-flex;
            align-items: baseline;
            white-space: nowrap;
            flex-shrink: 0;
        }}
        .sec-score {{
            font-family: {FONT_MONO};
            font-variant-numeric: tabular-nums;
            font-size: 0.88rem;
            font-weight: 600;
            white-space: nowrap;
        }}

        .metric-row {{
            padding: 0.44rem 0 0.35rem 0;
            border-bottom: 1px solid #161B22;
        }}
        .metric-row-top {{
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            gap: 0.6rem;
        }}
        .metric-label-wrap {{
            display: flex;
            flex-direction: column;
            min-width: 0;
        }}
        .metric-label-en {{
            font-size: 0.83rem;
            font-weight: 500;
            color: var(--text-primary);
            line-height: 1.25;
        }}
        .metric-label-th {{
            font-size: 0.72rem;
            color: var(--text-muted);
            line-height: 1.25;
        }}
        .metric-right {{
            display: flex;
            align-items: baseline;
            gap: 0.75rem;
            flex-shrink: 0;
        }}
        .metric-val {{
            font-family: {FONT_MONO};
            font-variant-numeric: tabular-nums;
            font-size: 0.86rem;
            font-weight: 600;
            color: var(--text-primary);
            min-width: 68px;
            text-align: right;
        }}
        .metric-score-badge {{
            font-family: {FONT_MONO};
            font-variant-numeric: tabular-nums;
            font-size: 0.76rem;
            font-weight: 500;
            min-width: 42px;
            text-align: right;
        }}
        .metric-wt {{
            font-family: {FONT_MONO};
            font-variant-numeric: tabular-nums;
            font-size: 0.7rem;
            color: var(--text-muted);
            min-width: 36px;
            text-align: right;
        }}
        .metric-bar-track {{
            height: 2px;
            width: 100%;
            background: #161B22;
            margin-top: 0.32rem;
            overflow: hidden;
        }}
        .metric-bar-fill {{
            height: 2px;
        }}

        .data-strip {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(115px, 1fr));
            gap: 0.65rem 0.9rem;
            padding: 0.65rem 0;
            margin: 0.35rem 0 0.65rem 0;
            border-top: 1px solid var(--border-hairline);
            border-bottom: 1px solid var(--border-hairline);
        }}
        .data-strip-3col {{
            grid-template-columns: repeat(3, minmax(0, 1fr));
        }}
        .data-strip-cell {{
            display: flex;
            flex-direction: column;
            gap: 0.12rem;
        }}
        .data-strip-label {{
            font-size: 0.69rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }}
        .data-strip-val {{
            font-family: {FONT_MONO};
            font-variant-numeric: tabular-nums;
            font-size: 0.88rem;
            font-weight: 600;
            color: var(--text-primary);
        }}

        .peer-table-wrap {{
            width: 100%;
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
            margin-top: 0.35rem;
        }}
        .peer-table {{
            width: 100%;
            min-width: 680px;
            border-collapse: collapse;
            font-size: 0.82rem;
        }}
        .peer-table th {{
            text-align: left;
            font-size: 0.7rem;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-muted);
            padding: 0.55rem 0.65rem;
            border-bottom: 1px solid var(--border-hairline);
            white-space: nowrap;
        }}
        .peer-table th.num {{
            text-align: right;
        }}
        .peer-table td {{
            padding: 0.6rem 0.65rem;
            border-bottom: 1px solid #151921;
            color: var(--text-primary);
            vertical-align: middle;
            white-space: nowrap;
        }}
        .peer-table td.num {{
            text-align: right;
            font-family: {FONT_MONO};
            font-variant-numeric: tabular-nums;
        }}
        .peer-table tr:hover td {{
            background-color: var(--bg-hover);
        }}
        .peer-table tr.active-row td:first-child {{
            border-left: 2px solid var(--text-primary);
        }}

        .scuttle-links {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.45rem;
            margin-top: 0.5rem;
        }}
        .scuttle-link {{
            display: inline-flex;
            align-items: center;
            gap: 0.38rem;
            padding: 0.32rem 0.65rem;
            border: 1px solid var(--border-hairline);
            border-radius: 5px;
            background: var(--bg-surface);
            color: var(--text-primary) !important;
            text-decoration: none !important;
            font-size: 0.76rem;
            font-weight: 500;
            transition: background-color 120ms ease, border-color 120ms ease;
        }}
        .scuttle-link:hover {{
            background: var(--bg-hover);
            border-color: #364050;
        }}

        .fisher-item-title {{
            font-size: 0.82rem;
            font-weight: 500;
            color: var(--text-primary);
            line-height: 1.3;
        }}
        .fisher-item-desc {{
            font-size: 0.73rem;
            color: var(--text-muted);
            margin-top: 0.15rem;
            line-height: 1.35;
        }}

        /* Smooth vertical page scroll over touch Plotly charts */
        .js-plotly-plot,
        .js-plotly-plot .plotly,
        .js-plotly-plot .draglayer {{
            touch-action: pan-y !important;
        }}

        /* Mobile responsive refinements (<= 768px) */
        @media (max-width: 768px) {{
            body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {{
                overflow-x: hidden !important;
                font-size: 14px !important;
            }}
            .block-container {{
                padding: 0.75rem 0.85rem 2.5rem 0.85rem !important;
            }}

            /* Hero Bar: 2 compact rows (Row 1: Ticker + Price + Change, Row 2: 2x2 KPI grid) */
            .hero-bar {{
                flex-direction: column;
                align-items: stretch;
                gap: 0.75rem;
                padding: 0.25rem 0 0.85rem 0;
            }}
            .hero-left {{
                display: flex;
                flex-direction: row;
                flex-wrap: wrap;
                justify-content: space-between;
                align-items: baseline;
                flex: 1 1 auto;
                min-width: 0;
                gap: 0.28rem 0.6rem;
            }}
            .hero-identity {{
                display: contents;
            }}
            .hero-ticker {{
                order: 1;
                font-size: 1.5rem;
            }}
            .hero-price-row {{
                order: 2;
                margin-top: 0;
                gap: 0.45rem;
                justify-content: flex-end;
            }}
            .hero-price {{
                font-size: 1.38rem;
            }}
            .hero-change {{
                font-size: 0.85rem;
            }}
            .hero-name {{
                order: 3;
                flex: 1 1 100%;
                font-size: 0.92rem;
            }}
            .hero-meta {{
                order: 4;
                flex: 1 1 100%;
                font-size: 0.82rem;
                gap: 0.35rem;
            }}
            .hero-right {{
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: 0.7rem 0.85rem;
                padding-top: 0.7rem;
                border-top: 1px solid var(--border-hairline);
                width: 100%;
            }}
            .hero-kpi {{
                border-left: none;
                padding: 0;
                white-space: normal;
                min-width: 0;
            }}
            .hero-kpi-val {{
                font-size: 1.3rem;
            }}
            .hero-kpi-sub {{
                font-size: 0.78rem;
            }}

            /* Adapt 3/4/5-col metric grids into 2-col grid */
            .data-strip,
            .data-strip-3col {{
                grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
                gap: 0.75rem 0.85rem !important;
            }}
            .data-strip-label {{
                font-size: 0.75rem;
            }}
            .data-strip-val {{
                font-size: 1.05rem;
            }}

            /* Alert & Red Flag bar clean wrapping */
            .alert-item {{
                flex-direction: column;
                align-items: flex-start;
                gap: 0.35rem;
                padding: 0.6rem 0.75rem;
                font-size: 0.875rem;
            }}
            .alert-left {{
                width: 100%;
                overflow-wrap: anywhere;
            }}

            /* Section headers & metric rows readability */
            .sec-header {{
                flex-wrap: wrap;
                gap: 0.3rem 0.75rem;
            }}
            .sec-title {{
                font-size: 1rem;
                white-space: normal;
            }}
            .sec-sub {{
                display: block;
                margin-left: 0;
                margin-top: 2px;
                font-size: 0.84rem;
            }}
            .sec-score {{
                font-size: 0.95rem;
            }}
            .metric-row-top {{
                flex-wrap: wrap;
                gap: 0.25rem 0.5rem;
            }}
            .metric-label-en {{
                font-size: 0.9rem;
            }}
            .metric-label-th {{
                font-size: 0.82rem;
            }}
            .metric-val {{
                font-size: 0.95rem;
            }}
            .metric-score-badge {{
                font-size: 0.84rem;
            }}
            .metric-wt {{
                font-size: 0.78rem;
            }}
            .fisher-item-title {{
                font-size: 0.9rem;
            }}
            .fisher-item-desc {{
                font-size: 0.82rem;
            }}

            /* Touch targets >= 42px */
            .stButton > button,
            .stFormSubmitButton > button,
            [data-testid="stSelectbox"] > div,
            [data-testid="stSelectbox"] > div > div,
            [data-testid="stSelectbox"] div[data-baseweb="select"] > div,
            div[data-baseweb="select"] > div,
            .scuttle-link,
            [data-testid="stExpander"] summary {{
                min-height: 44px !important;
            }}
            [data-testid="stSelectbox"] > div > div,
            [data-testid="stSelectbox"] div[data-baseweb="select"] > div {{
                height: auto !important;
                min-height: 44px !important;
            }}
            .stTextInput input {{
                min-height: 44px !important;
                font-size: 16px !important;
            }}
            .stTextArea textarea {{
                font-size: 16px !important;
            }}
            .stTabs [data-baseweb="tab-list"],
            [data-baseweb="tab-list"],
            [role="tablist"] {{
                overflow-x: auto;
                flex-wrap: nowrap;
                -webkit-overflow-scrolling: touch;
                gap: 0.9rem;
                min-height: 44px !important;
                height: auto !important;
            }}
            .stTabs [data-baseweb="tab"],
            [data-testid="stTabs"] [role="tab"],
            [role="tab"],
            [data-baseweb="tab"] {{
                min-height: 44px !important;
                height: 44px !important;
                padding: 0.5rem 0.2rem !important;
                font-size: 0.875rem !important;
                white-space: nowrap;
                flex-shrink: 0;
            }}
            [data-testid="stRadio"] div[role="radiogroup"] {{
                display: flex !important;
                flex-direction: row !important;
                flex-wrap: wrap !important;
                gap: 0.5rem !important;
            }}
            [data-testid="stRadio"] div[role="radiogroup"] label {{
                min-height: 42px !important;
                min-width: 52px !important;
                padding: 0.35rem 0.75rem !important;
                border: 1px solid var(--border-hairline);
                border-radius: 6px;
                display: inline-flex !important;
                align-items: center !important;
                justify-content: center !important;
            }}
            [data-testid="stPopover"] {{
                justify-content: flex-start;
                padding-top: 0.25rem;
                padding-bottom: 0.25rem;
            }}
            [data-testid="stPopover"] button {{
                width: 42px !important;
                min-width: 42px !important;
                max-width: 42px !important;
                height: 42px !important;
                min-height: 42px !important;
                font-size: 14px !important;
            }}
            div[data-testid="stPopoverBody"] {{
                max-width: calc(100vw - 1.75rem) !important;
                font-size: 0.875rem !important;
            }}
        }}
        </style>
        """
    )
    st.markdown(css, unsafe_allow_html=True)


def render_hero_bar(
    analysis: dict[str, Any], fisher_total: int, fisher_assessed: int
) -> None:
    """Render compact decisive Hero Bar with hairline vertical dividers."""
    ticker = analysis["ticker"]
    profile = analysis["profile"]
    market = analysis["market"]
    cls = analysis["classification"]
    ov = analysis["sector_overlay"]
    val = analysis["valuation_summary"]
    summary = analysis["scoring_summary"]

    price = market.get("current_price")
    chg = market.get("change_pct")
    mcap = market.get("market_cap")
    pe = val.get("pe_ttm")
    div_y = val.get("dividend_yield") or 0.0
    currency = market.get("currency", "USD")

    price_str = f"{price:,.2f}" if price is not None else "N/A"
    if chg is not None:
        chg_color = PALETTE["emerald"] if chg >= 0 else PALETTE["crimson"]
        chg_str = f"{chg * 100:+.2f}%"
    else:
        chg_color = PALETTE["text_muted"]
        chg_str = "0.00%"

    mcap_str = f"${mcap / 1e9:,.1f}B" if mcap else "N/A"
    pe_str = f"{pe:.1f}x" if pe is not None else "N/A"
    div_str = f"{div_y * 100:.2f}%"

    overlay_badge = ""
    if ov["overlay"] != "standard":
        overlay_badge = f'<span class="pill-subtle">{_esc(ov["label_en"])}</span>'

    override_tag = (
        '<span class="pill-subtle" style="color:#D97706;border-color:#D97706;">MANUAL</span>'
        if cls["is_overridden"]
        else '<span class="pill-subtle">AUTO</span>'
    )

    quant_score = summary["final_score"]
    quant_color = signal_color(summary["signal"])
    cov_pct = summary["data_coverage_pct"]
    cov_color = PALETTE["text_primary"] if cov_pct >= 80.0 else PALETTE["amber"]

    fisher_color = (
        PALETTE["emerald"]
        if fisher_total >= 22
        else PALETTE["amber"]
        if fisher_total >= 14
        else PALETTE["text_primary"]
    )

    html = _html(
        f"""
        <div class="hero-bar">
            <div class="hero-left">
                <div class="hero-identity">
                    <span class="hero-ticker">{_esc(ticker)}</span>
                    <span class="hero-name">{_esc(profile.get('company_name', ticker))}</span>
                    {overlay_badge}
                </div>
                <div class="hero-meta">
                    <span>{_esc(profile.get('sector', ''))}</span>
                    <span>/</span>
                    <span>{_esc(profile.get('industry', ''))}</span>
                    <span>/</span>
                    <span class="mono">Mkt Cap {mcap_str}</span>
                    <span>/</span>
                    <span class="mono">P/E {pe_str}</span>
                    <span>/</span>
                    <span class="mono">Div {div_str}</span>
                </div>
                <div class="hero-price-row">
                    <span class="hero-price">{price_str} <span style="font-size:0.78rem;color:{PALETTE['text_muted']};font-weight:400;">{_esc(currency)}</span></span>
                    <span class="hero-change" style="color:{chg_color};">{chg_str} (1D)</span>
                </div>
            </div>
            <div class="hero-right">
                <div class="hero-kpi">
                    <span class="hero-kpi-label">Lynch Category</span>
                    <div style="display:flex;align-items:center;gap:0.4rem;">
                        <span class="pill-badge">{_esc(cls['active_category'])}</span>
                        {override_tag}
                    </div>
                    <span class="hero-kpi-sub">{_esc(cls['label_th'])}</span>
                </div>
                <div class="hero-kpi">
                    <span class="hero-kpi-label">Quantitative</span>
                    <span class="hero-kpi-val" style="color:{quant_color};">{quant_score:.1f}<span style="font-size:0.8rem;color:{PALETTE['text_muted']};font-weight:400;"> / 100</span></span>
                    <span class="hero-kpi-sub">Raw {summary['raw_score']:.1f} / Pen {summary['red_flag_penalty']:+.0f}</span>
                </div>
                <div class="hero-kpi">
                    <span class="hero-kpi-label">Fisher 15-Pt</span>
                    <span class="hero-kpi-val" style="color:{fisher_color};">{fisher_total}<span style="font-size:0.8rem;color:{PALETTE['text_muted']};font-weight:400;"> / 30</span></span>
                    <span class="hero-kpi-sub">Assessed {fisher_assessed}/15</span>
                </div>
                <div class="hero-kpi">
                    <span class="hero-kpi-label">Data Coverage</span>
                    <span class="hero-kpi-val" style="color:{cov_color};">{cov_pct:.0f}%</span>
                    <span class="hero-kpi-sub">{_esc(ov['overlay'].upper())}</span>
                </div>
            </div>
        </div>
        """
    )
    st.markdown(html, unsafe_allow_html=True)


def render_red_flag_bar(red_flags: dict[str, Any]) -> None:
    """Render slim crimson/amber alert bar directly under Hero Bar when triggered."""
    hard = red_flags.get("hard_flags", [])
    warnings = red_flags.get("warnings", [])
    if not hard and not warnings:
        return

    items_html: list[str] = []
    for f in hard:
        items_html.append(
            _html(
                f"""
                <div class="alert-item alert-hard">
                    <div class="alert-left">
                        <span style="color:{PALETTE['crimson']};display:inline-flex;">{SVG_ICONS['alert']}</span>
                        <span style="font-weight:600;color:{PALETTE['text_primary']};">{_esc(f['label_th'])}</span>
                        <span style="color:{PALETTE['text_muted']};">{_esc(f['detail_th'])}</span>
                    </div>
                    <span class="mono" style="color:{PALETTE['crimson']};font-weight:600;white-space:nowrap;">{f['penalty']:+.0f} pts</span>
                </div>
                """
            )
        )

    for w in warnings:
        items_html.append(
            _html(
                f"""
                <div class="alert-item alert-warning">
                    <div class="alert-left">
                        <span style="color:{PALETTE['amber']};display:inline-flex;">{SVG_ICONS['warning']}</span>
                        <span style="font-weight:600;color:{PALETTE['text_primary']};">{_esc(w['label_th'])}</span>
                        <span style="color:{PALETTE['text_muted']};">{_esc(w['detail_th'])}</span>
                    </div>
                    <span class="pill-subtle" style="color:{PALETTE['amber']};border-color:{PALETTE['amber']};">WARNING (0 pts)</span>
                </div>
                """
            )
        )

    st.markdown(f'<div class="alert-strip">{"".join(items_html)}</div>', unsafe_allow_html=True)


def render_section_header(
    title_en: str, title_th: str, score: float | None = None, weight_pct: float | None = None
) -> None:
    right_parts: list[str] = []
    if weight_pct is not None:
        right_parts.append(
            f'<span class="mono" style="font-size:0.75rem;color:{PALETTE["text_muted"]};margin-right:0.75rem;">Wt {weight_pct:.0f}%</span>'
        )
    if score is not None:
        if score >= 70.0:
            col = PALETTE["emerald"]
        elif score >= 40.0:
            col = PALETTE["amber"]
        else:
            col = PALETTE["crimson"]
        right_parts.append(f'<span class="sec-score" style="color:{col};">{score:.1f} / 100</span>')
    elif weight_pct is not None:
        right_parts.append(f'<span class="sec-score" style="color:{PALETTE["text_muted"]};">N/A</span>')

    html = _html(
        f"""
        <div class="sec-header">
            <div style="min-width:0;">
                <span class="sec-title">{_esc(title_en)}</span>
                <span class="sec-sub">{_esc(title_th)}</span>
            </div>
            <div class="sec-right">{"".join(right_parts)}</div>
        </div>
        """
    )
    st.markdown(html, unsafe_allow_html=True)


def render_metric_row_html(metric: dict[str, Any]) -> str:
    """Return ultra-clean hairline HTML row for a scored or missing metric."""
    val_str = format_metric_value(metric.get("value"), metric["format_type"])
    score = metric.get("score")
    sig_col = signal_color(metric.get("signal", "neutral"))
    score_str = f"{score:.0f}" if score is not None else "N/A"
    wt = metric.get("effective_weight_in_pillar", 0.0)
    wt_str = f"{wt:.0f}%" if metric.get("status") == "scored" else "-"
    fill_w = f"{max(0.0, min(100.0, score)):.1f}%" if score is not None else "0%"

    # Extract concise Thai subtitle inside parentheses if present, or show full label_th.
    label_en = metric["label_en"]
    label_th = metric["label_th"]

    return _html(
        f"""
        <div class="metric-row">
            <div class="metric-row-top">
                <div class="metric-label-wrap">
                    <span class="metric-label-en">{_esc(label_en)}</span>
                    <span class="metric-label-th">{_esc(label_th)}</span>
                </div>
                <div class="metric-right">
                    <span class="metric-val">{_esc(val_str)}</span>
                    <span class="metric-score-badge" style="color:{sig_col};">{score_str}</span>
                    <span class="metric-wt">{wt_str}</span>
                </div>
            </div>
            <div class="metric-bar-track">
                <div class="metric-bar-fill" style="width:{fill_w};background:{sig_col};"></div>
            </div>
        </div>
        """
    )


def render_growth_strip_html(
    growth: dict[str, Any], valuation: dict[str, Any]
) -> str:
    """Compact hairline horizontal strip for growth decomposition & Lynch Fair Value."""
    hist_g = growth.get("hist_growth")
    fwd_g = growth.get("forward_growth")
    blend_g = growth.get("blended_growth")
    fv_mult = valuation.get("lynch_fair_value_multiple")
    fv = valuation.get("lynch_fair_value")
    upside = valuation.get("upside_to_fair_value")

    up_color = PALETTE["text_primary"]
    if upside is not None:
        up_color = PALETTE["emerald"] if upside >= 0 else PALETTE["crimson"]

    cells = [
        ("Hist EPS CAGR", f"{hist_g * 100:.1f}%" if hist_g is not None else "N/A", PALETTE["text_primary"]),
        ("Forward Est", f"{fwd_g * 100:.1f}%" if fwd_g is not None else "N/A", PALETTE["text_primary"]),
        ("Blended g", f"{blend_g * 100:.1f}%" if blend_g is not None else "N/A", PALETTE["text_primary"]),
        ("FV Mult (Cap 25x)", f"{fv_mult:.1f}x" if fv_mult is not None else "N/A", PALETTE["text_primary"]),
        ("Lynch Fair Value", f"${fv:,.2f}" if fv is not None else "N/A", PALETTE["text_primary"]),
        ("Upside / Downside", f"{upside * 100:+.1f}%" if upside is not None else "N/A", up_color),
    ]
    cells_html = "".join(
        f'<div class="data-strip-cell"><span class="data-strip-label">{label}</span>'
        f'<span class="data-strip-val" style="color:{col};">{val}</span></div>'
        for label, val, col in cells
    )
    return _html(f'<div class="data-strip data-strip-3col">{cells_html}</div>')


def render_revenue_strip_html(annual_statements: list[dict[str, Any]]) -> str:
    """Compact 5Y annual revenue & YoY growth hairline strip."""
    if not annual_statements:
        return ""
    cells: list[str] = []
    prev_rev: float | None = None
    for rec in annual_statements[-5:]:
        yr = str(rec.get("date", ""))[:4]
        rev = rec.get("revenue")
        if rev is not None:
            rev_b = f"${rev / 1e9:,.1f}B"
            yoy_str = ""
            yoy_col = PALETTE["text_muted"]
            if prev_rev is not None and prev_rev > 0:
                yoy = (rev - prev_rev) / prev_rev
                yoy_str = f" ({yoy * 100:+.1f}%)"
                yoy_col = PALETTE["emerald"] if yoy >= 0 else PALETTE["crimson"]
            prev_rev = rev
            cells.append(
                f'<div class="data-strip-cell">'
                f'<span class="data-strip-label">FY{yr} Revenue</span>'
                f'<span class="data-strip-val">{rev_b}<span style="font-size:0.74rem;color:{yoy_col};font-weight:400;">{yoy_str}</span></span>'
                f"</div>"
            )
    if not cells:
        return ""
    return _html(f'<div class="data-strip">{"".join(cells)}</div>')


def render_peer_table_html(
    peer_rows: list[dict[str, Any]], active_ticker: str
) -> str:
    """Render minimalist Swiss-editorial peer comparison table with tabular monospace nums."""
    rows_html: list[str] = []
    for r in peer_rows:
        t = r["ticker"]
        cls_name = ' class="active-row"' if t == active_ticker else ""
        price_s = f"{r['price']:,.2f}" if r.get("price") is not None else "N/A"
        pe_s = f"{r['pe']:.1f}x" if r.get("pe") is not None else "N/A"
        peg_s = f"{r['peg']:.2f}x" if r.get("peg") is not None else "N/A"
        g_s = f"{r['g'] * 100:.1f}%" if r.get("g") is not None else "N/A"
        cap_eff_s = (
            f"{r['cap_eff'] * 100:.1f}%" if r.get("cap_eff") is not None else "N/A"
        )
        score_s = f"{r['quant_score']:.1f}" if r.get("quant_score") is not None else "N/A"
        score_col = signal_color(r.get("signal", "neutral"))
        fisher_s = f"{r['fisher_score']}/30"
        cov_s = f"{r['coverage']:.0f}%"

        rows_html.append(
            _html(
                f"""
                <tr{cls_name}>
                    <td><span class="mono" style="font-weight:600;">{_esc(t)}</span> <span style="color:{PALETTE['text_muted']};font-size:0.76rem;margin-left:0.35rem;">{_esc(r.get('company_name', '')[:24])}</span></td>
                    <td><span class="pill-subtle">{_esc(r['category'])}</span></td>
                    <td class="num">{price_s}</td>
                    <td class="num">{pe_s}</td>
                    <td class="num">{peg_s}</td>
                    <td class="num">{g_s}</td>
                    <td class="num">{cap_eff_s} <span style="font-size:0.68rem;color:{PALETTE['text_muted']};">{_esc(r.get('cap_eff_label', 'ROIC'))}</span></td>
                    <td class="num" style="color:{score_col};font-weight:600;">{score_s}</td>
                    <td class="num">{fisher_s}</td>
                    <td class="num" style="color:{PALETTE['text_muted']};">{cov_s}</td>
                </tr>
                """
            )
        )

    return _html(
        f"""
        <div class="peer-table-wrap">
            <table class="peer-table">
                <thead>
                    <tr>
                        <th>Ticker / Company</th>
                        <th>Lynch Category</th>
                        <th class="num">Price</th>
                        <th class="num">P/E</th>
                        <th class="num">PEG</th>
                        <th class="num">Blended g</th>
                        <th class="num">5Y ROIC / ROE</th>
                        <th class="num">Quant (0-100)</th>
                        <th class="num">Fisher (0-30)</th>
                        <th class="num">Cov</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(rows_html)}
                </tbody>
            </table>
        </div>
        """
    )


def render_scuttlebutt_links_html(ticker: str, company_name: str) -> str:
    """Render 1-click Digital Scuttlebutt external research links with 1.5px SVG icons."""
    clean_t = ticker.strip().upper()
    q_name = quote_plus(company_name.split(",")[0].strip() or clean_t)
    links = [
        (
            "SEC EDGAR Filings",
            f"https://www.sec.gov/edgar/browse/?CIK={quote_plus(clean_t)}",
        ),
        (
            "Glassdoor Reviews",
            f"https://www.glassdoor.com/Search/results.htm?keyword={q_name}",
        ),
        (
            "G2 Software / Product",
            f"https://www.g2.com/search?query={q_name}",
        ),
        (
            "Trustpilot Sentiment",
            f"https://www.trustpilot.com/search?query={q_name}",
        ),
        (
            "Yahoo Finance Holders",
            f"https://finance.yahoo.com/quote/{quote_plus(clean_t)}/holders/",
        ),
    ]
    anchors = "".join(
        f'<a class="scuttle-link" href="{url}" target="_blank" rel="noopener noreferrer">'
        f"<span>{_esc(label)}</span>"
        f'<span style="color:{PALETTE["text_muted"]};display:inline-flex;">{SVG_ICONS["external_link"]}</span>'
        f"</a>"
        for label, url in links
    )
    return _html(f'<div class="scuttle-links">{anchors}</div>')


# ---------------------------------------------------------------------------
# Polished Dark-Minimal Plotly Builders
# ---------------------------------------------------------------------------


def _base_plotly_layout(height: int = 240) -> dict[str, Any]:
    return {
        "height": height,
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "showlegend": False,
        "dragmode": False,
        "margin": dict(l=8, r=8, t=28, b=24),
        "font": dict(family=FONT_MONO, size=11, color=PALETTE["text_muted"]),
        "hovermode": "x unified",
        "hoverlabel": dict(
            bgcolor=PALETTE["surface"],
            bordercolor=PALETTE["hairline"],
            font=dict(family=FONT_MONO, size=11, color=PALETTE["text_primary"]),
        ),
        "xaxis": dict(
            showgrid=False,
            zeroline=False,
            showline=True,
            linecolor=PALETTE["hairline"],
            fixedrange=True,
            automargin=True,
            tickfont=dict(family=FONT_MONO, size=10, color=PALETTE["text_muted"]),
        ),
        "yaxis": dict(
            showgrid=True,
            gridcolor=PALETTE["chart_grid"],
            gridwidth=1,
            zeroline=False,
            showline=False,
            fixedrange=True,
            automargin=True,
            tickfont=dict(family=FONT_MONO, size=10, color=PALETTE["text_muted"]),
        ),
    }


def build_lynch_fair_value_chart(analysis: dict[str, Any]) -> go.Figure:
    """5Y Price vs Peter Lynch Fair Value Line with non-clipping header annotations."""
    fig = go.Figure()
    layout = _base_plotly_layout(height=265)

    series = analysis["valuation_summary"].get("lynch_fair_value_series", [])
    price_hist = analysis.get("valuation_summary", {})
    if series:
        dates = [pt["date"] for pt in series]
        prices = [pt["price"] for pt in series]
        fvs = [pt["fair_value"] for pt in series]
    else:
        dates, prices, fvs = [], [], []

    if not dates:
        fig.update_layout(**layout)
        fig.add_annotation(
            text="No 5Y price series available",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(family=FONT_MONO, size=12, color=PALETTE["text_muted"]),
        )
        return fig

    fig.add_trace(
        go.Scatter(
            x=dates,
            y=prices,
            mode="lines",
            name="Price",
            line=dict(color=PALETTE["text_primary"], width=1.75),
            hovertemplate="Price: $%{y:,.2f}<extra></extra>",
        )
    )

    valid_fv = [(d, v) for d, v in zip(dates, fvs) if v is not None]
    last_price = prices[-1]

    fig.add_annotation(
        xref="paper",
        yref="paper",
        x=0.0,
        y=1.02,
        xanchor="left",
        yanchor="bottom",
        text=f"Price ${last_price:,.2f}",
        showarrow=False,
        font=dict(family=FONT_MONO, size=11, color=PALETTE["text_primary"]),
    )

    if valid_fv:
        p2fv = price_hist.get("price_to_fair_value")
        fv_color = PALETTE["emerald"]
        if p2fv is not None:
            if p2fv >= 1.25:
                fv_color = PALETTE["crimson"]
            elif p2fv >= 0.95:
                fv_color = PALETTE["amber"]

        fig.add_trace(
            go.Scatter(
                x=[d for d, _ in valid_fv],
                y=[v for _, v in valid_fv],
                mode="lines",
                name="Lynch FV",
                line=dict(color=fv_color, width=1.75, dash="dash"),
                hovertemplate="Lynch FV: $%{y:,.2f}<extra></extra>",
            )
        )

        last_fv_val = valid_fv[-1][1]
        fig.add_annotation(
            xref="paper",
            yref="paper",
            x=1.0,
            y=1.02,
            xanchor="right",
            yanchor="bottom",
            text=f"Lynch FV ${last_fv_val:,.2f}",
            showarrow=False,
            font=dict(family=FONT_MONO, size=11, color=fv_color),
        )
    else:
        fig.add_annotation(
            xref="paper",
            yref="paper",
            x=1.0,
            y=1.02,
            xanchor="right",
            yanchor="bottom",
            text="Lynch FV: N/A (g <= 0)",
            showarrow=False,
            font=dict(family=FONT_MONO, size=10, color=PALETTE["amber"]),
        )

    layout["yaxis"]["tickprefix"] = "$"
    fig.update_layout(**layout)
    return fig


def build_margin_trend_chart(analysis: dict[str, Any]) -> go.Figure:
    """5Y Gross Margin & Operating/Pre-Tax Margin lines with clean header annotations."""
    fig = go.Figure()
    layout = _base_plotly_layout(height=235)
    quality = analysis["quality_summary"]
    gm_hist = quality.get("gross_margin_history", [])
    om_hist = quality.get("operating_margin_history", [])
    om_label = quality.get("operating_margin_label", "Operating Margin")

    has_any = False
    if gm_hist:
        has_any = True
        gm_x = [str(p["date"])[:4] for p in gm_hist]
        gm_y = [p["margin"] * 100.0 for p in gm_hist]
        fig.add_trace(
            go.Scatter(
                x=gm_x,
                y=gm_y,
                mode="lines+markers",
                name="Gross Margin",
                line=dict(color=PALETTE["text_primary"], width=1.75),
                marker=dict(size=5, color=PALETTE["text_primary"]),
                hovertemplate="Gross Margin: %{y:.1f}%<extra></extra>",
            )
        )
        fig.add_annotation(
            xref="paper",
            yref="paper",
            x=0.0,
            y=1.02,
            xanchor="left",
            yanchor="bottom",
            text=f"Gross {gm_y[-1]:.1f}%",
            showarrow=False,
            font=dict(family=FONT_MONO, size=11, color=PALETTE["text_primary"]),
        )

    if om_hist:
        has_any = True
        om_x = [str(p["date"])[:4] for p in om_hist]
        om_y = [p["margin"] * 100.0 for p in om_hist]
        short_lbl = "Pre-Tax" if "Pre-Tax" in om_label else "Net" if "Net" in om_label else "Operating"
        fig.add_trace(
            go.Scatter(
                x=om_x,
                y=om_y,
                mode="lines+markers",
                name=om_label,
                line=dict(color=PALETTE["emerald"], width=1.75),
                marker=dict(size=5, color=PALETTE["emerald"]),
                hovertemplate=f"{om_label}: %{{y:.1f}}%<extra></extra>",
            )
        )
        fig.add_annotation(
            xref="paper",
            yref="paper",
            x=1.0 if gm_hist else 0.0,
            y=1.02,
            xanchor="right" if gm_hist else "left",
            yanchor="bottom",
            text=f"{short_lbl} {om_y[-1]:.1f}%",
            showarrow=False,
            font=dict(family=FONT_MONO, size=11, color=PALETTE["emerald"]),
        )

    if not has_any:
        fig.add_annotation(
            text="No margin history available",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(family=FONT_MONO, size=11, color=PALETTE["text_muted"]),
        )

    layout["yaxis"]["ticksuffix"] = "%"
    fig.update_layout(**layout)
    return fig


def build_capital_efficiency_chart(analysis: dict[str, Any]) -> go.Figure:
    """5Y ROIC (or ROE for Financials) vs Hurdle benchmark line."""
    fig = go.Figure()
    layout = _base_plotly_layout(height=235)
    overlay = analysis["sector_overlay"]["overlay"]
    quality = analysis["quality_summary"]

    if overlay == "financials":
        series = quality.get("roe_history", [])
        val_key = "roe"
        metric_label = "ROE"
        hurdle = 11.0
    else:
        series = quality.get("roic_history", [])
        val_key = "roic"
        metric_label = "ROIC"
        hurdle = 12.0

    if series:
        xs = [str(p["date"])[:4] for p in series]
        ys = [p[val_key] * 100.0 for p in series]
        last_y = ys[-1]
        line_col = (
            PALETTE["emerald"]
            if last_y >= hurdle
            else PALETTE["amber"]
            if last_y >= 6.0
            else PALETTE["crimson"]
        )

        fig.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="lines+markers",
                name=metric_label,
                line=dict(color=line_col, width=1.75),
                marker=dict(size=5, color=line_col),
                hovertemplate=f"{metric_label}: %{{y:.1f}}%<extra></extra>",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=xs,
                y=[hurdle] * len(xs),
                mode="lines",
                name="Hurdle",
                line=dict(color=PALETTE["hurdle"], width=1.75, dash="dot"),
                hoverinfo="skip",
            )
        )

        fig.add_annotation(
            xref="paper",
            yref="paper",
            x=0.0,
            y=1.02,
            xanchor="left",
            yanchor="bottom",
            text=f"{metric_label} {last_y:.1f}%",
            showarrow=False,
            font=dict(family=FONT_MONO, size=11, color=line_col),
        )
        fig.add_annotation(
            xref="paper",
            yref="paper",
            x=1.0,
            y=1.02,
            xanchor="right",
            yanchor="bottom",
            text=f"Hurdle {hurdle:.0f}%",
            showarrow=False,
            font=dict(family=FONT_MONO, size=10, color=PALETTE["text_muted"]),
        )
    else:
        fig.add_annotation(
            text=f"No {metric_label} history available",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(family=FONT_MONO, size=11, color=PALETTE["text_muted"]),
        )

    layout["yaxis"]["ticksuffix"] = "%"
    fig.update_layout(**layout)
    return fig
