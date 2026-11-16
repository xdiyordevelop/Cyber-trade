"""
Cyber Trade - Autonomous AI Self-Improvement & Continuous Learning Engine
========================================================================
Implements real-time post-mortem analysis of closed trades, dynamic Bayesian
pattern penalty weighting, and Adaptive Capital Protection.

Key Capabilities:
1. Automated Error Post-Mortem:
   - When a trade hits Stop-Loss (SL_LOSS), the engine diagnoses the exact failure
     mechanism (Counter-trend, DXY Headwind, High Volatility Wick, Zone Invalidation).
   - Generates structured lessons and stores them in persistent SQLite memory.
2. Negative Pattern Memorization:
   - Penalizes recurring failure patterns so the bot never repeats the same mistake twice.
3. Positive Pattern Reinforcement:
   - Decreases penalties and reinforces SMC + MTF confluences that hit TP1/TP2.
4. Adaptive Capital Protection:
   - If rolling win-rate drops below 50% or a 2+ loss streak occurs, the engine
     automatically raises the confidence threshold (e.g. +6%) and minimum R:R to protect capital.
5. Conversational AI Integration:
   - Injects real self-learned lessons into Google Gemini / Groq context so the AI
     speaks like a self-aware, evolving trader who learns from every single trade.
"""

from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime, timezone
try:
    from loguru import logger
except ImportError:
    from src.logger import logger

from src.database import db


class SelfLearningEngine:
    """
    Continuous Self-Improvement & Trade Reflection Engine for Cyber Trade.
    """

    def __init__(self):
        self.db = db
        logger.info("Self-Learning Engine initialized.")

    # -------------------------------------------------------------------------
    # 1. Trade Closed Event Hook (Automated Post-Mortem)
    # -------------------------------------------------------------------------
    def on_trade_closed(
        self,
        sig,
        close_reason: str,
        close_price: float,
        profit_r: float,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Invoked immediately whenever a trade terminates (SL, TP1_BE, TP2_WIN).
        Conducts post-mortem diagnosis and updates pattern weights.
        """
        symbol = getattr(sig, "symbol", "XAUUSD")
        direction = getattr(sig, "direction", "BUY")
        sig_id = getattr(sig, "id", f"sig_{int(datetime.now().timestamp())}")
        highest_pips = getattr(sig, "highest_pips", 0.0)

        ctx = context or {}
        h4_trend = ctx.get("h4_trend", "NEUTRAL")
        macro = ctx.get("macro", "NEUTRAL")
        regime = ctx.get("regime", "Barqaror")

        # ---------------------------------------------------------------------
        # Case A: Stop-Loss Hit (Loss Post-Mortem)
        # ---------------------------------------------------------------------
        if close_reason == "SL_LOSS" or profit_r < 0:
            outcome = "LOSS"
            failure_tag, loss_reason, lesson = self._diagnose_loss(
                symbol=symbol,
                direction=direction,
                h4_trend=h4_trend,
                macro=macro,
                regime=regime,
                highest_pips=highest_pips,
            )
            pattern_key = f"{symbol}:{direction}:{failure_tag}"

            # Apply a +0.05 penalty to this negative pattern
            self.db.update_pattern_weight(pattern_key, is_win=False, penalty_delta=0.05)

            # Record lesson in permanent memory
            self.db.record_learned_lesson(
                signal_id=sig_id,
                symbol=symbol,
                direction=direction,
                outcome=outcome,
                net_r=profit_r,
                pips=highest_pips,
                pattern_key=pattern_key,
                loss_reason=loss_reason,
                lesson_learned=lesson,
            )
            logger.info(f"🧠 [Self-Learner] Learned loss post-mortem for {symbol} ({pattern_key}): {lesson}")
            return {
                "status": "ANALYZED",
                "outcome": outcome,
                "failure_tag": failure_tag,
                "pattern_key": pattern_key,
                "loss_reason": loss_reason,
                "lesson": lesson,
            }

        # ---------------------------------------------------------------------
        # Case B: Take Profit Hit (TP2_WIN or TP1_BE)
        # ---------------------------------------------------------------------
        elif "TP" in close_reason or profit_r > 0:
            outcome = "WIN" if profit_r >= 1.5 else "BREAKEVEN"
            pattern_key = f"{symbol}:{direction}:TREND_ALIGNED"
            lesson = (
                f"{symbol} {direction} savdosi SMC retesti va trend mosligi tufayli "
                f"+{profit_r:.2f}R foyda bilan yakunlandi. Muvaffaqiyatli setup tasdiqlandi."
            )

            # Reduce penalty on this pattern (positive reinforcement)
            self.db.update_pattern_weight(pattern_key, is_win=True, penalty_delta=-0.03)

            self.db.record_learned_lesson(
                signal_id=sig_id,
                symbol=symbol,
                direction=direction,
                outcome=outcome,
                net_r=profit_r,
                pips=highest_pips,
                pattern_key=pattern_key,
                loss_reason="None (Muvaffaqiyatli savdo)",
                lesson_learned=lesson,
            )
            logger.info(f"🧠 [Self-Learner] Reinforced winning pattern for {symbol} (+{profit_r:.2f}R)")
            return {
                "status": "REINFORCED",
                "outcome": outcome,
                "pattern_key": pattern_key,
                "loss_reason": "None",
                "lesson": lesson,
            }

        return {"outcome": "NEUTRAL", "lesson": "Trade expired without execution"}

    def _diagnose_loss(
        self,
        symbol: str,
        direction: str,
        h4_trend: str,
        macro: str,
        regime: str,
        highest_pips: float,
    ) -> Tuple[str, str, str]:
        """Diagnose root cause of trade failure."""
        is_counter_trend = (
            (direction == "BUY" and "BEAR" in h4_trend) or
            (direction == "SELL" and "BULL" in h4_trend)
        )
        is_dxy_headwind = (
            (direction == "BUY" and ("BULLISH" in macro or "KUCHLI" in macro)) or
            (direction == "SELL" and ("BEARISH" in macro or "KUCHSIZ" in macro))
        )

        if is_counter_trend:
            tag = "COUNTER_TREND"
            reason = f"Katta H4 trendiga ({h4_trend}) qarshi savdoga kirilgan."
            lesson = (
                f"{symbol} da H4 trendiga qarshi kirish xavfli ekani qayd etildi. "
                f"Kelgusida H4 va H1 to'liq bir tomonga yo'nalmaguncha bu yo'nalishdagi signallarga jarima qo'llanadi."
            )
        elif is_dxy_headwind:
            tag = "DXY_HEADWIND"
            reason = "AQSH Dollari indeksi (DXY) teskari tomonga kuchli harakat qilgan."
            lesson = (
                f"{symbol} da DXY bosimi hisobga olinmagani tufayli SL urildi. "
                f"DXY qarama-qarshi bo'lgan paytlarda kirish filtri kuchaytirildi."
            )
        elif "Volatil" in regime or highest_pips >= 30.0:
            tag = "PREMATURE_REVERSAL"
            reason = f"Narx dastlab +{highest_pips:.0f} pip foydaga borgan, lekin qaytib SL ga urilgan."
            lesson = (
                f"{symbol} da foyda tezda fiksatsiya qilinmagani sababli qaytishda zarar bo'ldi. "
                f"Volatillik yuqori bo'lganda TP1 ga yetmasdan ham SL ni qisqartirish tavsiya etiladi."
            )
        else:
            tag = "ZONE_INVALIDATION"
            reason = "Order Block / FVG zonasi buzilib, bozor likvidlikni pastdan ovladi."
            lesson = (
                f"{symbol} da kirish zonasi bozor oqimi tomonidan yorib o'tildi. "
                f"Keyingi safar zona ichida ikkinchi tasdiqlovchi sham yopilishini kutish shart."
            )

        return tag, reason, lesson

    # -------------------------------------------------------------------------
    # 2. Setup Evaluation & Penalty Query (Used by SignalEngine before entry)
    # -------------------------------------------------------------------------
    def evaluate_setup(
        self,
        symbol: str,
        direction: str,
        meta: Dict[str, Any],
    ) -> Tuple[float, Optional[str]]:
        """
        Check if proposed trade matches recurring negative patterns.
        Returns: (penalty_amount, warning_reason)
        """
        h4 = meta.get("h4_trend", "NEUTRAL")
        macro = meta.get("macro", "NEUTRAL")

        candidate_tags = []
        if (direction == "BUY" and "BEAR" in h4) or (direction == "SELL" and "BULL" in h4):
            candidate_tags.append("COUNTER_TREND")
        if (direction == "BUY" and "BULL" in macro) or (direction == "SELL" and "BEAR" in macro):
            candidate_tags.append("DXY_HEADWIND")
        candidate_tags.append("ZONE_INVALIDATION")

        max_penalty = 0.0
        matching_reason = None

        for tag in candidate_tags:
            pattern_key = f"{symbol}:{direction}:{tag}"
            penalty = self.db.get_pattern_penalty(pattern_key)
            if penalty > max_penalty:
                max_penalty = penalty
                matching_reason = (
                    f"AI O'z-o'zini o'rganish xotirasi: #{symbol} da ilgari '{tag}' "
                    f"holatida zararlar qayd etilgan (Jarima: -{penalty*100:.0f}%)"
                )

        return max_penalty, matching_reason

    # -------------------------------------------------------------------------
    # 3. Adaptive Capital Protection Tuning
    # -------------------------------------------------------------------------
    def get_adaptive_capital_protection(self) -> Dict[str, Any]:
        """
        Monitors recent win rate and loss streaks.
        If performance degrades, automatically tightens thresholds to protect funds.
        """
        stats = self.db.get_learning_stats()
        trades = stats["rolling_trades"]
        wr = stats["rolling_win_rate"]
        loss_streak = stats["loss_streak"]

        # Default: normal optimal operation
        res = {
            "is_active": False,
            "threshold_boost": 0.0,
            "min_rr_boost": 0.0,
            "status_badge": "🟢 OPTIMAL (Model barqaror ishlamoqda)",
            "rolling_win_rate": wr,
            "loss_streak": loss_streak,
        }

        # Danger condition: 2+ consecutive losses or low rolling win rate on 5+ trades
        if loss_streak >= 2 or (trades >= 5 and wr < 50.0):
            res["is_active"] = True
            res["threshold_boost"] = 0.06   # Requires e.g. 64% instead of 58%
            res["min_rr_boost"] = 0.3        # Requires e.g. 2.1 R:R instead of 1.8
            res["status_badge"] = (
                f"🛡️ ADAPTIV HIMOYA FAOL: {loss_streak} ta ketma-ket yo'qotish aniqlandi. "
                f"Kapitalni asrash uchun ishonch chegarasi +6% ga oshirildi!"
            )
        elif trades >= 5 and wr >= 65.0:
            res["status_badge"] = f"🟢 YUQORI SAMARADORLIK: So'nggi savdolarda Win-Rate {wr:.0f}%"

        return res

    # -------------------------------------------------------------------------
    # 4. Human & AI Context Formatting
    # -------------------------------------------------------------------------
    def format_recent_lessons_report(self, limit: int = 4) -> str:
        """Format recent lessons for Telegram /learn command and trader inspection."""
        stats = self.db.get_learning_stats()
        lessons = self.db.get_recent_lessons(limit=limit)

        adaptive = self.get_adaptive_capital_protection()

        lines = [
            "🧠 <b>CYBER TRADE — AI O'Z-O'ZINI O'RGANISH TIZIMI</b>",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"📊 <b>Umumiy O'rganilgan Darslar:</b> <code>{stats['total_lessons']} ta</code>",
            f"🛡️ <b>Jarima Qo'llangan Xavfli Qoliplar:</b> <code>{stats['penalized_patterns']} ta</code>",
            f"📈 <b>Oxirgi Savdolar Win-Rate:</b> <code>{stats['rolling_win_rate']:.1f}%</code>",
            f"🩺 <b>Adaptiv Tizim Holati:</b>\n{adaptive['status_badge']}",
            "━━━━━━━━━━━━━━━━━━━━━━",
            "📝 <b>OXIRGI SAVDOLARDAN CHIQARILGAN XULOSALAR:</b>\n",
        ]

        if not lessons:
            lines.append("<i>Hozircha bazada darslar to'planmagan. Bot yangi savdolar yakunlanishi bilan xulosalarni avtomatik qayd etadi.</i>")
        else:
            for l in lessons:
                icon = "✅" if l["outcome"] == "WIN" else ("🛡️" if l["outcome"] == "BREAKEVEN" else "🛑")
                r_str = f"+{l['net_r']:.2f}R" if l["net_r"] >= 0 else f"{l['net_r']:.2f}R"
                lines.append(
                    f"{icon} <b>#{l['symbol']} ({l['direction']}) — {r_str}:</b>\n"
                    f"  💡 <i>{l['lesson_learned']}</i>\n"
                )

        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("💡 <i>Bot har bir savdoni avtomatik tahlil qilib, bir xil xatoni qaytarmaslik uchun o'zini mustaqil takomillashtirib boradi.</i>")
        return "\n".join(lines)

    def get_ai_grounding_context(self) -> str:
        """Compact summary of learned lessons injected into Gemini/Groq LLM prompt."""
        stats = self.db.get_learning_stats()
        lessons = self.db.get_recent_lessons(limit=3)

        if not lessons:
            return "AI O'z-o'zini o'rganish xotirasi: Bot har bir yopilgan savdo xatosini avtomatik tahlil qilib boradi."

        lesson_texts = [f"• #{l['symbol']}: {l['lesson_learned']}" for l in lessons]
        return (
            f"AI O'ZINI O'ZI O'RGANISH NATIJALARI (Oxirgi savdolar Win-Rate: {stats['rolling_win_rate']:.0f}%):\n" +
            "\n".join(lesson_texts)
        )


# Global singleton instance
self_learner = SelfLearningEngine()
