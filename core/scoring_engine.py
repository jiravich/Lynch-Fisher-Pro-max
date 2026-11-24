"""Peter Lynch & Philip Fisher quantitative scoring engine.

Includes:
- 6-category Lynch Auto-Classifier with strict priority ordering and manual override.
- Continuous Linear Interpolation scorer (0-100) between red/amber/green thresholds.
- Dynamic Re-weighting across missing/inapplicable metrics and data_coverage_pct.
- Hard Red Flag penalty scanner and Cyclical P/E Trap warning evaluator.
"""

from __future__ import annotations

import math
from typing import Any

from config.scoring_config import (
    CATEGORY_METADATA,
    CATEGORY_PRIORITY,
    CLASSIFICATION_RULES,
    METRIC_CONFIGS,
    PILLAR_METADATA,
    PILLAR_WEIGHTS,
    RED_FLAG_RULES,
    SECTOR_OVERLAYS,
    SIGNAL_THRESHOLDS,
)
from core.metrics import compute_all_metrics


def _clamp(val: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, val))


def _signal_from_score(score: float | None) -> str:
    if score is None:
        return "neutral"
    if score >= SIGNAL_THRESHOLDS["green"]:
        return "green"
    if score >= SIGNAL_THRESHOLDS["amber"]:
        return "amber"
    return "red"


def linear_interpolate_score(
    value: float,
    red: float,
    amber: float,
    green: float,
    direction: str,
) -> float:
    """Map metric value continuously to [0, 100] via piecewise linear interpolation."""
    if direction == "higher_is_better":
        if value <= red:
            return 0.0
        if value >= green:
            return 100.0
        if value <= amber:
            span = amber - red
            return 50.0 * ((value - red) / span) if span != 0 else 50.0
        span = green - amber
        return 50.0 + 50.0 * ((value - amber) / span) if span != 0 else 100.0

    # lower_is_better: red > amber > green
    if value >= red:
        return 0.0
    if value <= green:
        return 100.0
    if value >= amber:
        span = red - amber
        return 50.0 * ((red - value) / span) if span != 0 else 50.0
    span = amber - green
    return 50.0 + 50.0 * ((amber - value) / span) if span != 0 else 100.0


def classify_lynch_category(
    stock_data: dict[str, Any], metrics: dict[str, Any]
) -> dict[str, Any]:
    """Auto-classify into Peter Lynch's 6 categories using strict priority order."""
    profile = stock_data.get("profile", {})
    market = stock_data.get("market", {})
    overlay = metrics["overlay"]
    growth = metrics["growth"]
    valuation = metrics["valuation"]
    safety = metrics["safety"]
    quality = metrics["quality"]

    overlay_name = overlay["overlay"]
    sector = str(profile.get("sector", ""))
    industry = str(profile.get("industry", ""))
    industry_lower = industry.lower()

    eps_ttm = growth.get("eps_ttm")
    ni_ttm = growth.get("net_income_ttm")
    latest_annual_ni = growth.get("latest_annual_net_income")
    loss_years = growth.get("annual_loss_years", 0)
    blended_g = growth.get("blended_growth")
    rev_cagr = growth.get("revenue_cagr")
    fwd_g = growth.get("forward_growth")
    eps_cv = growth.get("eps_cv")
    max_eps_drop = growth.get("max_eps_yoy_drop")
    rev_consistency = quality.get("revenue_consistency_5y")

    pe_ttm = valuation.get("pe_ttm")
    pb_ratio = valuation.get("pb_ratio")
    cash_to_price = valuation.get("cash_to_price")
    net_cash_to_mcap = valuation.get("net_cash_to_market_cap")
    div_yield = valuation.get("dividend_yield") or 0.0
    market_cap = market.get("market_cap") or 0.0

    net_debt_ebitda = safety.get("net_debt_to_ebitda")
    int_cov = safety.get("interest_coverage")

    rules = CLASSIFICATION_RULES

    # 1. Turnarounds
    t_cfg = rules["turnarounds"]
    turnaround_reasons: list[str] = []
    if eps_ttm is not None and eps_ttm <= 0:
        turnaround_reasons.append("EPS TTM <= 0")
    if ni_ttm is not None and ni_ttm <= 0:
        turnaround_reasons.append("Net Income TTM <= 0")
    if latest_annual_ni is not None and latest_annual_ni <= 0:
        turnaround_reasons.append("กำไรสุทธิปีล่าสุดติดลบ (Latest Annual Net Income <= 0)")
    if loss_years >= t_cfg["min_loss_years"]:
        turnaround_reasons.append(f"ขาดทุน {loss_years} ปีในรอบ 5 ปี")
    if (
        overlay_name == "standard"
        and net_debt_ebitda is not None
        and int_cov is not None
        and net_debt_ebitda > t_cfg["distress_net_debt_to_ebitda"]
        and int_cov < t_cfg["distress_interest_coverage"]
    ):
        turnaround_reasons.append(
            f"ภาระหนี้สูง (Net Debt/EBITDA {net_debt_ebitda:.2f}x, Int Cov {int_cov:.2f}x)"
        )

    if turnaround_reasons:
        cat = "Turnarounds"
        return {
            "auto_category": cat,
            **CATEGORY_METADATA[cat],
            "rationale_th": "จัดอยู่ในกลุ่ม Turnarounds เนื่องจาก " + ", ".join(turnaround_reasons),
        }

    # 2. Cyclicals
    c_cfg = rules["cyclicals"]
    is_cyclical_sector = sector in c_cfg["sectors"]
    matched_kw = next(
        (kw for kw in c_cfg["industry_keywords"] if kw in industry_lower), None
    )
    secular_hyper_grower = (
        blended_g is not None
        and blended_g >= c_cfg["secular_growth_exclusion"]
        and rev_consistency is not None
        and rev_consistency >= c_cfg["secular_consistency_exclusion"]
    )
    quant_cyclical = (
        not secular_hyper_grower
        and eps_cv is not None
        and max_eps_drop is not None
        and eps_cv >= c_cfg["eps_cv_threshold"]
        and max_eps_drop <= c_cfg["max_eps_yoy_drop_threshold"]
    )

    if is_cyclical_sector or matched_kw or quant_cyclical:
        cat = "Cyclicals"
        if is_cyclical_sector:
            reason = f"อยู่ในกลุ่มอุตสาหกรรมวัฏจักรโดยตรง (Sector: {sector}, Industry: {industry})"
        elif matched_kw:
            reason = f"ธุรกิจอิงรอบเศรษฐกิจ/สินค้าโภคภัณฑ์ (Industry: {industry})"
        else:
            reason = (
                f"ความผันผวนของกำไรสูงตามวัฏจักร (EPS CV {eps_cv:.2f}, "
                f"Max YoY Drop {max_eps_drop * 100:.1f}%)"
            )
        return {
            "auto_category": cat,
            **CATEGORY_METADATA[cat],
            "rationale_th": reason,
        }

    # 3. Asset Plays
    a_cfg = rules["asset_plays"]
    asset_play_reason: str | None = None
    if pb_ratio is not None and 0 < pb_ratio < a_cfg["max_pb_for_asset_play"]:
        if cash_to_price is not None and cash_to_price >= a_cfg["min_cash_to_price"]:
            asset_play_reason = (
                f"P/B ต่ำ ({pb_ratio:.2f}x) ร่วมกับเงินสดต่อมูลค่าตลาดสูง ({cash_to_price * 100:.1f}%)"
            )
        elif (
            pb_ratio < a_cfg["low_growth_pb_ceiling"]
            and blended_g is not None
            and blended_g < a_cfg["low_growth_ceiling"]
        ):
            asset_play_reason = (
                f"ราคาต่ำกว่ามูลค่าทางบัญชีชัดเจน (P/B {pb_ratio:.2f}x, g {blended_g * 100:.1f}%)"
            )
    if (
        asset_play_reason is None
        and net_cash_to_mcap is not None
        and net_cash_to_mcap >= a_cfg["min_net_cash_to_market_cap"]
        and (
            (pe_ttm is not None and pe_ttm < a_cfg["net_cash_max_pe"])
            or (pb_ratio is not None and pb_ratio < a_cfg["net_cash_max_pb"])
        )
    ):
        asset_play_reason = (
            f"เงินสดสุทธิสูงเทียบ Market Cap ({net_cash_to_mcap * 100:.1f}%) และราคาไม่แพง"
        )
    if (
        asset_play_reason is None
        and overlay_name == "reit"
        and pb_ratio is not None
        and 0 < pb_ratio < a_cfg["reit_max_pb"]
    ):
        asset_play_reason = f"REIT ซื้อขายต่ำกว่า NAV/Book Value (P/B {pb_ratio:.2f}x)"

    if asset_play_reason:
        cat = "Asset Plays"
        return {
            "auto_category": cat,
            **CATEGORY_METADATA[cat],
            "rationale_th": asset_play_reason,
        }

    # 4. Fast Growers
    fg_cfg = rules["fast_growers"]
    if blended_g is not None and blended_g >= fg_cfg["min_blended_growth"]:
        rev_ok = (
            rev_cagr is None
            or rev_cagr >= fg_cfg["min_revenue_cagr"]
            or (fwd_g is not None and fwd_g >= fg_cfg["min_forward_growth_fallback"])
        )
        if rev_ok:
            cat = "Fast Growers"
            return {
                "auto_category": cat,
                **CATEGORY_METADATA[cat],
                "rationale_th": (
                    f"Blended Growth อยู่ที่ {blended_g * 100:.1f}% (>= 20%) "
                    f"พร้อมแรงส่งการเติบโตต่อเนื่อง"
                ),
            }

    # 5. Stalwarts
    st_cfg = rules["stalwarts"]
    is_stalwart = False
    if blended_g is not None:
        if st_cfg["min_blended_growth"] <= blended_g < st_cfg["max_blended_growth"]:
            is_stalwart = True
        elif (
            st_cfg["megacap_min_growth"] <= blended_g < st_cfg["max_blended_growth"]
            and market_cap >= st_cfg["megacap_market_cap"]
            and div_yield < st_cfg["megacap_max_dividend_yield"]
        ):
            is_stalwart = True

    if is_stalwart:
        cat = "Stalwarts"
        return {
            "auto_category": cat,
            **CATEGORY_METADATA[cat],
            "rationale_th": (
                f"Blended Growth อยู่ที่ {blended_g * 100:.1f}% "
                f"อยู่ในเกณฑ์ผู้นำตลาดโตมั่นคง (10%-20%)"
            ),
        }

    # 6. Slow Growers (Fallback)
    cat = "Slow Growers"
    g_disp = f"{blended_g * 100:.1f}%" if blended_g is not None else "N/A"
    return {
        "auto_category": cat,
        **CATEGORY_METADATA[cat],
        "rationale_th": (
            f"อัตราเติบโตผสมอยู่ที่ {g_disp} (ต่ำกว่าเกณฑ์ Stalwarts 10%) "
            f"และอัตราปันผล {div_yield * 100:.2f}%"
        ),
    }


def evaluate_red_flags(
    metrics: dict[str, Any], active_category: str, overlay: dict[str, Any]
) -> dict[str, Any]:
    """Scan hard red flag penalties and non-penalty warning badges."""
    overlay_name = overlay["overlay"]
    safety = metrics["safety"]
    valuation = metrics["valuation"]

    hard_flags: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    all_checks: list[dict[str, Any]] = []

    # 1. Inventory Pile-Up (-10)
    r_inv = RED_FLAG_RULES["inventory_pileup"]
    inv_triggered = False
    inv_detail = "ไม่พบสัญญาณสินค้าคงคลังบวม"
    if not safety.get("inventory_applicable"):
        inv_detail = "ไม่ใช้เกณฑ์นี้ (สินค้าคงคลัง <= 5% ของสินทรัพย์ หรืออยู่ในกลุ่ม Financials/REIT)"
    else:
        spread = safety.get("inventory_vs_revenue_spread")
        inv_yoy = safety.get("inventory_yoy")
        if (
            spread is not None
            and inv_yoy is not None
            and spread > r_inv["spread_threshold"]
            and inv_yoy > r_inv["inventory_yoy_threshold"]
        ):
            inv_triggered = True
            inv_detail = (
                f"Inventory YoY ({inv_yoy * 100:.1f}%) โตเร็วกว่า Revenue "
                f"(Spread +{spread * 100:.1f} pp)"
            )
    item_inv = {
        "id": r_inv["id"],
        "label_en": r_inv["label_en"],
        "label_th": r_inv["label_th"],
        "description_th": r_inv["description_th"],
        "severity": r_inv["severity"],
        "penalty": r_inv["penalty"] if inv_triggered else 0.0,
        "triggered": inv_triggered,
        "detail_th": inv_detail,
    }
    all_checks.append(item_inv)
    if inv_triggered:
        hard_flags.append(item_inv)

    # 2. Heavy Share Dilution (-8)
    r_dil = RED_FLAG_RULES["heavy_share_dilution"]
    dil_cagr = safety.get("share_dilution_cagr")
    dil_triggered = dil_cagr is not None and dil_cagr > r_dil["cagr_threshold"]
    if dil_cagr is None:
        dil_detail = "ไม่มีข้อมูลจำนวนหุ้นปรับลดเพียงพอ"
    elif dil_triggered:
        dil_detail = f"จำนวนหุ้นปรับลดเพิ่มขึ้นเฉลี่ย {dil_cagr * 100:.2f}% ต่อปี (> 5.0%)"
    else:
        dil_detail = f"อัตราเปลี่ยนแปลงจำนวนหุ้น {dil_cagr * 100:+.2f}% ต่อปี (ปกติ)"
    item_dil = {
        "id": r_dil["id"],
        "label_en": r_dil["label_en"],
        "label_th": r_dil["label_th"],
        "description_th": r_dil["description_th"],
        "severity": r_dil["severity"],
        "penalty": r_dil["penalty"] if dil_triggered else 0.0,
        "triggered": dil_triggered,
        "detail_th": dil_detail,
    }
    all_checks.append(item_dil)
    if dil_triggered:
        hard_flags.append(item_dil)

    # 3. Earnings vs FCF Divergence (-10)
    r_fcf = RED_FLAG_RULES["earnings_fcf_divergence"]
    ni_yoy = safety.get("net_income_yoy")
    fcf_neg_2y = bool(safety.get("fcf_negative_2y"))
    fcf_triggered = False
    if overlay_name == "financials":
        fcf_detail = "ข้ามการตรวจ FCF สำหรับกลุ่มสถาบันการเงิน (Financials Overlay)"
    elif (
        ni_yoy is not None
        and ni_yoy > r_fcf["ni_yoy_threshold"]
        and fcf_neg_2y
    ):
        fcf_triggered = True
        fcf_detail = (
            f"กำไรสุทธิโต +{ni_yoy * 100:.1f}% YoY แต่ Free Cash Flow ติดลบต่อเนื่อง 2 ปีล่าสุด"
        )
    else:
        fcf_detail = "ไม่พบความขัดแย้งระหว่างกำไรทางบัญชีและกระแสเงินสดอิสระ"
    item_fcf = {
        "id": r_fcf["id"],
        "label_en": r_fcf["label_en"],
        "label_th": r_fcf["label_th"],
        "description_th": r_fcf["description_th"],
        "severity": r_fcf["severity"],
        "penalty": r_fcf["penalty"] if fcf_triggered else 0.0,
        "triggered": fcf_triggered,
        "detail_th": fcf_detail,
    }
    all_checks.append(item_fcf)
    if fcf_triggered:
        hard_flags.append(item_fcf)

    # 4. Cyclical P/E Trap Warning (0 penalty)
    r_trap = RED_FLAG_RULES["cyclical_pe_trap"]
    pe_ttm = valuation.get("pe_ttm")
    trap_triggered = (
        active_category == "Cyclicals"
        and pe_ttm is not None
        and 0 < pe_ttm < r_trap["pe_ceiling"]
    )
    trap_detail = (
        f"หุ้น Cyclicals มี P/E {pe_ttm:.2f}x (< 15x) ระวังภาวะกำไรสูงสุดปลายรอบวัฏจักร"
        if trap_triggered
        else "ไม่อยู่ในเงื่อนไข Cyclical P/E Trap"
    )
    item_trap = {
        "id": r_trap["id"],
        "label_en": r_trap["label_en"],
        "label_th": r_trap["label_th"],
        "description_th": r_trap["description_th"],
        "severity": r_trap["severity"],
        "penalty": 0.0,
        "triggered": trap_triggered,
        "detail_th": trap_detail,
    }
    all_checks.append(item_trap)
    if trap_triggered:
        warnings.append(item_trap)

    total_penalty = sum(f["penalty"] for f in hard_flags)
    return {
        "hard_flags": hard_flags,
        "warnings": warnings,
        "all_checks": all_checks,
        "total_penalty": float(total_penalty),
    }


def _is_metric_applicable(
    metric_id: str,
    cfg: dict[str, Any],
    overlay_name: str,
    active_category: str,
    metrics: dict[str, Any],
) -> tuple[bool, str | None]:
    """Return (is_applicable, skip_reason_th) for a metric."""
    hidden = SECTOR_OVERLAYS.get(overlay_name, {}).get("hidden_metrics", [])
    if metric_id in hidden or overlay_name not in cfg.get("overlays", []):
        return False, f"ไม่ใช้ในโหมด {overlay_name} overlay"

    cat_map = cfg.get("categories_unless_overlay")
    if cat_map is not None:
        allowed_cats = cat_map.get(overlay_name)
        if allowed_cats is not None and active_category not in allowed_cats:
            return False, f"ใช้เฉพาะกลุ่ม {', '.join(allowed_cats)} หรือ Financials"

    safety = metrics["safety"]
    quality = metrics["quality"]

    if metric_id == "inventory_vs_revenue_spread" and not safety.get("inventory_applicable"):
        return False, "สินค้าคงคลัง <= 5% ของสินทรัพย์รวม (ไม่มีนัยสำคัญ)"

    if metric_id == "rd_productivity_3y" and not quality.get("rd_applicable"):
        return False, "ไม่มีงบ R&D ที่มีนัยสำคัญ (>= 1% ของรายได้)"

    if metric_id == "debt_to_equity" and safety.get("equity_negative"):
        return False, "Equity < 0 — ใช้ Interest Coverage แทน"

    return True, None


def analyze_stock(
    stock_data: dict[str, Any], category_override: str | None = None
) -> dict[str, Any]:
    """Run complete Lynch & Fisher analysis and return one unified JSON-safe dict."""
    metrics = compute_all_metrics(stock_data)
    overlay = metrics["overlay"]
    overlay_name = overlay["overlay"]

    classification = classify_lynch_category(stock_data, metrics)
    auto_category = classification["auto_category"]

    is_overridden = False
    active_category = auto_category
    if category_override is not None:
        if category_override not in CATEGORY_PRIORITY:
            raise ValueError(
                f"Invalid category_override '{category_override}'. "
                f"Must be one of {CATEGORY_PRIORITY}."
            )
        if category_override != auto_category:
            is_overridden = True
        active_category = category_override

    active_cat_meta = CATEGORY_METADATA[active_category]
    pillar_weights = dict(PILLAR_WEIGHTS[active_category])
    flat = metrics["flat_metrics"]
    safety = metrics["safety"]
    quality = metrics["quality"]

    pillar_results: dict[str, dict[str, Any]] = {}
    applicable_weight_total = 0.0
    available_weight_total = 0.0

    for pillar_id, p_meta in PILLAR_METADATA.items():
        p_weight = float(pillar_weights[pillar_id])
        metric_entries: list[dict[str, Any]] = []

        applicable_base_sum = 0.0
        scored_base_sum = 0.0
        weighted_score_sum = 0.0

        for metric_id, cfg in METRIC_CONFIGS.items():
            if cfg["pillar"] != pillar_id:
                continue

            applicable, skip_reason = _is_metric_applicable(
                metric_id, cfg, overlay_name, active_category, metrics
            )
            raw_val = flat.get(metric_id)
            base_w = float(cfg["base_weight"])

            score_val: float | None = None
            status = "missing"
            note_th = ""

            if not applicable:
                status = "skipped_inapplicable"
                note_th = skip_reason or "ไม่ใช้ในอุตสาหกรรมนี้"
            else:
                applicable_base_sum += base_w

                # Handle special financially healthy edge cases cleanly.
                if metric_id == "cash_to_debt" and safety.get("is_debt_free"):
                    score_val = 100.0
                    status = "scored"
                    note_th = "ไม่มีหนี้สินที่มีภาระดอกเบี้ย (Debt-free)"
                elif metric_id == "interest_coverage" and safety.get("no_interest_burden"):
                    score_val = 100.0
                    status = "scored"
                    note_th = "ไม่มีภาระดอกเบี้ยจ่ายและ EBIT เป็นบวก"
                elif metric_id == "net_debt_to_ebitda" and safety.get("is_debt_free"):
                    # Debt-free with positive/available EBITDA or net cash.
                    if raw_val is not None:
                        score_val = linear_interpolate_score(
                            raw_val,
                            cfg["red"],
                            cfg["amber"],
                            cfg["green"],
                            cfg["direction"],
                        )
                    else:
                        score_val = 100.0
                    status = "scored"
                    note_th = "ปลอดหนี้สิน (Debt-free)"
                elif raw_val is not None and math.isfinite(raw_val):
                    score_val = linear_interpolate_score(
                        raw_val,
                        cfg["red"],
                        cfg["amber"],
                        cfg["green"],
                        cfg["direction"],
                    )
                    status = "scored"
                else:
                    status = "missing"
                    if metric_id in {"peg_ratio", "pegy_ratio", "price_to_fair_value"}:
                        note_th = "N/A (P/E <= 0 หรืออัตราเติบโต g <= 0)"
                    elif metric_id == "fcf_conversion_3y":
                        note_th = "N/A (กำไรสุทธิสะสม 3 ปี <= 0 หรือขาดข้อมูล FCF)"
                    else:
                        note_th = "ไม่มีข้อมูลเพียงพอ"

                if status == "scored" and score_val is not None:
                    scored_base_sum += base_w
                    weighted_score_sum += score_val * base_w

            label_en = cfg["label_en"]
            if metric_id == "operating_margin_trend_5y":
                label_en = f"{quality.get('operating_margin_label', 'Operating Margin')} 5Y Trend"

            metric_entries.append(
                {
                    "metric_id": metric_id,
                    "label_en": label_en,
                    "label_th": cfg["label_th"],
                    "description_th": cfg["description_th"],
                    "format_type": cfg["format_type"],
                    "direction": cfg["direction"],
                    "thresholds": {
                        "red": cfg["red"],
                        "amber": cfg["amber"],
                        "green": cfg["green"],
                    },
                    "value": raw_val,
                    "score": round(score_val, 2) if score_val is not None else None,
                    "signal": _signal_from_score(score_val),
                    "base_weight": base_w,
                    "effective_weight_in_pillar": 0.0,
                    "status": status,
                    "note_th": note_th,
                }
            )

        # Assign dynamically normalized weights within the pillar.
        if scored_base_sum > 0:
            for item in metric_entries:
                if item["status"] == "scored":
                    item["effective_weight_in_pillar"] = round(
                        (item["base_weight"] / scored_base_sum) * 100.0, 2
                    )
            pillar_score = round(weighted_score_sum / scored_base_sum, 2)
        else:
            pillar_score = None

        pillar_coverage = (
            (scored_base_sum / applicable_base_sum)
            if applicable_base_sum > 0
            else 0.0
        )
        applicable_weight_total += p_weight if applicable_base_sum > 0 else 0.0
        available_weight_total += p_weight * pillar_coverage

        pillar_results[pillar_id] = {
            "pillar_id": pillar_id,
            "label_en": p_meta["label_en"],
            "label_th": p_meta["label_th"],
            "category_weight": p_weight,
            "effective_category_weight": 0.0,
            "score": pillar_score,
            "signal": _signal_from_score(pillar_score),
            "coverage_pct": round(pillar_coverage * 100.0, 2),
            "metrics": metric_entries,
        }

    # Dynamic re-weighting across pillars if an entire pillar has 0 scored metrics.
    active_pillar_weight_sum = sum(
        p["category_weight"]
        for p in pillar_results.values()
        if p["score"] is not None
    )
    if active_pillar_weight_sum > 0:
        raw_total = 0.0
        for p in pillar_results.values():
            if p["score"] is not None:
                eff_w = (p["category_weight"] / active_pillar_weight_sum) * 100.0
                p["effective_category_weight"] = round(eff_w, 2)
                raw_total += p["score"] * (eff_w / 100.0)
        raw_score = round(raw_total, 2)
    else:
        raw_score = 0.0

    data_coverage_pct = (
        round((available_weight_total / applicable_weight_total) * 100.0, 2)
        if applicable_weight_total > 0
        else 0.0
    )

    red_flags = evaluate_red_flags(metrics, active_category, overlay)
    final_score = round(_clamp(raw_score + red_flags["total_penalty"]), 2)

    return {
        "ticker": stock_data["ticker"],
        "profile": stock_data["profile"],
        "market": stock_data["market"],
        "cache_status": stock_data.get("cache_status", {}),
        "sector_overlay": overlay,
        "classification": {
            "auto_category": auto_category,
            "active_category": active_category,
            "is_overridden": is_overridden,
            "label_en": active_cat_meta["label_en"],
            "label_th": active_cat_meta["label_th"],
            "description_th": active_cat_meta["description_th"],
            "rationale_th": classification["rationale_th"],
        },
        "growth_summary": metrics["growth"],
        "valuation_summary": metrics["valuation"],
        "safety_summary": metrics["safety"],
        "quality_summary": metrics["quality"],
        "pillar_weights": pillar_weights,
        "pillars": pillar_results,
        "red_flags": red_flags,
        "scoring_summary": {
            "raw_score": raw_score,
            "red_flag_penalty": red_flags["total_penalty"],
            "final_score": final_score,
            "signal": _signal_from_score(final_score),
            "data_coverage_pct": data_coverage_pct,
        },
    }
