"""Pure financial calculation functions with strict edge-case handling.

All functions are deterministic and side-effect free, operating solely on
the normalized stock_data dictionary produced by StockDataFetcher.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

import numpy as np

from config.scoring_config import (
    FAIR_VALUE_GROWTH_CAP,
    INVENTORY_MATERIALITY_THRESHOLD,
    RD_MATERIALITY_THRESHOLD,
    SECTOR_OVERLAYS,
)


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        num = float(val)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(num):
        return None
    return num


def _safe_div(num: float | None, den: float | None) -> float | None:
    if num is None or den is None or den == 0:
        return None
    res = num / den
    return res if math.isfinite(res) else None


def _compute_cagr(
    start_val: float | None, end_val: float | None, years: float
) -> float | None:
    if (
        start_val is None
        or end_val is None
        or start_val <= 0
        or end_val <= 0
        or years <= 0
    ):
        return None
    val = (end_val / start_val) ** (1.0 / years) - 1.0
    return val if math.isfinite(val) else None


def _years_between(date_start: str, date_end: str) -> float:
    try:
        d1 = datetime.strptime(date_start[:10], "%Y-%m-%d")
        d2 = datetime.strptime(date_end[:10], "%Y-%m-%d")
        diff_days = (d2 - d1).days
        if diff_days > 0:
            return diff_days / 365.25
    except Exception:
        pass
    return 1.0


def _ols_slope(values: list[float]) -> float | None:
    """Return OLS linear slope (units per index step) for >= 3 points."""
    if len(values) < 3:
        return None
    x = np.arange(len(values), dtype=float)
    y = np.asarray(values, dtype=float)
    if not np.all(np.isfinite(y)):
        return None
    slope = float(np.polyfit(x, y, 1)[0])
    return slope if math.isfinite(slope) else None


def _sum_recent_quarters(
    quarterly: list[dict[str, Any]], field: str
) -> float | None:
    if len(quarterly) < 4:
        return None
    recent = quarterly[-4:]
    vals = [_safe_float(r.get(field)) for r in recent]
    if any(v is None for v in vals):
        return None
    return float(sum(v for v in vals if v is not None))


def detect_sector_overlay(profile: dict[str, Any]) -> dict[str, Any]:
    """Identify whether Financials/Banks or REIT overlay applies."""
    sector = str(profile.get("sector", "")).strip()
    industry = str(profile.get("industry", "")).strip()
    name = str(profile.get("company_name", "")).strip()

    sector_lower = sector.lower()
    industry_lower = industry.lower()
    name_lower = name.lower()

    fin_cfg = SECTOR_OVERLAYS["financials"]
    if sector in fin_cfg["sectors"] or any(
        kw in industry_lower for kw in fin_cfg["industry_keywords"]
    ):
        is_bank = any(kw in industry_lower for kw in fin_cfg["bank_keywords"])
        return {
            "overlay": "financials",
            "is_bank": is_bank,
            "is_reit": False,
            "label_en": fin_cfg["label_en"],
            "label_th": fin_cfg["label_th"],
        }

    reit_cfg = SECTOR_OVERLAYS["reit"]
    if sector in reit_cfg["sectors"] and (
        "reit" in industry_lower or "reit" in name_lower
    ):
        return {
            "overlay": "reit",
            "is_bank": False,
            "is_reit": True,
            "label_en": reit_cfg["label_en"],
            "label_th": reit_cfg["label_th"],
        }

    std_cfg = SECTOR_OVERLAYS["standard"]
    return {
        "overlay": "standard",
        "is_bank": False,
        "is_reit": False,
        "label_en": std_cfg["label_en"],
        "label_th": std_cfg["label_th"],
    }


def compute_growth_metrics(stock_data: dict[str, Any]) -> dict[str, Any]:
    """Compute historical EPS/Revenue CAGRs, blended growth g, and cyclicality stats."""
    annual = stock_data.get("annual_statements", [])
    quarterly = stock_data.get("quarterly_statements", [])
    profile = stock_data.get("profile", {})

    # Extract annual EPS series (oldest -> newest).
    eps_points: list[tuple[str, float]] = []
    rev_points: list[tuple[str, float]] = []
    for rec in annual:
        dt = rec.get("date", "")
        eps = _safe_float(rec.get("diluted_eps"))
        if eps is not None:
            eps_points.append((dt, eps))
        rev = _safe_float(rec.get("revenue"))
        if rev is not None:
            rev_points.append((dt, rev))

    # TTM EPS & Net Income.
    net_income_ttm = _sum_recent_quarters(quarterly, "net_income")
    if net_income_ttm is None and annual:
        net_income_ttm = _safe_float(annual[-1].get("net_income"))

    eps_ttm = _safe_float(profile.get("trailing_eps_info"))
    if eps_ttm is None:
        q_eps = _sum_recent_quarters(quarterly, "diluted_eps")
        if q_eps is not None:
            eps_ttm = q_eps
    if eps_ttm is None and net_income_ttm is not None:
        shares = _safe_float(profile.get("shares_outstanding"))
        if shares is None and annual:
            shares = _safe_float(annual[-1].get("diluted_shares"))
        if shares is not None and shares > 0:
            eps_ttm = net_income_ttm / shares
    if eps_ttm is None and eps_points:
        eps_ttm = eps_points[-1][1]

    # Historical EPS CAGR with strict fallback hierarchy:
    # 1) Full available window (up to 5Y), 2) 3Y (or >=2Y) EPS window, 3) Revenue CAGR.
    hist_eps_cagr_full: float | None = None
    hist_eps_cagr_3y: float | None = None
    revenue_cagr: float | None = None

    if len(eps_points) >= 2:
        yrs_full = _years_between(eps_points[0][0], eps_points[-1][0])
        hist_eps_cagr_full = _compute_cagr(
            eps_points[0][1], eps_points[-1][1], yrs_full
        )

    if len(eps_points) >= 3:
        sub = eps_points[-3:]
        yrs_sub = _years_between(sub[0][0], sub[-1][0])
        hist_eps_cagr_3y = _compute_cagr(sub[0][1], sub[-1][1], yrs_sub)
    elif len(eps_points) == 2:
        yrs_sub = _years_between(eps_points[0][0], eps_points[1][0])
        hist_eps_cagr_3y = _compute_cagr(eps_points[0][1], eps_points[1][1], yrs_sub)

    if len(rev_points) >= 2:
        yrs_rev = _years_between(rev_points[0][0], rev_points[-1][0])
        revenue_cagr = _compute_cagr(rev_points[0][1], rev_points[-1][1], yrs_rev)

    hist_growth: float | None = None
    hist_growth_source = "unavailable"
    if hist_eps_cagr_full is not None:
        hist_growth = hist_eps_cagr_full
        hist_growth_source = f"eps_cagr_{len(eps_points)}y_points"
    elif hist_eps_cagr_3y is not None:
        hist_growth = hist_eps_cagr_3y
        hist_growth_source = "eps_cagr_recent_fallback"
    elif revenue_cagr is not None:
        hist_growth = revenue_cagr
        hist_growth_source = "revenue_cagr_fallback"

    forward_growth = _safe_float(profile.get("forward_growth"))
    forward_growth_source = str(profile.get("forward_growth_source", "unavailable"))

    if hist_growth is not None and forward_growth is not None:
        blended_growth = 0.5 * hist_growth + 0.5 * forward_growth
        blended_source = "blended_50_50"
    elif hist_growth is not None:
        blended_growth = hist_growth
        blended_source = "historical_only"
    elif forward_growth is not None:
        blended_growth = forward_growth
        blended_source = "forward_only"
    else:
        blended_growth = None
        blended_source = "unavailable"

    fair_value_growth_capped = (
        min(FAIR_VALUE_GROWTH_CAP, blended_growth)
        if blended_growth is not None and blended_growth > 0
        else None
    )

    # Cyclicality stats over annual EPS.
    eps_values = [p[1] for p in eps_points]
    eps_cv: float | None = None
    if len(eps_values) >= 3:
        mean_eps = float(np.mean(eps_values))
        std_eps = float(np.std(eps_values, ddof=0))
        if abs(mean_eps) > 1e-6:
            eps_cv = std_eps / abs(mean_eps)

    max_eps_yoy_drop: float | None = None
    yoy_changes: list[float] = []
    for i in range(1, len(eps_values)):
        prev_e, curr_e = eps_values[i - 1], eps_values[i]
        if prev_e > 0:
            yoy_changes.append((curr_e - prev_e) / prev_e)
    if yoy_changes:
        max_eps_yoy_drop = min(yoy_changes)

    annual_loss_years = sum(
        1
        for rec in annual
        if _safe_float(rec.get("net_income")) is not None
        and float(rec["net_income"]) <= 0
    )
    latest_annual_net_income = (
        _safe_float(annual[-1].get("net_income")) if annual else None
    )

    return {
        "eps_ttm": eps_ttm,
        "net_income_ttm": net_income_ttm,
        "latest_annual_net_income": latest_annual_net_income,
        "annual_loss_years": annual_loss_years,
        "annual_years_count": len(annual),
        "hist_eps_cagr_full": hist_eps_cagr_full,
        "hist_eps_cagr_3y": hist_eps_cagr_3y,
        "revenue_cagr": revenue_cagr,
        "hist_growth": hist_growth,
        "hist_growth_source": hist_growth_source,
        "forward_growth": forward_growth,
        "forward_growth_source": forward_growth_source,
        "blended_growth": blended_growth,
        "blended_source": blended_source,
        "fair_value_growth_capped": fair_value_growth_capped,
        "eps_cv": eps_cv,
        "max_eps_yoy_drop": max_eps_yoy_drop,
        "eps_history": [{"date": d, "eps": e} for d, e in eps_points],
    }


def _interpolate_eps_at_date(
    target_date_str: str, anchors: list[tuple[datetime, float]]
) -> float | None:
    if not anchors:
        return None
    target_dt = datetime.strptime(target_date_str[:10], "%Y-%m-%d")
    if target_dt <= anchors[0][0]:
        return anchors[0][1]
    if target_dt >= anchors[-1][0]:
        return anchors[-1][1]
    for i in range(len(anchors) - 1):
        d0, e0 = anchors[i]
        d1, e1 = anchors[i + 1]
        if d0 <= target_dt <= d1:
            span = (d1 - d0).days
            if span <= 0:
                return e1
            frac = (target_dt - d0).days / span
            return e0 + frac * (e1 - e0)
    return anchors[-1][1]


def compute_valuation_metrics(
    stock_data: dict[str, Any], growth: dict[str, Any]
) -> dict[str, Any]:
    """Compute P/E, PEG, PEGY, Peter Lynch Fair Value & 5Y series, and P/B."""
    market = stock_data.get("market", {})
    profile = stock_data.get("profile", {})
    annual = stock_data.get("annual_statements", [])
    price_history = stock_data.get("price_history_5y", [])

    current_price = _safe_float(market.get("current_price"))
    market_cap = _safe_float(market.get("market_cap"))
    eps_ttm = _safe_float(growth.get("eps_ttm"))
    g = _safe_float(growth.get("blended_growth"))
    div_yield = _safe_float(profile.get("dividend_yield")) or 0.0

    pe_ttm: float | None = None
    if current_price is not None and eps_ttm is not None and eps_ttm > 0:
        pe_ttm = current_price / eps_ttm

    g_pct = g * 100.0 if g is not None else None
    div_pct = div_yield * 100.0

    peg_ratio: float | None = None
    pegy_ratio: float | None = None
    lynch_fair_value_multiple: float | None = None
    lynch_fair_value: float | None = None
    price_to_fair_value: float | None = None
    upside_to_fair_value: float | None = None

    if pe_ttm is not None and pe_ttm > 0 and g_pct is not None and g_pct > 0:
        peg_ratio = pe_ttm / g_pct
        if g_pct + div_pct > 0:
            pegy_ratio = pe_ttm / (g_pct + div_pct)

    if eps_ttm is not None and eps_ttm > 0 and g_pct is not None and g_pct > 0:
        lynch_fair_value_multiple = min(
            FAIR_VALUE_GROWTH_CAP * 100.0, g_pct + div_pct
        )
        lynch_fair_value = eps_ttm * lynch_fair_value_multiple
        if current_price is not None and lynch_fair_value > 0:
            price_to_fair_value = current_price / lynch_fair_value
            upside_to_fair_value = (lynch_fair_value - current_price) / current_price

    # Build 5-year Peter Lynch Fair Value series aligned to weekly price history.
    lynch_fair_value_series: list[dict[str, Any]] = []
    if lynch_fair_value_multiple is not None and price_history:
        anchors: list[tuple[datetime, float]] = []
        for pt in growth.get("eps_history", []):
            try:
                anchors.append(
                    (datetime.strptime(pt["date"][:10], "%Y-%m-%d"), float(pt["eps"]))
                )
            except Exception:
                continue
        if eps_ttm is not None and price_history:
            try:
                last_price_dt = datetime.strptime(
                    price_history[-1]["date"][:10], "%Y-%m-%d"
                )
                if not anchors or last_price_dt > anchors[-1][0]:
                    anchors.append((last_price_dt, eps_ttm))
                elif anchors:
                    anchors[-1] = (anchors[-1][0], eps_ttm)
            except Exception:
                pass
        anchors.sort(key=lambda x: x[0])

        for p_row in price_history:
            dt_str = p_row["date"]
            interp_eps = _interpolate_eps_at_date(dt_str, anchors)
            fv = (
                round(interp_eps * lynch_fair_value_multiple, 4)
                if interp_eps is not None and interp_eps > 0
                else None
            )
            lynch_fair_value_series.append(
                {"date": dt_str, "price": p_row["close"], "fair_value": fv}
            )

    # P/B and Asset-Play ratios.
    pb_ratio = _safe_float(profile.get("price_to_book_info"))
    latest_bal = annual[-1] if annual else {}
    latest_equity = _safe_float(latest_bal.get("total_equity"))
    if pb_ratio is None and market_cap is not None and latest_equity is not None and latest_equity > 0:
        pb_ratio = market_cap / latest_equity

    latest_cash = _safe_float(latest_bal.get("cash_and_equivalents"))
    latest_debt = _safe_float(latest_bal.get("total_debt")) or 0.0
    cash_to_price = (
        _safe_div(latest_cash, market_cap)
        if latest_cash is not None and market_cap is not None and market_cap > 0
        else None
    )
    net_cash_to_market_cap = (
        _safe_div(latest_cash - latest_debt, market_cap)
        if latest_cash is not None and market_cap is not None and market_cap > 0
        else None
    )

    return {
        "pe_ttm": pe_ttm,
        "dividend_yield": div_yield,
        "peg_ratio": peg_ratio,
        "pegy_ratio": pegy_ratio,
        "lynch_fair_value_multiple": lynch_fair_value_multiple,
        "lynch_fair_value": lynch_fair_value,
        "price_to_fair_value": price_to_fair_value,
        "upside_to_fair_value": upside_to_fair_value,
        "pb_ratio": pb_ratio,
        "cash_to_price": cash_to_price,
        "net_cash_to_market_cap": net_cash_to_market_cap,
        "lynch_fair_value_series": lynch_fair_value_series,
    }


def compute_safety_metrics(
    stock_data: dict[str, Any], overlay: dict[str, Any]
) -> dict[str, Any]:
    """Compute Lynch balance sheet safety, cash conversion, dilution, and overlay metrics."""
    annual = stock_data.get("annual_statements", [])
    profile = stock_data.get("profile", {})
    latest = annual[-1] if annual else {}
    prev = annual[-2] if len(annual) >= 2 else {}
    overlay_name = overlay["overlay"]

    cash = _safe_float(latest.get("cash_and_equivalents"))
    total_debt = _safe_float(latest.get("total_debt"))
    total_equity = _safe_float(latest.get("total_equity"))
    total_assets = _safe_float(latest.get("total_assets"))
    ebitda = _safe_float(latest.get("ebitda"))
    ebit = _safe_float(latest.get("ebit")) or _safe_float(latest.get("operating_income"))
    interest_exp = _safe_float(latest.get("interest_expense"))

    is_debt_free = total_debt is not None and total_debt == 0.0
    cash_to_debt: float | None = None
    if cash is not None and total_debt is not None:
        if total_debt > 0:
            cash_to_debt = cash / total_debt

    net_debt: float | None = None
    if total_debt is not None and cash is not None:
        net_debt = total_debt - cash

    net_debt_to_ebitda: float | None = None
    if net_debt is not None and ebitda is not None and ebitda > 0:
        net_debt_to_ebitda = net_debt / ebitda

    equity_negative = total_equity is not None and total_equity <= 0
    debt_to_equity: float | None = None
    if total_debt is not None and total_equity is not None and total_equity > 0:
        debt_to_equity = total_debt / total_equity

    no_interest_burden = (
        interest_exp is not None
        and interest_exp == 0.0
        and ebit is not None
        and ebit > 0
    )
    interest_coverage: float | None = None
    if ebit is not None and interest_exp is not None and interest_exp > 0:
        interest_coverage = ebit / interest_exp

    # 3Y FCF Conversion (strictly None if 3Y cumulative Net Income <= 0).
    fcf_conversion_3y: float | None = None
    recent_3 = annual[-3:]
    if recent_3:
        fcfs = [_safe_float(r.get("free_cash_flow")) for r in recent_3]
        nis = [_safe_float(r.get("net_income")) for r in recent_3]
        valid_pairs = [
            (f, n) for f, n in zip(fcfs, nis) if f is not None and n is not None
        ]
        if valid_pairs:
            sum_fcf = sum(f for f, _ in valid_pairs)
            sum_ni = sum(n for _, n in valid_pairs)
            if sum_ni > 0:
                fcf_conversion_3y = sum_fcf / sum_ni

    # Inventory materiality & YoY spread.
    latest_inv = _safe_float(latest.get("inventory"))
    prev_inv = _safe_float(prev.get("inventory"))
    latest_rev = _safe_float(latest.get("revenue"))
    prev_rev = _safe_float(prev.get("revenue"))

    inventory_to_assets = _safe_div(latest_inv, total_assets)
    inventory_applicable = (
        overlay_name == "standard"
        and inventory_to_assets is not None
        and inventory_to_assets > INVENTORY_MATERIALITY_THRESHOLD
    )
    inventory_yoy: float | None = None
    revenue_yoy: float | None = None
    inventory_vs_revenue_spread: float | None = None

    if latest_inv is not None and prev_inv is not None and prev_inv > 0:
        inventory_yoy = (latest_inv - prev_inv) / prev_inv
    if latest_rev is not None and prev_rev is not None and prev_rev > 0:
        revenue_yoy = (latest_rev - prev_rev) / prev_rev
    if (
        inventory_applicable
        and inventory_yoy is not None
        and revenue_yoy is not None
    ):
        inventory_vs_revenue_spread = inventory_yoy - revenue_yoy

    # Share dilution CAGR (from diluted_shares across annual history).
    share_points: list[tuple[str, float]] = []
    for rec in annual:
        sh = _safe_float(rec.get("diluted_shares")) or _safe_float(
            rec.get("ordinary_shares")
        )
        if sh is not None and sh > 0:
            share_points.append((rec.get("date", ""), sh))
    share_dilution_cagr: float | None = None
    if len(share_points) >= 2:
        yrs_sh = _years_between(share_points[0][0], share_points[-1][0])
        share_dilution_cagr = _compute_cagr(
            share_points[0][1], share_points[-1][1], yrs_sh
        )

    # Red flag helper stats: Net Income YoY and last 2Y FCF < 0.
    latest_ni = _safe_float(latest.get("net_income"))
    prev_ni = _safe_float(prev.get("net_income"))
    net_income_yoy: float | None = None
    if (
        latest_ni is not None
        and latest_ni > 0
        and prev_ni is not None
        and prev_ni > 0
    ):
        net_income_yoy = (latest_ni - prev_ni) / prev_ni

    fcf_negative_2y = False
    if len(annual) >= 2:
        f1 = _safe_float(annual[-1].get("free_cash_flow"))
        f2 = _safe_float(annual[-2].get("free_cash_flow"))
        if f1 is not None and f2 is not None and f1 < 0 and f2 < 0:
            fcf_negative_2y = True

    # Financials overlay metrics.
    equity_to_assets = _safe_div(total_equity, total_assets)

    ni_series = [
        _safe_float(r.get("net_income"))
        for r in annual
        if _safe_float(r.get("net_income")) is not None
    ]
    earnings_stability_5y: float | None = None
    if ni_series:
        pos_count = sum(1 for v in ni_series if v is not None and v > 0)
        earnings_stability_5y = pos_count / len(ni_series)

    payout_sustainability = _safe_float(profile.get("payout_ratio_info"))
    if payout_sustainability is None:
        div_paid = _safe_float(latest.get("dividends_paid"))
        if div_paid is not None and latest_ni is not None and latest_ni > 0:
            payout_sustainability = div_paid / latest_ni
        elif div_paid == 0.0 and latest_ni is not None and latest_ni > 0:
            payout_sustainability = 0.0

    return {
        "cash_to_debt": cash_to_debt,
        "is_debt_free": is_debt_free,
        "net_debt": net_debt,
        "net_debt_to_ebitda": net_debt_to_ebitda,
        "debt_to_equity": debt_to_equity,
        "equity_negative": equity_negative,
        "interest_coverage": interest_coverage,
        "no_interest_burden": no_interest_burden,
        "fcf_conversion_3y": fcf_conversion_3y,
        "inventory_to_assets": inventory_to_assets,
        "inventory_applicable": inventory_applicable,
        "inventory_yoy": inventory_yoy,
        "revenue_yoy": revenue_yoy,
        "inventory_vs_revenue_spread": inventory_vs_revenue_spread,
        "share_dilution_cagr": share_dilution_cagr,
        "net_income_yoy": net_income_yoy,
        "fcf_negative_2y": fcf_negative_2y,
        "equity_to_assets": equity_to_assets,
        "earnings_stability_5y": earnings_stability_5y,
        "payout_sustainability": payout_sustainability,
    }


def compute_quality_metrics(
    stock_data: dict[str, Any], overlay: dict[str, Any]
) -> dict[str, Any]:
    """Compute Fisher quality metrics: ROIC, ROE, margin trends, revenue consistency, R&D."""
    annual = stock_data.get("annual_statements", [])
    quarterly = stock_data.get("quarterly_statements", [])
    overlay_name = overlay["overlay"]

    # 5Y Avg ROIC & 5Y Avg ROE.
    roic_annual_series: list[dict[str, Any]] = []
    roe_annual_series: list[dict[str, Any]] = []

    for rec in annual:
        dt = rec.get("date", "")
        ebit = _safe_float(rec.get("ebit")) or _safe_float(rec.get("operating_income"))
        pretax = _safe_float(rec.get("pretax_income"))
        tax = _safe_float(rec.get("tax_provision"))
        ni = _safe_float(rec.get("net_income"))
        equity = _safe_float(rec.get("total_equity"))
        debt = _safe_float(rec.get("total_debt")) or 0.0
        cash = _safe_float(rec.get("cash_and_equivalents")) or 0.0
        assets = _safe_float(rec.get("total_assets"))

        if pretax is not None and pretax > 0 and tax is not None:
            eff_tax = max(0.0, min(0.40, tax / pretax))
        else:
            eff_tax = 0.21

        if ebit is not None and overlay_name != "financials":
            nopat = ebit * (1.0 - eff_tax)
            invested_capital = (equity + debt - cash) if equity is not None else None
            if invested_capital is not None and invested_capital <= 0:
                # Net-cash companies: fallback to total equity + debt or total assets proxy.
                alt_ic = (equity + debt) if equity is not None and (equity + debt) > 0 else assets
                invested_capital = alt_ic
            if invested_capital is not None and invested_capital > 0:
                roic_annual_series.append(
                    {"date": dt, "roic": nopat / invested_capital}
                )

        if ni is not None and equity is not None and equity > 0:
            roe_annual_series.append({"date": dt, "roe": ni / equity})

    roic_5y_avg = (
        float(np.mean([r["roic"] for r in roic_annual_series]))
        if roic_annual_series
        else None
    )
    roe_5y_avg = (
        float(np.mean([r["roe"] for r in roe_annual_series]))
        if roe_annual_series
        else None
    )

    # Margin histories & 5Y OLS slopes (percentage points per year).
    gross_margin_series: list[dict[str, Any]] = []
    operating_margin_series: list[dict[str, Any]] = []
    operating_margin_label = "Operating Margin"

    for rec in annual:
        dt = rec.get("date", "")
        rev = _safe_float(rec.get("revenue"))
        if rev is None or rev <= 0:
            continue
        gp = _safe_float(rec.get("gross_profit"))
        if gp is not None:
            gross_margin_series.append({"date": dt, "margin": gp / rev})

        op_inc = _safe_float(rec.get("operating_income"))
        if op_inc is not None:
            operating_margin_series.append({"date": dt, "margin": op_inc / rev})
        elif overlay_name == "financials":
            pretax = _safe_float(rec.get("pretax_income"))
            ni = _safe_float(rec.get("net_income"))
            if pretax is not None:
                operating_margin_label = "Pre-Tax Margin"
                operating_margin_series.append({"date": dt, "margin": pretax / rev})
            elif ni is not None:
                operating_margin_label = "Net Margin"
                operating_margin_series.append({"date": dt, "margin": ni / rev})

    gm_slope = _ols_slope([p["margin"] * 100.0 for p in gross_margin_series])
    om_slope = _ols_slope([p["margin"] * 100.0 for p in operating_margin_series])

    # 5Y Revenue Consistency (positive YoY revenue transitions out of up to 5).
    rev_points: list[tuple[str, float]] = []
    for rec in annual:
        rev = _safe_float(rec.get("revenue"))
        if rev is not None and rev > 0:
            rev_points.append((rec.get("date", ""), rev))

    # Include TTM revenue if >= 60 days newer than latest annual statement.
    rev_ttm = _sum_recent_quarters(quarterly, "revenue")
    if rev_ttm is not None and rev_ttm > 0 and rev_points and quarterly:
        last_q_dt = quarterly[-1].get("date", "")
        last_a_dt = rev_points[-1][0]
        try:
            d_q = datetime.strptime(last_q_dt[:10], "%Y-%m-%d")
            d_a = datetime.strptime(last_a_dt[:10], "%Y-%m-%d")
            if (d_q - d_a).days >= 60:
                rev_points.append((f"{last_q_dt}(TTM)", rev_ttm))
        except Exception:
            pass

    rev_transitions = 0
    rev_positive = 0
    if len(rev_points) >= 2:
        # Take at most the last 6 points -> up to 5 transitions.
        trimmed = rev_points[-6:]
        for i in range(1, len(trimmed)):
            rev_transitions += 1
            if trimmed[i][1] > trimmed[i - 1][1]:
                rev_positive += 1

    revenue_consistency_5y = (
        rev_positive / rev_transitions if rev_transitions > 0 else None
    )

    # 3Y R&D Productivity (Standard corporate overlay with material R&D >= 1% of revenue).
    rd_applicable = False
    rd_productivity_3y: float | None = None
    rd_to_revenue_avg: float | None = None

    if overlay_name == "standard" and len(annual) >= 2:
        rd_ratios: list[float] = []
        for rec in annual:
            rd = _safe_float(rec.get("rd_expense"))
            rev = _safe_float(rec.get("revenue"))
            if rd is not None and rd > 0 and rev is not None and rev > 0:
                rd_ratios.append(rd / rev)
        if rd_ratios:
            rd_to_revenue_avg = float(np.mean(rd_ratios))
            if rd_to_revenue_avg >= RD_MATERIALITY_THRESHOLD:
                span = annual[-3:] if len(annual) >= 3 else annual[-2:]
                gp_start = _safe_float(span[0].get("gross_profit"))
                gp_end = _safe_float(span[-1].get("gross_profit"))
                rd_sum = sum(
                    _safe_float(r.get("rd_expense")) or 0.0 for r in span
                )
                if gp_start is not None and gp_end is not None and rd_sum > 0:
                    rd_applicable = True
                    rd_productivity_3y = (gp_end - gp_start) / rd_sum

    return {
        "roic_5y_avg": roic_5y_avg,
        "roe_5y_avg": roe_5y_avg,
        "roic_history": roic_annual_series,
        "roe_history": roe_annual_series,
        "gross_margin_trend_5y": gm_slope,
        "operating_margin_trend_5y": om_slope,
        "operating_margin_label": operating_margin_label,
        "gross_margin_history": gross_margin_series,
        "operating_margin_history": operating_margin_series,
        "revenue_consistency_5y": revenue_consistency_5y,
        "revenue_positive_years": rev_positive,
        "revenue_total_transitions": rev_transitions,
        "rd_applicable": rd_applicable,
        "rd_to_revenue_avg": rd_to_revenue_avg,
        "rd_productivity_3y": rd_productivity_3y,
    }


def compute_all_metrics(stock_data: dict[str, Any]) -> dict[str, Any]:
    """Compute all valuation, safety, quality, and overlay indicators."""
    profile = stock_data.get("profile", {})
    overlay = detect_sector_overlay(profile)
    growth = compute_growth_metrics(stock_data)
    valuation = compute_valuation_metrics(stock_data, growth)
    safety = compute_safety_metrics(stock_data, overlay)
    quality = compute_quality_metrics(stock_data, overlay)

    flat_metrics: dict[str, Any] = {
        "peg_ratio": valuation["peg_ratio"],
        "pegy_ratio": valuation["pegy_ratio"],
        "price_to_fair_value": valuation["price_to_fair_value"],
        "pb_ratio": valuation["pb_ratio"],
        "cash_to_debt": safety["cash_to_debt"],
        "net_debt_to_ebitda": safety["net_debt_to_ebitda"],
        "debt_to_equity": safety["debt_to_equity"],
        "interest_coverage": safety["interest_coverage"],
        "fcf_conversion_3y": safety["fcf_conversion_3y"],
        "inventory_vs_revenue_spread": safety["inventory_vs_revenue_spread"],
        "equity_to_assets": safety["equity_to_assets"],
        "earnings_stability_5y": safety["earnings_stability_5y"],
        "payout_sustainability": safety["payout_sustainability"],
        "roic_5y_avg": quality["roic_5y_avg"],
        "roe_5y_avg": quality["roe_5y_avg"],
        "gross_margin_trend_5y": quality["gross_margin_trend_5y"],
        "operating_margin_trend_5y": quality["operating_margin_trend_5y"],
        "revenue_consistency_5y": quality["revenue_consistency_5y"],
        "rd_productivity_3y": quality["rd_productivity_3y"],
    }

    return {
        "overlay": overlay,
        "growth": growth,
        "valuation": valuation,
        "safety": safety,
        "quality": quality,
        "flat_metrics": flat_metrics,
    }
