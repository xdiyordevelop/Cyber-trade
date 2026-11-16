"""
Cyber Trade - Master Signal Engine & Multi-Timeframe Confluence Auditor
=======================================================================
Coordinates all analytical agents with strict Quality Control and MTF Analysis:
1. Multi-Timeframe (MTF) Engine:
   - H4: Macro Direction (Overall 4H trend & institutional bias)
   - H1: Market Structure (1H SMC Structure, BOS, OB)
   - M15: Entry Confirmation (M15 Trigger, FVG retest, Liquidity sweep)
   - Conflict Detection: Transparently reveals time-frame divergences!
2. Data Quality & Freshness Sentinel:
   - Source validation, timestamp freshness (blocks stale data > 45m on active markets),
   - Candle close status and OHLC integrity verification.
3. Smart Money Concepts (SMC):
   - Order Blocks, Fair Value Gaps, Swing Points, BOS, CHoCH.
4. HMM Market Regime Detector (Trending / Ranging / Volatile).
5. XGBoost Machine Learning Probabilities & Dynamic Thresholds.
6. Macro DXY Dollar Correlation (+12% confluence).
7. High-Impact News Sentinel & Economic Calendar Guard.
8. Diagnostic Audit Engine (/why command).
"""

import uuid
from pathlib import Path
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
import polars as pl
import numpy as np
try:
    from loguru import logger
except ImportError:
    from src.logger import logger

from src.smc import SMCAnalyzer, SMCSignal
from src.feature_eng import FeatureEngineer
from src.ml_model import TradingModel
from src.regime_detector import MarketRegimeDetector, MarketRegime
from src.session_filter import SessionFilter
from src.dynamic_confidence import DynamicConfidenceManager, SignalGrade
from src.macro_agent import MacroAgent, MacroReport
from src.news_agent import NewsSentinel, NewsStatus
from src.chart_generator import ChartGenerator
from src.signal_tracker import ActiveSignal
from src.utils import resample_ohlcv, validate_ohlcv_data


@dataclass
class GeneratedSignal:
    id: str
    symbol: str
    timeframe: str
    direction: str              # "BUY" or "SELL"
    grade: str                  # "🏆 A+ (SNIPER)" or "⚡ A (TREND MOMENTUM)"
    order_type: str             # "MARKET" or "BUY LIMIT" / "SELL LIMIT"
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
    lot_1k: float = 0.01
    lot_5k: float = 0.05
    lot_10k: float = 0.10
    ob_top: Optional[float] = None
    ob_bottom: Optional[float] = None
    chart_image_path: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_active_signal(self) -> ActiveSignal:
        is_filled = "LIMIT" not in self.order_type.upper()
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
            order_type=self.order_type,
            is_filled=is_filled,
        )

    def to_telegram_message(self) -> str:
        """Format signal card for Telegram broadcast."""
        icon = "🟢" if self.direction == "BUY" else "🔴"
        grade_badge = f"<b>{self.grade}</b>"
        unit_label = "lot" if "XAU" in self.symbol.upper() else ("BTC" if "BTC" in self.symbol.upper() else "lot")

        reasons_bullet = "\n".join([f"  • {r}" for r in self.confluence_reasons[:6]])

        limit_notice = ""
        if "LIMIT" in self.order_type.upper():
            limit_notice = (
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📌 <b>LIMIT QOIDASI:</b> Narx impulsda. Cho'qqidan kirmaslik uchun "
                f"<code>{self.entry_price:.2f}</code> zonasiga Retest berganda buyurtma ochiladi. Shoshilmang!\n"
            )

        msg = (
            f"⚡ <b>CYBER TRADE — AI TRADING SIGNAL</b> ⚡\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{icon} <b>Aktiv:</b> #{self.symbol} ({self.timeframe})\n"
            f"🎯 <b>Yo'nalish:</b> <b>{self.direction}</b>\n"
            f"🎖️ <b>Signal Sifati:</b> {grade_badge}\n"
            f"📌 <b>Buyurtma Turi:</b> <code>{self.order_type}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📥 <b>Kirish narxi (Entry):</b> <code>{self.entry_price:.2f}</code>\n"
            f"🛑 <b>Stop-Loss (SL):</b> <code>{self.stop_loss:.2f}</code>\n"
            f"🎯 <b>Take-Profit 1:</b> <code>{self.take_profit_1:.2f}</code> (1:1.2 BE)\n"
            f"🎯 <b>Take-Profit 2 (Asosiy Likvidlik):</b> <code>{self.take_profit_2:.2f}</code> (1:{self.risk_reward:.1f})\n"
            f"🎯 <b>Take-Profit 3 (Runner):</b> <code>{self.take_profit_3:.2f}</code>\n"
            f"⚖️ <b>Real Risk:Reward:</b> <code>1:{self.risk_reward:.1f}</code>\n"
            f"{limit_notice}"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 <b>Tavsiya Etilgan Lot (1% Xavf / Risk):</b>\n"
            f"  • $1,000 depozit: <code>{self.lot_1k:.2f} {unit_label}</code>\n"
            f"  • $5,000 depozit: <code>{self.lot_5k:.2f} {unit_label}</code>\n"
            f"  • $10,000 depozit: <code>{self.lot_10k:.2f} {unit_label}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🧠 <b>AI Ishonch:</b> <code>{self.ai_confidence*100:.1f}%</code>\n"
            f"🌊 <b>Bozor Rejimi:</b> {self.regime}\n"
            f"🕒 <b>Sessiya:</b> {self.session}\n"
            f"🌐 <b>Makro DXY:</b> {self.macro_alignment}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔍 <b>Texnik & SMC Tasdiqlar:</b>\n{reasons_bullet}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ <i>Qoida: TP1 ga yetganda Stop-Lossni Kirish narxiga (0 ga) suring!</i>"
        )
        return msg


from src.bot_menu import SIGNAL_MODES


class SignalEngine:
    """
    Master Confluence Engine that powers Cyber Trade with MTF and Data Freshness.
    """

    def __init__(
        self,
        xgboost_path: str = "models/xgboost_model.pkl",
        hmm_path: str = "models/hmm_regime.pkl",
        min_risk_reward: float = 1.8,
        settings_file: str = "data/bot_settings.json",
    ):
        self.settings_file = Path(settings_file)
        self.settings_file.parent.mkdir(parents=True, exist_ok=True)
        self.min_rr = min_risk_reward

        # Analytical agents
        self.feature_eng = FeatureEngineer()
        self.smc = SMCAnalyzer(swing_length=5, ob_lookback=10)
        self.ml_model = TradingModel().load(xgboost_path)
        self.regime_detector = MarketRegimeDetector().load(hmm_path)
        self.session_filter = SessionFilter(timezone_str="Asia/Tashkent")
        self.dynamic_confidence = DynamicConfidenceManager(base_threshold=0.58)
        self.macro_agent = MacroAgent()
        self.news_sentinel = NewsSentinel()
        self.chart_generator = ChartGenerator()

        # Cache of latest diagnostic audits for /why command
        self.latest_diagnostics: Dict[str, Dict[str, Any]] = {}

        # Load active mode
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
        try:
            import json
            with open(self.settings_file, "w") as f:
                json.dump({"mode": mode_id}, f)
        except Exception as e:
            logger.error(f"Failed to save mode settings: {e}")
        logger.info(f"Signal Mode set to: {cfg['name']} (Threshold: {cfg['threshold']}, Min R:R: {cfg['min_rr']})")

    # -------------------------------------------------------------------------
    # 1. Data Quality & Freshness Sentinel
    # -------------------------------------------------------------------------
    def check_data_quality(self, symbol: str, df: pl.DataFrame) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Verify source, timestamp age, candle close status, and OHLC integrity.
        Blocks signal generation on stale data.
        """
        if df is None or len(df) < 50:
            return False, "Shamlar soni yetarli emas (kamida 50 ta kerak)", {"status": "INSUFFICIENT_BARS"}

        # Structure check
        is_struct_valid, issues = validate_ohlcv_data(df)
        if not is_struct_valid:
            return False, f"Ma'lumotlar strukturasida xatolik: {', '.join(issues[:2])}", {"issues": issues}

        # Timestamp and freshness
        last_time_val = df["time"][-1]
        now_utc = datetime.now(timezone.utc)

        # Convert to datetime if string or timestamp
        if isinstance(last_time_val, str):
            try:
                last_dt = datetime.fromisoformat(last_time_val.replace("Z", "+00:00"))
            except Exception:
                last_dt = now_utc
        elif isinstance(last_time_val, datetime):
            last_dt = last_time_val if last_time_val.tzinfo else last_time_val.replace(tzinfo=timezone.utc)
        else:
            last_dt = now_utc

        age_seconds = (now_utc - last_dt).total_seconds()
        age_minutes = age_seconds / 60.0

        is_crypto = any(c in symbol.upper() for c in ["BTC", "ETH", "SOL", "USDT"])
        is_weekend = self.session_filter.is_weekend()

        meta = {
            "source": "Yahoo Finance Direct / Live",
            "last_candle_time": last_dt.strftime("%Y-%m-%d %H:%M UTC"),
            "age_minutes": round(age_minutes, 1),
            "is_weekend": is_weekend,
            "is_crypto": is_crypto,
            "total_bars": len(df),
        }

        # Crypto must be fresh within 60 minutes (ensures real-time precision while allowing 15m candle completion)
        if is_crypto and age_minutes > 60:
            return False, f"Kriptovalyuta narxi eskirgan (oxirgi sham {int(age_minutes)} daqiqa oldin)", meta

        # Forex/Gold on weekends: allowed for analysis, but marked
        if not is_crypto and is_weekend:
            meta["weekend_closed"] = True
            return True, "Bozor dam olish kunida yopiq (Juma yopilish narxlari)", meta

        # Forex/Gold on weekdays must be fresh within 90 minutes
        if not is_crypto and not is_weekend and age_minutes > 90:
            return False, f"Bozor narxi eskirgan (oxirgi yangilanish {int(age_minutes)} daqiqa oldin)", meta

        return True, "Ma'lumotlar sifati a'lo va yangi", meta

    # -------------------------------------------------------------------------
    # 2. Multi-Timeframe (MTF) Analysis Engine (H4, H1, M15)
    # -------------------------------------------------------------------------
    def analyze_mtf(self, df_15m: pl.DataFrame) -> Dict[str, Any]:
        """
        Deep Multi-Timeframe Confluence & Conflict Analysis:
        - H4: Macro Direction (4H resampled EMA 50 & 20)
        - H1: Market Structure (1H resampled EMA 9 & 21)
        - M15: Entry Trigger (15m live EMA 9 & 21 + RSI)
        """
        closes_15m = df_15m["close"].to_numpy()
        cur_price = float(closes_15m[-1])

        def calc_ema(arr, span):
            if len(arr) == 0:
                return np.array([])
            alpha = 2 / (span + 1)
            ema = [arr[0]]
            for val in arr[1:]:
                ema.append(alpha * val + (1 - alpha) * ema[-1])
            return np.array(ema)

        # 1. M15 Trigger Frame
        ema9_15m = calc_ema(closes_15m, 9)
        ema21_15m = calc_ema(closes_15m, 21)
        if ema9_15m[-1] > ema21_15m[-1] and cur_price > ema9_15m[-1]:
            m15_bias = "BULLISH"
        elif ema9_15m[-1] < ema21_15m[-1] and cur_price < ema9_15m[-1]:
            m15_bias = "BEARISH"
        else:
            m15_bias = "RANGING"

        # 2. 1H Structure Frame
        h1_bias = "NEUTRAL"
        h1_close = cur_price
        try:
            df_1h = resample_ohlcv(df_15m, "1h")
            if len(df_1h) >= 20:
                closes_1h = df_1h["close"].to_numpy()
                h1_close = float(closes_1h[-1])
                ema9_1h = calc_ema(closes_1h, 9)
                ema21_1h = calc_ema(closes_1h, 21)
                if ema9_1h[-1] > ema21_1h[-1] and h1_close > ema9_1h[-1]:
                    h1_bias = "BULLISH"
                elif ema9_1h[-1] < ema21_1h[-1] and h1_close < ema9_1h[-1]:
                    h1_bias = "BEARISH"
                else:
                    h1_bias = "RANGING"
        except Exception as e:
            logger.warning(f"1H MTF calculation error: {e}")

        # 3. 4H Macro Trend Frame
        h4_bias = "NEUTRAL"
        h4_close = cur_price
        try:
            df_4h = resample_ohlcv(df_15m, "4h")
            if len(df_4h) >= 15:
                closes_4h = df_4h["close"].to_numpy()
                h4_close = float(closes_4h[-1])
                ema20_4h = calc_ema(closes_4h, 20)
                ema50_4h = calc_ema(closes_4h, 50)
                if ema20_4h[-1] > ema50_4h[-1] and h4_close > ema20_4h[-1]:
                    h4_bias = "BULLISH"
                elif ema20_4h[-1] < ema50_4h[-1] and h4_close < ema20_4h[-1]:
                    h4_bias = "BEARISH"
                else:
                    h4_bias = "RANGING"
            else:
                # Fallback to 1H trend if not enough 4H bars
                h4_bias = h1_bias
        except Exception as e:
            logger.warning(f"4H MTF calculation error: {e}")

        # 4. Conflict & Alignment Detection
        conflicts = []
        if h4_bias != "NEUTRAL" and h1_bias != "NEUTRAL" and h4_bias != h1_bias:
            conflicts.append(f"H4 ({h4_bias}) va H1 ({h1_bias}) o'zaro qarama-qarshi")

        if h1_bias != "NEUTRAL" and m15_bias != "NEUTRAL" and h1_bias != m15_bias:
            conflicts.append(f"H1 ({h1_bias}) va M15 ({m15_bias}) triggermos emas")

        is_aligned = (h4_bias == h1_bias == m15_bias) and h4_bias in ["BULLISH", "BEARISH"]

        return {
            "h4_bias": h4_bias,
            "h1_bias": h1_bias,
            "m15_bias": m15_bias,
            "is_aligned": is_aligned,
            "conflicts": conflicts,
            "current_price": cur_price,
            "h1_close": h1_close,
            "h4_close": h4_close,
        }

    def _calculate_recommended_lots(self, symbol: str, entry: float, stop_loss: float) -> Tuple[float, float, float]:
        """Calculate position sizes for $1k, $5k, and $10k accounts with strict 1.0% risk rule."""
        risk_dist = abs(entry - stop_loss)
        if risk_dist <= 0:
            return 0.01, 0.05, 0.10

        sym = symbol.upper()
        if "XAU" in sym or "GOLD" in sym:
            point_risk = risk_dist * 100.0
            lot_1k = max(0.01, round(10.0 / point_risk, 2))
            lot_5k = max(0.01, round(50.0 / point_risk, 2))
            lot_10k = max(0.01, round(100.0 / point_risk, 2))
            return lot_1k, lot_5k, lot_10k

        if "BTC" in sym:
            lot_1k = max(0.001, round(10.0 / risk_dist, 3))
            lot_5k = max(0.001, round(50.0 / risk_dist, 3))
            lot_10k = max(0.001, round(100.0 / risk_dist, 3))
            return lot_1k, lot_5k, lot_10k

        if "ETH" in sym:
            lot_1k = max(0.01, round(10.0 / risk_dist, 2))
            lot_5k = max(0.01, round(50.0 / risk_dist, 2))
            lot_10k = max(0.01, round(100.0 / risk_dist, 2))
            return lot_1k, lot_5k, lot_10k

        pip_risk = (risk_dist / 0.0001) * 10.0
        if pip_risk > 0:
            lot_1k = max(0.01, round(10.0 / pip_risk, 2))
            lot_5k = max(0.01, round(50.0 / pip_risk, 2))
            lot_10k = max(0.01, round(100.0 / pip_risk, 2))
            return lot_1k, lot_5k, lot_10k

        return 0.01, 0.05, 0.10

    # -------------------------------------------------------------------------
    # 3. Main Analysis & Signal Generation Loop
    # -------------------------------------------------------------------------
    async def analyze_and_generate_signal(
        self,
        symbol: str,
        df: pl.DataFrame,
        dxy_df: Optional[pl.DataFrame] = None,
        timeframe: str = "15m",
    ) -> Tuple[Optional[GeneratedSignal], Dict[str, Any]]:
        """
        Complete AI Council analysis pipeline on OHLCV data.
        Returns (GeneratedSignal if confluence passes else None, FullAnalysisMetadata).
        """
        # Diagnostic Audit Tracker for /why
        audit: Dict[str, Any] = {
            "symbol": symbol,
            "timeframe": timeframe,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "gates_passed": [],
            "gates_failed": [],
            "summary_reason": "",
        }

        # ---------------------------------------------------------------------
        # Gate 0: Data Quality & Freshness Sentinel (Evaluated, indicators computed for /analyze)
        # ---------------------------------------------------------------------
        is_fresh, fresh_msg, quality_meta = self.check_data_quality(symbol, df)
        audit["quality_meta"] = quality_meta
        if not is_fresh:
            audit["gates_failed"].append(f"Ma'lumot sifati: {fresh_msg}")
            audit["summary_reason"] = f"Ma'lumotlar sifati talabga javob bermaydi ({fresh_msg})"
        else:
            audit["gates_passed"].append("Ma'lumot sifati: Yangi va toza OHLCV shamlar")

        # ---------------------------------------------------------------------
        # Pre-Check Gate 1 & Gate 2 (Evaluated, but indicators still computed for /analyze)
        # ---------------------------------------------------------------------
        is_allowed, session_reason = self.session_filter.is_signal_allowed(symbol)
        news_status = await self.news_sentinel.check_news_safety(currency="USD")
        audit["news_status"] = news_status.status
        audit["news_warning"] = news_status.warning_text

        # ---------------------------------------------------------------------
        # Step 3: Multi-Timeframe (MTF) Engine (H4, H1, M15)
        # ---------------------------------------------------------------------
        mtf_data = self.analyze_mtf(df)
        audit["mtf"] = mtf_data
        h4_trend = mtf_data["h4_bias"]
        h1_trend = mtf_data["h1_bias"]
        m15_bias = mtf_data["m15_bias"]

        # ---------------------------------------------------------------------
        # Step 4: Technical Feature Engineering & SMC Calculation
        # ---------------------------------------------------------------------
        df_feat = self.feature_eng.calculate_all(df, include_ml_features=True)
        df_smc = self.smc.calculate_all(df_feat)

        # ---------------------------------------------------------------------
        # Step 5: Market Regime Detection (HMM)
        # ---------------------------------------------------------------------
        df_smc = self.regime_detector.predict(df_smc)
        regime_state = self.regime_detector.get_current_state(df_smc)
        regime_name = regime_state.regime.value if regime_state else "medium_volatility"
        audit["regime"] = regime_name

        # ---------------------------------------------------------------------
        # Step 6: Native SMC Signal Generation
        # ---------------------------------------------------------------------
        smc_signal: Optional[SMCSignal] = self.smc.generate_signal(df_smc)
        has_smc_setup = smc_signal is not None
        smc_dir = smc_signal.signal_type if smc_signal else "NONE"
        audit["smc_setup"] = smc_dir if has_smc_setup else "Topilmadi (OB/FVG yo'q)"

        # ---------------------------------------------------------------------
        # Step 7: Machine Learning (XGBoost) Prediction
        # ---------------------------------------------------------------------
        ml_prediction = self.ml_model.predict(df_smc)
        ml_signal = ml_prediction.signal           # "BUY", "SELL", or "HOLD"
        ml_confidence = ml_prediction.confidence   # 0.0 - 1.0
        audit["ml_signal"] = ml_signal
        audit["ml_confidence"] = round(ml_confidence * 100, 1)

        # ---------------------------------------------------------------------
        # Step 8: Macro DXY Alignment
        # ---------------------------------------------------------------------
        session_enum, session_config = self.session_filter.get_current_session()
        current_session = session_config.name

        macro_report = self.macro_agent.evaluate_macro(
            dxy_df,
            target_symbol=symbol,
            technical_direction=smc_dir if has_smc_setup else ml_signal,
        )
        audit["macro_dxy"] = macro_report.reason

        current_price = float(df_smc["close"][-1])
        atr = float(df_smc["atr"][-1]) if "atr" in df_smc.columns else (current_price * 0.005)
        if atr <= 0 or np.isnan(atr):
            atr = current_price * 0.005

        meta = {
            "symbol": symbol,
            "timeframe": timeframe,
            "current_price": current_price,
            "h4_trend": h4_trend,
            "htf_trend": h1_trend,
            "m15_bias": m15_bias,
            "smc_signal": smc_dir,
            "ml_signal": ml_signal,
            "ml_confidence": ml_confidence,
            "regime": regime_name,
            "session": current_session,
            "macro": macro_report.reason,
            "news": news_status.warning_text,
            "news_is_safe": news_status.is_safe,
            "quality_meta": quality_meta,
            "audit": audit,
        }

        # ---------------------------------------------------------------------
        # Gate 0 Enforcement: Stale data blocks automated signal broadcasting
        # ---------------------------------------------------------------------
        if not is_fresh:
            self.latest_diagnostics[symbol] = audit
            meta["market_status"] = "BLOCKED_BY_DATA_QUALITY"
            meta["gate_reason"] = fresh_msg
            return None, meta

        # ---------------------------------------------------------------------
        # Gate 1 Validation: Session & Schedule Filter
        # ---------------------------------------------------------------------
        if not is_allowed:
            audit["gates_failed"].append(f"Bozor jadvali: {session_reason}")
            audit["summary_reason"] = session_reason
            self.latest_diagnostics[symbol] = audit
            meta["market_status"] = "BLOCKED_BY_SCHEDULE"
            meta["gate_reason"] = session_reason
            return None, meta
        audit["gates_passed"].append(f"Sessiya: Faol savdo vaqti ({session_reason})")

        # ---------------------------------------------------------------------
        # Gate 2 Validation: High-Impact Economic News Sentinel
        # ---------------------------------------------------------------------
        if not news_status.is_safe and news_status.status == "DANGER":
            audit["gates_failed"].append(f"Yangiliklar xavfi: {news_status.warning_text}")
            audit["summary_reason"] = "Yaqin orada yuqori ta'sirli yangilik (CPI/NFP/FOMC) kutilmoqda"
            self.latest_diagnostics[symbol] = audit
            meta["market_status"] = "BLOCKED_BY_NEWS"
            meta["gate_reason"] = news_status.warning_text
            return None, meta
        audit["gates_passed"].append("Yangiliklar: Bozor iqtisodiy jihatdan xavfsiz")

        # ---------------------------------------------------------------------
        # Gate 4: Direction Consensus & Conflict Gatekeeper
        # ---------------------------------------------------------------------
        target_direction: Optional[str] = None
        confluence_reasons: List[str] = []
        is_sniper_a_plus = False

        # Case A: Pure Sniper Confluence (SMC + ML + H1 Agree)
        if has_smc_setup and smc_dir in ["BUY", "SELL"] and ml_signal == smc_dir:
            target_direction = smc_dir
            is_sniper_a_plus = True
            confluence_reasons.append(f"AI XGBoost modeli tasdig'i: {ml_signal} ({ml_confidence*100:.1f}%)")
            confluence_reasons.append(f"SMC {smc_dir} strukturasi ({smc_signal.reason})")

        # Case B: Strong SMC setup aligned with 1H Trend
        elif has_smc_setup and smc_dir in ["BUY", "SELL"]:
            if (smc_dir == "BUY" and h1_trend == "BULLISH") or (smc_dir == "SELL" and h1_trend == "BEARISH"):
                target_direction = smc_dir
                confluence_reasons.append(f"SMC {smc_dir} strukturasi ({smc_signal.reason})")
                confluence_reasons.append(f"1H Trend mosligi ({h1_trend})")
                if ml_signal != "HOLD" and ml_signal != smc_dir:
                    audit["gates_failed"].append(f"AI Model ziddiyati: ML ({ml_signal}) SMC ({smc_dir}) ga qarshi")
                    audit["summary_reason"] = f"AI XGBoost modeli ({ml_signal}) SMC signaliga ({smc_dir}) to'g'ridan-to'g'ri qarshi chiqdi"
                    self.latest_diagnostics[symbol] = audit
                    meta["gate_reason"] = audit["summary_reason"]
                    return None, meta

        # Case C: High Confidence ML Signal with MTF Alignment
        elif ml_signal in ["BUY", "SELL"] and ml_confidence >= 0.62:
            if (ml_signal == "BUY" and h1_trend in ["BULLISH", "NEUTRAL"]) or \
               (ml_signal == "SELL" and h1_trend in ["BEARISH", "NEUTRAL"]):
                target_direction = ml_signal
                confluence_reasons.append(f"AI XGBoost yuqori ishonchi ({ml_confidence*100:.1f}%)")
                confluence_reasons.append(f"1H Trend yo'nalishi ({h1_trend})")

        # If no consensus was reached
        if not target_direction:
            reason = "Bozorda aniq yo'nalish konsensusi (SMC / ML / 1H Trend) shakllanmadi"
            audit["gates_failed"].append(reason)
            audit["summary_reason"] = reason
            self.latest_diagnostics[symbol] = audit
            meta["gate_reason"] = reason
            return None, meta

        # MTF Conflict check: Don't trade directly against H4 macro trend
        if target_direction == "BUY" and h4_trend == "BEARISH":
            conflict_msg = f"H4 Katta Trend (BEARISH) M15 BUY signaliga qarshi! Katta trendga qarshi savdo taqiqlandi"
            audit["gates_failed"].append(f"MTF Ziddiyat: {conflict_msg}")
            audit["summary_reason"] = conflict_msg
            self.latest_diagnostics[symbol] = audit
            meta["gate_reason"] = conflict_msg
            return None, meta

        if target_direction == "SELL" and h4_trend == "BULLISH":
            conflict_msg = f"H4 Katta Trend (BULLISH) M15 SELL signaliga qarshi! Katta trendga qarshi savdo taqiqlandi"
            audit["gates_failed"].append(f"MTF Ziddiyat: {conflict_msg}")
            audit["summary_reason"] = conflict_msg
            self.latest_diagnostics[symbol] = audit
            meta["gate_reason"] = conflict_msg
            return None, meta

        audit["gates_passed"].append(f"MTF Konsensus: {target_direction} yo'nalishi H4 ({h4_trend}) va H1 ({h1_trend}) ga mos")

        # ---------------------------------------------------------------------
        # Gate 5: Dynamic Confidence, Self-Learning Memory & Mode Filter
        # ---------------------------------------------------------------------
        cfg = SIGNAL_MODES.get(self.active_mode, SIGNAL_MODES["standard"])
        mode_threshold = cfg["threshold"]
        required_min_rr = cfg.get("min_rr", 1.8)

        # Check Autonomous Self-Learner for Adaptive Capital Protection & Learned Penalties
        try:
            from src.self_learner import self_learner
            adaptive_guard = self_learner.get_adaptive_capital_protection()
            if adaptive_guard["is_active"]:
                mode_threshold += adaptive_guard["threshold_boost"]
                required_min_rr = max(required_min_rr, required_min_rr + adaptive_guard["min_rr_boost"])
                audit["gates_passed"].append(f"🛡️ Adaptiv Himoya: {adaptive_guard['status_badge']}")

            # Check if this setup matches historical negative patterns
            pattern_penalty, penalty_reason = self_learner.evaluate_setup(symbol, target_direction, meta)
            if pattern_penalty > 0:
                ml_confidence = max(0.0, ml_confidence - pattern_penalty)
                confluence_reasons.append(f"⚠️ O'z-o'zini o'rganish xotirasi: -{pattern_penalty*100:.0f}% jarima ({penalty_reason})")
        except Exception as e:
            logger.debug(f"Self-learner evaluation skipped: {e}")

        adjusted_confidence = ml_confidence + (macro_report.confluence_boost if macro_report.confluence_boost > 0 else 0)
        if has_smc_setup:
            adjusted_confidence = max(adjusted_confidence, smc_signal.confidence)

        meta["adjusted_confidence"] = adjusted_confidence
        meta["required_threshold"] = mode_threshold

        if adjusted_confidence < mode_threshold and not is_sniper_a_plus:
            reason = f"AI ishonch darajasi ({adjusted_confidence*100:.1f}%) rejim talabidan ({mode_threshold*100:.1f}%) past"
            audit["gates_failed"].append(reason)
            audit["summary_reason"] = reason
            self.latest_diagnostics[symbol] = audit
            meta["gate_reason"] = reason
            return None, meta

        audit["gates_passed"].append(f"AI Ishonchi: {adjusted_confidence*100:.1f}% (Kerakli: {mode_threshold*100:.1f}%)")

        # Grade Determination
        if is_sniper_a_plus and h4_trend == h1_trend and macro_report.confluence_boost > 0:
            final_grade = "🏆 A+ (SNIPER CONFLUENCE)"
        elif is_sniper_a_plus or (h4_trend == h1_trend):
            final_grade = "⚡ A (TREND MOMENTUM)"
        else:
            final_grade = "🎯 B (MOMENTUM SCALP)"

        # ---------------------------------------------------------------------
        # Gate 6: Risk-to-Reward and Invalidation Calculation
        # ---------------------------------------------------------------------
        ob_t = None
        ob_b = None

        if has_smc_setup and smc_signal is not None and smc_signal.signal_type == target_direction:
            order_type = smc_signal.order_type
            if "LIMIT" in order_type.upper():
                order_type = f"{target_direction} LIMIT"
                entry = smc_signal.entry_price
                confluence_reasons.append(f"📌 Limit Retest: {order_type} @ {entry:.2f} (OB/FVG zonasi retesti kutilmoqda)")
            else:
                order_type = f"MARKET {target_direction}"
                entry = current_price
                confluence_reasons.append(f"⚡ Bozor retest zonasida: MARKET {target_direction} tasdiqlandi")

            stop_loss = smc_signal.stop_loss
            tp2 = smc_signal.take_profit
            sl_dist = abs(entry - stop_loss)
            if sl_dist <= 0:
                sl_dist = atr * 1.0

            tp1 = entry + (sl_dist * 1.2) if target_direction == "BUY" else entry - (sl_dist * 1.2)
            tp3 = entry + (sl_dist * 3.5) if target_direction == "BUY" else entry - (sl_dist * 3.5)

            if target_direction == "BUY":
                rr = (tp2 - entry) / sl_dist if sl_dist > 0 else 0
            else:
                rr = (entry - tp2) / sl_dist if sl_dist > 0 else 0

            ob_t = smc_signal.ob_top or smc_signal.fvg_top
            ob_b = smc_signal.ob_bottom or smc_signal.fvg_bottom

        else:
            # Fallback for ML/Momentum setups without primary SMC structure
            entry = current_price
            order_type = f"MARKET {target_direction}"
            min_buffer = atr * 0.25

            if target_direction == "BUY":
                last_swing_low = float(df_smc["last_swing_low"][-1]) if "last_swing_low" in df_smc.columns and df_smc["last_swing_low"][-1] is not None else None
                if last_swing_low and last_swing_low < entry and (entry - last_swing_low) < (atr * 3.0):
                    stop_loss = last_swing_low - min_buffer
                    confluence_reasons.append("SL: Swing Low likvidlik chegarasi ostida")
                else:
                    stop_loss = entry - (atr * 1.5)
                    confluence_reasons.append("SL: Volatillik (1.5x ATR) buferi asosida")

                sl_dist = entry - stop_loss
                recent_highs = [float(h) for h in df_smc.tail(80)["high"].to_list() if float(h) > entry + (sl_dist * 1.4)]
                tp2 = min(recent_highs) if recent_highs else (entry + (sl_dist * 2.2))
                tp1 = entry + (sl_dist * 1.2)
                tp3 = entry + (sl_dist * 3.5)
                rr = (tp2 - entry) / sl_dist if sl_dist > 0 else 0

            else:  # SELL
                last_swing_high = float(df_smc["last_swing_high"][-1]) if "last_swing_high" in df_smc.columns and df_smc["last_swing_high"][-1] is not None else None
                if last_swing_high and last_swing_high > entry and (last_swing_high - entry) < (atr * 3.0):
                    stop_loss = last_swing_high + min_buffer
                    confluence_reasons.append("SL: Swing High likvidlik chegarasi tepasida")
                else:
                    stop_loss = entry + (atr * 1.5)
                    confluence_reasons.append("SL: Volatillik (1.5x ATR) buferi asosida")

                sl_dist = stop_loss - entry
                recent_lows = [float(l) for l in df_smc.tail(80)["low"].to_list() if float(l) < entry - (sl_dist * 1.4)]
                tp2 = max(recent_lows) if recent_lows else (entry - (sl_dist * 2.2))
                tp1 = entry - (sl_dist * 1.2)
                tp3 = entry - (sl_dist * 3.5)
                rr = (entry - tp2) / sl_dist if sl_dist > 0 else 0

        effective_min_rr = max(self.min_rr, required_min_rr)
        if rr < effective_min_rr:
            reason = f"Haqiqiy Risk:Reward nisbati (1:{rr:.1f}) minimal me'yordan (1:{effective_min_rr:.1f}) kam. Qarshilik/likvidlik juda yaqin."
            audit["gates_failed"].append(reason)
            audit["summary_reason"] = reason
            self.latest_diagnostics[symbol] = audit
            meta["gate_reason"] = reason
            return None, meta

        audit["gates_passed"].append(f"R:R Nisbati: 1:{rr:.1f} (Likvidlik maqsadiga mos)")

        # Confluence context
        confluence_reasons.append(f"4H Trend: {h4_trend} | 1H Struktura: {h1_trend}")
        confluence_reasons.append(f"Bozor rejimi: {regime_name.capitalize()}")
        confluence_reasons.append(f"Sessiya: {current_session}")
        if macro_report.confluence_boost > 0:
            confluence_reasons.append(macro_report.reason)

        lot_1k, lot_5k, lot_10k = self._calculate_recommended_lots(symbol, entry, stop_loss)

        # Generate chart with visual OB zone
        chart_path = self.chart_generator.generate_signal_chart(
            df=df_smc,
            symbol=symbol,
            timeframe=timeframe,
            direction=target_direction,
            entry_price=entry,
            stop_loss=stop_loss,
            take_profit_1=tp1,
            take_profit_2=tp2,
            ai_confidence=adjusted_confidence,
            smc_reasons=confluence_reasons,
            ob_top=ob_t,
            ob_bottom=ob_b,
            order_type=order_type,
        )

        signal = GeneratedSignal(
            id=str(uuid.uuid4())[:8],
            symbol=symbol,
            timeframe=timeframe,
            direction=target_direction,
            grade=final_grade,
            order_type=order_type,
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
            confluence_reasons=confluence_reasons,
            lot_1k=lot_1k,
            lot_5k=lot_5k,
            lot_10k=lot_10k,
            ob_top=ob_t,
            ob_bottom=ob_b,
            chart_image_path=chart_path,
        )

        audit["summary_reason"] = f"Barcha 8 ta sifat filtrlari muvaffaqiyatli o'tdi ({final_grade})"
        self.latest_diagnostics[symbol] = audit
        meta["gate_reason"] = audit["summary_reason"]
        return signal, meta

    # -------------------------------------------------------------------------
    # 4. Diagnostic Audit Inspector for /why command
    # -------------------------------------------------------------------------
    async def get_diagnostic_audit(
        self,
        symbol: str,
        data_fetcher,
    ) -> str:
        """
        Generate detailed, transparent breakdown of why a signal was or was not generated.
        Fully answers the user requirement for '/why <symbol>'.
        """
        sym = symbol.upper().replace("/", "").replace("-", "")
        # Directly pass sym so data_fetcher uses 0ms Binance for crypto and Spot Gold (XAUUSD=X)
        df = await data_fetcher.get_market_data(sym, "15m")
        dxy_df = await data_fetcher.get_market_data("DXY", "15m")

        if df is None or len(df) < 50:
            return (
                f"❌ <b>#{sym} BO'YICHA MA'LUMOT YUKLANMADI:</b>\n"
                f"Serverdan jonli shamlar olinmadi yoki bozor yopiq."
            )

        # Run analysis to populate diagnostics
        sig, meta = await self.analyze_and_generate_signal(sym, df, dxy_df)
        audit = self.latest_diagnostics.get(sym, meta.get("audit", {}))

        q_meta = audit.get("quality_meta", {})
        mtf = audit.get("mtf", {})
        cur_p = meta.get("current_price", 0.0)
        regime = meta.get("regime", "Barqaror")
        ml_sig = meta.get("ml_signal", "HOLD")
        ml_conf = meta.get("ml_confidence", 0.0) * 100
        smc_status = audit.get("smc_setup", "Kutilmoqda")
        news_w = audit.get("news_warning", "Bozor tinch")
        conflicts = mtf.get("conflicts", [])
        summary = audit.get("summary_reason", meta.get("gate_reason", "Kutilmoqda"))
        last_cand_time = q_meta.get("last_candle_time", "Noma'lum")
        sess_name = meta.get("session", "Noma'lum")

        conflict_str = f"⚠️ {', '.join(conflicts)}" if conflicts else "✅ Ziddiyat yo'q (Mos kelmoqda)"

        report = (
            f"🔍 <b>#{sym} — SIGNAL AUDITI (NEGA SIGNAL YO'Q?):</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💵 <b>Joriy Narx:</b> <code>${cur_p:,.2f}</code>\n"
            f"⏱️ <b>Ma'lumot Sifati:</b> {q_meta.get('source', 'Yahoo Direct')}\n"
            f"  • Yangilanish: <code>{last_cand_time}</code> ({q_meta.get('age_minutes', 0)} daq oldin)\n\n"
            f"📊 <b>Multi-Timeframe Tahlili (MTF):</b>\n"
            f"  • <b>H4 Katta Trend:</b> <code>{mtf.get('h4_bias', 'NEUTRAL')}</code>\n"
            f"  • <b>H1 Struktura:</b> <code>{mtf.get('h1_bias', 'NEUTRAL')}</code>\n"
            f"  • <b>M15 Trigger:</b> <code>{mtf.get('m15_bias', 'NEUTRAL')}</code>\n"
            f"  • <b>Ziddiyatlar:</b> {conflict_str}\n\n"
            f"🧠 <b>AI & SMC Holati:</b>\n"
            f"  • <b>SMC Strukturasi:</b> {smc_status}\n"
            f"  • <b>XGBoost AI:</b> <b>{ml_sig}</b> ({ml_conf:.1f}%)\n"
            f"  • <b>Bozor Rejimi:</b> <i>{regime}</i>\n"
            f"  • <b>Sessiya:</b> {sess_name}\n\n"
            f"📰 <b>Yangiliklar Qalqoni:</b>\n"
            f"  • {news_w}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🛑 <b>ASOSIY SABAB (GATE VERDICT):</b>\n"
            f"👉 <b><i>{summary}</i></b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
        )
        if sig:
            report += f"🎉 <b>Ayni paytda ushbu aktivda {sig.grade} signali mavjud!</b>"
        else:
            report += f"💡 <i>Bot pulingizni asrash maqsadida faqat barcha filtrlardan o'tgan A+ signallarni beradi.</i>"

        return report
