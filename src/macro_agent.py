"""
Cyber Trade - Macro & Cross-Market Correlation Agent
=====================================================
Analyzes the global macro environment:
- US Dollar Index (DXY) trend & key levels
- Correlation between DXY and Gold (XAUUSD)
- Correlation between DXY and Bitcoin (BTC)
- Risk-On vs Risk-Off market sentiment

Provides macro confluence boost (+10% to +15%) to valid technical signals.
"""

from dataclasses import dataclass
from typing import Optional, Dict, Tuple
import polars as pl
import numpy as np
from loguru import logger


@dataclass
class MacroReport:
    """Summary of global macro conditions."""
    dxy_price: float
    dxy_trend: str              # "BULLISH", "BEARISH", "RANGING"
    risk_sentiment: str         # "RISK_ON", "RISK_OFF", "NEUTRAL"
    gold_alignment: str         # "STRONG_BUY_FAVORABLE", "STRONG_SELL_FAVORABLE", "NEUTRAL"
    crypto_alignment: str       # "STRONG_BUY_FAVORABLE", "STRONG_SELL_FAVORABLE", "NEUTRAL"
    confluence_boost: float     # e.g. +0.10 or -0.10
    reason: str


class MacroAgent:
    """
    Evaluates global macro indicators and asset correlations.
    """

    def __init__(self, ema_fast: int = 20, ema_slow: int = 50):
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow

    def analyze_dxy(self, dxy_df: Optional[pl.DataFrame]) -> Tuple[str, float]:
        """
        Determine DXY trend (Bullish/Bearish/Ranging) using EMAs and price action.
        """
        if dxy_df is None or len(dxy_df) < 20:
            return "NEUTRAL", 0.0

        close = dxy_df["close"].to_numpy()
        current_price = float(close[-1])

        # Simple fast/slow EMA calculation using numpy
        def calc_ema(arr, span):
            if len(arr) == 0:
                return np.array([])
            effective_span = min(span, len(arr))
            alpha = 2 / (effective_span + 1)
            ema = [arr[0]]
            for val in arr[1:]:
                ema.append(alpha * val + (1 - alpha) * ema[-1])
            return np.array(ema)

        ema20 = calc_ema(close, self.ema_fast)
        ema50 = calc_ema(close, self.ema_slow)

        if len(ema20) > 0 and len(ema50) > 0:
            if ema20[-1] > ema50[-1] and current_price > ema20[-1]:
                trend = "BULLISH"
            elif ema20[-1] < ema50[-1] and current_price < ema20[-1]:
                trend = "BEARISH"
            else:
                trend = "RANGING"
        else:
            trend = "NEUTRAL"

        return trend, current_price

    def evaluate_macro(
        self,
        dxy_df: Optional[pl.DataFrame],
        target_symbol: str = "XAUUSD",
        technical_direction: str = "BUY",
    ) -> MacroReport:
        """
        Evaluate how macro conditions affect the proposed technical signal.
        """
        dxy_trend, dxy_price = self.analyze_dxy(dxy_df)

        # Default Neutral
        risk_sentiment = "NEUTRAL"
        gold_alignment = "NEUTRAL"
        crypto_alignment = "NEUTRAL"
        confluence_boost = 0.0
        reasons = []

        if dxy_trend == "BEARISH":
            # Weak dollar = Bullish for Gold & Crypto (Risk-On)
            risk_sentiment = "RISK_ON"
            gold_alignment = "STRONG_BUY_FAVORABLE"
            crypto_alignment = "STRONG_BUY_FAVORABLE"
            reasons.append("AQSH Dollari (DXY) pasayuvchi trendda — XAU va BTC uchun o'sish qulay muhit.")

            if technical_direction == "BUY":
                confluence_boost = 0.12  # +12% confidence boost
                reasons.append("DXY pasayishi Buy signalini to'liq tasdiqlaydi (+12% Confluence).")
            else:
                confluence_boost = -0.10  # Penalize Sell signals against macro trend
                reasons.append("Sell signali zaif dollar foniga zid kelmoqda.")

        elif dxy_trend == "BULLISH":
            # Strong dollar = Pressure on Gold & Crypto (Risk-Off)
            risk_sentiment = "RISK_OFF"
            gold_alignment = "STRONG_SELL_FAVORABLE"
            crypto_alignment = "STRONG_SELL_FAVORABLE"
            reasons.append("AQSH Dollari (DXY) o'suvchi trendda — XAU va BTC ustidan bosim mavjud.")

            if technical_direction == "SELL":
                confluence_boost = 0.12  # +12% confidence boost
                reasons.append("DXY kuchayishi Sell signalini to'liq tasdiqlaydi (+12% Confluence).")
            else:
                confluence_boost = -0.10  # Penalize counter-trend Buy
                reasons.append("Buy signali kuchli dollar foniga zid kelmoqda.")

        else:
            reasons.append("DXY flet (konsolidatsiya) holatida — neytral makro fon.")

        return MacroReport(
            dxy_price=dxy_price,
            dxy_trend=dxy_trend,
            risk_sentiment=risk_sentiment,
            gold_alignment=gold_alignment,
            crypto_alignment=crypto_alignment,
            confluence_boost=confluence_boost,
            reason=" | ".join(reasons),
        )
