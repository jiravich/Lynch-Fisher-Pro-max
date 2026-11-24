"""Financial rules, category weights, metric thresholds, sector overlays, and red flag rules.

All quantitative thresholds and categorization rules are isolated here so the
calculation and scoring engines remain pure and easily auditable.
"""

from __future__ import annotations

from typing import Any

# Priority order for Peter Lynch 6-category auto-classification.
CATEGORY_PRIORITY: list[str] = [
    "Turnarounds",
    "Cyclicals",
    "Asset Plays",
    "Fast Growers",
    "Stalwarts",
    "Slow Growers",
]

CATEGORY_METADATA: dict[str, dict[str, str]] = {
    "Turnarounds": {
        "label_en": "Turnarounds",
        "label_th": "หุ้นฟื้นตัว (Turnarounds)",
        "description_th": (
            "บริษัทที่กำไรหดตัว ขาดทุน หรือมีภาระหนี้สูงผิดปกติ "
            "จุดตัดสินอยู่ที่ความอยู่รอดของงบดุล (Balance Sheet) และการฟื้นตัวของกระแสเงินสด"
        ),
    },
    "Cyclicals": {
        "label_en": "Cyclicals",
        "label_th": "หุ้นวัฏจักร (Cyclicals)",
        "description_th": (
            "ธุรกิจที่รายได้และกำไรขึ้นลงตามรอบเศรษฐกิจหรือราคาสินค้าโภคภัณฑ์ "
            "ควรระวังกับดักค่า P/E ต่ำช่วงปลายวัฏจักร (Cyclical P/E Trap)"
        ),
    },
    "Asset Plays": {
        "label_en": "Asset Plays",
        "label_th": "หุ้นสินทรัพย์แฝง (Asset Plays)",
        "description_th": (
            "บริษัทที่ราคาตลาดต่ำกว่ามูลค่าทางบัญชี (Book Value) หรือมีเงินสดสุทธิสูงเมื่อเทียบกับมูลค่ากิจการ "
            "ต้องตรวจสอบคุณภาพสินทรัพย์และส่วนลดมูลค่า"
        ),
    },
    "Fast Growers": {
        "label_en": "Fast Growers",
        "label_th": "หุ้นเติบโตเร็ว (Fast Growers)",
        "description_th": (
            "บริษัทขนาดกลางถึงใหญ่ที่มีการเติบโตของกำไรระดับ 20% ต่อปีขึ้นไป "
            "หัวใจสำคัญคือความคุ้มค่าเทียบการเติบโต (PEG) และความยั่งยืนของคุณภาพธุรกิจ (ROIC)"
        ),
    },
    "Stalwarts": {
        "label_en": "Stalwarts",
        "label_th": "หุ้นแข็งแกร่งโตมั่นคง (Stalwarts)",
        "description_th": (
            "ผู้นำตลาดขนาดใหญ่ที่เติบโตระดับ 10%-20% ต่อปี มีความทนทานต่อภาวะเศรษฐกิจ "
            "เน้นสมดุลระหว่างราคาที่เหมาะสม (PEGY) และความสามารถในการทำกำไรสม่ำเสมอ"
        ),
    },
    "Slow Growers": {
        "label_en": "Slow Growers",
        "label_th": "หุ้นเติบโตช้าปันผลสูง (Slow Growers)",
        "description_th": (
            "บริษัทขนาดใหญ่ที่อิ่มตัว เติบโตต่ำกว่า 10% ต่อปี และมักจ่ายเงินปันผลสม่ำเสมอ "
            "เน้นราคาที่ไม่แพงเมื่อรวมปันผล (PEGY) และความแข็งแกร่งของกระแสเงินสด"
        ),
    },
}

# Exact pillar weight distribution per Lynch category (must sum to 100).
PILLAR_WEIGHTS: dict[str, dict[str, int]] = {
    "Fast Growers": {"lynch_valuation": 35, "lynch_safety": 25, "fisher_quality": 40},
    "Stalwarts": {"lynch_valuation": 30, "lynch_safety": 30, "fisher_quality": 40},
    "Slow Growers": {"lynch_valuation": 40, "lynch_safety": 35, "fisher_quality": 25},
    "Cyclicals": {"lynch_valuation": 35, "lynch_safety": 40, "fisher_quality": 25},
    "Turnarounds": {"lynch_valuation": 20, "lynch_safety": 50, "fisher_quality": 30},
    "Asset Plays": {"lynch_valuation": 45, "lynch_safety": 35, "fisher_quality": 20},
}

PILLAR_METADATA: dict[str, dict[str, str]] = {
    "lynch_valuation": {
        "label_en": "Lynch Valuation",
        "label_th": "ความคุ้มค่าเชิงมูลค่า (Lynch Valuation)",
    },
    "lynch_safety": {
        "label_en": "Lynch Safety",
        "label_th": "ความปลอดภัยทางการเงิน (Lynch Safety)",
    },
    "fisher_quality": {
        "label_en": "Fisher Quality",
        "label_th": "คุณภาพธุรกิจระยะยาว (Fisher Quality)",
    },
}

# Constants for valuation caps, materiality gates, and signal classification.
FAIR_VALUE_GROWTH_CAP: float = 0.25
INVENTORY_MATERIALITY_THRESHOLD: float = 0.05
RD_MATERIALITY_THRESHOLD: float = 0.01
SIGNAL_THRESHOLDS: dict[str, float] = {
    "green": 70.0,
    "amber": 40.0,
}

# Auto-classifier rule parameters.
CLASSIFICATION_RULES: dict[str, Any] = {
    "turnarounds": {
        "min_loss_years": 2,
        "distress_net_debt_to_ebitda": 5.0,
        "distress_interest_coverage": 1.5,
    },
    "cyclicals": {
        "sectors": {"Energy", "Basic Materials"},
        "industry_keywords": [
            "auto manufacturers",
            "auto parts",
            "airlines",
            "steel",
            "aluminum",
            "copper",
            "oil & gas",
            "chemicals",
            "agricultural inputs",
            "lumber",
            "paper",
            "building materials",
            "residential construction",
            "marine shipping",
            "railroads",
            "trucking",
            "heavy construction machinery",
            "resorts & casinos",
            "hotels",
            "lodging",
            "coal",
            "uranium",
            "gold",
            "silver",
            "metals & mining",
        ],
        "eps_cv_threshold": 0.45,
        "max_eps_yoy_drop_threshold": -0.25,
        "secular_growth_exclusion": 0.25,
        "secular_consistency_exclusion": 0.80,
    },
    "asset_plays": {
        "max_pb_for_asset_play": 1.10,
        "min_cash_to_price": 0.30,
        "low_growth_pb_ceiling": 0.90,
        "low_growth_ceiling": 0.12,
        "min_net_cash_to_market_cap": 0.35,
        "net_cash_max_pe": 15.0,
        "net_cash_max_pb": 1.50,
        "reit_max_pb": 0.85,
    },
    "fast_growers": {
        "min_blended_growth": 0.20,
        "min_revenue_cagr": 0.10,
        "min_forward_growth_fallback": 0.18,
    },
    "stalwarts": {
        "min_blended_growth": 0.10,
        "max_blended_growth": 0.20,
        "megacap_min_growth": 0.08,
        "megacap_market_cap": 50_000_000_000.0,
        "megacap_max_dividend_yield": 0.025,
    },
}

# Sector overlay detection and metric visibility rules.
SECTOR_OVERLAYS: dict[str, dict[str, Any]] = {
    "financials": {
        "label_en": "Financials / Banks Overlay",
        "label_th": "กลุ่มการเงินและธนาคาร (Financials Overlay)",
        "sectors": {"Financial Services", "Financials"},
        "industry_keywords": [
            "bank",
            "insurance",
            "capital markets",
            "credit services",
            "asset management",
            "mortgage finance",
            "financial",
        ],
        "bank_keywords": ["bank", "credit services", "mortgage finance"],
        "hidden_metrics": [
            "inventory_vs_revenue_spread",
            "debt_to_equity",
            "net_debt_to_ebitda",
            "cash_to_debt",
            "interest_coverage",
            "fcf_conversion_3y",
            "gross_margin_trend_5y",
            "rd_productivity_3y",
            "roic_5y_avg",
        ],
        "enabled_metrics": [
            "equity_to_assets",
            "earnings_stability_5y",
            "payout_sustainability",
            "roe_5y_avg",
            "pb_ratio",
        ],
    },
    "reit": {
        "label_en": "REIT Overlay",
        "label_th": "กองทรัสต์อสังหาริมทรัพย์ (REIT Overlay)",
        "sectors": {"Real Estate"},
        "hidden_metrics": [
            "inventory_vs_revenue_spread",
            "debt_to_equity",
            "rd_productivity_3y",
        ],
        "enabled_metrics": [],
    },
    "standard": {
        "label_en": "Standard Corporate",
        "label_th": "ธุรกิจทั่วไป (Standard Corporate)",
        "hidden_metrics": [],
        "enabled_metrics": [],
    },
}

# Metric definitions and Linear Interpolation thresholds (red -> 0, amber -> 50, green -> 100).
METRIC_CONFIGS: dict[str, dict[str, Any]] = {
    # --- Lynch Valuation ---
    "peg_ratio": {
        "pillar": "lynch_valuation",
        "label_en": "PEG Ratio",
        "label_th": "PEG Ratio (ราคาเทียบการเติบโต)",
        "description_th": "อัตราส่วน P/E หารด้วยอัตราการเติบโตของกำไร (g%) ค่าต่ำกว่า 1.0 บ่งชี้ว่าราคายังถูกเทียบการเติบโต",
        "direction": "lower_is_better",
        "red": 2.5,
        "amber": 1.5,
        "green": 0.8,
        "base_weight": 35.0,
        "overlays": ["standard", "reit", "financials"],
        "categories": None,
        "format_type": "ratio_x",
    },
    "pegy_ratio": {
        "pillar": "lynch_valuation",
        "label_en": "PEGY Ratio",
        "label_th": "PEGY Ratio (ราคาเทียบการเติบโตและปันผล)",
        "description_th": "อัตราส่วน P/E หารด้วยผลรวมของการเติบโตและอัตราเงินปันผล (g% + Dividend Yield%)",
        "direction": "lower_is_better",
        "red": 2.2,
        "amber": 1.3,
        "green": 0.7,
        "base_weight": 35.0,
        "overlays": ["standard", "reit", "financials"],
        "categories": None,
        "format_type": "ratio_x",
    },
    "price_to_fair_value": {
        "pillar": "lynch_valuation",
        "label_en": "Price / Lynch Fair Value",
        "label_th": "Price / Fair Value (ราคาเทียบมูลค่าเหมาะสม)",
        "description_th": "ราคาตลาดปัจจุบันเทียบกับเส้นมูลค่าเหมาะสมตามสูตร Peter Lynch (จำกัดตัวคูณสูงสุด 25x)",
        "direction": "lower_is_better",
        "red": 1.6,
        "amber": 1.0,
        "green": 0.7,
        "base_weight": 30.0,
        "overlays": ["standard", "reit", "financials"],
        "categories": None,
        "format_type": "ratio_x",
    },
    "pb_ratio": {
        "pillar": "lynch_valuation",
        "label_en": "P/B Ratio",
        "label_th": "P/B Ratio (ราคาเทียบมูลค่าทางบัญชี)",
        "description_th": "อัตราส่วนราคาต่อมูลค่าทางบัญชี ใช้ประเมินกลุ่มการเงินและหุ้นสินทรัพย์แฝงเป็นหลัก",
        "direction": "lower_is_better",
        "red": 3.5,
        "amber": 1.8,
        "green": 0.9,
        "base_weight": 25.0,
        "overlays": ["standard", "reit", "financials"],
        "categories_unless_overlay": {
            "financials": None,
            "standard": ["Asset Plays", "Turnarounds"],
            "reit": ["Asset Plays", "Turnarounds"],
        },
        "format_type": "ratio_x",
    },
    # --- Lynch Safety (Standard / REIT) ---
    "cash_to_debt": {
        "pillar": "lynch_safety",
        "label_en": "Cash-to-Debt",
        "label_th": "Cash-to-Debt (เงินสดต่อหนี้สินรวม)",
        "description_th": "สัดส่วนเงินสดและเงินลงทุนระยะสั้นต่อหนี้สินทั้งหมด สะท้อนกันชนสภาพคล่องของกิจการ",
        "direction": "higher_is_better",
        "red": 0.15,
        "amber": 0.50,
        "green": 1.20,
        "base_weight": 20.0,
        "overlays": ["standard", "reit"],
        "categories": None,
        "format_type": "ratio_x",
    },
    "net_debt_to_ebitda": {
        "pillar": "lynch_safety",
        "label_en": "Net Debt / EBITDA",
        "label_th": "Net Debt / EBITDA (หนี้สินสุทธิต่อกำไรก่อนดอกเบี้ยและค่าเสื่อม)",
        "description_th": "จำนวนปีที่ใช้กำไรจากการดำเนินงาน (EBITDA) ในการชำระหนี้สุทธิทั้งหมด",
        "direction": "lower_is_better",
        "red": 4.0,
        "amber": 2.0,
        "green": 0.5,
        "base_weight": 20.0,
        "overlays": ["standard", "reit"],
        "categories": None,
        "format_type": "ratio_x",
    },
    "debt_to_equity": {
        "pillar": "lynch_safety",
        "label_en": "Debt-to-Equity",
        "label_th": "Debt-to-Equity (หนี้สินต่อส่วนของผู้ถือหุ้น)",
        "description_th": "อัตราส่วนหนี้สินรวมต่อทุน (ข้ามการคำนวณอัตโนมัติเมื่อส่วนทุนติดลบและใช้ Interest Coverage แทน)",
        "direction": "lower_is_better",
        "red": 2.5,
        "amber": 1.0,
        "green": 0.3,
        "base_weight": 15.0,
        "overlays": ["standard"],
        "categories": None,
        "format_type": "ratio_x",
    },
    "interest_coverage": {
        "pillar": "lynch_safety",
        "label_en": "Interest Coverage",
        "label_th": "Interest Coverage (ความสามารถในการจ่ายดอกเบี้ย)",
        "description_th": "กำไรจากการดำเนินงาน (EBIT) หารด้วยดอกเบี้ยจ่าย บ่งชี้ความปลอดภัยของภาระหนี้",
        "direction": "higher_is_better",
        "red": 2.0,
        "amber": 6.0,
        "green": 15.0,
        "base_weight": 20.0,
        "overlays": ["standard", "reit"],
        "categories": None,
        "format_type": "ratio_x",
    },
    "fcf_conversion_3y": {
        "pillar": "lynch_safety",
        "label_en": "3Y FCF Conversion",
        "label_th": "3Y FCF Conversion (อัตราแปลงกำไรเป็นกระแสเงินสดอิสระ 3 ปี)",
        "description_th": "กระแสเงินสดอิสระ (Free Cash Flow) สะสม 3 ปี หารด้วยกำไรสุทธิสะสม 3 ปี",
        "direction": "higher_is_better",
        "red": 0.40,
        "amber": 0.75,
        "green": 1.00,
        "base_weight": 15.0,
        "overlays": ["standard", "reit"],
        "categories": None,
        "format_type": "percent",
    },
    "inventory_vs_revenue_spread": {
        "pillar": "lynch_safety",
        "label_en": "Inventory vs Revenue Spread",
        "label_th": "Inventory vs Revenue Spread (ส่วนต่างการโตของสินค้าคงคลังเทียบรายได้)",
        "description_th": "การเติบโตของสินค้าคงคลังลบด้วยรายได้ YoY (ใช้เฉพาะธุรกิจที่สินค้าคงคลังเกิน 5% ของสินทรัพย์รวม)",
        "direction": "lower_is_better",
        "red": 0.15,
        "amber": 0.03,
        "green": -0.03,
        "base_weight": 10.0,
        "overlays": ["standard"],
        "categories": None,
        "format_type": "spread_pct",
    },
    # --- Lynch Safety (Financials Overlay) ---
    "equity_to_assets": {
        "pillar": "lynch_safety",
        "label_en": "Equity / Total Assets",
        "label_th": "Equity / Assets (สัดส่วนส่วนทุนต่อสินทรัพย์รวม)",
        "description_th": "ฐานะความแข็งแกร่งของเงินกองทุนในสถาบันการเงิน ยิ่งสูงยิ่งรองรับความเสี่ยงได้ดี",
        "direction": "higher_is_better",
        "red": 0.05,
        "amber": 0.08,
        "green": 0.12,
        "base_weight": 40.0,
        "overlays": ["financials"],
        "categories": None,
        "format_type": "percent",
    },
    "earnings_stability_5y": {
        "pillar": "lynch_safety",
        "label_en": "5Y Earnings Stability",
        "label_th": "5Y Earnings Stability (ความสม่ำเสมอของกำไร 5 ปี)",
        "description_th": "สัดส่วนจำนวนปีที่มีกำไรสุทธิเป็นบวกตลอดช่วงข้อมูล 5 ปีย้อนหลัง",
        "direction": "higher_is_better",
        "red": 0.40,
        "amber": 0.80,
        "green": 1.00,
        "base_weight": 35.0,
        "overlays": ["financials"],
        "categories": None,
        "format_type": "percent",
    },
    "payout_sustainability": {
        "pillar": "lynch_safety",
        "label_en": "Dividend Payout Ratio",
        "label_th": "Payout Sustainability (ความยั่งยืนของการจ่ายปันผล)",
        "description_th": "สัดส่วนเงินปันผลจ่ายต่อกำไรสุทธิ (Payout Ratio) ค่าที่ไม่สูงเกินไปช่วยให้สถาบันการเงินสะสมทุนได้",
        "direction": "lower_is_better",
        "red": 0.85,
        "amber": 0.55,
        "green": 0.30,
        "base_weight": 25.0,
        "overlays": ["financials"],
        "categories": None,
        "format_type": "percent",
    },
    # --- Fisher Quality ---
    "roic_5y_avg": {
        "pillar": "fisher_quality",
        "label_en": "5Y Avg ROIC",
        "label_th": "5Y Avg ROIC (ผลตอบแทนต่อเงินลงทุนเฉลี่ย 5 ปี)",
        "description_th": "อัตราผลตอบแทนจากเงินลงทุน (NOPAT / Invested Capital) เฉลี่ย 5 ปี สะท้อนความได้เปรียบเชิงแข่งขัน",
        "direction": "higher_is_better",
        "red": 0.06,
        "amber": 0.12,
        "green": 0.22,
        "base_weight": 35.0,
        "overlays": ["standard", "reit"],
        "categories": None,
        "format_type": "percent",
    },
    "roe_5y_avg": {
        "pillar": "fisher_quality",
        "label_en": "5Y Avg ROE",
        "label_th": "5Y Avg ROE (ผลตอบแทนต่อส่วนของผู้ถือหุ้นเฉลี่ย 5 ปี)",
        "description_th": "ผลตอบแทนต่อส่วนของผู้ถือหุ้นเฉลี่ย 5 ปี สำหรับประเมินประสิทธิภาพทำกำไรของกลุ่มการเงิน",
        "direction": "higher_is_better",
        "red": 0.06,
        "amber": 0.11,
        "green": 0.16,
        "base_weight": 40.0,
        "overlays": ["financials"],
        "categories": None,
        "format_type": "percent",
    },
    "gross_margin_trend_5y": {
        "pillar": "fisher_quality",
        "label_en": "Gross Margin 5Y Trend",
        "label_th": "Gross Margin 5Y Trend (แนวโน้มอัตรากำไรขั้นต้น 5 ปี)",
        "description_th": "ความชันรายปีของอัตรากำไรขั้นต้น (Percentage Points/ปี) สะท้อนอำนาจการตั้งราคา (Pricing Power)",
        "direction": "higher_is_better",
        "red": -1.5,
        "amber": -0.2,
        "green": 1.0,
        "base_weight": 15.0,
        "overlays": ["standard", "reit"],
        "categories": None,
        "format_type": "pp_per_year",
    },
    "operating_margin_trend_5y": {
        "pillar": "fisher_quality",
        "label_en": "Operating Margin 5Y Trend",
        "label_th": "Operating Margin 5Y Trend (แนวโน้มอัตรากำไรจากการดำเนินงาน 5 ปี)",
        "description_th": "ความชันรายปีของอัตรากำไรจากการดำเนินงาน (หรือ Pre-Tax/Net Margin ในกลุ่มการเงิน)",
        "direction": "higher_is_better",
        "red": -1.5,
        "amber": -0.2,
        "green": 1.0,
        "base_weight": 20.0,
        "overlays": ["standard", "reit", "financials"],
        "categories": None,
        "format_type": "pp_per_year",
    },
    "revenue_consistency_5y": {
        "pillar": "fisher_quality",
        "label_en": "5Y Revenue Consistency",
        "label_th": "5Y Revenue Consistency (ความสม่ำเสมอการเติบโตของรายได้)",
        "description_th": "จำนวนปีที่รายได้เติบโตเป็นบวกเทียบกับช่วงปีที่ตรวจสอบ (x/N)",
        "direction": "higher_is_better",
        "red": 0.40,
        "amber": 0.75,
        "green": 1.00,
        "base_weight": 15.0,
        "overlays": ["standard", "reit", "financials"],
        "categories": None,
        "format_type": "consistency",
    },
    "rd_productivity_3y": {
        "pillar": "fisher_quality",
        "label_en": "3Y R&D Productivity",
        "label_th": "3Y R&D Productivity (ประสิทธิภาพการลงทุน R&D 3 ปี)",
        "description_th": "กำไรขั้นต้นที่เพิ่มขึ้นเทียบกับงบวิจัยและพัฒนา (R&D) สะสมในช่วงเดียวกัน (ข้ามหากไม่มี R&D ที่มีนัยสำคัญ)",
        "direction": "higher_is_better",
        "red": 0.0,
        "amber": 1.0,
        "green": 2.5,
        "base_weight": 15.0,
        "overlays": ["standard"],
        "categories": None,
        "format_type": "ratio_x",
    },
}

# Hard Red Flag penalty rules and non-penalty warning badges.
RED_FLAG_RULES: dict[str, dict[str, Any]] = {
    "inventory_pileup": {
        "id": "inventory_pileup",
        "label_en": "Inventory Pile-Up",
        "label_th": "สัญญาณเตือนสินค้าคงคลังบวม (Inventory Pile-Up)",
        "description_th": (
            "สินค้าคงคลังเติบโตเร็วกว่ายอดขายเกิน 15 percentage points และเพิ่มขึ้นเกิน 10% YoY "
            "อาจสะท้อนปัญหาสินค้าขายไม่ออก"
        ),
        "severity": "hard",
        "penalty": -10.0,
        "spread_threshold": 0.15,
        "inventory_yoy_threshold": 0.10,
    },
    "heavy_share_dilution": {
        "id": "heavy_share_dilution",
        "label_en": "Heavy Share Dilution",
        "label_th": "การเพิ่มทุน/ออกหุ้นใหม่เจือจางสูง (Heavy Share Dilution)",
        "description_th": (
            "จำนวนหุ้นปรับลด (Diluted Shares) เพิ่มขึ้นเฉลี่ยเกิน 5% ต่อปี ลดทอนสัดส่วนกำไรต่อหุ้นของผู้ถือหุ้นเดิม"
        ),
        "severity": "hard",
        "penalty": -8.0,
        "cagr_threshold": 0.05,
    },
    "earnings_fcf_divergence": {
        "id": "earnings_fcf_divergence",
        "label_en": "Earnings vs FCF Divergence",
        "label_th": "กำไรทางบัญชีโตสวนทางกระแสเงินสด (Earnings/FCF Divergence)",
        "description_th": (
            "กำไรสุทธิเติบโตเกิน 15% YoY แต่กระแสเงินสดอิสระ (FCF) ติดลบต่อเนื่อง 2 ปีงบประมาณล่าสุด"
        ),
        "severity": "hard",
        "penalty": -10.0,
        "ni_yoy_threshold": 0.15,
        "negative_fcf_years": 2,
    },
    "cyclical_pe_trap": {
        "id": "cyclical_pe_trap",
        "label_en": "Cyclical P/E Trap",
        "label_th": "ข้อควรระวังกับดัก P/E หุ้นวัฏจักร (Cyclical P/E Trap)",
        "description_th": (
            "หุ้นวัฏจักรที่ค่า P/E ดูต่ำกว่า 15x อาจเกิดจากกำไรอยู่ในจุดสูงสุดของรอบวัฏจักร (Peak Earnings)"
        ),
        "severity": "warning",
        "penalty": 0.0,
        "pe_ceiling": 15.0,
    },
}
