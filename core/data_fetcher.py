"""Yahoo Finance data acquisition, statement normalization, and SQLite caching.

Fetches 5-year price history and financial statements via yfinance, normalizes
field aliases into chronological (oldest -> newest) records, and caches price
data daily (24h TTL) and financial statements weekly (7d TTL) in SQLite.
"""

from __future__ import annotations

import json
import math
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
from typing import Any, Iterator

import pandas as pd
import yfinance as yf


class DataFetchError(Exception):
    """Raised when market or financial statement data cannot be fetched."""


DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "market_cache.db"
PRICE_TTL = timedelta(hours=24)
STATEMENTS_TTL = timedelta(days=7)

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

    records: list[dict[str, Any]] = []
    for date_key in sorted(period_map.keys()):
        rec = period_map[date_key]
        # Safe derived fallbacks.
        if rec.get("diluted_eps") is None:
            ni = rec.get("net_income")
            shares = rec.get("diluted_shares")
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

        # Normalize dividends_paid magnitude to positive cash outflow if present.
        if rec.get("dividends_paid") is not None:
            rec["dividends_paid"] = abs(rec["dividends_paid"])

        # Normalize interest_expense to positive magnitude if it was negative in GAAP.
        if rec.get("interest_expense") is not None:
            rec["interest_expense"] = abs(rec["interest_expense"])

        records.append(rec)

    return records


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
        # Yahoo's trailingAnnualDividendYield is typically a decimal (e.g. 0.029).
        if trailing_yield > 0.25:
            return trailing_yield / 100.0
        return trailing_yield

    raw_yield = _clean_float(info.get("dividendYield"))
    if raw_yield is not None and raw_yield >= 0:
        # Recent yfinance returns dividendYield in percentage points (e.g. 2.95 or 0.03).
        return raw_yield / 100.0

    return 0.0


def _extract_forward_growth(
    ticker_obj: yf.Ticker, info: dict[str, Any]
) -> tuple[float | None, str]:
    """Defensively extract forward EPS growth estimate across yfinance versions."""
    # 1. growth_estimates table (+5y / 5y / LTG / +1y)
    try:
        ge = ticker_obj.growth_estimates
        if isinstance(ge, pd.DataFrame) and not ge.empty:
            # Prefer column representing the stock itself.
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

    # 2. earnings_estimate table (0y -> +1y or growth column)
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

    # 3. Implied forwardEps / trailingEps
    fwd_eps = _clean_float(info.get("forwardEps"))
    trl_eps = _clean_float(info.get("trailingEps"))
    if fwd_eps is not None and trl_eps is not None and trl_eps > 0:
        implied = (fwd_eps / trl_eps) - 1.0
        if -0.50 <= implied <= 1.50:
            return implied, "info:forwardEps_vs_trailingEps"

    # 4. info['earningsGrowth'] fallback
    eg = _clean_float(info.get("earningsGrowth"))
    if eg is not None and -0.50 <= eg <= 1.50:
        return eg, "info:earningsGrowth"

    return None, "unavailable"


def _resolve_writable_db_path(db_path: Path) -> Path:
    """Ensure parent directory exists, falling back to OS temp dir if read-only."""
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return db_path
    except OSError:
        fallback = Path(tempfile.gettempdir()) / "lynch_fisher_data" / db_path.name
        fallback.parent.mkdir(parents=True, exist_ok=True)
        return fallback


class StockDataFetcher:
    """Fetches, normalizes, and caches stock data in SQLite."""

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
            conn.commit()

    def _read_cache(
        self, table: str, ticker: str, ttl: timedelta
    ) -> tuple[dict[str, Any] | None, str | None]:
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT fetched_at, payload_json FROM {table} WHERE ticker = ?",
                (ticker,),
            ).fetchone()
        if not row:
            return None, None
        fetched_at_str, payload_json = row
        try:
            fetched_dt = _parse_iso_utc(fetched_at_str)
            if datetime.now(timezone.utc) - fetched_dt <= ttl:
                return json.loads(payload_json), fetched_at_str
        except Exception:
            return None, None
        return None, None

    def _write_cache(
        self, table: str, ticker: str, payload: dict[str, Any]
    ) -> str:
        now_iso = datetime.now(timezone.utc).isoformat()
        serialized = json.dumps(payload, allow_nan=False)
        with self._connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {table} (ticker, fetched_at, payload_json)
                VALUES (?, ?, ?)
                ON CONFLICT(ticker) DO UPDATE SET
                    fetched_at = excluded.fetched_at,
                    payload_json = excluded.payload_json
                """,
                (ticker, now_iso, serialized),
            )
            conn.commit()
        return now_iso

    def _fetch_price_payload(self, ticker: str) -> dict[str, Any]:
        tk = yf.Ticker(ticker)
        try:
            hist_5y = tk.history(period="5y", interval="1wk", auto_adjust=True)
        except Exception as exc:
            raise DataFetchError(
                f"Failed to download 5Y price history for {ticker}: {exc}"
            ) from exc

        if hist_5y is None or hist_5y.empty or "Close" not in hist_5y.columns:
            raise DataFetchError(f"No price history returned for ticker '{ticker}'.")

        price_history: list[dict[str, Any]] = []
        for idx, row in hist_5y.iterrows():
            close_val = _clean_float(row.get("Close"))
            if close_val is None or close_val <= 0:
                continue
            date_str = pd.Timestamp(idx).strftime("%Y-%m-%d")
            price_history.append({"date": date_str, "close": round(close_val, 4)})

        if not price_history:
            raise DataFetchError(f"Empty valid price points for ticker '{ticker}'.")

        current_price: float | None = None
        previous_close: float | None = None
        market_cap: float | None = None
        fifty_two_week_high: float | None = None
        fifty_two_week_low: float | None = None
        currency = "USD"

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
            currency = _clean_str(fast.get("currency"), currency)
        except Exception:
            pass

        try:
            info = tk.info or {}
            if current_price is None:
                current_price = _clean_float(
                    info.get("currentPrice") or info.get("regularMarketPrice")
                )
            if previous_close is None:
                previous_close = _clean_float(info.get("previousClose"))
            if market_cap is None:
                market_cap = _clean_float(info.get("marketCap"))
            if fifty_two_week_high is None:
                fifty_two_week_high = _clean_float(info.get("fiftyTwoWeekHigh"))
            if fifty_two_week_low is None:
                fifty_two_week_low = _clean_float(info.get("fiftyTwoWeekLow"))
            currency = _clean_str(info.get("currency"), currency)
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
            "price_history_5y": price_history,
        }

    def _fetch_statements_payload(
        self, ticker: str, current_price: float | None
    ) -> dict[str, Any]:
        tk = yf.Ticker(ticker)
        try:
            info = tk.info or {}
        except Exception as exc:
            raise DataFetchError(
                f"Failed to retrieve company profile for {ticker}: {exc}"
            ) from exc

        if not info or (
            not info.get("shortName")
            and not info.get("longName")
            and not info.get("quoteType")
        ):
            raise DataFetchError(f"Ticker '{ticker}' returned empty profile metadata.")

        try:
            annual_inc = tk.income_stmt
            annual_bal = tk.balance_sheet
            annual_cf = tk.cashflow
            qtr_inc = tk.quarterly_income_stmt
            qtr_cf = tk.quarterly_cashflow
        except Exception as exc:
            raise DataFetchError(
                f"Failed to retrieve financial statements for {ticker}: {exc}"
            ) from exc

        annual_records = _normalize_statements(annual_inc, annual_bal, annual_cf)
        quarterly_records = _normalize_statements(qtr_inc, None, qtr_cf)

        if not annual_records:
            raise DataFetchError(
                f"No annual financial statements available for ticker '{ticker}'."
            )

        dividend_yield = _extract_dividend_yield(info, current_price)
        forward_growth, forward_growth_source = _extract_forward_growth(tk, info)

        profile = {
            "ticker": ticker,
            "company_name": _clean_str(
                info.get("longName") or info.get("shortName"), ticker
            ),
            "sector": _clean_str(info.get("sector"), "Unknown"),
            "industry": _clean_str(info.get("industry"), "Unknown"),
            "exchange": _clean_str(info.get("exchange"), ""),
            "quote_type": _clean_str(info.get("quoteType"), "EQUITY"),
            "market_cap": _clean_float(info.get("marketCap")),
            "shares_outstanding": _clean_float(info.get("sharesOutstanding")),
            "trailing_eps_info": _clean_float(info.get("trailingEps")),
            "forward_eps_info": _clean_float(info.get("forwardEps")),
            "book_value_per_share": _clean_float(info.get("bookValue")),
            "price_to_book_info": _clean_float(info.get("priceToBook")),
            "dividend_rate": _clean_float(info.get("dividendRate")),
            "dividend_yield": dividend_yield,
            "payout_ratio_info": _clean_float(info.get("payoutRatio")),
            "forward_growth": forward_growth,
            "forward_growth_source": forward_growth_source,
        }

        return {
            "profile": profile,
            "annual_statements": annual_records,
            "quarterly_statements": quarterly_records,
        }

    def get_stock_data(
        self, ticker: str, force_refresh: bool = False
    ) -> dict[str, Any]:
        """Return normalized stock data dict using SQLite daily/weekly caches."""
        clean_ticker = ticker.strip().upper()
        if not clean_ticker:
            raise DataFetchError("Ticker symbol cannot be empty.")

        price_payload = None
        price_fetched_at = None
        price_cached = False
        if not force_refresh:
            price_payload, price_fetched_at = self._read_cache(
                "price_cache", clean_ticker, PRICE_TTL
            )
            if price_payload is not None:
                price_cached = True

        if price_payload is None:
            price_payload = self._fetch_price_payload(clean_ticker)
            price_fetched_at = self._write_cache(
                "price_cache", clean_ticker, price_payload
            )

        stmt_payload = None
        stmt_fetched_at = None
        statements_cached = False
        if not force_refresh:
            stmt_payload, stmt_fetched_at = self._read_cache(
                "statements_cache", clean_ticker, STATEMENTS_TTL
            )
            if stmt_payload is not None:
                statements_cached = True

        if stmt_payload is None:
            stmt_payload = self._fetch_statements_payload(
                clean_ticker, price_payload.get("current_price")
            )
            stmt_fetched_at = self._write_cache(
                "statements_cache", clean_ticker, stmt_payload
            )

        profile = dict(stmt_payload["profile"])
        if profile.get("market_cap") is None:
            profile["market_cap"] = price_payload.get("market_cap")

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
                "currency": price_payload.get("currency", "USD"),
            },
            "price_history_5y": price_payload.get("price_history_5y", []),
            "annual_statements": stmt_payload.get("annual_statements", []),
            "quarterly_statements": stmt_payload.get("quarterly_statements", []),
            "cache_status": {
                "price_cached": price_cached,
                "statements_cached": statements_cached,
                "price_fetched_at": price_fetched_at,
                "statements_fetched_at": stmt_fetched_at,
            },
        }
