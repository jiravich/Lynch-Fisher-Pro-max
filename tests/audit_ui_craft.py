"""Automated UI/UX craft audit, Plotly chart audit, UserWorkspaceDB CRUD, and Streamlit AppTest."""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.data_fetcher import StockDataFetcher
from core.scoring_engine import analyze_stock
from storage.user_db import FISHER_15_POINTS, UserWorkspaceDB
from theme import (
    PALETTE,
    PLOTLY_CONFIG,
    build_capital_efficiency_chart,
    build_lynch_fair_value_chart,
    build_margin_trend_chart,
)

# Strict emoji regex covering standard pictographs, dingbats, symbols, and variation selectors.
EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0000FE0F"
    "]+",
    flags=re.UNICODE,
)


def audit_zero_emojis_and_ai_slop() -> None:
    print("1. Auditing zero emojis and zero AI-slop patterns across all .py files...")
    py_files = [
        p
        for p in PROJECT_ROOT.rglob("*.py")
        if ".venv" not in p.parts and "__pycache__" not in p.parts
    ]
    assert py_files, "No Python files found to audit."
    for py_file in py_files:
        content = py_file.read_text(encoding="utf-8")
        match = EMOJI_RE.search(content)
        assert match is None, f"Emoji detected in {py_file}: {match.group(0)!r}"

    theme_src = (PROJECT_ROOT / "theme.py").read_text(encoding="utf-8")
    for forbidden in ["backdrop-filter", "linear-gradient", "radial-gradient", "#8B5CF6", "#06B6D4"]:
        assert forbidden.lower() not in theme_src.lower(), (
            f"Forbidden AI-slop CSS pattern '{forbidden}' found in theme.py"
        )
    for required in [
        PALETTE["bg"],
        PALETTE["surface"],
        PALETTE["hairline"],
        "IBM Plex Sans Thai",
        "IBM Plex Mono",
        "tabular-nums",
        "box-shadow: none !important",
        "[data-testid=\"stDecoration\"]",
    ]:
        assert required in theme_src, f"Missing required theme token '{required}' in theme.py"
    print(f"   Audited {len(py_files)} Python files: PASSED")


def audit_plotly_charts() -> None:
    print("2. Auditing Plotly dark-minimal charts across NVDA, KO, XOM, JPM...")
    assert PLOTLY_CONFIG.get("displayModeBar") is False, "Modebar must be disabled."
    fetcher = StockDataFetcher()
    for ticker in ["NVDA", "KO", "XOM", "JPM"]:
        data = fetcher.get_stock_data(ticker, force_refresh=False)
        res = analyze_stock(data)
        for builder_name, fig in [
            ("fair_value", build_lynch_fair_value_chart(res)),
            ("margin_trend", build_margin_trend_chart(res)),
            ("capital_eff", build_capital_efficiency_chart(res)),
        ]:
            assert fig.layout.showlegend is False, (
                f"{ticker} {builder_name}: showlegend must be False"
            )
            assert fig.layout.xaxis.showgrid is False, (
                f"{ticker} {builder_name}: xaxis grid must be hidden"
            )
            assert fig.layout.yaxis.showgrid is True, (
                f"{ticker} {builder_name}: yaxis horizontal hairline grid must be enabled"
            )
            assert fig.layout.yaxis.gridcolor == PALETTE["chart_grid"], (
                f"{ticker} {builder_name}: yaxis.gridcolor must be {PALETTE['chart_grid']}"
            )
            assert len(fig.layout.annotations) >= 1, (
                f"{ticker} {builder_name}: missing direct end-of-line annotations"
            )
            assert "IBM Plex Mono" in (fig.layout.hoverlabel.font.family or ""), (
                f"{ticker} {builder_name}: hover tooltip must use IBM Plex Mono"
            )
            for tr in fig.data:
                if tr.line and tr.line.width is not None:
                    assert tr.line.width == 1.75, (
                        f"{ticker} {builder_name}: trace '{tr.name}' width must be 1.75px, got {tr.line.width}"
                    )
    print("   Plotly craft audit across 4 stocks x 3 charts: PASSED")


def audit_user_db_crud() -> None:
    print("3. Auditing UserWorkspaceDB CRUD persistence...")
    with tempfile.TemporaryDirectory() as tmpdir:
        db = UserWorkspaceDB(Path(tmpdir) / "test_ws.db")
        wl = [w["ticker"] for w in db.get_watchlist()]
        assert wl == ["NVDA", "KO", "XOM", "JPM"], f"Unexpected default seed: {wl}"

        db.add_to_watchlist("AAPL", "Apple Inc.", "Technology")
        assert db.is_in_watchlist("AAPL") is True
        db.set_category_override("AAPL", "Stalwarts")
        assert db.get_category_override("AAPL") == "Stalwarts"

        scores = {item["id"]: (2 if item["id"] <= 10 else 1) for item in FISHER_15_POINTS}
        db.save_fisher_scores("AAPL", scores)
        summary = db.get_fisher_summary("AAPL")
        assert summary == {"total_score": 25, "assessed_count": 15}, summary

        db.save_thesis_notes("AAPL", "Ecosystem moat", "Services growth", "Antitrust")
        notes = db.get_thesis_notes("AAPL")
        assert notes["two_minute_drill"] == "Ecosystem moat"

        db.remove_from_watchlist("AAPL")
        assert db.is_in_watchlist("AAPL") is False
    print("   UserWorkspaceDB CRUD persistence: PASSED")


def audit_streamlit_apptest() -> None:
    print("4. Running Streamlit AppTest end-to-end render verification...")
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=30)
    at.run()
    assert not at.exception, f"AppTest raised exception: {at.exception}"
    assert not at.error, f"AppTest displayed error: {at.error}"
    assert len(at.markdown) > 0, "Expected editorial markdown blocks to render."
    print("   Streamlit AppTest render check: PASSED")


def main() -> int:
    audit_zero_emojis_and_ai_slop()
    audit_plotly_charts()
    audit_user_db_crud()
    audit_streamlit_apptest()
    print("\nALL UI/UX CRAFT AUDIT CHECKS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
