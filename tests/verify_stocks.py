"""Phase 1 CLI verification script for Lynch & Fisher equity research engine.

Tests live market data for NVDA, KO, XOM, and JPM, validates SQLite caching,
manual category overrides, strict JSON serializability, and synthetic edge cases.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Ensure UTF-8 stdout on Windows and allow running directly as a script.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.data_fetcher import StockDataFetcher
from core.scoring_engine import analyze_stock

BENCHMARK_TICKERS = ["NVDA", "KO", "XOM", "JPM"]


def _fmt_val(val: float | None, fmt_type: str) -> str:
    if val is None:
        return "N/A"
    if fmt_type in {"percent", "spread_pct", "consistency"}:
        return f"{val * 100:.2f}%"
    if fmt_type == "pp_per_year":
        return f"{val:+.2f} pp/yr"
    if fmt_type == "ratio_x":
        return f"{val:.2f}x"
    return f"{val:.2f}"


def _fmt_pct(val: float | None) -> str:
    return f"{val * 100:.2f}%" if val is not None else "N/A"


def _fmt_num(val: float | None, suffix: str = "") -> str:
    return f"{val:.2f}{suffix}" if val is not None else "N/A"


def print_stock_report(result: dict[str, Any]) -> None:
    ticker = result["ticker"]
    profile = result["profile"]
    market = result["market"]
    cls = result["classification"]
    ov = result["sector_overlay"]
    gr = result["growth_summary"]
    val = result["valuation_summary"]
    summary = result["scoring_summary"]
    rf = result["red_flags"]

    line = "=" * 96
    subline = "-" * 96
    print(line)
    print(
        f"[{ticker}] {profile.get('company_name')} | Sector: {profile.get('sector')} "
        f"| Industry: {profile.get('industry')}"
    )
    print(
        f"Category: {cls['active_category']} (Auto: {cls['auto_category']}, "
        f"Overridden: {cls['is_overridden']}) | Overlay: {ov['overlay']}"
    )
    print(f"Rationale: {cls['rationale_th']}")
    print(subline)

    mcap_b = (market["market_cap"] / 1e9) if market.get("market_cap") else None
    print(
        f"Price: {_fmt_num(market.get('current_price'))} {market.get('currency', 'USD')} | "
        f"Market Cap: {_fmt_num(mcap_b, 'B')} | "
        f"EPS TTM: {_fmt_num(gr.get('eps_ttm'))} | "
        f"P/E TTM: {_fmt_num(val.get('pe_ttm'), 'x')} | "
        f"Div Yield: {_fmt_pct(val.get('dividend_yield'))}"
    )
    print(
        f"Growth -> Hist: {_fmt_pct(gr.get('hist_growth'))} ({gr.get('hist_growth_source')}) | "
        f"Fwd: {_fmt_pct(gr.get('forward_growth'))} ({gr.get('forward_growth_source')}) | "
        f"Blended g: {_fmt_pct(gr.get('blended_growth'))} | "
        f"FV Multiple (cap 25x): {_fmt_num(val.get('lynch_fair_value_multiple'), 'x')} | "
        f"Lynch FV: {_fmt_num(val.get('lynch_fair_value'))}"
    )
    print(subline)
    print(
        f"{'Pillar / Metric':<36} {'Value':>14} {'Score':>8} {'Weight':>8} "
        f"{'Status':<20} {'Notes'}"
    )
    print(subline)

    for pillar_id in ["lynch_valuation", "lynch_safety", "fisher_quality"]:
        p = result["pillars"][pillar_id]
        p_score_str = f"{p['score']:.2f}" if p["score"] is not None else "N/A"
        print(
            f">> {p['label_en']} (Cat Wt: {p['category_weight']:.0f}%, "
            f"Eff Wt: {p['effective_category_weight']:.1f}%, "
            f"Cov: {p['coverage_pct']:.1f}%) -> Pillar Score: {p_score_str}"
        )
        for m in p["metrics"]:
            v_str = _fmt_val(m["value"], m["format_type"])
            s_str = f"{m['score']:.2f}" if m["score"] is not None else "N/A"
            w_str = (
                f"{m['effective_weight_in_pillar']:.1f}%"
                if m["status"] == "scored"
                else "-"
            )
            print(
                f"   {m['label_en']:<33} {v_str:>14} {s_str:>8} {w_str:>8} "
                f"{m['status']:<20} {m['note_th']}"
            )

    print(subline)
    hard_labels = (
        ", ".join(f"{f['label_en']} ({f['penalty']:+.0f})" for f in rf["hard_flags"])
        if rf["hard_flags"]
        else "None"
    )
    warn_labels = (
        ", ".join(w["label_en"] for w in rf["warnings"]) if rf["warnings"] else "None"
    )
    print(f"Hard Red Flags: {hard_labels}")
    print(f"Warnings:       {warn_labels}")
    print(
        f"SUMMARY -> Raw Score: {summary['raw_score']:.2f} | "
        f"Penalty: {summary['red_flag_penalty']:+.2f} | "
        f"FINAL SCORE: {summary['final_score']:.2f} [{summary['signal'].upper()}] | "
        f"Data Coverage: {summary['data_coverage_pct']:.2f}%"
    )
    print(line)
    print()


def run_synthetic_edge_case_tests() -> None:
    """Validate critical financial edge cases using deterministic synthetic fixtures."""
    print("Running synthetic edge-case unit checks...")

    # 1. Negative equity swaps D/E to Interest Coverage; g <= 0 yields N/A for PEG/PEGY/FV.
    neg_eq_stock = {
        "ticker": "SYN_NEGEQ",
        "profile": {
            "ticker": "SYN_NEGEQ",
            "company_name": "Synthetic Negative Equity Corp",
            "sector": "Consumer Cyclical",
            "industry": "Restaurants",
            "market_cap": 10_000_000_000.0,
            "dividend_yield": 0.02,
            "forward_growth": -0.05,
            "forward_growth_source": "synthetic",
        },
        "market": {
            "current_price": 100.0,
            "previous_close": 99.0,
            "change_pct": 0.01,
            "market_cap": 10_000_000_000.0,
            "currency": "USD",
        },
        "price_history_5y": [{"date": "2024-01-01", "close": 100.0}],
        "annual_statements": [
            {
                "date": "2022-12-31",
                "revenue": 1_000_000_000.0,
                "gross_profit": 400_000_000.0,
                "operating_income": 200_000_000.0,
                "ebit": 200_000_000.0,
                "ebitda": 240_000_000.0,
                "net_income": 120_000_000.0,
                "diluted_eps": 5.0,
                "diluted_shares": 24_000_000.0,
                "interest_expense": 20_000_000.0,
                "cash_and_equivalents": 150_000_000.0,
                "total_debt": 500_000_000.0,
                "total_equity": -100_000_000.0,
                "total_assets": 900_000_000.0,
                "inventory": 10_000_000.0,
                "free_cash_flow": 110_000_000.0,
            },
            {
                "date": "2023-12-31",
                "revenue": 950_000_000.0,
                "gross_profit": 380_000_000.0,
                "operating_income": 180_000_000.0,
                "ebit": 180_000_000.0,
                "ebitda": 220_000_000.0,
                "net_income": 100_000_000.0,
                "diluted_eps": 4.2,
                "diluted_shares": 23_800_000.0,
                "interest_expense": 20_000_000.0,
                "cash_and_equivalents": 140_000_000.0,
                "total_debt": 500_000_000.0,
                "total_equity": -120_000_000.0,
                "total_assets": 880_000_000.0,
                "inventory": 10_000_000.0,
                "free_cash_flow": 95_000_000.0,
            },
        ],
        "quarterly_statements": [],
    }
    res_negeq = analyze_stock(neg_eq_stock)
    json.dumps(res_negeq, allow_nan=False)
    safety_map = {
        m["metric_id"]: m for m in res_negeq["pillars"]["lynch_safety"]["metrics"]
    }
    val_map = {
        m["metric_id"]: m for m in res_negeq["pillars"]["lynch_valuation"]["metrics"]
    }
    assert safety_map["debt_to_equity"]["status"] == "skipped_inapplicable"
    assert "Interest Coverage" in safety_map["debt_to_equity"]["note_th"]
    assert safety_map["interest_coverage"]["status"] == "scored"
    assert val_map["peg_ratio"]["value"] is None
    assert val_map["pegy_ratio"]["value"] is None
    assert res_negeq["valuation_summary"]["lynch_fair_value"] is None

    # 2. All 3 hard red flags trigger (-10, -8, -10 => -28 total penalty).
    red_flag_stock = {
        "ticker": "SYN_RED",
        "profile": {
            "ticker": "SYN_RED",
            "company_name": "Synthetic Red Flag Corp",
            "sector": "Industrials",
            "industry": "Specialty Industrial Machinery",
            "market_cap": 2_000_000_000.0,
            "dividend_yield": 0.0,
            "forward_growth": 0.15,
            "forward_growth_source": "synthetic",
        },
        "market": {
            "current_price": 40.0,
            "previous_close": 40.0,
            "change_pct": 0.0,
            "market_cap": 2_000_000_000.0,
            "currency": "USD",
        },
        "price_history_5y": [{"date": "2024-01-01", "close": 40.0}],
        "annual_statements": [
            {
                "date": "2022-12-31",
                "revenue": 500_000_000.0,
                "gross_profit": 150_000_000.0,
                "operating_income": 50_000_000.0,
                "ebit": 50_000_000.0,
                "ebitda": 70_000_000.0,
                "net_income": 30_000_000.0,
                "diluted_eps": 1.0,
                "diluted_shares": 30_000_000.0,
                "interest_expense": 5_000_000.0,
                "cash_and_equivalents": 40_000_000.0,
                "total_debt": 100_000_000.0,
                "total_equity": 300_000_000.0,
                "total_assets": 600_000_000.0,
                "inventory": 80_000_000.0,
                "free_cash_flow": -20_000_000.0,
            },
            {
                "date": "2023-12-31",
                "revenue": 520_000_000.0,
                "gross_profit": 160_000_000.0,
                "operating_income": 60_000_000.0,
                "ebit": 60_000_000.0,
                "ebitda": 80_000_000.0,
                "net_income": 40_000_000.0,
                "diluted_eps": 1.1,
                "diluted_shares": 36_000_000.0,
                "interest_expense": 5_000_000.0,
                "cash_and_equivalents": 45_000_000.0,
                "total_debt": 120_000_000.0,
                "total_equity": 320_000_000.0,
                "total_assets": 650_000_000.0,
                "inventory": 120_000_000.0,
                "free_cash_flow": -25_000_000.0,
            },
        ],
        "quarterly_statements": [],
    }
    res_rf = analyze_stock(red_flag_stock)
    json.dumps(res_rf, allow_nan=False)
    flag_ids = {f["id"] for f in res_rf["red_flags"]["hard_flags"]}
    assert flag_ids == {
        "inventory_pileup",
        "heavy_share_dilution",
        "earnings_fcf_divergence",
    }
    assert res_rf["scoring_summary"]["red_flag_penalty"] == -28.0

    # 3. REIT overlay skips Inventory and standard D/E.
    reit_stock = {
        "ticker": "SYN_REIT",
        "profile": {
            "ticker": "SYN_REIT",
            "company_name": "Synthetic Realty Income REIT",
            "sector": "Real Estate",
            "industry": "REIT - Retail",
            "market_cap": 5_000_000_000.0,
            "dividend_yield": 0.05,
            "forward_growth": 0.04,
            "forward_growth_source": "synthetic",
        },
        "market": {
            "current_price": 50.0,
            "previous_close": 49.5,
            "change_pct": 0.01,
            "market_cap": 5_000_000_000.0,
            "currency": "USD",
        },
        "price_history_5y": [{"date": "2024-01-01", "close": 50.0}],
        "annual_statements": [
            {
                "date": "2022-12-31",
                "revenue": 400_000_000.0,
                "gross_profit": 280_000_000.0,
                "operating_income": 180_000_000.0,
                "ebit": 180_000_000.0,
                "ebitda": 240_000_000.0,
                "net_income": 100_000_000.0,
                "diluted_eps": 1.5,
                "diluted_shares": 66_000_000.0,
                "interest_expense": 40_000_000.0,
                "cash_and_equivalents": 50_000_000.0,
                "total_debt": 800_000_000.0,
                "total_equity": 1_500_000_000.0,
                "total_assets": 2_500_000_000.0,
                "inventory": 200_000_000.0,
                "free_cash_flow": 150_000_000.0,
            },
            {
                "date": "2023-12-31",
                "revenue": 430_000_000.0,
                "gross_profit": 300_000_000.0,
                "operating_income": 195_000_000.0,
                "ebit": 195_000_000.0,
                "ebitda": 260_000_000.0,
                "net_income": 115_000_000.0,
                "diluted_eps": 1.65,
                "diluted_shares": 69_000_000.0,
                "interest_expense": 42_000_000.0,
                "cash_and_equivalents": 60_000_000.0,
                "total_debt": 820_000_000.0,
                "total_equity": 1_550_000_000.0,
                "total_assets": 2_600_000_000.0,
                "inventory": 220_000_000.0,
                "free_cash_flow": 160_000_000.0,
            },
        ],
        "quarterly_statements": [],
    }
    res_reit = analyze_stock(reit_stock)
    json.dumps(res_reit, allow_nan=False)
    assert res_reit["sector_overlay"]["overlay"] == "reit"
    reit_safety = {
        m["metric_id"]: m for m in res_reit["pillars"]["lynch_safety"]["metrics"]
    }
    assert reit_safety["debt_to_equity"]["status"] == "skipped_inapplicable"
    assert reit_safety["inventory_vs_revenue_spread"]["status"] == "skipped_inapplicable"
    print("Synthetic edge-case unit checks: PASSED\n")


def main() -> int:
    fetcher = StockDataFetcher()
    results: dict[str, dict[str, Any]] = {}

    for ticker in BENCHMARK_TICKERS:
        stock_data = fetcher.get_stock_data(ticker, force_refresh=True)
        res = analyze_stock(stock_data)
        json.dumps(res, allow_nan=False)
        results[ticker] = res
        print_stock_report(res)

    # Benchmark assertions on live outputs.
    nvda = results["NVDA"]
    assert nvda["classification"]["active_category"] == "Fast Growers", (
        f"Expected NVDA Fast Growers, got {nvda['classification']['active_category']}"
    )
    fv_mult = nvda["valuation_summary"]["lynch_fair_value_multiple"]
    assert fv_mult is not None and fv_mult <= 25.0, (
        f"NVDA FV multiple exceeded 25x cap: {fv_mult}"
    )
    assert nvda["valuation_summary"]["dividend_yield"] < 0.01, (
        f"NVDA dividend_yield suspiciously high: {nvda['valuation_summary']['dividend_yield']}"
    )
    nvda_dil = nvda["safety_summary"]["share_dilution_cagr"]
    assert nvda_dil is None or nvda_dil <= 0.05, (
        f"NVDA false share dilution triggered: {nvda_dil}"
    )

    xom = results["XOM"]
    assert xom["classification"]["active_category"] == "Cyclicals", (
        f"Expected XOM Cyclicals, got {xom['classification']['active_category']}"
    )

    jpm = results["JPM"]
    assert jpm["sector_overlay"]["overlay"] == "financials", (
        f"Expected JPM financials overlay, got {jpm['sector_overlay']['overlay']}"
    )
    jpm_safety = {
        m["metric_id"]: m for m in jpm["pillars"]["lynch_safety"]["metrics"]
    }
    assert jpm_safety["inventory_vs_revenue_spread"]["status"] == "skipped_inapplicable"
    assert jpm_safety["debt_to_equity"]["status"] == "skipped_inapplicable"

    # Manual category override test on KO -> Stalwarts (30/30/40).
    ko_data = fetcher.get_stock_data("KO", force_refresh=False)
    assert ko_data["cache_status"]["price_cached"] is True
    assert ko_data["cache_status"]["statements_cached"] is True

    ko_override = analyze_stock(ko_data, category_override="Stalwarts")
    assert ko_override["classification"]["active_category"] == "Stalwarts"
    assert ko_override["pillar_weights"] == {
        "lynch_valuation": 30,
        "lynch_safety": 30,
        "fisher_quality": 40,
    }
    print(
        f"Manual Override & Cache Test (KO): price_cached={ko_data['cache_status']['price_cached']}, "
        f"statements_cached={ko_data['cache_status']['statements_cached']}, "
        f"Stalwarts weights={ko_override['pillar_weights']}, "
        f"Override Final Score={ko_override['scoring_summary']['final_score']:.2f}"
    )

    # SQLite cache hit test on NVDA.
    nvda_cached = fetcher.get_stock_data("NVDA", force_refresh=False)
    assert nvda_cached["cache_status"]["price_cached"] is True
    assert nvda_cached["cache_status"]["statements_cached"] is True
    print(
        f"SQLite Cache Hit Test (NVDA): price_cached={nvda_cached['cache_status']['price_cached']}, "
        f"statements_cached={nvda_cached['cache_status']['statements_cached']}\n"
    )

    run_synthetic_edge_case_tests()
    print("ALL PHASE 1 VERIFICATION CHECKS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
