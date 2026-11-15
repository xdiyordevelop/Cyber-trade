"""
Cyber Trade - Dynamic Confidence & Signal Quality Manager
=========================================================
Dynamically adjusts the required confidence threshold based on market quality:
- Golden sessions (London-NY Overlap, High Liquidity) -> Lower threshold (permits great setups)
- Choppy / Ranging / Low liquidity periods -> Higher strict threshold (blocks bad setups)
- Assigns Signal Grades:
  • Grade A+ (Sniper / High Confluence): SMC + Trend + ML + Session aligned
  • Grade A  (Standard / Trend Momentum): Solid structure + Volume/Trend confirmation
  • Grade B  (Scalp / Quick Reaction): Aggressive setups for active scalpers
"""

from dataclasses import dataclass
from typing import Optional, Tuple, List, Dict
from enum import Enum
from loguru import logger


class SignalGrade(Enum):
    GRADE_A_PLUS = "A+ (Sniper Confluence)"
    GRADE_A = "A (Trend Momentum)"
    GRADE_B = "B (Scalp / Quick Reaction)"


class MarketQuality(Enum):
    EXCELLENT = "A'lo (Yuqori Likvidlik)"
    GOOD = "Yaxshi (Normal Trend)"
    MODERATE = "O'rtacha (Konsolidatsiya)"
    POOR = "Past (Shovqinli Bozor)"
    AVOID = "Xavfli (Savdo Qilish Tavsiya Etilmaydi)"


@dataclass
class MarketAnalysis:
    quality: MarketQuality
    confidence_threshold: float
    grade: SignalGrade
    score: int                  # 0 to 100
    reasons: List[str]


class DynamicConfidenceManager:
    """
    Intelligent Market Confluence Evaluator.
    Prevents both extremes:
    1. Being too strict (0 signals for days)
    2. Being too loose (spamming fake signals)
    """

    def __init__(
        self,
        base_threshold: float = 0.58,
        min_threshold: float = 0.50,
        max_threshold: float = 0.75,
    ):
        self.base_threshold = base_threshold
        self.min_threshold = min_threshold
        self.max_threshold = max_threshold

    def evaluate_setup(
        self,
        session_name: str,
        regime: str,
        trend_aligned: bool,
        has_smc_confirmation: bool,
        ml_confidence: float,
        macro_boost: float = 0.0,
    ) -> MarketAnalysis:
        """
        Dynamically calculate setup quality score (0-100) and required threshold.
        """
        score = 50
        reasons = []

        # 1. Session Weight (Up to +20 points)
        sess_lower = session_name.lower()
        if "overlap" in sess_lower or "kesishuvi" in sess_lower or "oltin" in sess_lower:
            score += 20
            reasons.append("Eng faol sessiya (London-NY Overlap)")
        elif "london" in sess_lower:
            score += 15
            reasons.append("London sessiyasi (Kuchli hajm)")
        elif "ny" in sess_lower or "nyu-york" in sess_lower:
            score += 12
            reasons.append("Nyu-York sessiyasi")
        elif "osiyo" in sess_lower or "tokio" in sess_lower:
            score += 5
            reasons.append("Osiyo sessiyasi (O'rtacha hajm)")
        else:
            score -= 10
            reasons.append("Nofaol savdo soatlari")

        # 2. Market Regime Weight (Up to +15 points)
        reg_lower = regime.lower().replace(" ", "_")
        if "trending" in reg_lower or "medium_volatility" in reg_lower:
            score += 15
            reasons.append("Sog'lom bozor rejimi (Trending)")
        elif "low_volatility" in reg_lower or "ranging" in reg_lower:
            score -= 5
            reasons.append("Bozor flet (konsolidatsiya) holatida")
        elif "high_volatility" in reg_lower:
            score += 5
            reasons.append("Yuqori volatillik (Kengroq harakatlar)")
        elif "crisis" in reg_lower:
            score -= 25
            reasons.append("Xavfli bozor inqirozi rejimi")

        # 3. Multi-Timeframe Trend Alignment (Up to +15 points)
        if trend_aligned:
            score += 15
            reasons.append("Katta timeframe (HTF) trendi bilan mos")
        else:
            score -= 10
            reasons.append("Katta trendga qarshi (Counter-trend)")

        # 4. SMC Confirmation (Up to +15 points)
        if has_smc_confirmation:
            score += 15
            reasons.append("SMC Zonasi (Order Block / FVG / BOS)")
        else:
            score -= 5
            reasons.append("SMC zonasi aniqlanmadi")

        # 5. Macro DXY Alignment (+10 points)
        if macro_boost > 0.05:
            score += 10
            reasons.append("Makro DXY korrelyatsiyasi signalni qo'llab-quvvatlaydi")
        elif macro_boost < -0.05:
            score -= 10
            reasons.append("Makro DXY foniga zid")

        # Clamp score between 0 and 100
        score = max(0, min(100, score))

        # Determine Market Quality and Adaptive Threshold
        if score >= 80:
            quality = MarketQuality.EXCELLENT
            threshold = self.min_threshold       # 50% - Best conditions, don't miss great setups
            grade = SignalGrade.GRADE_A_PLUS
        elif score >= 65:
            quality = MarketQuality.GOOD
            threshold = self.base_threshold      # 55-58% - Standard reliable setups
            grade = SignalGrade.GRADE_A
        elif score >= 50:
            quality = MarketQuality.MODERATE
            threshold = 0.62                     # 62% - Moderate conditions, require better ML proof
            grade = SignalGrade.GRADE_B
        elif score >= 35:
            quality = MarketQuality.POOR
            threshold = 0.70
            grade = SignalGrade.GRADE_B
        else:
            quality = MarketQuality.AVOID
            threshold = self.max_threshold       # 75% - Bad market, avoid trading
            grade = SignalGrade.GRADE_B

        return MarketAnalysis(
            quality=quality,
            confidence_threshold=threshold,
            grade=grade,
            score=score,
            reasons=reasons,
        )
