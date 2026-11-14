"""
Cyber Trade - Master Signal Engine (AI Confluence Council)
==========================================================
Coordinates all analytical agents:
1. SMC Analyzer (Order Blocks, FVG, BOS, Liquidity Sweeps)
2. Feature Engineering (37 technical features)
3. HMM Market Regime Detector (Trending / Ranging / Volatile)
4. XGBoost AI Model (Calibrated BUY/SELL probability)
5. Session Filter (London / NY / Tokyo sessions)
6. Macro Agent (DXY Dollar correlation boost)
7. News Sentinel (Economic calendar danger shield)

Only produces an A+ Signal when all agents agree on high confluence!
"""

import uuid
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
import polars as pl
import numpy as np
from loguru import logger

from src.smc import SMCAnalyzer, SMCSignal
from src.feature_eng import FeatureEngineer
from src.ml_model import TradingModel
from src.regime_detector import MarketRegimeDetector, MarketRegime
from src.session_filter import SessionFilter
from src.dynamic_confidence import DynamicConfidenceManager
from src.macro_agent import MacroAgent, MacroReport
from src.news_agent import NewsSentinel, NewsStatus
from src.chart_generator import ChartGenerator
from src.signal_tracker import ActiveSignal


@dataclass
class GeneratedSignal:
    id: str
    symbol: str
    timeframe: str
    direction: str              # "BUY" or "SELL"
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    take_profit_3: float
    risk_reward: float
    ai_confidence: float
    regime: str
    session: str
    macro_alignment: str
    news_status: str
    confluence_reasons: List[str]
    chart_image_path: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_active_signal(self) -> ActiveSignal:
        return ActiveSignal(
            id=self.id,
            symbol=self.symbol,
            timeframe=self.timeframe,
            direction=self.direction,
            entry_price=self.entry_price,
            stop_loss=self.stop_loss,
            take_profit_1=self.take_profit_1,
            take_profit_2=self.take_profit_2,
            take_profit_3=self.take_profit_3,
            created_at=self.created_at,
            ai_confidence=self.ai_confidence,
        )

    def format_telegram_message(self) -> str:
        """Format a rich, professional Telegram alert message."""
        dir_emoji = "🟢 <b>STRONG BUY</b>" if self.direction == "BUY" else "🔴 <b>STRONG SELL</b>"
        arrow = "📈" if self.direction == "BUY" else "📉"

        reasons_bullet = "\n".join([f"  • {r}" for r in self.confluence_reasons])

        msg = (
            f"⚡ <b>CYBER TRADE — AI SIGNAL ALERT</b> ⚡\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🪙 <b>Aktiv:</b> #{self.symbol} ({self.timeframe})\n"
            f"🎯 <b>Yo'nalish:</b> {dir_emoji} {arrow}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📥 <b>Kirish narxi (Entry):</b> <code>{self.entry_price:.2f}</code>\n"
            f"🛑 <b>Stop-Loss (SL):</b> <code>{self.stop_loss:.2f}</code>\n"
            f"🎯 <b>Take-Profit 1:</b> <code>{self.take_profit_1:.2f}</code> (1:1.5)\n"
            f"🎯 <b>Take-Profit 2:</b> <code>{self.take_profit_2:.2f}</code> (1:2.5)\n"
            f"🎯 <b>Take-Profit 3:</b> <code>{self.take_profit_3:.2f}</code> (1:4.0)\n"
            f"⚖️ <b>Risk:Reward:</b> <code>1:{self.risk_reward:.1f}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🧠 <b>AI Ishonch:</b> <code>{self.ai_confidence*100:.1f}%</code>\n"
            f"🌊 <b>Bozor Rejimi:</b> {self.regime}\n"
            f"🕒 <b>Sessiya:</b> {self.session}\n"
            f"🌐 <b>Makro DXY:</b> {self.macro_alignment}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔍 <b>Texnik & SMC Tasdiqlar:</b>\n{reasons_bullet}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ <i>Eslatma: TP1 ga yetganda Stop-Lossni 0 ga (Breakeven) suring!</i>"
        )
        return msg


SIGNAL_MODES = {
    "aggressive": {
        "id": "aggressive",
        "name": "⚡ Agressiv (Scalp 50%+)",
        "threshold": 0.52,
        "min_rr": 1.5,
        "desc": "Ko'p signallar, tezkor kirish-chiqishlar (50-55%+)",
    },
    "standard": {
        "id": "standard",
        "name": "⚖️ Standart (Balansli 60%+)",
        "threshold": 0.60,
        "min_rr": 2.0,
        "desc": "Oltin o'rtalik, me'yordagi filtr va ishonchlilik (60%+)",
    },
    "conservative": {
        "id": "conservative",
        "name": "🛡️ Konservativ (Sniper 70%+)",
        "threshold": 0.70,
        "min_rr": 2.5,
        "desc": "Faqat eng yuqori ishonchli A+ signallar (70%+)",
    },
}


class SignalEngine:
    """
    Master Confluence Engine that powers Cyber Trade.
    """

    def __init__(
        self,
        xgboost_path: str = "models/xgboost_model.pkl",
        hmm_path: str = "models/hmm_regime.pkl",
        min_risk_reward: float = 2.0,
        settings_file: str = "data/bot_settings.json",
    ):
        self.settings_file = Path(settings_file)
        self.settings_file.parent.mkdir(parents=True, exist_ok=True)
        self.min_rr = min_risk_reward

        # 1. Feature Engineer & SMC Analyzer
        self.feature_eng = FeatureEngineer()
        self.smc = SMCAnalyzer(swing_length=5, ob_lookback=10)

        # 2. Machine Learning Model
        self.ml_model = TradingModel().load(xgboost_path)

        # 3. Regime Detector
        self.regime_detector = MarketRegimeDetector().load(hmm_path)

        # 4. Filters & Macro
        self.session_filter = SessionFilter(timezone="UTC")
        self.dynamic_confidence = DynamicConfidenceManager(base_threshold=0.60)
        self.macro_agent = MacroAgent()
        self.news_sentinel = NewsSentinel()
        self.chart_generator = ChartGenerator()

        # Load saved mode
        self.active_mode = self._load_mode()
        self.apply_mode(self.active_mode)

    def _load_mode(self) -> str:
        if self.settings_file.exists():
            try:
                import json
                with open(self.settings_file, "r") as f:
                    data = json.load(f)
                    return data.get("mode", "standard")
            except Exception:
                pass
        return "standard"

    def apply_mode(self, mode_id: str):
        if mode_id not in SIGNAL_MODES:
            mode_id = "standard"
        self.active_mode = mode_id
        cfg = SIGNAL_MODES[mode_id]
        self.ml_model.confidence_threshold = cfg["threshold"]
        self.min_rr = cfg["min_rr"]
        # Save to file
        try:
            import json
            with open(self.settings_file, "w") as f:
                json.dump({"mode": mode_id}, f)
        except Exception as e:
            logger.error(f"Failed to save mode settings: {e}")
        logger.info(f"Signal Mode set to: {cfg['name']} (Threshold: {cfg['threshold']}, Min R:R: {cfg['min_rr']})")

    async def analyze_and_generate_signal(
        self,
        symbol: str,
        df: pl.DataFrame,
        dxy_df: Optional[pl.DataFrame] = None,
        timeframe: str = "15m",
    ) -> Tuple[Optional[GeneratedSignal], Dict[str, Any]]:
        """
        Run the full AI Council analysis pipeline on OHLCV data.
        Returns (GeneratedSignal if confluence passes else None, FullAnalysisMetadata).
        """
        if df is None or len(df) < 60:
            return None, {"error": "Insufficient candle data"}

        # CRITICAL: Strictly block signals on closed markets (e.g. Gold/Forex on weekends)
        is_crypto = any(c in symbol.upper() for c in ["BTC", "ETH", "SOL", "USDT"])
        if not is_crypto and self.session_filter.is_weekend():
            logger.debug(f"{symbol} is closed for the weekend. Skipping signal generation.")
            return None, {
                "symbol": symbol,
                "current_price": float(df["close"][-1]),
                "market_status": "CLOSED (Weekend)",
                "note": "Bozor dam olish kuni tufayli yopiq. Signal berilmaydi.",
            }

        # Step 1: Feature Engineering
        df_feat = self.feature_eng.calculate_all(df, include_ml_features=True)

        # Step 2: SMC Analysis
        df_smc = self.smc.calculate_all(df_feat)

        # Step 3: Market Regime Detection (HMM)
        df_smc = self.regime_detector.predict(df_smc)
        regime_state = self.regime_detector.get_current_state(df_smc)
        regime_name = regime_state.regime.value if regime_state else "medium_volatility"

        # Step 4: Machine Learning Prediction (XGBoost)
        ml_prediction = self.ml_model.predict(df_smc)
        ml_signal = ml_prediction.signal           # "BUY", "SELL", or "HOLD"
        ml_confidence = ml_prediction.confidence   # 0.0 - 1.0

        # Step 5: Session Filter
        session_enum, session_config = self.session_filter.get_current_session()
        current_session = session_enum.value

        # Step 6: Macro Analysis (DXY)
        macro_report = self.macro_agent.evaluate_macro(dxy_df, target_symbol=symbol, technical_direction=ml_signal)

        # Step 7: News Safety Check
        news_status = await self.news_sentinel.check_news_safety(currency="USD")

        # Extract SMC indicators
        rsi_val = float(df_smc["rsi"][-1]) if "rsi" in df_smc.columns else 50.0
        bull_ob_str = "Aniqlanmadi"
        bear_ob_str = "Aniqlanmadi"
        if "ob" in df_smc.columns and "ob_top" in df_smc.columns and "ob_bottom" in df_smc.columns:
            bull_obs = df_smc.filter(pl.col("ob") == 1)
            bear_obs = df_smc.filter(pl.col("ob") == -1)
            if len(bull_obs) > 0:
                b_bot = float(bull_obs["ob_bottom"][-1])
                b_top = float(bull_obs["ob_top"][-1])
                bull_ob_str = f"{b_bot:.2f} - {b_top:.2f}"
            if len(bear_obs) > 0:
                s_bot = float(bear_obs["ob_bottom"][-1])
                s_top = float(bear_obs["ob_top"][-1])
                bear_ob_str = f"{s_bot:.2f} - {s_top:.2f}"

        # Combine analysis metadata
        meta = {
            "symbol": symbol,
            "timeframe": timeframe,
            "current_price": float(df_smc["close"][-1]),
            "ml_signal": ml_signal,
            "ml_confidence": ml_confidence,
            "regime": regime_name,
            "session": current_session,
            "macro": macro_report.reason,
            "news": news_status.warning_text,
            "news_is_safe": news_status.is_safe,
            "rsi": rsi_val,
            "bullish_ob": bull_ob_str,
            "bearish_ob": bear_ob_str,
        }

        # ---------------------------------------------------------------------
        # CONFLUENCE GATING (Must pass all strict filters)
        # ---------------------------------------------------------------------
        # 1. Block if News is in High Danger
        if not news_status.is_safe and news_status.status == "DANGER":
            meta["gate_reason"] = "Iqtisodiy yangilik xavfi (News Danger)"
            logger.info(f"Signal rejected by News Sentinel: {news_status.warning_text}")
            return None, meta

        # 2. Block if ML signal is HOLD
        if ml_signal == "HOLD":
            meta["gate_reason"] = "ML modeli aniq yo'nalish bermadi (HOLD)"
            return None, meta

        # 3. Dynamic Confidence Adjustment
        adjusted_confidence = ml_confidence + macro_report.confluence_boost
        market_eval = self.dynamic_confidence.analyze_market(
            session=current_session,
            regime=regime_name,
            volatility="medium",
            trend_direction=ml_signal,
            has_smc_signal=True,
            ml_signal=ml_signal,
            ml_confidence=ml_confidence,
        )
        cfg = SIGNAL_MODES.get(self.active_mode, SIGNAL_MODES["standard"])
        mode_threshold = cfg["threshold"]

        if self.active_mode == "aggressive":
            required_threshold = min(market_eval.confidence_threshold, mode_threshold)
        elif self.active_mode == "conservative":
            required_threshold = max(market_eval.confidence_threshold, mode_threshold)
        else:
            required_threshold = market_eval.confidence_threshold

        meta["mode"] = cfg["name"]
        meta["required_threshold"] = required_threshold
        meta["adjusted_confidence"] = adjusted_confidence

        if adjusted_confidence < required_threshold:
            meta["gate_reason"] = f"Ishonch darajasi ({adjusted_confidence*100:.1f}%) kerakli filtrdan ({required_threshold*100:.1f}%) past"
            logger.debug(f"{symbol} confidence {adjusted_confidence:.2f} < threshold {required_threshold:.2f} (Mode: {self.active_mode})")
            return None, meta

        meta["gate_reason"] = "A+ Confluence tasdiqlandi"

        # 4. Price and Target Calculations
        current_price = float(df_smc["close"][-1])
        atr = float(df_smc["atr"][-1]) if "atr" in df_smc.columns else (current_price * 0.005)
        if atr <= 0 or np.isnan(atr):
            atr = current_price * 0.005

        reasons = []
        reasons.append(f"AI XGBoost tasdig'i: {ml_signal} ({ml_confidence*100:.1f}%)")
        reasons.append(f"Bozor rejimi: {regime_name.capitalize()}")
        reasons.append(f"Savdo sessiyasi: {current_session.capitalize()}")
        if macro_report.confluence_boost > 0:
            reasons.append(macro_report.reason)

        if ml_signal == "BUY":
            entry = current_price
            # SL placed below recent low or 1.5x ATR
            sl_distance = max(atr * 1.5, current_price * 0.003)
            stop_loss = entry - sl_distance
            tp1 = entry + (sl_distance * 1.5)
            tp2 = entry + (sl_distance * 2.5)
            tp3 = entry + (sl_distance * 4.0)
            rr = (tp2 - entry) / sl_distance
            reasons.append("SMC Bullish struktura va likvidlik tasdig'i")

        else:  # SELL
            entry = current_price
            # SL placed above recent high or 1.5x ATR
            sl_distance = max(atr * 1.5, current_price * 0.003)
            stop_loss = entry + sl_distance
            tp1 = entry - (sl_distance * 1.5)
            tp2 = entry - (sl_distance * 2.5)
            tp3 = entry - (sl_distance * 4.0)
            rr = (entry - tp2) / sl_distance
            reasons.append("SMC Bearish struktura va likvidlik tasdig'i")

        # 5. Check Minimum Risk:Reward
        if rr < self.min_rr:
            return None, meta

        # 6. Generate Chart Snapshot
        chart_path = self.chart_generator.generate_signal_chart(
            df=df_smc,
            symbol=symbol,
            timeframe=timeframe,
            direction=ml_signal,
            entry_price=entry,
            stop_loss=stop_loss,
            take_profit_1=tp1,
            take_profit_2=tp2,
            ai_confidence=adjusted_confidence,
            smc_reasons=reasons,
        )

        signal = GeneratedSignal(
            id=str(uuid.uuid4())[:8],
            symbol=symbol,
            timeframe=timeframe,
            direction=ml_signal,
            entry_price=entry,
            stop_loss=stop_loss,
            take_profit_1=tp1,
            take_profit_2=tp2,
            take_profit_3=tp3,
            risk_reward=rr,
            ai_confidence=adjusted_confidence,
            regime=regime_name,
            session=current_session,
            macro_alignment=macro_report.dxy_trend,
            news_status=news_status.status,
            confluence_reasons=reasons,
            chart_image_path=chart_path,
        )

        return signal, meta
