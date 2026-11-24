"""Main Streamlit application for Lynch & Fisher Equity Research Terminal."""

from __future__ import annotations

from datetime import datetime
import sys
from pathlib import Path
from typing import Any

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
try:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    pass
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.scoring_config import CATEGORY_PRIORITY
from core.data_fetcher import (
    DataFetchError,
    fetch_combined_stock_data,
    fetch_financial_statements,
    fetch_peer_stock_data,
    fetch_quote_snapshot,
    get_currency_symbol,
)
from core.scoring_engine import analyze_stock
from storage.user_db import FISHER_15_POINTS, FISHER_SECTIONS, UserWorkspaceDB
from theme import (
    PALETTE,
    PLOTLY_CONFIG,
    build_capital_efficiency_chart,
    build_lynch_fair_value_chart,
    build_margin_trend_chart,
    format_threshold_value,
    inject_theme_css,
    render_balance_strip_html,
    render_error_notice_html,
    render_growth_strip_html,
    render_hero_bar,
    render_loading_notice_html,
    render_metric_row_html,
    render_peer_table_html,
    render_red_flag_bar,
    render_revenue_strip_html,
    render_scuttlebutt_links_html,
    render_section_header,
)

MONOCHROME_FAVICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
    'fill="none" stroke="#F1F5F9" stroke-width="2">'
    '<rect x="3" y="3" width="18" height="18" rx="3"/>'
    '<path d="M8 15V9l4 6V9m4 0v6"/>'
    "</svg>"
)

CURATED_QUICK_PICKS: list[str] = [
    "NVDA",
    "MSFT",
    "KO",
    "JPM",
    "CPALL.BK",
    "ADVANC.BK",
    "BDMS.BK",
]

st.set_page_config(
    page_title="Lynch & Fisher Terminal",
    page_icon=MONOCHROME_FAVICON_SVG,
    layout="wide",
    initial_sidebar_state="auto",
)

inject_theme_css()


@st.cache_resource
def _get_user_db() -> UserWorkspaceDB:
    return UserWorkspaceDB()


def _render_metric_block(metrics: list[dict[str, Any]], key_prefix: str) -> None:
    """Render active metrics with ? popovers and tuck skipped metrics into a hairline drawer."""
    active = [m for m in metrics if m["status"] != "skipped_inapplicable"]
    skipped = [m for m in metrics if m["status"] == "skipped_inapplicable"]

    for m in active:
        col_row, col_pop = st.columns([0.92, 0.08], gap="small")
        with col_row:
            st.markdown(render_metric_row_html(m), unsafe_allow_html=True)
        with col_pop:
            with st.popover("?", width="content"):
                st.markdown(f"**{m['label_th']}**")
                st.caption(m["description_th"])
                th = m["thresholds"]
                fmt = m["format_type"]
                direction_th = (
                    "ยิ่งสูงยิ่งดี (Higher is better)"
                    if m["direction"] == "higher_is_better"
                    else "ยิ่งต่ำยิ่งดี (Lower is better)"
                )
                st.markdown(
                    (
                        f"`{direction_th}`\n\n"
                        f"- Green (100): `{format_threshold_value(th['green'], fmt)}`\n"
                        f"- Amber (50): `{format_threshold_value(th['amber'], fmt)}`\n"
                        f"- Red (0): `{format_threshold_value(th['red'], fmt)}`"
                    )
                )
                if m.get("note_th"):
                    st.caption(f"หมายเหตุ: {m['note_th']}")

    if skipped:
        with st.expander(f"เกณฑ์ที่ไม่ใช้กับกลุ่มธุรกิจนี้ ({len(skipped)})", expanded=False):
            for m in skipped:
                st.markdown(
                    f"<div style='display:flex;justify-content:space-between;padding:0.25rem 0;"
                    f"border-bottom:1px solid #161B22;font-size:0.76rem;color:{PALETTE['text_muted']};'>"
                    f"<span>{m['label_en']}</span>"
                    f"<span>{m['note_th']}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )


def _save_fisher_callback(ticker: str) -> None:
    db = _get_user_db()
    updated: dict[int, int] = {}
    for item in FISHER_15_POINTS:
        k = f"fisher_{ticker}_{item['id']}"
        if k in st.session_state:
            updated[item["id"]] = int(st.session_state[k])
    if updated:
        db.save_fisher_scores(ticker, updated)


def _trigger_refresh(ticker: str) -> None:
    nonces = st.session_state["refresh_nonces"]
    nonces[ticker] = nonces.get(ticker, 0) + 1
    fetch_quote_snapshot.clear()
    fetch_financial_statements.clear()
    fetch_peer_stock_data.clear()


def _build_quick_pick_list(watchlist_tickers: list[str]) -> list[str]:
    ordered: list[str] = []
    for sym in watchlist_tickers + CURATED_QUICK_PICKS:
        clean = sym.strip().upper()
        if clean and clean not in ordered:
            ordered.append(clean)
    return ordered


def main() -> None:
    db = _get_user_db()
    watchlist = db.get_watchlist()
    watchlist_tickers = [w["ticker"] for w in watchlist]

    if "active_ticker" not in st.session_state:
        st.session_state["active_ticker"] = (
            watchlist_tickers[0] if watchlist_tickers else "NVDA"
        )
    if "refresh_nonces" not in st.session_state:
        st.session_state["refresh_nonces"] = {}
    if "extra_peers" not in st.session_state:
        st.session_state["extra_peers"] = []
    if "peers_loaded" not in st.session_state:
        st.session_state["peers_loaded"] = False
    if "peer_cache_bust" not in st.session_state:
        st.session_state["peer_cache_bust"] = 0

    # ------------------------------------------------------------------
    # Minimalist Left Sidebar
    # ------------------------------------------------------------------
    with st.sidebar:
        st.markdown(
            """
            <div class="sidebar-brand">
                <div class="sidebar-brand-title">LYNCH / FISHER</div>
                <div class="sidebar-brand-sub">Institutional Equity Research (TH/EN)</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.form("ticker_search_form", clear_on_submit=False):
            search_val = st.text_input(
                "ค้นหาหุ้น (Ticker Symbol)",
                value=st.session_state["active_ticker"],
                placeholder="e.g. NVDA, CPALL.BK, JPM",
            )
            c_btn1, c_btn2 = st.columns(2, gap="small")
            with c_btn1:
                submitted = st.form_submit_button("Analyze", type="primary", width="stretch")
            with c_btn2:
                force_btn = st.form_submit_button("Refresh", width="stretch")

        if submitted and search_val.strip():
            st.session_state["active_ticker"] = search_val.strip().upper()
            st.rerun()

        if force_btn:
            t_target = (search_val or st.session_state["active_ticker"]).strip().upper()
            if t_target:
                st.session_state["active_ticker"] = t_target
                _trigger_refresh(t_target)
                st.rerun()

        active_ticker = st.session_state["active_ticker"]
        in_wl = db.is_in_watchlist(active_ticker)

        if in_wl:
            if st.button("นำออกจาก Watchlist (Remove)", width="stretch", key="rm_wl_btn"):
                db.remove_from_watchlist(active_ticker)
                st.rerun()
        else:
            if st.button("เพิ่มเข้า Watchlist (Add)", width="stretch", key="add_wl_btn"):
                db.add_to_watchlist(active_ticker)
                st.rerun()

        st.markdown(
            f"<div style='margin:1rem 0 0.45rem 0;font-size:0.7rem;text-transform:uppercase;"
            f"letter-spacing:0.06em;color:{PALETTE['text_muted']};border-top:1px solid {PALETTE['hairline']};"
            f"padding-top:0.85rem;'>Watchlist ({len(watchlist)})</div>",
            unsafe_allow_html=True,
        )

        for item in watchlist:
            t_sym = item["ticker"]
            btn_type = "primary" if t_sym == active_ticker else "secondary"
            tbp = item.get("target_buy_price")
            suffix = f" [{tbp:,.1f}]" if tbp else ""
            label = f"{t_sym}{suffix}  -  {(item['company_name'] or '')[:16]}"
            if st.button(label, key=f"wl_{t_sym}", type=btn_type, width="stretch"):
                st.session_state["active_ticker"] = t_sym
                st.rerun()

    # ------------------------------------------------------------------
    # Top Main-Canvas Search Strip & Single-Row Quick-Pick Chips (Mobile-First)
    # ------------------------------------------------------------------
    active_ticker = st.session_state["active_ticker"]
    with st.form("top_ticker_bar", clear_on_submit=False):
        s_col1, s_col2, s_col3 = st.columns([0.62, 0.19, 0.19], gap="small")
        with s_col1:
            top_search = st.text_input(
                "ค้นหาหุ้น (US / Thai .BK)",
                value=active_ticker,
                placeholder="Ticker: NVDA, CPALL.BK, ADVANC.BK, JPM",
                label_visibility="collapsed",
            )
        with s_col2:
            top_go = st.form_submit_button("Analyze", type="primary", width="stretch")
        with s_col3:
            top_ref = st.form_submit_button("Refresh", width="stretch")

    if top_go and top_search.strip():
        st.session_state["active_ticker"] = top_search.strip().upper()
        st.rerun()

    if top_ref:
        t_target = (top_search or active_ticker).strip().upper()
        if t_target:
            st.session_state["active_ticker"] = t_target
            _trigger_refresh(t_target)
            st.rerun()

    quick_picks = _build_quick_pick_list(watchlist_tickers)
    with st.container(key="quick_pick_strip", horizontal=True, wrap=False, gap="small"):
        for qp_sym in quick_picks:
            chip_type = "primary" if qp_sym == active_ticker else "secondary"
            if st.button(qp_sym, key=f"qp_{qp_sym}", type=chip_type):
                st.session_state["active_ticker"] = qp_sym
                st.rerun()

    # ------------------------------------------------------------------
    # Load & Analyze Active Ticker (Cloud-Safe Split Caching + Clean Error UI)
    # ------------------------------------------------------------------
    active_ticker = st.session_state["active_ticker"]
    nonce = st.session_state["refresh_nonces"].get(active_ticker, 0)
    loading_slot = st.empty()
    loading_slot.markdown(render_loading_notice_html(active_ticker), unsafe_allow_html=True)

    try:
        stock_data = fetch_combined_stock_data(active_ticker, cache_bust=nonce)
        override = db.get_category_override(active_ticker)
        analysis = analyze_stock(stock_data, category_override=override)
    except DataFetchError as exc:
        loading_slot.empty()
        st.markdown(render_error_notice_html(str(exc)), unsafe_allow_html=True)
        st.stop()
    except Exception:
        loading_slot.empty()
        st.markdown(
            render_error_notice_html(
                f"ระบบไม่สามารถดึงหรือประมวลผลข้อมูลของ '{active_ticker}' ได้ในขณะนี้ "
                "(อาจเกิดจาก Yahoo Finance จำกัดคำขอชั่วคราว หรือชื่อย่อหุ้นไม่ถูกต้อง)"
            ),
            unsafe_allow_html=True,
        )
        st.stop()

    loading_slot.empty()

    # Keep watchlist metadata fresh if ticker is saved.
    if db.is_in_watchlist(active_ticker):
        db.add_to_watchlist(
            active_ticker,
            analysis["profile"].get("company_name", ""),
            analysis["profile"].get("sector", ""),
        )

    fisher_summary = db.get_fisher_summary(active_ticker)
    fisher_scores = db.get_fisher_scores(active_ticker)
    target_buy_price = db.get_target_buy_price(active_ticker)

    trading_ccy = analysis["market"].get("currency", "USD")
    fin_ccy = analysis["market"].get("financial_currency", trading_ccy)
    cur_sym = get_currency_symbol(trading_ccy)

    # Sidebar cache & provenance footer
    with st.sidebar:
        cs = analysis.get("cache_status", {})
        p_dt = str(cs.get("price_fetched_at", ""))[:16].replace("T", " ")
        s_dt = str(cs.get("statements_fetched_at", ""))[:16].replace("T", " ")
        d_src = str(cs.get("data_source", "unknown")).upper()
        st.markdown(
            f"<div style='margin-top:1.25rem;padding-top:0.75rem;border-top:1px solid {PALETTE['hairline']};"
            f"font-size:0.71rem;color:{PALETTE['text_muted']};font-family:IBM Plex Mono,monospace;'>"
            f"<div>SOURCE: {d_src}</div>"
            f"<div style='margin-top:3px;'>PRICE: {'HIT' if cs.get('price_cached') else 'LIVE'} ({p_dt})</div>"
            f"<div style='margin-top:3px;'>STMTS: {'HIT' if cs.get('statements_cached') else 'LIVE'} ({s_dt})</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    # ------------------------------------------------------------------
    # 1. Hero Bar + Freshness + Category Override & Target Buy Price
    # ------------------------------------------------------------------
    render_hero_bar(
        analysis,
        fisher_total=fisher_summary["total_score"],
        fisher_assessed=fisher_summary["assessed_count"],
        target_buy_price=target_buy_price,
    )

    if analysis.get("cache_status", {}).get("data_source") in {"stale_cache", "seed_snapshot"}:
        st.markdown(
            f"<div class='alert-strip'>"
            f"<div class='alert-item alert-warning'>"
            f"<div class='alert-left'>"
            f"<span style='color:{PALETTE['amber']};font-weight:600;'>FALLBACK DATA</span>"
            f"<span style='color:{PALETTE['text_muted']};'>Yahoo Finance ถูกจำกัดอัตราการเรียกจาก Cloud IP ชั่วคราว ระบบกำลังแสดงข้อมูลจากแคชล่าสุด/ฐานข้อมูลตั้งต้น (Snapshot) กด Refresh เพื่อลองดึงใหม่</span>"
            f"</div>"
            f"</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    cls = analysis["classification"]
    ov_col1, ov_col2, ov_col3, ov_col4 = st.columns([0.38, 0.22, 0.30, 0.10], gap="small")
    with ov_col1:
        st.markdown(
            f"<div style='font-size:0.76rem;color:{PALETTE['text_muted']};padding-top:0.35rem;'>"
            f"<span style='color:{PALETTE['text_primary']};font-weight:500;'>Category Logic:</span> "
            f"{cls['rationale_th']}</div>",
            unsafe_allow_html=True,
        )
    with ov_col2:
        auto_label = f"Auto ({cls['auto_category']})"
        options = [auto_label] + CATEGORY_PRIORITY
        current_override = db.get_category_override(active_ticker)
        default_idx = options.index(current_override) if current_override in options else 0
        selected_cat = st.selectbox(
            "ปรับหมวดหมู่ Peter Lynch (Manual Override)",
            options=options,
            index=default_idx,
            key=f"cat_override_{active_ticker}",
            label_visibility="collapsed",
        )
        target_override = None if selected_cat == auto_label else selected_cat
        if target_override != current_override:
            db.set_category_override(
                active_ticker,
                target_override,
                analysis["profile"].get("company_name", ""),
                analysis["profile"].get("sector", ""),
            )
            st.rerun()
    with ov_col3:
        with st.form(f"target_buy_form_{active_ticker}", clear_on_submit=False):
            tb_in, tb_btn = st.columns([0.62, 0.38], gap="small")
            with tb_in:
                tbp_input = st.text_input(
                    f"Target Buy ({cur_sym})",
                    value=f"{target_buy_price:.2f}" if target_buy_price else "",
                    placeholder=f"Target Buy ({cur_sym})",
                    label_visibility="collapsed",
                )
            with tb_btn:
                save_tbp = st.form_submit_button("Set Target", width="stretch")
        if save_tbp:
            raw_txt = tbp_input.strip().replace(",", "")
            if not raw_txt or raw_txt == "0":
                db.set_target_buy_price(
                    active_ticker,
                    None,
                    analysis["profile"].get("company_name", ""),
                    analysis["profile"].get("sector", ""),
                )
                st.rerun()
            else:
                try:
                    parsed_tbp = float(raw_txt)
                    if parsed_tbp <= 0:
                        raise ValueError
                    db.set_target_buy_price(
                        active_ticker,
                        parsed_tbp,
                        analysis["profile"].get("company_name", ""),
                        analysis["profile"].get("sector", ""),
                    )
                    st.rerun()
                except ValueError:
                    st.markdown(
                        render_error_notice_html("กรุณากรอกราคาเป้าหมาย (Target Buy Price) เป็นตัวเลขมากกว่า 0"),
                        unsafe_allow_html=True,
                    )
    with ov_col4:
        with st.popover("?", width="content"):
            st.markdown(f"**{cls['label_th']}**")
            st.caption(cls["description_th"])
            pw = analysis["pillar_weights"]
            st.markdown(
                f"สัดส่วนน้ำหนักของหมวดหมู่นี้:\n"
                f"- Lynch Valuation: `{pw['lynch_valuation']}%`\n"
                f"- Lynch Safety: `{pw['lynch_safety']}%`\n"
                f"- Fisher Quality: `{pw['fisher_quality']}%`"
            )

    render_red_flag_bar(analysis["red_flags"])

    # ------------------------------------------------------------------
    # 2. Asymmetric Lynch Valuation (Left) & Lynch Safety (Right)
    # ------------------------------------------------------------------
    col_val, col_saf = st.columns([1.35, 1.0], gap="large")

    val_pillar = analysis["pillars"]["lynch_valuation"]
    with col_val:
        render_section_header(
            val_pillar["label_en"],
            val_pillar["label_th"],
            score=val_pillar["score"],
            weight_pct=val_pillar["effective_category_weight"],
        )
        fig_fv = build_lynch_fair_value_chart(analysis)
        st.plotly_chart(fig_fv, use_container_width=True, theme=None, config=PLOTLY_CONFIG)

        g_col1, g_col2 = st.columns([0.92, 0.08], gap="small")
        with g_col1:
            st.markdown(
                render_growth_strip_html(
                    analysis["growth_summary"],
                    analysis["valuation_summary"],
                    currency=trading_ccy,
                ),
                unsafe_allow_html=True,
            )
        with g_col2:
            with st.popover("?", width="content"):
                gs = analysis["growth_summary"]
                vs = analysis["valuation_summary"]
                st.markdown("**สูตรคำนวณ Peter Lynch Fair Value**")
                st.caption(
                    "ใช้อัตราเติบโตผสม g = 50% Historical EPS CAGR + 50% Forward Growth "
                    "และจำกัดตัวคูณ P/E สูงสุดที่ 25x เพื่อป้องกันการประเมินมูลค่าสูงเกินจริง"
                )
                st.markdown(
                    f"- Hist Source: `{gs.get('hist_growth_source')}`\n"
                    f"- Fwd Source: `{gs.get('forward_growth_source')}`\n"
                    f"- Fair Value Formula: `EPS_TTM * min(25, g% + DivYield%)`\n"
                    f"- Current P/E TTM: `{vs['pe_ttm']:.2f}x`"
                    if vs.get("pe_ttm") is not None
                    else "- Current P/E TTM: `N/A`"
                )

        _render_metric_block(val_pillar["metrics"], f"val_{active_ticker}")

    saf_pillar = analysis["pillars"]["lynch_safety"]
    with col_saf:
        render_section_header(
            saf_pillar["label_en"],
            saf_pillar["label_th"],
            score=saf_pillar["score"],
            weight_pct=saf_pillar["effective_category_weight"],
        )
        bal_strip = render_balance_strip_html(
            stock_data.get("annual_statements", []), financial_currency=fin_ccy
        )
        if bal_strip:
            st.markdown(bal_strip, unsafe_allow_html=True)

        _render_metric_block(saf_pillar["metrics"], f"saf_{active_ticker}")

        rf_checks = analysis["red_flags"]["all_checks"]
        with st.expander("รายละเอียดการตรวจสอบ Red Flags ทั้งหมด (4 รายการ)", expanded=False):
            for chk in rf_checks:
                status_tag = "TRIGGERED" if chk["triggered"] else "CLEAR"
                tag_col = (
                    PALETTE["crimson"]
                    if chk["triggered"] and chk["severity"] == "hard"
                    else PALETTE["amber"]
                    if chk["triggered"]
                    else PALETTE["emerald"]
                )
                st.markdown(
                    f"<div style='padding:0.35rem 0;border-bottom:1px solid #161B22;'>"
                    f"<div style='display:flex;justify-content:space-between;font-size:0.78rem;'>"
                    f"<span style='font-weight:500;color:{PALETTE['text_primary']};'>{chk['label_th']}</span>"
                    f"<span class='mono' style='color:{tag_col};'>{status_tag} ({chk['penalty']:+.0f})</span>"
                    f"</div>"
                    f"<div style='font-size:0.72rem;color:{PALETTE['text_muted']};margin-top:2px;'>{chk['detail_th']}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

    # ------------------------------------------------------------------
    # 3. Fisher Quality Charts & Metrics
    # ------------------------------------------------------------------
    qual_pillar = analysis["pillars"]["fisher_quality"]
    render_section_header(
        qual_pillar["label_en"],
        qual_pillar["label_th"],
        score=qual_pillar["score"],
        weight_pct=qual_pillar["effective_category_weight"],
    )

    q_chart_left, q_chart_right = st.columns([1.15, 1.0], gap="large")
    with q_chart_left:
        st.caption("Margin Trajectory 5Y (%): Gross & Operating / Pre-Tax Margin")
        st.plotly_chart(
            build_margin_trend_chart(analysis),
            use_container_width=True,
            theme=None,
            config=PLOTLY_CONFIG,
        )
    with q_chart_right:
        eff_title = (
            "Capital Efficiency 5Y (%): Return on Equity (ROE)"
            if analysis["sector_overlay"]["overlay"] == "financials"
            else "Capital Efficiency 5Y (%): Return on Invested Capital (ROIC)"
        )
        st.caption(eff_title)
        st.plotly_chart(
            build_capital_efficiency_chart(analysis),
            use_container_width=True,
            theme=None,
            config=PLOTLY_CONFIG,
        )

    rev_strip = render_revenue_strip_html(
        stock_data.get("annual_statements", []), financial_currency=fin_ccy
    )
    if rev_strip:
        st.markdown(rev_strip, unsafe_allow_html=True)

    q_metrics = qual_pillar["metrics"]
    q_active = [m for m in q_metrics if m["status"] != "skipped_inapplicable"]
    q_skipped = [m for m in q_metrics if m["status"] == "skipped_inapplicable"]
    mid = (len(q_active) + 1) // 2
    qm_col1, qm_col2 = st.columns(2, gap="large")
    with qm_col1:
        _render_metric_block(q_active[:mid], f"qual_l_{active_ticker}")
    with qm_col2:
        _render_metric_block(q_active[mid:], f"qual_r_{active_ticker}")
    if q_skipped:
        _render_metric_block(q_skipped, f"qual_skip_{active_ticker}")

    # ------------------------------------------------------------------
    # 4. Lazy-Loaded Peer Comparison Table
    # ------------------------------------------------------------------
    render_section_header(
        "Peer & Watchlist Comparison",
        "ตารางเปรียบเทียบเชิงปริมาณและคุณภาพเทียบกลุ่ม (โหลดเมื่อกดเพื่อความรวดเร็วบน Cloud)",
    )

    peer_ctl1, peer_ctl2, peer_ctl3 = st.columns([0.34, 0.42, 0.24], gap="small")
    with peer_ctl1:
        if st.button("โหลดข้อมูลเทียบคู่แข่ง (Load Peers)", type="primary" if not st.session_state["peers_loaded"] else "secondary", key="load_peers_btn", width="stretch"):
            st.session_state["peers_loaded"] = True
            st.rerun()
    with peer_ctl2:
        with st.form("add_peer_form", clear_on_submit=True):
            p_in_col, p_btn_col = st.columns([0.66, 0.34], gap="small")
            with p_in_col:
                peer_sym = st.text_input(
                    "เพิ่มหุ้นเปรียบเทียบ",
                    placeholder="Add ticker (e.g. AAPL, SCB.BK)",
                    label_visibility="collapsed",
                )
            with p_btn_col:
                add_peer = st.form_submit_button("Compare", width="stretch")
        if add_peer and peer_sym.strip():
            sym_clean = peer_sym.strip().upper()
            if sym_clean not in st.session_state["extra_peers"]:
                st.session_state["extra_peers"].append(sym_clean)
            st.session_state["peers_loaded"] = True
            st.rerun()
    with peer_ctl3:
        if st.session_state["peers_loaded"]:
            if st.button("Refresh Peers", key="refresh_peers_btn", width="stretch"):
                fetch_peer_stock_data.clear()
                st.session_state["peer_cache_bust"] += 1
                st.rerun()

    if st.session_state["peers_loaded"]:
        compare_tickers: list[str] = []
        for t in [active_ticker] + watchlist_tickers + st.session_state["extra_peers"]:
            if t not in compare_tickers:
                compare_tickers.append(t)

        peer_rows: list[dict[str, Any]] = []
        peer_bust = st.session_state["peer_cache_bust"]
        for pt in compare_tickers[:10]:
            try:
                if pt == active_ticker:
                    p_res = analysis
                else:
                    p_data = fetch_peer_stock_data(pt, cache_bust=peer_bust)
                    p_ov = db.get_category_override(pt)
                    p_res = analyze_stock(p_data, category_override=p_ov)
                p_fs = db.get_fisher_summary(pt)
                is_fin = p_res["sector_overlay"]["overlay"] == "financials"
                cap_eff = (
                    p_res["quality_summary"].get("roe_5y_avg")
                    if is_fin
                    else p_res["quality_summary"].get("roic_5y_avg")
                )
                peer_rows.append(
                    {
                        "ticker": pt,
                        "company_name": p_res["profile"].get("company_name", pt),
                        "category": p_res["classification"]["active_category"],
                        "currency": p_res["market"].get("currency", "USD"),
                        "price": p_res["market"].get("current_price"),
                        "target_buy_price": db.get_target_buy_price(pt),
                        "pe": p_res["valuation_summary"].get("pe_ttm"),
                        "peg": p_res["valuation_summary"].get("peg_ratio"),
                        "g": p_res["growth_summary"].get("blended_growth"),
                        "cap_eff": cap_eff,
                        "cap_eff_label": "ROE" if is_fin else "ROIC",
                        "quant_score": p_res["scoring_summary"]["final_score"],
                        "signal": p_res["scoring_summary"]["signal"],
                        "fisher_score": p_fs["total_score"],
                        "coverage": p_res["scoring_summary"]["data_coverage_pct"],
                    }
                )
            except Exception:
                continue

        if peer_rows:
            st.markdown(render_peer_table_html(peer_rows, active_ticker), unsafe_allow_html=True)
    else:
        st.markdown(
            f"<div style='padding:0.55rem 0;font-size:0.78rem;color:{PALETTE['text_muted']};'>"
            f"ยังไม่ได้โหลดข้อมูลคู่แข่ง เพื่อประหยัดโควตาและเร่งความเร็วการเปิดหน้าแรก กดปุ่ม 'โหลดข้อมูลเทียบคู่แข่ง (Load Peers)' ด้านบนเมื่อต้องการเปรียบเทียบ {len(watchlist_tickers)} หุ้นใน Watchlist"
            f"</div>",
            unsafe_allow_html=True,
        )

    # ------------------------------------------------------------------
    # 5. Decision Workspace & JSON Backup Persistence
    # ------------------------------------------------------------------
    ws_head_col, ws_pop_col = st.columns([0.94, 0.06], gap="small")
    with ws_head_col:
        render_section_header(
            "Decision Workspace (Qualitative)",
            "พื้นที่ประเมินเชิงคุณภาพแยกส่วนจากคะแนนตัวเลข (Philip Fisher 15-Point & 2-Minute Drill)",
        )
    with ws_pop_col:
        with st.popover("?", width="content"):
            st.markdown("**เกณฑ์คะแนน Philip Fisher (0-30)**")
            st.caption(
                "คะแนนเชิงคุณภาพคำนวณแยกอิสระจาก Quantitative Score เพื่อให้ผู้ลงทุนแยกข้อเท็จจริงทางบัญชีออกจากข้อได้เปรียบเชิงคุณภาพ:\n"
                "- 0 = ไม่ผ่านเกณฑ์ / อ่อนแอ\n"
                "- 1 = ปานกลาง / ยังต้องติดตาม\n"
                "- 2 = ยอดเยี่ยม / มีหลักฐานชัดเจน"
            )

    ws_left, ws_right = st.columns([1.3, 1.0], gap="large")

    with ws_left:
        st.markdown(
            f"<div style='display:flex;justify-content:space-between;align-items:baseline;margin-bottom:0.4rem;'>"
            f"<span style='font-size:0.84rem;font-weight:600;color:{PALETTE['text_primary']};'>Philip Fisher 15-Point Checklist</span>"
            f"<span class='mono' style='font-size:0.84rem;color:{PALETTE['emerald']};'>Total: {fisher_summary['total_score']} / 30</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
        tab_labels = {
            "growth": "1. Growth",
            "moat": "2. Moat & Margins",
            "org": "3. Organization",
            "gov": "4. Governance",
        }
        tabs = st.tabs([tab_labels.get(sec["id"], sec["label_en"]) for sec in FISHER_SECTIONS])
        for tab, sec in zip(tabs, FISHER_SECTIONS):
            with tab:
                sec_items = [it for it in FISHER_15_POINTS if it["section"] == sec["id"]]
                for it in sec_items:
                    cur_val = fisher_scores.get(it["id"], 0)
                    item_col, radio_col = st.columns([0.62, 0.38], gap="small")
                    with item_col:
                        st.markdown(
                            f"<div class='fisher-item-title'>{it['title_th']}</div>"
                            f"<div class='fisher-item-desc'>{it['description_th']}</div>",
                            unsafe_allow_html=True,
                        )
                    with radio_col:
                        st.radio(
                            it["title_en"],
                            options=[0, 1, 2],
                            index=cur_val if cur_val in (0, 1, 2) else 0,
                            horizontal=True,
                            key=f"fisher_{active_ticker}_{it['id']}",
                            format_func=lambda v: f"{v}",
                            label_visibility="collapsed",
                            on_change=_save_fisher_callback,
                            args=(active_ticker,),
                        )
                    st.markdown(
                        "<div style='border-bottom:1px solid #161B22;margin:0.2rem 0 0.45rem 0;'></div>",
                        unsafe_allow_html=True,
                    )

    with ws_right:
        notes = db.get_thesis_notes(active_ticker)
        st.markdown(
            f"<div style='font-size:0.84rem;font-weight:600;color:{PALETTE['text_primary']};margin-bottom:0.45rem;'>"
            f"Peter Lynch 2-Minute Drill</div>",
            unsafe_allow_html=True,
        )
        with st.form(f"thesis_form_{active_ticker}"):
            drill_txt = st.text_area(
                "2-Minute Drill (เหตุผลหลักที่ซื้อหุ้นตัวนี้ภายใน 2 นาที)",
                value=notes["two_minute_drill"],
                height=115,
                placeholder="บริษัททำอะไร ชนะคู่แข่งด้วยอะไร และกำไรในอีก 3-5 ปีข้างหน้าจะโตจากปัจจัยใด...",
            )
            cat_txt = st.text_area(
                "Key Catalysts (ตัวเร่งมูลค่าใน 1-3 ปี)",
                value=notes["key_catalysts"],
                height=72,
                placeholder="เช่น สินค้าใหม่ การขยายมาร์จิ้น การซื้อหุ้นคืน...",
            )
            risk_txt = st.text_area(
                "Key Risks & Kill-Switch (ความเสี่ยงและจุดตัดใจขาย)",
                value=notes["key_risks"],
                height=72,
                placeholder="เงื่อนไขใดเกิดขึ้นแล้วสมมติฐานการลงทุนถือว่าผิด...",
            )
            save_notes_btn = st.form_submit_button("Save Thesis Notes", type="primary")

        if save_notes_btn:
            db.save_thesis_notes(active_ticker, drill_txt, cat_txt, risk_txt)
            st.toast(f"บันทึกโน้ตการลงทุน {active_ticker} แล้ว")

        st.markdown(
            f"<div style='margin-top:1.05rem;padding-top:0.75rem;border-top:1px solid {PALETTE['hairline']};'>"
            f"<div style='font-size:0.82rem;font-weight:600;color:{PALETTE['text_primary']};'>Digital Scuttlebutt</div>"
            f"<div style='font-size:0.73rem;color:{PALETTE['text_muted']};margin-top:2px;'>ลิงก์ตรวจสอบข้อมูลภาคสนามภายนอกแบบ 1 คลิก</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            render_scuttlebutt_links_html(
                active_ticker, analysis["profile"].get("company_name", active_ticker)
            ),
            unsafe_allow_html=True,
        )

        # Backup & Restore JSON Persistence
        st.markdown(
            f"<div style='margin-top:1.15rem;padding-top:0.8rem;border-top:1px solid {PALETTE['hairline']};'>"
            f"<div style='font-size:0.82rem;font-weight:600;color:{PALETTE['text_primary']};'>Watchlist &amp; Notes Backup (JSON)</div>"
            f"<div style='font-size:0.73rem;color:{PALETTE['text_muted']};margin-top:2px;'>สำรองหรือกู้คืน Watchlist, Target Buy, Fisher Checklist และ 2-Minute Drill</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
        if st.session_state.get("import_success_msg"):
            st.markdown(
                f"<div style='margin:0.45rem 0;padding:0.45rem 0.75rem;border-left:3px solid {PALETTE['emerald']};"
                f"background:rgba(16,185,129,0.08);font-size:0.78rem;color:{PALETTE['text_primary']};'>"
                f"{st.session_state.pop('import_success_msg')}</div>",
                unsafe_allow_html=True,
            )

        bk_col1, bk_col2 = st.columns(2, gap="small")
        with bk_col1:
            backup_str = db.export_backup_json()
            today_tag = datetime.now().strftime("%Y%m%d")
            st.download_button(
                "สำรองข้อมูล (Export JSON)",
                data=backup_str,
                file_name=f"lynch_fisher_backup_{today_tag}.json",
                mime="application/json",
                use_container_width=True,
            )
        with bk_col2:
            uploaded_backup = st.file_uploader(
                "กู้คืนข้อมูล (Import JSON)",
                type=["json"],
                key="backup_json_uploader",
                label_visibility="collapsed",
            )

        if uploaded_backup is not None:
            raw_bytes = uploaded_backup.getvalue()
            sig = f"{uploaded_backup.name}:{len(raw_bytes)}:{hash(raw_bytes)}"
            if st.session_state.get("last_imported_sig") != sig:
                try:
                    decoded = raw_bytes.decode("utf-8")
                    counts = db.import_backup_json(decoded)
                    st.session_state["last_imported_sig"] = sig
                    # Sync Fisher session keys for active ticker after import.
                    fresh_scores = db.get_fisher_scores(active_ticker)
                    for item in FISHER_15_POINTS:
                        st.session_state[f"fisher_{active_ticker}_{item['id']}"] = (
                            fresh_scores.get(item["id"], 0)
                        )
                    st.session_state["import_success_msg"] = (
                        f"นำเข้าข้อมูลเรียบร้อย: {counts['tickers_imported']} หุ้น "
                        f"(Watchlist {counts['watchlist_count']}, Fisher {counts['checklists_count']}, Drill {counts['drills_count']})"
                    )
                    st.rerun()
                except UnicodeDecodeError:
                    st.markdown(
                        render_error_notice_html("ไฟล์ต้องเข้ารหัสเป็น UTF-8 JSON"),
                        unsafe_allow_html=True,
                    )
                except ValueError as exc:
                    st.markdown(
                        render_error_notice_html(str(exc)),
                        unsafe_allow_html=True,
                    )


if __name__ == "__main__":
    main()
