"""
Cyber Trade - Precision Virtual Signal Tracker & Performance Auditor
=====================================================================
Calculates signal metrics according to strict professional prop-firm accounting rules:
- Intra-candle High/Low Wick monitoring (never misses SL or TP touch!).
- Limit Order Retest execution: detects when pending Buy/Sell Limit orders are filled or expired.
- TP1 Hit: 50% partial profit secured (+0.75R based on 1:1.5 target).
- Breakeven Activation: Stop-loss automatically updated to Entry Price (0 risk).
- TP2 Hit: Remaining 50% secured (+1.25R based on 1:2.5 target). Total: +2.0R!
- Retrace to Entry after TP1: Remaining 50% closes at 0. Total: +0.75R (Protected Win).
- Direct Stop-Loss Hit: -1.0R loss (strict risk control).
- 24h Expiration: Closes trade based on floating R at the 24h mark.
"""

import json
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Any
try:
    from loguru import logger
except ImportError:
    from src.logger import logger
from src.database import db


def calculate_pips(symbol: str, entry: float, current: float, direction: str) -> float:
    """Calculate price movement in pips/points based on asset type."""
    diff = (current - entry) if direction.upper() == "BUY" else (entry - current)
    sym = symbol.upper()
    if "XAU" in sym or "GOLD" in sym:
        return diff * 10.0        # Oltinda $1 harakat = 10 pips ($0.10 = 1 pip)
    if "BTC" in sym:
        return diff               # Bitcoinda $1 = 1 point/pip
    if "ETH" in sym:
        return diff * 10.0        # Ethereumda $0.10 = 1 pip
    if "SOL" in sym:
        return diff * 10.0        # Solana
    return diff * 10000.0         # Standart Forex


@dataclass
class ActiveSignal:
    id: str
    symbol: str
    timeframe: str
    direction: str              # "BUY" or "SELL"
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    take_profit_3: float
    created_at: str
    ai_confidence: float
    order_type: str = "MARKET"   # "MARKET" or "BUY LIMIT" / "SELL LIMIT"
    is_filled: bool = True       # False for pending Limit orders until triggered
    tp1_hit: bool = False
    breakeven_active: bool = False
    tp2_hit: bool = False
    tp3_hit: bool = False
    closed: bool = False
    close_reason: str = ""      # "TP2_WIN", "TP1_BE", "SL_LOSS", "EXPIRED", "MANUAL_CLOSE", "LIMIT_EXPIRED"
    close_price: float = 0.0
    profit_r: float = 0.0
    last_pips: float = 0.0
    highest_pips: float = 0.0
    last_alert_milestone: int = 0


class SignalTracker:
    """
    Precision Virtual Trade Performance Manager.
    Logs each closed trade with exact R:R profit metrics.
    """

    def __init__(self, state_file: str = "data/signals_state.json"):
        self.state_file = Path(state_file)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.active_signals: List[ActiveSignal] = []
        self.closed_signals: List[ActiveSignal] = []
        self._load_state()

    def _load_state(self):
        """Load signals state from JSON file."""
        if not self.state_file.exists():
            return
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.active_signals = [ActiveSignal(**s) for s in data.get("active", [])]
                self.closed_signals = [ActiveSignal(**s) for s in data.get("closed", [])]
        except Exception as e:
            logger.error(f"Error loading signals state: {e}")

    def _save_state(self):
        """Persist state to JSON file."""
        try:
            data = {
                "active": [asdict(s) for s in self.active_signals],
                "closed": [asdict(s) for s in self.closed_signals[-150:]],
            }
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving signals state: {e}")

    def has_active_signal(self, symbol: str) -> bool:
        """Check if an open trade signal already exists for this symbol (prevent duplicates)."""
        clean_sym = symbol.upper().replace("/", "").replace("-", "")
        for s in self.active_signals:
            curr_clean = s.symbol.upper().replace("/", "").replace("-", "")
            # Only consider active if not closed and still has initial risk (not yet at breakeven)
            if curr_clean == clean_sym and not s.closed and not s.breakeven_active:
                return True
        return False

    def add_signal(self, signal: ActiveSignal):
        """Register a newly broadcasted signal."""
        if self.has_active_signal(signal.symbol):
            logger.warning(f"Active signal already exists for {signal.symbol}, rejecting duplicate.")
            return

        # If it's a Limit order, mark it as pending fill
        if "LIMIT" in signal.order_type.upper():
            signal.is_filled = False

        self.active_signals.append(signal)
        self._save_state()
        db.log_signal(signal)
        logger.info(f"Registered active signal: {signal.symbol} {signal.order_type} @ {signal.entry_price}")

    def _finalize_trade_closure(
        self,
        sig: ActiveSignal,
        close_reason: str,
        close_price: float,
        profit_r: float,
    ):
        """Mark signal closed in memory, update DB, and invoke AI self-learner."""
        sig.closed = True
        sig.close_reason = close_reason
        sig.close_price = close_price
        sig.profit_r = profit_r
        self.closed_signals.append(sig)
        db.close_signal(sig.id, close_reason, close_price, profit_r, sig.highest_pips)
        try:
            from src.self_learner import self_learner
            self_learner.on_trade_closed(sig, close_reason, close_price, profit_r)
        except Exception as e:
            logger.debug(f"Self-learner hook skipped: {e}")

    def clear_all_signals(self) -> int:
        """Manually close all open active signals."""
        count = len(self.active_signals)
        for s in self.active_signals:
            self._finalize_trade_closure(s, "MANUAL_CLOSE", s.entry_price, s.profit_r)
        self.active_signals = []
        self._save_state()
        return count

    def update_price(
        self,
        symbol: str,
        current_price: float,
        high_price: Optional[float] = None,
        low_price: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Check active signals for this symbol against current market price and candle extremes
        using prop-firm precision accounting (Intra-candle Wicks: High/Low -> TP1 -> BE -> TP2).
        """
        alerts = []
        remaining_signals = []
        now_utc = datetime.now(timezone.utc)

        # High/Low fallback
        high_check = high_price if high_price is not None else current_price
        low_check = low_price if low_price is not None else current_price

        for sig in self.active_signals:
            if sig.symbol != symbol or sig.closed:
                remaining_signals.append(sig)
                continue

            risk = abs(sig.entry_price - sig.stop_loss)
            if risk <= 0:
                risk = 0.001

            # -------------------------------------------------------------
            # 0. Expiration Check (24 hours timeout)
            # -------------------------------------------------------------
            try:
                created_dt = datetime.fromisoformat(sig.created_at)
                age_hours = (now_utc - created_dt).total_seconds() / 3600.0
                if age_hours >= 24:
                    sig.closed = True
                    sig.close_reason = "EXPIRED"
                    sig.close_price = current_price

                    if not sig.is_filled:
                        sig.profit_r = 0.0
                    elif sig.tp1_hit:
                        floating_diff = (current_price - sig.entry_price) if sig.direction == "BUY" else (sig.entry_price - current_price)
                        floating_r = floating_diff / risk
                        sig.profit_r = round(0.75 + (max(0.0, floating_r) * 0.5), 2)
                    else:
                        floating_diff = (current_price - sig.entry_price) if sig.direction == "BUY" else (sig.entry_price - current_price)
                        floating_r = floating_diff / risk
                        sig.profit_r = round(max(-1.0, floating_r), 2)

                    self._finalize_trade_closure(sig, "EXPIRED", current_price, sig.profit_r)
                    alerts.append({
                        "type": "SIGNAL_EXPIRED",
                        "signal": sig,
                        "message": (
                            f"⏱️ <b>SIGNAL MUDDATI TUGADI (24h):</b> #{sig.symbol}\n"
                            f"Yo'nalish: <b>{sig.direction}</b> | Joriy: <code>{current_price:.2f}</code>\n"
                            f"Natija: <b>{'+' if sig.profit_r >= 0 else ''}{sig.profit_r:.2f}R</b>\n"
                            f"Signal 24 soat davomida ochiq turdi va avtomatik yakunlandi."
                        ),
                    })
                    continue
            except Exception:
                pass

            # -------------------------------------------------------------
            # 1. Pending Limit Order Fill Verification
            # -------------------------------------------------------------
            if not sig.is_filled:
                if sig.direction == "BUY":
                    # Buy limit filled if low dipped to or below entry
                    if low_check <= sig.entry_price:
                        sig.is_filled = True
                        alerts.append({
                            "type": "LIMIT_FILLED",
                            "signal": sig,
                            "message": (
                                f"📥 <b>BUY LIMIT ISHGA TUSHDI:</b> #{sig.symbol}\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                                f"Narx retest darajasiga (<code>{sig.entry_price:.2f}</code>) kirdi va buyurtma to'liq ochildi!\n"
                                f"🛑 Stop-Loss: <code>{sig.stop_loss:.2f}</code>\n"
                                f"🎯 TP1: <code>{sig.take_profit_1:.2f}</code> | TP2: <code>{sig.take_profit_2:.2f}</code>"
                            ),
                        })
                    # Expire limit if price already ran 2.5x ATR away without retest
                    elif high_check >= sig.entry_price + (risk * 2.2):
                        self._finalize_trade_closure(sig, "LIMIT_EXPIRED", current_price, 0.0)
                        alerts.append({
                            "type": "LIMIT_CANCELLED",
                            "signal": sig,
                            "message": (
                                f"ℹ️ <b>BUY LIMIT BEKOR QILINDI:</b> #{sig.symbol}\n"
                                f"Narx kirish zonasiga retestsiz maqsadga qarab ketdi. "
                                f"Xavfsizlik maqsadida limit buyurtma bekor qilindi."
                            ),
                        })
                        continue

                elif sig.direction == "SELL":
                    # Sell limit filled if high reached or exceeded entry
                    if high_check >= sig.entry_price:
                        sig.is_filled = True
                        alerts.append({
                            "type": "LIMIT_FILLED",
                            "signal": sig,
                            "message": (
                                f"📥 <b>SELL LIMIT ISHGA TUSHDI:</b> #{sig.symbol}\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                                f"Narx retest darajasiga (<code>{sig.entry_price:.2f}</code>) kirdi va buyurtma to'liq ochildi!\n"
                                f"🛑 Stop-Loss: <code>{sig.stop_loss:.2f}</code>\n"
                                f"🎯 TP1: <code>{sig.take_profit_1:.2f}</code> | TP2: <code>{sig.take_profit_2:.2f}</code>"
                            ),
                        })
                    elif low_check <= sig.entry_price - (risk * 2.2):
                        self._finalize_trade_closure(sig, "LIMIT_EXPIRED", current_price, 0.0)
                        alerts.append({
                            "type": "LIMIT_CANCELLED",
                            "signal": sig,
                            "message": (
                                f"ℹ️ <b>SELL LIMIT BEKOR QILINDI:</b> #{sig.symbol}\n"
                                f"Narx kirish zonasiga retestsiz maqsadga qarab ketdi. "
                                f"Xavfsizlik maqsadida limit buyurtma bekor qilindi."
                            ),
                        })
                        continue

                # If still not filled, keep monitoring
                if not sig.is_filled:
                    remaining_signals.append(sig)
                    continue

            # Calculate floating pips
            pips = calculate_pips(sig.symbol, sig.entry_price, current_price, sig.direction)
            sig.last_pips = pips
            sig.highest_pips = max(sig.highest_pips, pips)

            # -------------------------------------------------------------
            # 2. Milestone Progress Notification
            # -------------------------------------------------------------
            milestones = [30, 60, 100, 150, 250, 400, 600]
            for m in milestones:
                if pips >= m and m > sig.last_alert_milestone:
                    sig.last_alert_milestone = m
                    alerts.append({
                        "type": "PROGRESS_UPDATE",
                        "signal": sig,
                        "message": (
                            f"📈 <b>FOYDA PROGRESSI:</b> #{sig.symbol}\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"🎯 Yo'nalish: <b>{sig.direction}</b>\n"
                            f"🚀 Harakat: <b>+{pips:.0f} pips foydada!</b>\n"
                            f"💵 Kirish: <code>{sig.entry_price:.2f}</code> ➔ Joriy: <code>{current_price:.2f}</code>\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"<i>Signal maqsad sari muvaffaqiyatli harakatlanmoqda.</i>"
                        ),
                    })
                    break

            # -------------------------------------------------------------
            # 3. Active Buy Trades Execution
            # -------------------------------------------------------------
            if sig.direction == "BUY":
                # Check Direct Stop Loss Hit First (Wick low touch before Breakeven)
                if not sig.breakeven_active and low_check <= sig.stop_loss:
                    self._finalize_trade_closure(sig, "SL_LOSS", sig.stop_loss, -1.0)
                    alerts.append({
                        "type": "SL_HIT",
                        "signal": sig,
                        "message": (
                            f"🛑 <b>STOP-LOSS URILDI:</b> #{sig.symbol}\n"
                            f"Yo'nalish: <b>BUY</b>\n"
                            f"Kirish: <code>{sig.entry_price:.2f}</code> | SL: <code>{sig.stop_loss:.2f}</code>\n"
                            f"Natija: -1.0R (Risk qoidasi buzilmadi, yo'qotish 1% bilan cheklandi)."
                        ),
                    })
                    continue

                # Check TP2 Hit (Target Achieved)
                if high_check >= sig.take_profit_2:
                    sig.tp2_hit = True
                    self._finalize_trade_closure(sig, "TP2_WIN", sig.take_profit_2, 2.0)
                    alerts.append({
                        "type": "TP2_HIT",
                        "signal": sig,
                        "message": (
                            f"🎯🎯 <b>MUVAFFAQIYAT! TP2 TO'LIQ URILDI:</b> #{sig.symbol}\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"Yo'nalish: <b>BUY</b> | Narx: <code>{sig.take_profit_2:.2f}</code>\n"
                            f"💰 <b>Natija: +2.0R (+{pips:.0f} pips) SOF FOYDA!</b>\n"
                            f"Savdo reja bo'yicha to'liq yakunlandi va yopildi. Tabriklaymiz! 🏆"
                        ),
                    })
                    continue

                # Check TP1 Hit (Secure 50% profit & Move SL to Breakeven)
                just_hit_tp1 = False
                if high_check >= sig.take_profit_1 and not sig.tp1_hit:
                    sig.tp1_hit = True
                    sig.breakeven_active = True
                    just_hit_tp1 = True
                    alerts.append({
                        "type": "TP1_HIT",
                        "signal": sig,
                        "message": (
                            f"⚡ <b>TP1 URILDI:</b> #{sig.symbol}\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"Yo'nalish: <b>BUY</b> | Narx: <code>{sig.take_profit_1:.2f}</code> (+{pips:.0f} pips)\n"
                            f"🔔 <b>QAT'IY QOIDA:</b>\n"
                            f"1. Stop-Lossni Kirish narxiga (<code>{sig.entry_price:.2f}</code> — 0 ga) suring!\n"
                            f"2. Pozitsiyaning 50% qismini fiksatsiya qiling (+0.75R daromad olindi).\n"
                            f"Qolgan 50% qismi TP2 maqsadiga xavfsiz qoldiriladi."
                        ),
                    })

                # Check Retrace to Breakeven (only after TP1 was hit, on subsequent retrace)
                if sig.breakeven_active and not just_hit_tp1 and (current_price <= sig.entry_price or low_check <= sig.entry_price):
                    self._finalize_trade_closure(sig, "TP1_BE", sig.entry_price, 0.75)
                    alerts.append({
                        "type": "BREAKEVEN_HIT",
                        "signal": sig,
                        "message": (
                            f"🛡️ <b>BREAKEVEN (0 GA) YOPILDI:</b> #{sig.symbol}\n"
                            f"Yo'nalish: <b>BUY</b> | Qaytdi: <code>{sig.entry_price:.2f}</code>\n"
                            f"Natija: <b>+0.75R SOF FOYDA</b> (TP1 da 50% foyda olingan, qolgani zararsiz yopildi)."
                        ),
                    })
                    continue

            # -------------------------------------------------------------
            # 4. Active Sell Trades Execution
            # -------------------------------------------------------------
            elif sig.direction == "SELL":
                # Check Direct Stop Loss Hit First
                if not sig.breakeven_active and high_check >= sig.stop_loss:
                    self._finalize_trade_closure(sig, "SL_LOSS", sig.stop_loss, -1.0)
                    alerts.append({
                        "type": "SL_HIT",
                        "signal": sig,
                        "message": (
                            f"🛑 <b>STOP-LOSS URILDI:</b> #{sig.symbol}\n"
                            f"Yo'nalish: <b>SELL</b>\n"
                            f"Kirish: <code>{sig.entry_price:.2f}</code> | SL: <code>{sig.stop_loss:.2f}</code>\n"
                            f"Natija: -1.0R (Risk qoidasi buzilmadi, yo'qotish 1% bilan cheklandi)."
                        ),
                    })
                    continue

                # Check TP2 Hit
                if low_check <= sig.take_profit_2:
                    sig.tp2_hit = True
                    self._finalize_trade_closure(sig, "TP2_WIN", sig.take_profit_2, 2.0)
                    alerts.append({
                        "type": "TP2_HIT",
                        "signal": sig,
                        "message": (
                            f"🎯🎯 <b>MUVAFFAQIYAT! TP2 TO'LIQ URILDI:</b> #{sig.symbol}\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"Yo'nalish: <b>SELL</b> | Narx: <code>{sig.take_profit_2:.2f}</code>\n"
                            f"💰 <b>Natija: +2.0R (+{pips:.0f} pips) SOF FOYDA!</b>\n"
                            f"Savdo reja bo'yicha to'liq yakunlandi va yopildi. Tabriklaymiz! 🏆"
                        ),
                    })
                    continue

                # Check TP1 Hit
                just_hit_tp1_sell = False
                if low_check <= sig.take_profit_1 and not sig.tp1_hit:
                    sig.tp1_hit = True
                    sig.breakeven_active = True
                    just_hit_tp1_sell = True
                    alerts.append({
                        "type": "TP1_HIT",
                        "signal": sig,
                        "message": (
                            f"⚡ <b>TP1 URILDI:</b> #{sig.symbol}\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"Yo'nalish: <b>SELL</b> | Narx: <code>{sig.take_profit_1:.2f}</code> (+{pips:.0f} pips)\n"
                            f"🔔 <b>QAT'IY QOIDA:</b>\n"
                            f"1. Stop-Lossni Kirish narxiga (<code>{sig.entry_price:.2f}</code> — 0 ga) suring!\n"
                            f"2. Pozitsiyaning 50% qismini fiksatsiya qiling (+0.75R daromad olindi).\n"
                            f"Qolgan 50% qismi TP2 maqsadiga xavfsiz qoldiriladi."
                        ),
                    })

                # Check Retrace to Breakeven
                if sig.breakeven_active and not just_hit_tp1_sell and (current_price >= sig.entry_price or high_check >= sig.entry_price):
                    self._finalize_trade_closure(sig, "TP1_BE", sig.entry_price, 0.75)
                    alerts.append({
                        "type": "BREAKEVEN_HIT",
                        "signal": sig,
                        "message": (
                            f"🛡️ <b>BREAKEVEN (0 GA) YOPILDI:</b> #{sig.symbol}\n"
                            f"Yo'nalish: <b>SELL</b> | Qaytdi: <code>{sig.entry_price:.2f}</code>\n"
                            f"Natija: <b>+0.75R SOF FOYDA</b> (TP1 da 50% foyda olingan, qolgani zararsiz yopildi)."
                        ),
                    })
                    continue

            # Keep active
            remaining_signals.append(sig)

        self.active_signals = remaining_signals
        self._save_state()
        return alerts

    def get_performance_summary(self) -> Dict[str, Any]:
        """
        Calculate realistic prop-firm performance metrics:
        Win-Rate, Total R profit, Profit Factor, and trade breakdown.
        """
        all_closed = list(self.closed_signals)
        total_closed = len(all_closed)
        if total_closed == 0:
            return {
                "total_signals": 0,
                "win_rate": 0.0,
                "total_r": 0.0,
                "tp2_count": 0,
                "be_win_count": 0,
                "sl_count": 0,
                "expired_count": 0,
                "profit_factor": 0.0,
            }

        wins = [s for s in all_closed if s.profit_r > 0]
        losses = [s for s in all_closed if s.profit_r < 0]
        tp2_wins = [s for s in all_closed if s.close_reason == "TP2_WIN"]
        be_wins = [s for s in all_closed if s.close_reason == "TP1_BE"]
        sl_losses = [s for s in all_closed if s.close_reason == "SL_LOSS"]
        expired = [s for s in all_closed if s.close_reason == "EXPIRED"]

        win_rate = (len(wins) / total_closed) * 100.0
        total_r = sum(s.profit_r for s in all_closed)

        total_gain = sum(s.profit_r for s in wins)
        total_loss = abs(sum(s.profit_r for s in losses))
        profit_factor = round(total_gain / total_loss, 2) if total_loss > 0 else (99.0 if total_gain > 0 else 1.0)

        return {
            "total_signals": total_closed,
            "win_rate": win_rate,
            "total_r": round(total_r, 2),
            "tp2_count": len(tp2_wins),
            "be_win_count": len(be_wins),
            "sl_count": len(sl_losses),
            "expired_count": len(expired),
            "profit_factor": profit_factor,
        }
