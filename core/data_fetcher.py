"""Cloud-resilient market & financial statement acquisition with SQLite caching and fallbacks.

Acquisition & fallback chain:
1. SQLite daily/weekly cache (data/market_cache.db)
2. yfinance with shared browser-impersonating curl_cffi session + retry/backoff
3. Direct Yahoo v8 chart endpoint (for 5Y price history)
4. Official SEC EDGAR APIs (submissions + XBRL companyfacts) for US fundamentals
5. Stale SQLite cache -> bundled data/seed_snapshot.json fallback
"""

from __future__ import annotations

from contextlib import contextmanager
import json
import math
import sqlite3
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, TypeVar

import pandas as pd
import requests
import yfinance as yf
from curl_cffi import requests as cffi_requests


class DataFetchError(Exception):
    """Raised when market or financial statement data cannot be fetched."""


_T = TypeVar("_T")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "market_cache.db"
SEED_SNAPSHOT_PATH = PROJECT_ROOT / "data" / "seed_snapshot.json"

PRICE_TTL = timedelta(hours=24)
STATEMENTS_TTL = timedelta(days=7)
SEC_CIK_TTL = timedelta(days=30)

SEC_HEADERS = {
    "User-Agent": "LynchFisherEquityResearch/1.0 (contact: research@lynchfisher.app)",
    "Accept": "application/json",
}
IMPERSONATE_PROFILES = ["chrome", "safari15_5", "edge"]

CURRENCY_SYMBOLS: dict[str, str] = {
    "USD": "$",
    "THB": "฿",
    "EUR": "€",
    "GBP": "£",
    "JPY": "¥",
    "HKD": "HK$",
    "SGD": "S$",
    "CNY": "¥",
}


def get_currency_symbol(currency_code: str | None) -> str:
    """Return compact currency symbol for USD, THB, EUR, GBP, JPY, HKD, SGD, CNY."""
    code = str(currency_code or "USD").strip().upper()
    if not code:
        return "$"
    return CURRENCY_SYMBOLS.get(code, f"{code} ")


def _infer_currency_from_ticker(ticker: str) -> str:
    upper = ticker.strip().upper()
    if upper.endswith(".BK"):
        return "THB"
    if upper.endswith(".T"):
        return "JPY"
    if upper.endswith(".HK"):
        return "HKD"
    if upper.endswith(".SI"):
        return "SGD"
    if upper.endswith(".L"):
        return "GBP"
    return "USD"


def _extract_latest_statement_meta(
    annual_records: list[dict[str, Any]],
    quarterly_records: list[dict[str, Any]],
) -> tuple[str, str]:
    """Return (latest_date_iso, human_readable_label) across quarterly/annual records."""
    best_q = quarterly_records[-1].get("date", "") if quarterly_records else ""
    best_a = annual_records[-1].get("date", "") if annual_records else ""

    if best_q and (not best_a or best_q >= best_a):
        try:
            dt = datetime.strptime(best_q[:10], "%Y-%m-%d")
            q_num = (dt.month - 1) // 3 + 1
            return best_q[:10], f"Q{q_num} {dt.year} ({best_q[:10]})"
        except Exception:
            return best_q[:10], best_q[:10]

    if best_a:
        try:
            dt = datetime.strptime(best_a[:10], "%Y-%m-%d")
            return best_a[:10], f"FY {dt.year} ({best_a[:10]})"
        except Exception:
            return best_a[:10], best_a[:10]

    return "", "N/A"


def _st_cache_data(ttl: int) -> Callable[[Callable[..., _T]], Callable[..., _T]]:
    """Apply @st.cache_data(ttl=ttl, show_spinner=False) when Streamlit is available."""
    try:
        import streamlit as st

        return st.cache_data(ttl=ttl, show_spinner=False)
    except Exception:
        def _identity(fn: Callable[..., _T]) -> Callable[..., _T]:
            return fn

        return _identity

# Canonical field -> ordered yfinance row label aliases.
INCOME_FIELD_ALIASES: dict[str, list[str]] = {
    "revenue": ["Total Revenue", "Operating Revenue", "TotalRevenue"],
    "gross_profit": ["Gross Profit", "GrossProfit"],
    "operating_income": ["Operating Income", "OperatingIncome", "EBIT"],
    "pretax_income": ["Pretax Income", "PretaxIncome"],
    "tax_provision": ["Tax Provision", "TaxProvision"],
    "net_income": [
        "Net Income Common Stockholders",
        "Net Income",
        "NetIncome",
        "Net Income Continuous Operations",
    ],
    "interest_expense": [
        "Interest Expense",
        "Interest Expense Non Operating",
        "Net Interest Income",
    ],
    "rd_expense": ["Research And Development", "ResearchAndDevelopment"],
    "ebit": ["EBIT", "Operating Income"],
    "ebitda": ["EBITDA", "Normalized EBITDA"],
    "diluted_eps": ["Diluted EPS", "DilutedEPS", "Basic EPS"],
    "diluted_shares": [
        "Diluted Average Shares",
        "DilutedAverageShares",
        "Basic Average Shares",
    ],
}

BALANCE_FIELD_ALIASES: dict[str, list[str]] = {
    "cash_and_equivalents": [
        "Cash Cash Equivalents And Short Term Investments",
        "Cash And Cash Equivalents",
        "CashCashEquivalentsAndShortTermInvestments",
    ],
    "total_debt": ["Total Debt", "TotalDebt"],
    "long_term_debt": ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"],
    "current_debt": ["Current Debt", "Current Debt And Capital Lease Obligation"],
    "total_equity": [
        "Stockholders Equity",
        "Total Equity Gross Minority Interest",
        "Common Stock Equity",
        "StockholdersEquity",
    ],
    "total_assets": ["Total Assets", "TotalAssets"],
    "inventory": ["Inventory", "Inventories"],
    "ordinary_shares": ["Ordinary Shares Number", "Share Issued"],
}

CASHFLOW_FIELD_ALIASES: dict[str, list[str]] = {
    "operating_cash_flow": [
        "Operating Cash Flow",
        "Cash Flow From Continuing Operating Activities",
        "Total Cash From Operating Activities",
    ],
    "capex": ["Capital Expenditure", "Capital Expenditures"],
    "free_cash_flow": ["Free Cash Flow", "FreeCashFlow"],
    "depreciation_amortization": [
        "Depreciation And Amortization",
        "Depreciation Amortization Depletion",
        "Reconciled Depreciation",
    ],
    "dividends_paid": ["Cash Dividends Paid", "Common Stock Dividend Paid"],
}

# SEC US-GAAP XBRL tag priority lists for annual 10-K fallback.
SEC_FLOW_TAGS: dict[str, list[str]] = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "InterestAndDividendIncomeOperating",
    ],
    "cost_of_revenue": [
        "CostOfGoodsAndServicesSold",
        "CostOfRevenue",
        "CostOfGoodsSold",
    ],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncomeLoss"],
    "pretax_income": [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ],
    "tax_provision": ["IncomeTaxExpenseBenefit"],
    "net_income": [
        "NetIncomeLoss",
        "ProfitLoss",
        "NetIncomeLossAvailableToCommonStockholdersBasic",
    ],
    "interest_expense": [
        "InterestExpense",
        "InterestExpenseNonoperating",
        "InterestExpenseDebt",
    ],
    "rd_expense": [
        "ResearchAndDevelopmentExpense",
        "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
    ],
    "depreciation_amortization": [
        "DepreciationDepletionAndAmortization",
        "DepreciationAndAmortization",
        "Depreciation",
    ],
    "diluted_eps": ["EarningsPerShareDiluted", "EarningsPerShareBasic"],
    "diluted_shares": [
        "WeightedAverageNumberOfDilutedSharesOutstanding",
        "WeightedAverageNumberOfSharesOutstandingBasic",
    ],
    "operating_cash_flow": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
    ],
    "dividends_paid": [
        "PaymentsOfDividends",
        "PaymentsOfDividendsCommonStock",
    ],
}

SEC_INSTANT_TAGS: dict[str, list[str]] = {
    "cash_and_equivalents": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        "CashAndDueFromBanks",
    ],
    "short_term_investments": [
        "MarketableSecuritiesCurrent",
        "ShortTermInvestments",
        "AvailableForSaleSecuritiesCurrent",
    ],
    "total_debt": ["LongTermDebtAndCapitalLeaseObligations", "DebtAndCapitalLeaseObligations"],
    "long_term_debt": [
        "LongTermDebtNoncurrent",
        "LongTermDebt",
        "LongTermDebtAndCapitalLeaseObligations",
    ],
    "current_debt": [
        "LongTermDebtCurrent",
        "ShortTermBorrowings",
        "DebtCurrent",
    ],
    "total_equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "total_assets": ["Assets"],
    "inventory": ["InventoryNet", "InventoryFinishedGoodsNetOfReserves"],
    "ordinary_shares": ["CommonStockSharesOutstanding", "EntityCommonStockSharesOutstanding"],
}


def _clean_float(val: Any) -> float | None:
    """Convert any numeric scalar to a finite Python float, or None."""
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    try:
        num = float(val)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(num):
        return None
    return num


def _clean_str(val: Any, default: str = "") -> str:
    if val is None:
        return default
    text = str(val).strip()
    return text if text else default


def _parse_iso_utc(ts_str: str) -> datetime:
    dt = datetime.fromisoformat(ts_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _resolve_writable_db_path(db_path: Path) -> Path:
    """Ensure parent directory exists, falling back to OS temp dir if read-only."""
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return db_path
    except OSError:
        fallback = Path(tempfile.gettempdir()) / "lynch_fisher_data" / db_path.name
        fallback.parent.mkdir(parents=True, exist_ok=True)
        return fallback


def _build_cffi_session(impersonate: str = "chrome") -> cffi_requests.Session:
    return cffi_requests.Session(impersonate=impersonate)


def _retry_yahoo(fn: Callable[[], _T], attempts: int = 3) -> _T:
    """Retry transient / rate-limit Yahoo calls with exponential backoff."""
    delays = [0.8, 2.0]
    last_exc: Exception | None = None
    for idx in range(attempts):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            msg = str(exc).lower()
            is_retryable = any(
                k in msg
                for k in ["rate limit", "too many requests", "429", "timeout", "timed out", "connection"]
            )
            if idx >= attempts - 1 or not is_retryable:
                raise
            time.sleep(delays[min(idx, len(delays) - 1)])
    assert last_exc is not None
    raise last_exc


def _map_sic_to_sector_industry(sic_raw: Any, sic_desc: str) -> tuple[str, str]:
    """Map SEC SIC code to canonical Yahoo-style sector & industry labels."""
    desc = _clean_str(sic_desc, "Unknown")
    try:
        sic = int(sic_raw)
    except (TypeError, ValueError):
        return "Unknown", desc

    if sic == 6798:
        return "Real Estate", f"REIT - {desc}" if "reit" not in desc.lower() else desc
    if 6500 <= sic <= 6599:
        return "Real Estate", desc
    if 6000 <= sic <= 6799:
        return "Financial Services", desc
    if 1300 <= sic <= 1399 or sic in {2911, 2990, 4922, 4923, 4924}:
        return "Energy", desc
    if 1000 <= sic <= 1299 or 1400 <= sic <= 1499 or 2600 <= sic <= 2699 or 2800 <= sic <= 2829 or 2860 <= sic <= 2879 or 3300 <= sic <= 3399:
        return "Basic Materials", desc
    if 4900 <= sic <= 4999:
        return "Utilities", desc
    if 2830 <= sic <= 2839 or 3840 <= sic <= 3859 or 8000 <= sic <= 8099:
        return "Healthcare", desc
    if 3570 <= sic <= 3579 or 3660 <= sic <= 3679 or 7370 <= sic <= 7379:
        return "Technology", desc
    if 4800 <= sic <= 4899 or 7800 <= sic <= 7849:
        return "Communication Services", desc
    if 2000 <= sic <= 2199 or 2840 <= sic <= 2849 or 5400 <= sic <= 5499:
        return "Consumer Defensive", desc
    if 2300 <= sic <= 2399 or 3710 <= sic <= 3719 or 5200 <= sic <= 5999 or 7000 <= sic <= 7099:
        return "Consumer Cyclical", desc
    return "Industrials", desc


def _extract_row_value(df: pd.DataFrame, col: Any, aliases: list[str]) -> float | None:
    if df is None or df.empty or col not in df.columns:
        return None
    index_map = {str(idx).strip().lower(): idx for idx in df.index}
    for alias in aliases:
        if alias in df.index:
            val = _clean_float(df.at[alias, col])
            if val is not None:
                return val
        lower_alias = alias.lower()
        if lower_alias in index_map:
            val = _clean_float(df.at[index_map[lower_alias], col])
            if val is not None:
                return val
    return None


def _finalize_statement_record(rec: dict[str, Any]) -> dict[str, Any]:
    """Compute derived fallbacks and normalize sign conventions on one record."""
    if rec.get("gross_profit") is None:
        rev = rec.get("revenue")
        cost = rec.get("cost_of_revenue")
        if rev is not None and cost is not None:
            rec["gross_profit"] = rev - cost

    if rec.get("diluted_eps") is None:
        ni = rec.get("net_income")
        shares = rec.get("diluted_shares") or rec.get("ordinary_shares")
        if ni is not None and shares is not None and shares > 0:
            rec["diluted_eps"] = ni / shares

    if rec.get("free_cash_flow") is None:
        ocf = rec.get("operating_cash_flow")
        capex = rec.get("capex")
        if ocf is not None and capex is not None:
            rec["free_cash_flow"] = ocf - abs(capex)

    if rec.get("total_debt") is None:
        ltd = rec.get("long_term_debt")
        cd = rec.get("current_debt")
        if ltd is not None or cd is not None:
            rec["total_debt"] = (ltd or 0.0) + (cd or 0.0)

    if rec.get("ebit") is None:
        rec["ebit"] = rec.get("operating_income")

    if rec.get("ebitda") is None:
        op_inc = rec.get("operating_income")
        da = rec.get("depreciation_amortization")
        if op_inc is not None and da is not None:
            rec["ebitda"] = op_inc + abs(da)

    if rec.get("dividends_paid") is not None:
        rec["dividends_paid"] = abs(rec["dividends_paid"])

    if rec.get("interest_expense") is not None:
        rec["interest_expense"] = abs(rec["interest_expense"])

    return rec


def _normalize_statements(
    income_df: pd.DataFrame | None,
    balance_df: pd.DataFrame | None,
    cashflow_df: pd.DataFrame | None,
) -> list[dict[str, Any]]:
    """Merge and normalize statement DataFrames into oldest->newest records."""
    period_map: dict[str, dict[str, Any]] = {}

    def _register_columns(df: pd.DataFrame | None) -> list[tuple[str, Any]]:
        pairs: list[tuple[str, Any]] = []
        if df is None or df.empty:
            return pairs
        for col in df.columns:
            try:
                ts = pd.Timestamp(col)
                if pd.isna(ts):
                    continue
                date_key = ts.strftime("%Y-%m-%d")
            except Exception:
                date_key = str(col)[:10]
            pairs.append((date_key, col))
            if date_key not in period_map:
                period_map[date_key] = {"date": date_key}
        return pairs

    inc_cols = _register_columns(income_df)
    bal_cols = _register_columns(balance_df)
    cf_cols = _register_columns(cashflow_df)

    for date_key, col in inc_cols:
        rec = period_map[date_key]
        for field, aliases in INCOME_FIELD_ALIASES.items():
            rec[field] = _extract_row_value(income_df, col, aliases)

    for date_key, col in bal_cols:
        rec = period_map[date_key]
        for field, aliases in BALANCE_FIELD_ALIASES.items():
            rec[field] = _extract_row_value(balance_df, col, aliases)

    for date_key, col in cf_cols:
        rec = period_map[date_key]
        for field, aliases in CASHFLOW_FIELD_ALIASES.items():
            rec[field] = _extract_row_value(cashflow_df, col, aliases)

    return [_finalize_statement_record(period_map[dk]) for dk in sorted(period_map.keys())]


def _extract_dividend_yield(info: dict[str, Any], current_price: float | None) -> float:
    """Normalize dividend yield to a decimal fraction (e.g., 0.03 = 3%)."""
    if current_price is not None and current_price > 0:
        div_rate = _clean_float(info.get("dividendRate"))
        if div_rate is not None and div_rate >= 0:
            return div_rate / current_price

        trailing_rate = _clean_float(info.get("trailingAnnualDividendRate"))
        if trailing_rate is not None and trailing_rate >= 0:
            return trailing_rate / current_price

    trailing_yield = _clean_float(info.get("trailingAnnualDividendYield"))
    if trailing_yield is not None and trailing_yield >= 0:
        if trailing_yield > 0.25:
            return trailing_yield / 100.0
        return trailing_yield

    raw_yield = _clean_float(info.get("dividendYield"))
    if raw_yield is not None and raw_yield >= 0:
        return raw_yield / 100.0

    return 0.0


def _extract_forward_growth(
    ticker_obj: yf.Ticker, info: dict[str, Any]
) -> tuple[float | None, str]:
    """Defensively extract forward EPS growth estimate across yfinance versions."""
    try:
        ge = ticker_obj.growth_estimates
        if isinstance(ge, pd.DataFrame) and not ge.empty:
            stock_col = None
            for candidate in ["stockTrend", "stock", info.get("symbol", "")]:
                for col in ge.columns:
                    if str(col).strip().lower() == str(candidate).strip().lower():
                        stock_col = col
                        break
                if stock_col is not None:
                    break
            if stock_col is None:
                stock_col = ge.columns[0]

            idx_lower = {str(i).strip().lower(): i for i in ge.index}
            for key in ["+5y", "5y", "ltg", "next 5 years (per annum)", "+1y", "1y"]:
                if key in idx_lower:
                    val = _clean_float(ge.at[idx_lower[key], stock_col])
                    if val is not None and -0.50 <= val <= 1.50:
                        return val, f"growth_estimates:{key}"
    except Exception:
        pass

    try:
        ee = ticker_obj.earnings_estimate
        if isinstance(ee, pd.DataFrame) and not ee.empty:
            idx_lower = {str(i).strip().lower(): i for i in ee.index}
            col_lower = {str(c).strip().lower(): c for c in ee.columns}

            if "growth" in col_lower and "+1y" in idx_lower:
                val = _clean_float(ee.at[idx_lower["+1y"], col_lower["growth"]])
                if val is not None and -0.50 <= val <= 1.50:
                    return val, "earnings_estimate:+1y_growth"

            if "avg" in col_lower and "0y" in idx_lower and "+1y" in idx_lower:
                eps_0y = _clean_float(ee.at[idx_lower["0y"], col_lower["avg"]])
                eps_1y = _clean_float(ee.at[idx_lower["+1y"], col_lower["avg"]])
                if eps_0y is not None and eps_1y is not None and eps_0y > 0:
                    implied = (eps_1y / eps_0y) - 1.0
                    if -0.50 <= implied <= 1.50:
                        return implied, "earnings_estimate:0y_to_+1y"
    except Exception:
        pass

    fwd_eps = _clean_float(info.get("forwardEps"))
    trl_eps = _clean_float(info.get("trailingEps"))
    if fwd_eps is not None and trl_eps is not None and trl_eps > 0:
        implied = (fwd_eps / trl_eps) - 1.0
        if -0.50 <= implied <= 1.50:
            return implied, "info:forwardEps_vs_trailingEps"

    eg = _clean_float(info.get("earningsGrowth"))
    if eg is not None and -0.50 <= eg <= 1.50:
        return eg, "info:earningsGrowth"

    return None, "unavailable"


def _parse_sec_annual_facts(facts_json: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract normalized annual 10-K/20-F statements from SEC companyfacts JSON."""
    us_gaap = facts_json.get("facts", {}).get("us-gaap", {})
    dei = facts_json.get("facts", {}).get("dei", {})
    annual_forms = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F"}

    def _collect_flow(tag_list: list[str]) -> dict[str, float]:
        merged: dict[str, tuple[int, str, float]] = {}
        for prio, tag in enumerate(tag_list):
            node = us_gaap.get(tag)
            if not node:
                continue
            units = node.get("units", {})
            unit_key = next(
                (k for k in ["USD", "USD/shares", "shares"] if k in units),
                None,
            )
            if not unit_key:
                continue
            for item in units[unit_key]:
                if item.get("form") not in annual_forms:
                    continue
                start_s = item.get("start")
                end_s = item.get("end")
                val = _clean_float(item.get("val"))
                if not start_s or not end_s or val is None:
                    continue
                try:
                    d_start = datetime.strptime(start_s[:10], "%Y-%m-%d")
                    d_end = datetime.strptime(end_s[:10], "%Y-%m-%d")
                    days = (d_end - d_start).days
                except Exception:
                    continue
                if not (300 <= days <= 400):
                    continue
                dt_key = end_s[:10]
                filed = str(item.get("filed", ""))
                prev = merged.get(dt_key)
                # Prefer latest filing date; break ties by tag priority.
                if prev is None or (filed, -prio) > (prev[1], -prev[0]):
                    merged[dt_key] = (prio, filed, val)
        return {dt: val for dt, (_, _, val) in merged.items()}

    def _collect_instant(tag_list: list[str]) -> list[tuple[str, str, float]]:
        by_end: dict[str, tuple[int, str, float]] = {}
        for prio, tag in enumerate(tag_list):
            node = us_gaap.get(tag) or dei.get(tag)
            if not node:
                continue
            units = node.get("units", {})
            unit_key = next((k for k in ["USD", "shares"] if k in units), None)
            if not unit_key:
                continue
            for item in units[unit_key]:
                if item.get("form") not in annual_forms:
                    continue
                end_s = item.get("end")
                val = _clean_float(item.get("val"))
                if not end_s or val is None or item.get("start"):
                    continue
                dt_key = end_s[:10]
                filed = str(item.get("filed", ""))
                prev = by_end.get(dt_key)
                if prev is None or (filed, -prio) > (prev[1], -prev[0]):
                    by_end[dt_key] = (prio, filed, val)
        return sorted((dt, filed, val) for dt, (_, filed, val) in by_end.items())

    flow_series = {field: _collect_flow(tags) for field, tags in SEC_FLOW_TAGS.items()}
    anchor_dates = sorted(
        set(flow_series.get("revenue", {}).keys())
        | set(flow_series.get("net_income", {}).keys())
    )
    if not anchor_dates:
        return []
    anchor_dates = anchor_dates[-5:]

    instant_series = {
        field: _collect_instant(tags) for field, tags in SEC_INSTANT_TAGS.items()
    }

    def _match_instant(entries: list[tuple[str, str, float]], target_dt: str) -> float | None:
        if not entries:
            return None
        try:
            t_dt = datetime.strptime(target_dt[:10], "%Y-%m-%d")
        except Exception:
            return None
        best_val: float | None = None
        best_diff = 999
        for dt_s, _, val in entries:
            try:
                d = datetime.strptime(dt_s[:10], "%Y-%m-%d")
            except Exception:
                continue
            diff = abs((d - t_dt).days)
            if diff <= 15 and diff < best_diff:
                best_diff = diff
                best_val = val
        return best_val

    records: list[dict[str, Any]] = []
    for dt in anchor_dates:
        rec: dict[str, Any] = {"date": dt}
        for field in SEC_FLOW_TAGS:
            rec[field] = flow_series.get(field, {}).get(dt)
        for field in SEC_INSTANT_TAGS:
            rec[field] = _match_instant(instant_series.get(field, []), dt)

        # Combine cash + short term marketable securities if both present.
        cash = rec.get("cash_and_equivalents")
        st_inv = rec.pop("short_term_investments", None)
        if cash is not None and st_inv is not None:
            rec["cash_and_equivalents"] = cash + st_inv

        records.append(_finalize_statement_record(rec))

    # Normalize pre-split vs post-split diluted_eps and shares relative to latest FY.
    latest_sh = _clean_float(records[-1].get("diluted_shares")) or _clean_float(
        records[-1].get("ordinary_shares")
    )
    if latest_sh is not None and latest_sh > 0:
        for rec in records[:-1]:
            sh = _clean_float(rec.get("diluted_shares")) or _clean_float(
                rec.get("ordinary_shares")
            )
            if sh is not None and sh > 0:
                ratio = latest_sh / sh
                if ratio >= 1.8:
                    split_factor = round(ratio)
                    if split_factor >= 2 and abs(ratio - split_factor) / split_factor < 0.20:
                        if rec.get("diluted_shares") is not None:
                            rec["diluted_shares"] = rec["diluted_shares"] * split_factor
                        if rec.get("ordinary_shares") is not None:
                            rec["ordinary_shares"] = rec["ordinary_shares"] * split_factor
                        if rec.get("diluted_eps") is not None:
                            rec["diluted_eps"] = rec["diluted_eps"] / split_factor

    return records


class StockDataFetcher:
    """Fetches, normalizes, and caches stock data in SQLite with multi-source fallbacks."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        target = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path = _resolve_writable_db_path(target)
        self._init_db()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=15.0)
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS price_cache (
                    ticker TEXT PRIMARY KEY,
                    fetched_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS statements_cache (
                    ticker TEXT PRIMARY KEY,
                    fetched_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sec_cik_cache (
                    cache_key TEXT PRIMARY KEY,
                    fetched_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def _read_cache(
        self, table: str, key: str, ttl: timedelta | None, key_col: str = "ticker"
    ) -> tuple[dict[str, Any] | None, str | None]:
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT fetched_at, payload_json FROM {table} WHERE {key_col} = ?",
                (key,),
            ).fetchone()
        if not row:
            return None, None
        fetched_at_str, payload_json = row
        try:
            if ttl is not None:
                fetched_dt = _parse_iso_utc(fetched_at_str)
                if datetime.now(timezone.utc) - fetched_dt > ttl:
                    return None, None
            return json.loads(payload_json), fetched_at_str
        except Exception:
            return None, None

    def _write_cache(
        self, table: str, key: str, payload: dict[str, Any], key_col: str = "ticker"
    ) -> str:
        now_iso = datetime.now(timezone.utc).isoformat()
        serialized = json.dumps(payload, allow_nan=False)
        with self._connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {table} ({key_col}, fetched_at, payload_json)
                VALUES (?, ?, ?)
                ON CONFLICT({key_col}) DO UPDATE SET
                    fetched_at = excluded.fetched_at,
                    payload_json = excluded.payload_json
                """,
                (key, now_iso, serialized),
            )
            conn.commit()
        return now_iso

    def _load_seed_snapshot(self, ticker: str) -> dict[str, Any] | None:
        if not SEED_SNAPSHOT_PATH.exists():
            return None
        try:
            raw = json.loads(SEED_SNAPSHOT_PATH.read_text(encoding="utf-8"))
            entry = raw.get(ticker)
            if isinstance(entry, dict) and entry.get("price") and entry.get("statements"):
                return entry
        except Exception:
            return None
        return None

    def _resolve_sec_cik(self, ticker: str) -> tuple[str | None, str | None]:
        """Look up 10-digit SEC CIK and official title for US-listed tickers."""
        cik_map, _ = self._read_cache(
            "sec_cik_cache", "company_tickers", SEC_CIK_TTL, key_col="cache_key"
        )
        if cik_map is None:
            resp = requests.get(
                "https://www.sec.gov/files/company_tickers.json",
                headers=SEC_HEADERS,
                timeout=12,
            )
            resp.raise_for_status()
            raw = resp.json()
            cik_map = {}
            for entry in raw.values():
                sym = str(entry.get("ticker", "")).strip().upper()
                cik_num = entry.get("cik_str")
                title = _clean_str(entry.get("title"), sym)
                if sym and cik_num is not None:
                    cik_map[sym] = {
                        "cik": str(cik_num).zfill(10),
                        "title": title,
                    }
            self._write_cache(
                "sec_cik_cache", "company_tickers", cik_map, key_col="cache_key"
            )

        hit = cik_map.get(ticker) or cik_map.get(ticker.replace("-", "."))
        if not hit:
            return None, None
        return hit["cik"], hit["title"]

    def _fetch_sec_profile_meta(self, ticker: str) -> dict[str, Any]:
        cik, title = self._resolve_sec_cik(ticker)
        if not cik:
            return {}
        try:
            sub = requests.get(
                f"https://data.sec.gov/submissions/CIK{cik}.json",
                headers=SEC_HEADERS,
                timeout=12,
            )
            sub.raise_for_status()
            j = sub.json()
            name = _clean_str(j.get("name"), title or ticker)
            sector, industry = _map_sic_to_sector_industry(
                j.get("sic"), _clean_str(j.get("sicDescription"), "Unknown")
            )
            return {
                "cik": cik,
                "company_name": name,
                "sector": sector,
                "industry": industry,
            }
        except Exception:
            return {"cik": cik, "company_name": title or ticker}

    def _fetch_sec_edgar_statements(
        self, ticker: str, current_price: float | None
    ) -> dict[str, Any]:
        """Fetch and normalize annual statements via official SEC EDGAR XBRL API."""
        meta = self._fetch_sec_profile_meta(ticker)
        cik = meta.get("cik")
        if not cik:
            raise DataFetchError(
                f"SEC EDGAR has no CIK mapping for ticker '{ticker}'."
            )
        facts_resp = requests.get(
            f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
            headers=SEC_HEADERS,
            timeout=20,
        )
        facts_resp.raise_for_status()
        annual_records = _parse_sec_annual_facts(facts_resp.json())
        if not annual_records:
            raise DataFetchError(
                f"SEC EDGAR returned no annual 10-K XBRL records for '{ticker}'."
            )

        latest = annual_records[-1]
        shares = _clean_float(latest.get("diluted_shares")) or _clean_float(
            latest.get("ordinary_shares")
        )
        market_cap = (
            current_price * shares
            if current_price is not None and shares is not None and shares > 0
            else None
        )
        equity = _clean_float(latest.get("total_equity"))
        pb_ratio = (
            market_cap / equity
            if market_cap is not None and equity is not None and equity > 0
            else None
        )
        div_paid = _clean_float(latest.get("dividends_paid"))
        div_yield = 0.0
        if (
            div_paid is not None
            and div_paid > 0
            and shares is not None
            and shares > 0
            and current_price is not None
            and current_price > 0
        ):
            div_yield = (div_paid / shares) / current_price

        ni = _clean_float(latest.get("net_income"))
        payout = div_paid / ni if div_paid is not None and ni is not None and ni > 0 else None

        profile = {
            "ticker": ticker,
            "company_name": meta.get("company_name", ticker),
            "sector": meta.get("sector", "Unknown"),
            "industry": meta.get("industry", "Unknown"),
            "exchange": "US",
            "quote_type": "EQUITY",
            "market_cap": market_cap,
            "shares_outstanding": shares,
            "trailing_eps_info": _clean_float(latest.get("diluted_eps")),
            "forward_eps_info": None,
            "book_value_per_share": (
                equity / shares if equity is not None and shares is not None and shares > 0 else None
            ),
            "price_to_book_info": pb_ratio,
            "dividend_rate": (
                div_paid / shares if div_paid is not None and shares is not None and shares > 0 else None
            ),
            "dividend_yield": div_yield,
            "payout_ratio_info": payout,
            "forward_growth": None,
            "forward_growth_source": "unavailable (sec_edgar_fallback)",
            "source_tag": "sec_edgar",
        }
        return {
            "profile": profile,
            "annual_statements": annual_records,
            "quarterly_statements": [],
        }

    def _fetch_price_v8_direct(
        self, ticker: str, session: cffi_requests.Session
    ) -> dict[str, Any]:
        """Direct Yahoo v8 chart JSON fallback using browser-impersonating curl_cffi."""
        last_exc: Exception | None = None
        for host in ["query2.finance.yahoo.com", "query1.finance.yahoo.com"]:
            url = f"https://{host}/v8/finance/chart/{ticker}?range=5y&interval=1wk"
            try:
                resp = session.get(url, timeout=12)
                if resp.status_code == 429:
                    time.sleep(1.0)
                    continue
                resp.raise_for_status()
                body = resp.json()
                result = body["chart"]["result"][0]
                meta = result.get("meta", {})
                timestamps = result.get("timestamp", [])
                quote = result.get("indicators", {}).get("quote", [{}])[0]
                closes = quote.get("close", [])
                price_history: list[dict[str, Any]] = []
                for ts, cl in zip(timestamps, closes):
                    c_val = _clean_float(cl)
                    if c_val is None or c_val <= 0:
                        continue
                    dt_str = datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")
                    price_history.append({"date": dt_str, "close": round(c_val, 4)})
                if not price_history:
                    continue

                current_price = _clean_float(meta.get("regularMarketPrice")) or price_history[-1]["close"]
                previous_close = _clean_float(meta.get("previousClose") or meta.get("chartPreviousClose"))
                if previous_close is None and len(price_history) >= 2:
                    previous_close = price_history[-2]["close"]

                change_pct = (
                    (current_price - previous_close) / previous_close
                    if current_price is not None and previous_close is not None and previous_close > 0
                    else None
                )
                return {
                    "ticker": ticker,
                    "current_price": current_price,
                    "previous_close": previous_close,
                    "change_pct": change_pct,
                    "market_cap": None,
                    "fifty_two_week_high": _clean_float(meta.get("fiftyTwoWeekHigh")),
                    "fifty_two_week_low": _clean_float(meta.get("fiftyTwoWeekLow")),
                    "currency": _clean_str(
                        meta.get("currency"), _infer_currency_from_ticker(ticker)
                    ).upper(),
                    "meta_name": _clean_str(meta.get("longName") or meta.get("shortName"), ""),
                    "price_history_5y": price_history,
                }
            except Exception as exc:
                last_exc = exc
        raise DataFetchError(f"Direct Yahoo v8 chart failed for '{ticker}': {last_exc}")

    def _fetch_price_payload(
        self, ticker: str, tk: yf.Ticker, session: cffi_requests.Session
    ) -> dict[str, Any]:
        price_history: list[dict[str, Any]] = []
        current_price: float | None = None
        previous_close: float | None = None
        market_cap: float | None = None
        fifty_two_week_high: float | None = None
        fifty_two_week_low: float | None = None
        currency = _infer_currency_from_ticker(ticker)
        meta_name = ""

        try:
            hist_5y = _retry_yahoo(
                lambda: tk.history(period="5y", interval="1wk", auto_adjust=True)
            )
            if hist_5y is not None and not hist_5y.empty and "Close" in hist_5y.columns:
                for idx, row in hist_5y.iterrows():
                    close_val = _clean_float(row.get("Close"))
                    if close_val is None or close_val <= 0:
                        continue
                    date_str = pd.Timestamp(idx).strftime("%Y-%m-%d")
                    price_history.append({"date": date_str, "close": round(close_val, 4)})
        except Exception:
            price_history = []

        if not price_history:
            return self._fetch_price_v8_direct(ticker, session)

        try:
            hist_5d = tk.history(period="5d", interval="1d", auto_adjust=True)
            if hist_5d is not None and not hist_5d.empty and "Close" in hist_5d.columns:
                closes = [
                    _clean_float(v)
                    for v in hist_5d["Close"].tolist()
                    if _clean_float(v) is not None
                ]
                if closes:
                    current_price = closes[-1]
                if len(closes) >= 2:
                    previous_close = closes[-2]
        except Exception:
            pass

        try:
            fast = tk.fast_info
            if current_price is None:
                current_price = _clean_float(fast.get("lastPrice"))
            if previous_close is None:
                previous_close = _clean_float(fast.get("previousClose"))
            market_cap = _clean_float(fast.get("marketCap"))
            fifty_two_week_high = _clean_float(fast.get("yearHigh"))
            fifty_two_week_low = _clean_float(fast.get("yearLow"))
            currency = _clean_str(fast.get("currency"), currency).upper()
        except Exception:
            pass

        if current_price is None:
            current_price = price_history[-1]["close"]
        if previous_close is None and len(price_history) >= 2:
            previous_close = price_history[-2]["close"]

        change_pct: float | None = None
        if current_price is not None and previous_close is not None and previous_close > 0:
            change_pct = (current_price - previous_close) / previous_close

        return {
            "ticker": ticker,
            "current_price": current_price,
            "previous_close": previous_close,
            "change_pct": change_pct,
            "market_cap": market_cap,
            "fifty_two_week_high": fifty_two_week_high,
            "fifty_two_week_low": fifty_two_week_low,
            "currency": currency,
            "meta_name": meta_name,
            "price_history_5y": price_history,
        }

    def _fetch_statements_payload(
        self,
        ticker: str,
        tk: yf.Ticker,
        current_price: float | None,
        price_meta_name: str = "",
        trading_currency: str | None = None,
    ) -> dict[str, Any]:
        info: dict[str, Any] = {}
        try:
            info = _retry_yahoo(lambda: tk.info or {})
        except Exception:
            info = {}

        annual_records: list[dict[str, Any]] = []
        quarterly_records: list[dict[str, Any]] = []
        try:
            annual_inc = _retry_yahoo(lambda: tk.income_stmt)
            annual_bal = _retry_yahoo(lambda: tk.balance_sheet)
            annual_cf = _retry_yahoo(lambda: tk.cashflow)
            qtr_inc = tk.quarterly_income_stmt
            qtr_cf = tk.quarterly_cashflow
            annual_records = _normalize_statements(annual_inc, annual_bal, annual_cf)
            quarterly_records = _normalize_statements(qtr_inc, None, qtr_cf)
        except Exception:
            annual_records = []

        if not annual_records:
            # Official SEC EDGAR XBRL fallback for US equities when Yahoo statements fail.
            return self._fetch_sec_edgar_statements(ticker, current_price)

        company_name = _clean_str(
            info.get("longName") or info.get("shortName") or price_meta_name, ""
        )
        sector = _clean_str(info.get("sector"), "Unknown")
        industry = _clean_str(info.get("industry"), "Unknown")

        if not company_name or sector == "Unknown":
            sec_meta = self._fetch_sec_profile_meta(ticker)
            if not company_name:
                company_name = sec_meta.get("company_name", ticker)
            if sector == "Unknown" and sec_meta.get("sector"):
                sector = sec_meta["sector"]
            if industry == "Unknown" and sec_meta.get("industry"):
                industry = sec_meta["industry"]

        dividend_yield = _extract_dividend_yield(info, current_price)
        forward_growth, forward_growth_source = _extract_forward_growth(tk, info)

        latest_annual = annual_records[-1]
        shares = _clean_float(info.get("sharesOutstanding")) or _clean_float(
            latest_annual.get("diluted_shares")
        ) or _clean_float(latest_annual.get("ordinary_shares"))
        market_cap = _clean_float(info.get("marketCap"))
        if market_cap is None and current_price is not None and shares is not None and shares > 0:
            market_cap = current_price * shares

        inferred_ccy = _infer_currency_from_ticker(ticker)
        resolved_ccy = _clean_str(
            info.get("currency") or trading_currency, inferred_ccy
        ).upper()
        financial_ccy = _clean_str(
            info.get("financialCurrency"), resolved_ccy
        ).upper()

        profile = {
            "ticker": ticker,
            "company_name": company_name or ticker,
            "sector": sector,
            "industry": industry,
            "exchange": _clean_str(info.get("exchange"), ""),
            "quote_type": _clean_str(info.get("quoteType"), "EQUITY"),
            "currency": resolved_ccy,
            "financial_currency": financial_ccy,
            "market_cap": market_cap,
            "shares_outstanding": shares,
            "trailing_eps_info": _clean_float(info.get("trailingEps")),
            "forward_eps_info": _clean_float(info.get("forwardEps")),
            "book_value_per_share": _clean_float(info.get("bookValue")),
            "price_to_book_info": _clean_float(info.get("priceToBook")),
            "dividend_rate": _clean_float(info.get("dividendRate")),
            "dividend_yield": dividend_yield,
            "payout_ratio_info": _clean_float(info.get("payoutRatio")),
            "forward_growth": forward_growth,
            "forward_growth_source": forward_growth_source,
            "source_tag": "yahoo_live",
        }

        return {
            "profile": profile,
            "annual_statements": annual_records,
            "quarterly_statements": quarterly_records,
        }

    def _assemble_stock_data(
        self,
        clean_ticker: str,
        price_payload: dict[str, Any],
        stmt_payload: dict[str, Any],
        price_cached: bool,
        statements_cached: bool,
        price_fetched_at: str | None,
        stmt_fetched_at: str | None,
        used_stale_or_seed: bool,
        seed_used: bool,
    ) -> dict[str, Any]:
        profile = dict(stmt_payload["profile"])
        if profile.get("market_cap") is None:
            profile["market_cap"] = price_payload.get("market_cap")

        inferred_ccy = _infer_currency_from_ticker(clean_ticker)
        trading_ccy = _clean_str(
            profile.get("currency") or price_payload.get("currency"), inferred_ccy
        ).upper()
        # Preserve fast_info / v8 trading currency when profile lacked one.
        if price_payload.get("currency") and not profile.get("currency"):
            trading_ccy = _clean_str(price_payload.get("currency"), inferred_ccy).upper()
        financial_ccy = _clean_str(
            profile.get("financial_currency"), trading_ccy
        ).upper()
        currency_mismatch = financial_ccy != trading_ccy

        annual_records = stmt_payload.get("annual_statements", [])
        quarterly_records = stmt_payload.get("quarterly_statements", [])
        latest_stmt_date, latest_stmt_label = _extract_latest_statement_meta(
            annual_records, quarterly_records
        )

        profile["currency"] = trading_ccy
        profile["financial_currency"] = financial_ccy
        profile["currency_mismatch"] = currency_mismatch
        profile["latest_statement_date"] = latest_stmt_date
        profile["latest_statement_label"] = latest_stmt_label

        stmt_source = profile.get("source_tag", "yahoo_live")
        if seed_used:
            data_source = "seed_snapshot"
        elif used_stale_or_seed:
            data_source = "stale_cache"
        elif stmt_source == "sec_edgar":
            data_source = "sec_edgar"
        elif price_cached and statements_cached:
            data_source = "yahoo_cache"
        else:
            data_source = "yahoo_live"

        return {
            "ticker": clean_ticker,
            "profile": profile,
            "market": {
                "current_price": price_payload.get("current_price"),
                "previous_close": price_payload.get("previous_close"),
                "change_pct": price_payload.get("change_pct"),
                "market_cap": profile.get("market_cap"),
                "fifty_two_week_high": price_payload.get("fifty_two_week_high"),
                "fifty_two_week_low": price_payload.get("fifty_two_week_low"),
                "currency": trading_ccy,
                "financial_currency": financial_ccy,
                "currency_mismatch": currency_mismatch,
            },
            "price_history_5y": price_payload.get("price_history_5y", []),
            "annual_statements": annual_records,
            "quarterly_statements": quarterly_records,
            "cache_status": {
                "price_cached": price_cached,
                "statements_cached": statements_cached,
                "price_fetched_at": price_fetched_at,
                "statements_fetched_at": stmt_fetched_at,
                "data_source": data_source,
                "latest_statement_date": latest_stmt_date,
                "latest_statement_label": latest_stmt_label,
            },
        }

    def get_quote_snapshot(
        self,
        ticker: str,
        force_refresh: bool = False,
        allow_network: bool = True,
    ) -> dict[str, Any]:
        """Fetch or load quote + 5Y weekly price payload (15-min Streamlit TTL / 24h SQLite)."""
        clean_ticker = ticker.strip().upper()
        if not clean_ticker:
            raise DataFetchError("Ticker symbol cannot be empty.")

        price_payload = None
        price_fetched_at = None
        price_cached = False
        used_stale = False
        seed_used = False

        if not force_refresh:
            price_payload, price_fetched_at = self._read_cache(
                "price_cache", clean_ticker, PRICE_TTL
            )
            if price_payload is not None:
                price_cached = True

        if price_payload is None:
            if allow_network:
                try:
                    sess = _build_cffi_session(IMPERSONATE_PROFILES[0])
                    ticker_obj = yf.Ticker(clean_ticker, session=sess)
                    price_payload = self._fetch_price_payload(clean_ticker, ticker_obj, sess)
                    price_fetched_at = self._write_cache(
                        "price_cache", clean_ticker, price_payload
                    )
                except Exception:
                    price_payload = None

            if price_payload is None:
                stale_p, stale_p_dt = self._read_cache("price_cache", clean_ticker, None)
                if stale_p is not None:
                    price_payload, price_fetched_at = stale_p, stale_p_dt
                    price_cached = True
                    used_stale = True
                else:
                    seed = self._load_seed_snapshot(clean_ticker)
                    if seed is not None:
                        price_payload = seed["price"]
                        price_fetched_at = seed["price_fetched_at"]
                        price_cached = True
                        used_stale = True
                        seed_used = True

        if price_payload is None:
            raise DataFetchError(
                f"ไม่พบข้อมูลราคาของ '{clean_ticker}' หรือถูกจำกัดการเข้าถึงชั่วคราว"
            )

        return {
            "payload": price_payload,
            "fetched_at": price_fetched_at,
            "cached": price_cached,
            "used_stale": used_stale,
            "seed_used": seed_used,
        }

    def get_statements_snapshot(
        self,
        ticker: str,
        force_refresh: bool = False,
        allow_network: bool = True,
        current_price: float | None = None,
        meta_name: str = "",
        trading_currency: str | None = None,
    ) -> dict[str, Any]:
        """Fetch or load 5Y financial statements payload (24h Streamlit TTL / 7d SQLite)."""
        clean_ticker = ticker.strip().upper()
        if not clean_ticker:
            raise DataFetchError("Ticker symbol cannot be empty.")

        stmt_payload = None
        stmt_fetched_at = None
        statements_cached = False
        used_stale = False
        seed_used = False

        if not force_refresh:
            stmt_payload, stmt_fetched_at = self._read_cache(
                "statements_cache", clean_ticker, STATEMENTS_TTL
            )
            if stmt_payload is not None:
                statements_cached = True

        if stmt_payload is None:
            if allow_network:
                try:
                    sess = _build_cffi_session(IMPERSONATE_PROFILES[0])
                    ticker_obj = yf.Ticker(clean_ticker, session=sess)
                    stmt_payload = self._fetch_statements_payload(
                        clean_ticker,
                        ticker_obj,
                        current_price,
                        meta_name,
                        trading_currency=trading_currency,
                    )
                    stmt_fetched_at = self._write_cache(
                        "statements_cache", clean_ticker, stmt_payload
                    )
                except Exception:
                    stmt_payload = None

            if stmt_payload is None:
                stale_s, stale_s_dt = self._read_cache("statements_cache", clean_ticker, None)
                if stale_s is not None:
                    stmt_payload, stmt_fetched_at = stale_s, stale_s_dt
                    statements_cached = True
                    used_stale = True
                else:
                    seed = self._load_seed_snapshot(clean_ticker)
                    if seed is not None:
                        stmt_payload = seed["statements"]
                        stmt_fetched_at = seed["statements_fetched_at"]
                        statements_cached = True
                        used_stale = True
                        seed_used = True

        if stmt_payload is None:
            raise DataFetchError(
                f"ไม่พบข้อมูลรายงานการเงินของ '{clean_ticker}' จาก Yahoo Finance หรือ SEC EDGAR"
            )

        return {
            "payload": stmt_payload,
            "fetched_at": stmt_fetched_at,
            "cached": statements_cached,
            "used_stale": used_stale,
            "seed_used": seed_used,
        }

    def get_stock_data(
        self,
        ticker: str,
        force_refresh: bool = False,
        allow_network: bool = True,
    ) -> dict[str, Any]:
        """Return normalized stock data dict using SQLite cache, live APIs, and fallbacks."""
        clean_ticker = ticker.strip().upper()
        if not clean_ticker:
            raise DataFetchError("Ticker symbol cannot be empty.")

        q_wrap = self.get_quote_snapshot(
            clean_ticker, force_refresh=force_refresh, allow_network=allow_network
        )
        price_payload = q_wrap["payload"]

        s_wrap = self.get_statements_snapshot(
            clean_ticker,
            force_refresh=force_refresh,
            allow_network=allow_network,
            current_price=price_payload.get("current_price"),
            meta_name=price_payload.get("meta_name", ""),
            trading_currency=price_payload.get("currency"),
        )
        stmt_payload = s_wrap["payload"]

        return self._assemble_stock_data(
            clean_ticker=clean_ticker,
            price_payload=price_payload,
            stmt_payload=stmt_payload,
            price_cached=q_wrap["cached"],
            statements_cached=s_wrap["cached"],
            price_fetched_at=q_wrap["fetched_at"],
            stmt_fetched_at=s_wrap["fetched_at"],
            used_stale_or_seed=(q_wrap["used_stale"] or s_wrap["used_stale"]),
            seed_used=(q_wrap["seed_used"] or s_wrap["seed_used"]),
        )


_SHARED_FETCHER: StockDataFetcher | None = None


def _get_shared_fetcher() -> StockDataFetcher:
    global _SHARED_FETCHER
    if _SHARED_FETCHER is None:
        _SHARED_FETCHER = StockDataFetcher()
    return _SHARED_FETCHER


@_st_cache_data(ttl=900)
def fetch_quote_snapshot(ticker: str, cache_bust: int = 0) -> dict[str, Any]:
    """Cached 15-min quote & 5Y price snapshot for Streamlit Cloud."""
    return _get_shared_fetcher().get_quote_snapshot(
        ticker, force_refresh=(cache_bust > 0), allow_network=True
    )


@_st_cache_data(ttl=86400)
def fetch_financial_statements(
    ticker: str,
    cache_bust: int = 0,
    current_price: float | None = None,
    meta_name: str = "",
    trading_currency: str | None = None,
) -> dict[str, Any]:
    """Cached 24-hr 5Y financial statements snapshot for Streamlit Cloud."""
    return _get_shared_fetcher().get_statements_snapshot(
        ticker,
        force_refresh=(cache_bust > 0),
        allow_network=True,
        current_price=current_price,
        meta_name=meta_name,
        trading_currency=trading_currency,
    )


@_st_cache_data(ttl=86400)
def fetch_peer_stock_data(ticker: str, cache_bust: int = 0) -> dict[str, Any]:
    """Dedicated 24-hr cached loader for lazy-loaded Peer Comparison rows."""
    return _get_shared_fetcher().get_stock_data(
        ticker, force_refresh=(cache_bust > 0), allow_network=True
    )


def fetch_combined_stock_data(ticker: str, cache_bust: int = 0) -> dict[str, Any]:
    """Combine 15-min quote cache + 24-hr statements cache into normalized stock_data."""
    clean_ticker = ticker.strip().upper()
    if not clean_ticker:
        raise DataFetchError("กรุณาระบุชื่อย่อหุ้น (Ticker Symbol)")

    fetcher = _get_shared_fetcher()
    q_wrap = fetch_quote_snapshot(clean_ticker, cache_bust=cache_bust)
    price_payload = q_wrap["payload"]
    s_wrap = fetch_financial_statements(
        clean_ticker,
        cache_bust=cache_bust,
        current_price=price_payload.get("current_price"),
        meta_name=price_payload.get("meta_name", ""),
        trading_currency=price_payload.get("currency"),
    )
    return fetcher._assemble_stock_data(
        clean_ticker=clean_ticker,
        price_payload=price_payload,
        stmt_payload=s_wrap["payload"],
        price_cached=q_wrap["cached"],
        statements_cached=s_wrap["cached"],
        price_fetched_at=q_wrap["fetched_at"],
        stmt_fetched_at=s_wrap["fetched_at"],
        used_stale_or_seed=(q_wrap["used_stale"] or s_wrap["used_stale"]),
        seed_used=(q_wrap["seed_used"] or s_wrap["seed_used"]),
    )
