"""SQLite persistence for Watchlist, Target Buy Prices, Category Overrides, Fisher 15-Point Checklist, Thesis Notes, and JSON Backup/Restore."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sqlite3
import tempfile
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

_VALID_FISHER_IDS = {item["id"] for item in FISHER_15_POINTS}


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


def _clean_positive_price(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(num) or num <= 0:
        return None
    return round(num, 4)


class UserWorkspaceDB:
    """SQLite persistence layer for Watchlist, Target Buy Prices, Overrides, Fisher 15-Point, and Notes."""

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
                    target_buy_price REAL DEFAULT NULL,
                    added_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            cols = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(watchlist)").fetchall()
            }
            if "target_buy_price" not in cols:
                conn.execute(
                    "ALTER TABLE watchlist ADD COLUMN target_buy_price REAL DEFAULT NULL"
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
                    INSERT INTO watchlist (ticker, company_name, sector, category_override, target_buy_price, added_at, updated_at)
                    VALUES (?, ?, ?, NULL, NULL, ?, ?)
                    """,
                    [(t, name, sec, now, now) for t, name, sec in DEFAULT_WATCHLIST_SEED],
                )
            conn.commit()

    # --- Watchlist, Target Buy Prices & Category Overrides ---

    def get_watchlist(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT ticker, company_name, sector, category_override, target_buy_price, added_at, updated_at
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
        self,
        ticker: str,
        company_name: str = "",
        sector: str = "",
        target_buy_price: float | None = None,
    ) -> None:
        clean = ticker.strip().upper()
        if not clean:
            return
        now = _now_iso()
        target_val = _clean_positive_price(target_buy_price)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO watchlist (ticker, company_name, sector, category_override, target_buy_price, added_at, updated_at)
                VALUES (?, ?, ?, NULL, ?, ?, ?)
                ON CONFLICT(ticker) DO UPDATE SET
                    company_name = CASE WHEN excluded.company_name != '' THEN excluded.company_name ELSE watchlist.company_name END,
                    sector = CASE WHEN excluded.sector != '' THEN excluded.sector ELSE watchlist.sector END,
                    target_buy_price = COALESCE(excluded.target_buy_price, watchlist.target_buy_price),
                    updated_at = excluded.updated_at
                """,
                (clean, company_name, sector, target_val, now, now),
            )
            conn.commit()

    def remove_from_watchlist(self, ticker: str) -> None:
        clean = ticker.strip().upper()
        with self._connect() as conn:
            conn.execute("DELETE FROM watchlist WHERE ticker = ?", (clean,))
            conn.commit()

    def get_target_buy_price(self, ticker: str) -> float | None:
        clean = ticker.strip().upper()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT target_buy_price FROM watchlist WHERE ticker = ?", (clean,)
            ).fetchone()
        if row and row["target_buy_price"] is not None:
            return _clean_positive_price(row["target_buy_price"])
        return None

    def set_target_buy_price(
        self,
        ticker: str,
        target_buy_price: float | None,
        company_name: str = "",
        sector: str = "",
    ) -> None:
        clean = ticker.strip().upper()
        if not clean:
            return
        now = _now_iso()
        target_val = _clean_positive_price(target_buy_price)
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT 1 FROM watchlist WHERE ticker = ?", (clean,)
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE watchlist
                    SET target_buy_price = ?, updated_at = ?
                    WHERE ticker = ?
                    """,
                    (target_val, now, clean),
                )
            elif target_val is not None:
                conn.execute(
                    """
                    INSERT INTO watchlist (ticker, company_name, sector, category_override, target_buy_price, added_at, updated_at)
                    VALUES (?, ?, ?, NULL, ?, ?, ?)
                    """,
                    (clean, company_name, sector, target_val, now, now),
                )
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
                    INSERT INTO watchlist (ticker, company_name, sector, category_override, target_buy_price, added_at, updated_at)
                    VALUES (?, ?, ?, ?, NULL, ?, ?)
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

    # --- Versioned JSON Backup Export & Validated Import ---

    def export_backup_json(self) -> str:
        """Serialize watchlist, overrides, Fisher checklists, and 2-Minute Drills to JSON."""
        with self._connect() as conn:
            wl_rows = conn.execute(
                """
                SELECT ticker, company_name, sector, category_override, target_buy_price, added_at
                FROM watchlist
                ORDER BY rowid ASC
                """
            ).fetchall()
            fisher_rows = conn.execute(
                "SELECT ticker, item_id, score FROM fisher_checklist ORDER BY ticker ASC, item_id ASC"
            ).fetchall()
            notes_rows = conn.execute(
                "SELECT ticker, two_minute_drill, key_catalysts, key_risks, updated_at FROM thesis_notes ORDER BY ticker ASC"
            ).fetchall()

        watchlist_out: list[dict[str, Any]] = []
        category_overrides: dict[str, str] = {}
        for r in wl_rows:
            t = str(r["ticker"]).strip().upper()
            watchlist_out.append(
                {
                    "ticker": t,
                    "company_name": str(r["company_name"] or ""),
                    "sector": str(r["sector"] or ""),
                    "target_buy_price": _clean_positive_price(r["target_buy_price"]),
                    "added_at": str(r["added_at"] or _now_iso()),
                }
            )
            if r["category_override"]:
                category_overrides[t] = str(r["category_override"])

        fisher_checklists: dict[str, dict[str, int]] = {}
        for r in fisher_rows:
            t = str(r["ticker"]).strip().upper()
            fisher_checklists.setdefault(t, {})[str(int(r["item_id"]))] = int(r["score"])

        two_minute_drills: dict[str, dict[str, str]] = {}
        for r in notes_rows:
            t = str(r["ticker"]).strip().upper()
            two_minute_drills[t] = {
                "two_minute_drill": str(r["two_minute_drill"] or ""),
                "key_catalysts": str(r["key_catalysts"] or ""),
                "key_risks": str(r["key_risks"] or ""),
                "updated_at": str(r["updated_at"] or ""),
            }

        payload = {
            "schema_version": 1,
            "app": "lynch-fisher-terminal",
            "exported_at": _now_iso(),
            "watchlist": watchlist_out,
            "category_overrides": category_overrides,
            "fisher_checklists": fisher_checklists,
            "two_minute_drills": two_minute_drills,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)

    def import_backup_json(self, raw_text: str) -> dict[str, int]:
        """Strictly validate and merge-upsert JSON backup into SQLite."""
        try:
            data = json.loads(raw_text)
        except Exception as exc:
            raise ValueError("ไฟล์ JSON ไม่ถูกต้อง (Invalid JSON syntax)") from exc

        if not isinstance(data, dict):
            raise ValueError("โครงสร้างไฟล์สำรองข้อมูลต้องเป็น JSON Object")

        required_keys = {"watchlist", "fisher_checklists", "two_minute_drills", "category_overrides"}
        if not any(k in data for k in required_keys):
            raise ValueError("ไม่พบข้อมูล Watchlist หรือ Checklist ที่รองรับในไฟล์นี้")

        wl_raw = data.get("watchlist", [])
        ov_raw = data.get("category_overrides", {})
        fc_raw = data.get("fisher_checklists", {})
        dr_raw = data.get("two_minute_drills", {})

        if not isinstance(wl_raw, list):
            raise ValueError("รูปแบบข้อมูล watchlist ไม่ถูกต้อง (ต้องเป็น list)")
        if not isinstance(ov_raw, dict):
            raise ValueError("รูปแบบข้อมูล category_overrides ไม่ถูกต้อง (ต้องเป็น object)")
        if not isinstance(fc_raw, dict):
            raise ValueError("รูปแบบข้อมูล fisher_checklists ไม่ถูกต้อง (ต้องเป็น object)")
        if not isinstance(dr_raw, dict):
            raise ValueError("รูปแบบข้อมูล two_minute_drills ไม่ถูกต้อง (ต้องเป็น object)")

        # Pre-validate all sections cleanly before opening transaction.
        clean_wl: list[tuple[str, str, str, float | None, str]] = []
        for entry in wl_raw:
            if not isinstance(entry, dict) or not str(entry.get("ticker", "")).strip():
                raise ValueError("พบรายการใน watchlist ที่ไม่มีรหัสหุ้น (ticker)")
            t = str(entry["ticker"]).strip().upper()
            cname = str(entry.get("company_name") or "")
            sec = str(entry.get("sector") or "")
            raw_tbp = entry.get("target_buy_price")
            if raw_tbp is not None and raw_tbp != "":
                tbp = _clean_positive_price(raw_tbp)
                if tbp is None:
                    raise ValueError(f"ราคาเป้าหมาย (target_buy_price) ของ {t} ไม่ถูกต้อง")
            else:
                tbp = None
            added_at = str(entry.get("added_at") or _now_iso())
            clean_wl.append((t, cname, sec, tbp, added_at))

        clean_ov: dict[str, str | None] = {}
        for k, v in ov_raw.items():
            t = str(k).strip().upper()
            if not t:
                continue
            clean_ov[t] = str(v).strip() if v else None

        clean_fc: dict[str, dict[int, int]] = {}
        for k, scores_map in fc_raw.items():
            t = str(k).strip().upper()
            if not t or not isinstance(scores_map, dict):
                raise ValueError(f"ข้อมูล Fisher checklist ของ {k} ไม่ถูกต้อง")
            parsed_scores: dict[int, int] = {}
            for item_k, score_v in scores_map.items():
                try:
                    item_id = int(item_k)
                    score_int = int(score_v)
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"คะแนน Fisher ของ {t} ต้องเป็นตัวเลข 0-2") from exc
                if item_id not in _VALID_FISHER_IDS or score_int not in (0, 1, 2):
                    raise ValueError(f"รหัสข้อหรือคะแนน Fisher ของ {t} อยู่นอกช่วงที่กำหนด")
                parsed_scores[item_id] = score_int
            clean_fc[t] = parsed_scores

        clean_dr: dict[str, tuple[str, str, str]] = {}
        for k, note_obj in dr_raw.items():
            t = str(k).strip().upper()
            if not t or not isinstance(note_obj, dict):
                raise ValueError(f"ข้อมูล 2-Minute Drill ของ {k} ไม่ถูกต้อง")
            clean_dr[t] = (
                str(note_obj.get("two_minute_drill") or ""),
                str(note_obj.get("key_catalysts") or ""),
                str(note_obj.get("key_risks") or ""),
            )

        now = _now_iso()
        touched_tickers: set[str] = set()
        with self._connect() as conn:
            for t, cname, sec, tbp, added_at in clean_wl:
                touched_tickers.add(t)
                conn.execute(
                    """
                    INSERT INTO watchlist (ticker, company_name, sector, category_override, target_buy_price, added_at, updated_at)
                    VALUES (?, ?, ?, NULL, ?, ?, ?)
                    ON CONFLICT(ticker) DO UPDATE SET
                        company_name = CASE WHEN excluded.company_name != '' THEN excluded.company_name ELSE watchlist.company_name END,
                        sector = CASE WHEN excluded.sector != '' THEN excluded.sector ELSE watchlist.sector END,
                        target_buy_price = COALESCE(excluded.target_buy_price, watchlist.target_buy_price),
                        updated_at = excluded.updated_at
                    """,
                    (t, cname, sec, tbp, added_at, now),
                )

            for t, ov_val in clean_ov.items():
                touched_tickers.add(t)
                exists = conn.execute(
                    "SELECT 1 FROM watchlist WHERE ticker = ?", (t,)
                ).fetchone()
                if exists:
                    conn.execute(
                        "UPDATE watchlist SET category_override = ?, updated_at = ? WHERE ticker = ?",
                        (ov_val, now, t),
                    )
                elif ov_val is not None:
                    conn.execute(
                        """
                        INSERT INTO watchlist (ticker, company_name, sector, category_override, target_buy_price, added_at, updated_at)
                        VALUES (?, '', '', ?, NULL, ?, ?)
                        """,
                        (t, ov_val, now, now),
                    )

            for t, parsed_scores in clean_fc.items():
                touched_tickers.add(t)
                for item_id, score_int in parsed_scores.items():
                    conn.execute(
                        """
                        INSERT INTO fisher_checklist (ticker, item_id, score, updated_at)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(ticker, item_id) DO UPDATE SET
                            score = excluded.score,
                            updated_at = excluded.updated_at
                        """,
                        (t, item_id, score_int, now),
                    )

            for t, (drill, cat, risk) in clean_dr.items():
                touched_tickers.add(t)
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
                    (t, drill, cat, risk, now),
                )
            conn.commit()

        return {
            "tickers_imported": len(touched_tickers),
            "watchlist_count": len(clean_wl),
            "checklists_count": len(clean_fc),
            "drills_count": len(clean_dr),
            "overrides_count": len(clean_ov),
        }
