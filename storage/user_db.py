"""SQLite persistence for Watchlist, Category Overrides, Fisher 15-Point Checklist, and Thesis Notes."""

from __future__ import annotations

import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

DEFAULT_USER_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "user_workspace.db"

DEFAULT_WATCHLIST_SEED: list[tuple[str, str, str]] = [
    ("NVDA", "NVIDIA Corporation", "Technology"),
    ("KO", "The Coca-Cola Company", "Consumer Defensive"),
    ("XOM", "Exxon Mobil Corporation", "Energy"),
    ("JPM", "JPMorgan Chase & Co.", "Financial Services"),
]

# Classic Philip Fisher 15-Point Checklist grouped into 4 sections (0/1/2 per item -> total 0-30).
FISHER_SECTIONS: list[dict[str, str]] = [
    {
        "id": "growth",
        "label_en": "Growth & Market Runway",
        "label_th": "การเติบโตและตลาดเป้าหมาย",
    },
    {
        "id": "moat",
        "label_en": "Profitability & Competitive Moat",
        "label_th": "อัตรากำไรและความได้เปรียบเชิงแข่งขัน",
    },
    {
        "id": "org",
        "label_en": "Organization & Financial Discipline",
        "label_th": "องค์กรและวินัยทางการเงิน",
    },
    {
        "id": "gov",
        "label_en": "Shareholder Alignment & Integrity",
        "label_th": "ธรรมาภิบาลและผู้บริหาร",
    },
]

FISHER_15_POINTS: list[dict[str, Any]] = [
    # Section 1: Growth & Market Runway (Items 1-4)
    {
        "id": 1,
        "section": "growth",
        "title_en": "1. Expanding Market Potential",
        "title_th": "1. ศักยภาพการเติบโตของยอดขายระยะยาว (Market Runway)",
        "description_th": "บริษัทมีสินค้าหรือบริการที่ขยายตลาดและเพิ่มยอดขายต่อเนื่องได้อีกหลายปีข้างหน้าหรือไม่",
    },
    {
        "id": 2,
        "section": "growth",
        "title_en": "2. R&D & New Product Pipeline",
        "title_th": "2. ความมุ่งมั่นพัฒนาสินค้าใหม่ (Product Pipeline)",
        "description_th": "ฝ่ายบริหารมีแผนพัฒนาสินค้าหรือบริการใหม่เพื่อต่อยอดการเติบโตเมื่อตลาดเดิมเริ่มอิ่มตัวหรือไม่",
    },
    {
        "id": 3,
        "section": "growth",
        "title_en": "3. R&D Efficiency vs Peers",
        "title_th": "3. ประสิทธิภาพการลงทุนวิจัยและพัฒนา (R&D Effectiveness)",
        "description_th": "งบวิจัยและพัฒนา (หรือเงินลงทุนนวัตกรรม) สร้างผลตอบแทนเชิงพาณิชย์ได้คุ้มค่ากว่าคู่แข่งหรือไม่",
    },
    {
        "id": 4,
        "section": "growth",
        "title_en": "4. Above-Average Sales Organization",
        "title_th": "4. ศักยภาพทีมขายและการกระจายสินค้า (Sales Organization)",
        "description_th": "บริษัทมีช่องทางจัดจำหน่าย ทีมขาย และกลยุทธ์การตลาดที่แข็งแกร่งเหนือกว่าค่าเฉลี่ยอุตสาหกรรมหรือไม่",
    },
    # Section 2: Profitability & Competitive Moat (Items 5-8)
    {
        "id": 5,
        "section": "moat",
        "title_en": "5. Worthwhile Profit Margins",
        "title_th": "5. อัตรากำไรที่โดดเด่น (Profit Margin)",
        "description_th": "อัตรากำไรจากการดำเนินงานสูงพอที่จะสร้างกันชนทางการเงินและเงินทุนหมุนเวียนสำหรับการเติบโตหรือไม่",
    },
    {
        "id": 6,
        "section": "moat",
        "title_en": "6. Margin Preservation & Improvement",
        "title_th": "6. ความสามารถรักษาและขยายอัตรากำไร (Margin Durability)",
        "description_th": "บริษัทมีอำนาจปรับราคา (Pricing Power) หรือลดต้นทุนต่อหน่วยเพื่อรักษาอัตรากำไรระยะยาวหรือไม่",
    },
    {
        "id": 7,
        "section": "moat",
        "title_en": "7. Outstanding Labor & Personnel Relations",
        "title_th": "7. ความสัมพันธ์กับพนักงานและวัฒนธรรมองค์กร (Talent Retention)",
        "description_th": "อัตราการลาออกต่ำ วัฒนธรรมองค์กรแข็งแกร่ง และดึงดูดบุคลากรคุณภาพสูงได้ดีเทียบคู่แข่งหรือไม่",
    },
    {
        "id": 8,
        "section": "moat",
        "title_en": "8. Outstanding Executive Relations",
        "title_th": "8. ความเป็นเอกภาพและคุณภาพทีมผู้บริหารระดับสูง (Executive Alignment)",
        "description_th": "ผู้บริหารทำงานสอดประสานกันอย่างมีประสิทธิภาพและเลื่อนตำแหน่งจากคนภายในที่มีผลงานจริงหรือไม่",
    },
    # Section 3: Organization & Financial Discipline (Items 9-12)
    {
        "id": 9,
        "section": "org",
        "title_en": "9. Depth of Management",
        "title_th": "9. ความลึกของทีมบริหารรุ่นถัดไป (Management Depth)",
        "description_th": "กิจการไม่ได้พึ่งพาซีอีโอเพียงคนเดียว แต่มีผู้บริหารระดับรองที่เก่งพร้อมรับช่วงต่อหรือไม่",
    },
    {
        "id": 10,
        "section": "org",
        "title_en": "10. Cost Analysis & Accounting Controls",
        "title_th": "10. ระบบควบคุมต้นทุนและบัญชีที่แม่นยำ (Cost & Accounting Controls)",
        "description_th": "บริษัทสามารถติดตามต้นทุนรายผลิตภัณฑ์และควบคุมงบประมาณได้อย่างละเอียดแม่นยำหรือไม่",
    },
    {
        "id": 11,
        "section": "org",
        "title_en": "11. Industry-Specific Competitive Edge",
        "title_th": "11. จุดแข็งเฉพาะอุตสาหกรรมเหนือคู่แข่ง (Unique Competitive Edge)",
        "description_th": "มีปัจจัยเฉพาะตัว เช่น สิทธิบัตร ต้นทุนต่อหน่วยต่ำสุด เครือข่ายผู้ใช้ หรือทำเลที่ได้เปรียบถาวรหรือไม่",
    },
    {
        "id": 12,
        "section": "org",
        "title_en": "12. Long-Range Profit Outlook",
        "title_th": "12. วิสัยทัศน์เน้นกำไรระยะยาวมากกว่างบไตรมาส (Long-Range Outlook)",
        "description_th": "ผู้บริหารยอมลงทุนระยะยาวเพื่อสร้างความแข็งแกร่ง มากกว่าการตกแต่งตัวเลขเพื่อเอาใจตลาดระยะสั้นหรือไม่",
    },
    # Section 4: Shareholder Alignment & Integrity (Items 13-15)
    {
        "id": 13,
        "section": "gov",
        "title_en": "13. Avoiding Equity Dilution",
        "title_th": "13. การไม่เพิ่มทุนพร่ำเพรื่อ (Non-Dilutive Financing)",
        "description_th": "การเติบโตในอนาคตใช้กระแสเงินสดภายในเป็นหลัก โดยไม่ต้องออกหุ้นใหม่มาลดสัดส่วนผู้ถือหุ้นเดิมหรือไม่",
    },
    {
        "id": 14,
        "section": "gov",
        "title_en": "14. Management Candor in Bad Times",
        "title_th": "14. ความโปร่งใสเมื่อเกิดปัญหา (Management Candor)",
        "description_th": "ผู้บริหารสื่อสารตรงไปตรงมาเมื่อธุรกิจเจออุปสรรคหรือผิดแผน ไม่ปกปิดข่าวร้ายหรือไม่",
    },
    {
        "id": 15,
        "section": "gov",
        "title_en": "15. Unquestionable Integrity",
        "title_th": "15. ความซื่อสัตย์สุจริตของผู้บริหาร (Unquestionable Integrity)",
        "description_th": "ไม่มีประวัติผลประโยชน์ทับซ้อน การใช้ข้อมูลภายใน หรือพฤติกรรมเอาเปรียบผู้ถือหุ้นรายย่อยหรือไม่",
    },
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_writable_db_path(db_path: Path) -> Path:
    """Ensure parent directory exists, falling back to OS temp dir if read-only."""
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return db_path
    except OSError:
        fallback = Path(tempfile.gettempdir()) / "lynch_fisher_data" / db_path.name
        fallback.parent.mkdir(parents=True, exist_ok=True)
        return fallback


class UserWorkspaceDB:
    """SQLite persistence layer for user Watchlist, Category Overrides, Fisher 15-Point, and Notes."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        target = Path(db_path) if db_path else DEFAULT_USER_DB_PATH
        self.db_path = _resolve_writable_db_path(target)
        self._init_db()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=15.0)
        conn.row_factory = sqlite3.Row
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
                CREATE TABLE IF NOT EXISTS watchlist (
                    ticker TEXT PRIMARY KEY,
                    company_name TEXT NOT NULL DEFAULT '',
                    sector TEXT NOT NULL DEFAULT '',
                    category_override TEXT DEFAULT NULL,
                    added_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS fisher_checklist (
                    ticker TEXT NOT NULL,
                    item_id INTEGER NOT NULL,
                    score INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (ticker, item_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS thesis_notes (
                    ticker TEXT PRIMARY KEY,
                    two_minute_drill TEXT NOT NULL DEFAULT '',
                    key_catalysts TEXT NOT NULL DEFAULT '',
                    key_risks TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL
                )
                """
            )
            count = conn.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0]
            if count == 0:
                now = _now_iso()
                conn.executemany(
                    """
                    INSERT INTO watchlist (ticker, company_name, sector, category_override, added_at, updated_at)
                    VALUES (?, ?, ?, NULL, ?, ?)
                    """,
                    [(t, name, sec, now, now) for t, name, sec in DEFAULT_WATCHLIST_SEED],
                )
            conn.commit()

    # --- Watchlist & Category Overrides ---

    def get_watchlist(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT ticker, company_name, sector, category_override, added_at, updated_at
                FROM watchlist
                ORDER BY rowid ASC
                """
            ).fetchall()
        return [dict(r) for r in rows]

    def is_in_watchlist(self, ticker: str) -> bool:
        clean = ticker.strip().upper()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM watchlist WHERE ticker = ?", (clean,)
            ).fetchone()
        return row is not None

    def add_to_watchlist(
        self, ticker: str, company_name: str = "", sector: str = ""
    ) -> None:
        clean = ticker.strip().upper()
        if not clean:
            return
        now = _now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO watchlist (ticker, company_name, sector, category_override, added_at, updated_at)
                VALUES (?, ?, ?, NULL, ?, ?)
                ON CONFLICT(ticker) DO UPDATE SET
                    company_name = CASE WHEN excluded.company_name != '' THEN excluded.company_name ELSE watchlist.company_name END,
                    sector = CASE WHEN excluded.sector != '' THEN excluded.sector ELSE watchlist.sector END,
                    updated_at = excluded.updated_at
                """,
                (clean, company_name, sector, now, now),
            )
            conn.commit()

    def remove_from_watchlist(self, ticker: str) -> None:
        clean = ticker.strip().upper()
        with self._connect() as conn:
            conn.execute("DELETE FROM watchlist WHERE ticker = ?", (clean,))
            conn.commit()

    def get_category_override(self, ticker: str) -> str | None:
        clean = ticker.strip().upper()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT category_override FROM watchlist WHERE ticker = ?", (clean,)
            ).fetchone()
        if row and row["category_override"]:
            return str(row["category_override"])
        return None

    def set_category_override(
        self, ticker: str, category: str | None, company_name: str = "", sector: str = ""
    ) -> None:
        clean = ticker.strip().upper()
        if not clean:
            return
        now = _now_iso()
        override_val = category if category else None
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT 1 FROM watchlist WHERE ticker = ?", (clean,)
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE watchlist
                    SET category_override = ?, updated_at = ?
                    WHERE ticker = ?
                    """,
                    (override_val, now, clean),
                )
            elif override_val is not None:
                conn.execute(
                    """
                    INSERT INTO watchlist (ticker, company_name, sector, category_override, added_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (clean, company_name, sector, override_val, now, now),
                )
            conn.commit()

    # --- Fisher 15-Point Checklist ---

    def get_fisher_scores(self, ticker: str) -> dict[int, int]:
        clean = ticker.strip().upper()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT item_id, score FROM fisher_checklist WHERE ticker = ?",
                (clean,),
            ).fetchall()
        return {int(r["item_id"]): int(r["score"]) for r in rows}

    def get_fisher_summary(self, ticker: str) -> dict[str, int]:
        scores = self.get_fisher_scores(ticker)
        total = sum(max(0, min(2, scores.get(item["id"], 0))) for item in FISHER_15_POINTS)
        assessed = sum(1 for item in FISHER_15_POINTS if item["id"] in scores)
        return {"total_score": total, "assessed_count": assessed}

    def save_fisher_scores(self, ticker: str, scores: dict[int, int]) -> None:
        clean = ticker.strip().upper()
        if not clean:
            return
        now = _now_iso()
        with self._connect() as conn:
            for item_id, raw_score in scores.items():
                val = max(0, min(2, int(raw_score)))
                conn.execute(
                    """
                    INSERT INTO fisher_checklist (ticker, item_id, score, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(ticker, item_id) DO UPDATE SET
                        score = excluded.score,
                        updated_at = excluded.updated_at
                    """,
                    (clean, int(item_id), val, now),
                )
            conn.commit()

    # --- Lynch 2-Minute Drill & Thesis Notes ---

    def get_thesis_notes(self, ticker: str) -> dict[str, str]:
        clean = ticker.strip().upper()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT two_minute_drill, key_catalysts, key_risks, updated_at
                FROM thesis_notes
                WHERE ticker = ?
                """,
                (clean,),
            ).fetchone()
        if not row:
            return {
                "two_minute_drill": "",
                "key_catalysts": "",
                "key_risks": "",
                "updated_at": "",
            }
        return {
            "two_minute_drill": row["two_minute_drill"] or "",
            "key_catalysts": row["key_catalysts"] or "",
            "key_risks": row["key_risks"] or "",
            "updated_at": row["updated_at"] or "",
        }

    def save_thesis_notes(
        self,
        ticker: str,
        two_minute_drill: str,
        key_catalysts: str = "",
        key_risks: str = "",
    ) -> None:
        clean = ticker.strip().upper()
        if not clean:
            return
        now = _now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO thesis_notes (ticker, two_minute_drill, key_catalysts, key_risks, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(ticker) DO UPDATE SET
                    two_minute_drill = excluded.two_minute_drill,
                    key_catalysts = excluded.key_catalysts,
                    key_risks = excluded.key_risks,
                    updated_at = excluded.updated_at
                """,
                (clean, two_minute_drill, key_catalysts, key_risks, now),
            )
            conn.commit()
