"""
Cyber Trade - Precision Virtual Signal Tracker & Performance Auditor
=====================================================================
Calculates signal metrics according to strict professional prop-firm accounting rules:
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
from loguru import logger
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
    tp1_hit: bool = False
    breakeven_active: bool = False
    tp2_hit: bool = False
    tp3_hit: bool = False
    closed: bool = False
    close_reason: str = ""      # "TP2_WIN", "TP1_BE", "SL_LOSS", "EXPIRED", "MANUAL_CLOSE"
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
            if curr_clean == clean_sym and not s.closed:
                return True
        return False

    def add_signal(self, signal: ActiveSignal):
        """Register a newly broadcasted signal."""
        if self.has_active_signal(signal.symbol):
            logger.warning(f"Active signal already exists for {signal.symbol}, rejecting duplicate.")
            return

        self.active_signals.append(signal)
        self._save_state()
        db.log_signal(signal)
        logger.info(f"Registered active signal: {signal.symbol} {signal.direction} @ {signal.entry_price}")

    def clear_all_signals(self) -> int:
        """Manually close all open active signals."""
        count = len(self.active_signals)
        for s in self.active_signals:
            s.closed = True
            s.close_reason = "MANUAL_CLOSE"
            self.closed_signals.append(s)
            db.close_signal(s.id, "MANUAL_CLOSE", s.entry_price, s.profit_r, s.highest_pips)
        self.active_signals = []
        self._save_state()
        return count

    def update_price(self, symbol: str, current_price: float) -> List[Dict[str, Any]]:
        """
        Check active signals for this symbol against current market price using
        prop-firm precision accounting (TP1 -> BE -> TP2).
        """
        alerts = []
        remaining_signals = []
        now_utc = datetime.now(timezone.utc)

        for sig in self.active_signals:
            if sig.symbol != symbol or sig.closed:
                remaining_signals.append(sig)
                continue

            risk = abs(sig.entry_price - sig.stop_loss)
            if risk <= 0:
                risk = 0.001

            # -------------------------------------------------------------
            # 0. Expiration Check (24 soatdan oshsa signal yakunlanadi)
            # -------------------------------------------------------------
            try:
                created_dt = datetime.fromisoformat(sig.created_at)
                age_hours = (now_utc - created_dt).total_seconds() / 3600.0
                if age_hours >= 24:
                    sig.closed = True
                    sig.close_reason = "EXPIRED"
                    sig.close_price = current_price

                    # Accounting on expiration
                    floating_diff = (current_price - sig.entry_price) if sig.direction == "BUY" else (sig.entry_price - current_price)
                    floating_r = floating_diff / risk
                    if sig.tp1_hit:
                        # 50% was closed at TP1 (+0.75R), remaining 50% closed at current price
                        sig.profit_r = round(0.75 + (max(0.0, floating_r) * 0.5), 2)
                    else:
                        sig.profit_r = round(max(-1.0, floating_r), 2)

                    self.closed_signals.append(sig)
                    db.close_signal(sig.id, "EXPIRED", current_price, sig.profit_r, sig.highest_pips)
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

            # Calculate floating pips
            pips = calculate_pips(sig.symbol, sig.entry_price, current_price, sig.direction)
            sig.last_pips = pips
            sig.highest_pips = max(sig.highest_pips, pips)

            # -------------------------------------------------------------
            # 1. Milestone Progress Notification (30, 60, 100, 200, 350, 500 pips)
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
            # 2. Buy Trades Execution
            # -------------------------------------------------------------
            if sig.direction == "BUY":
                # Condition A: TP2 Hit (Target Achieved)
                if current_price >= sig.take_profit_2:
                    sig.tp2_hit = True
                    sig.closed = True
                    sig.close_reason = "TP2_WIN"
                    sig.close_price = current_price
                    # 50% at TP1 (1.5R * 0.5 = +0.75R) + 50% at TP2 (2.5R * 0.5 = +1.25R) = +2.0R
                    sig.profit_r = 2.0
                    self.closed_signals.append(sig)
                    db.close_signal(sig.id, "TP2_WIN", current_price, sig.profit_r, sig.highest_pips)
                    alerts.append({
                        "type": "TP2_HIT",
                        "signal": sig,
                        "message": (
                            f"🎯🎯 <b>MUVAFFAQIYAT! TP2 TO'LIQ URILDI:</b> #{sig.symbol}\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"Yo'nalish: <b>BUY</b> | Narx: <code>{current_price:.2f}</code>\n"
                            f"💰 <b>Natija: +2.0R (+{pips:.0f} pips) SOF FOYDA!</b>\n"
                            f"Savdo reja bo'yicha to'liq yakunlandi va yopildi. Tabriklaymiz! 🏆"
                        ),
                    })
                    continue

                # Condition B: TP1 Hit (Secure 50% profit & Move SL to Breakeven)
                if current_price >= sig.take_profit_1 and not sig.tp1_hit:
                    sig.tp1_hit = True
                    sig.breakeven_active = True
                    alerts.append({
                        "type": "TP1_HIT",
                        "signal": sig,
                        "message": (
                            f"⚡ <b>TP1 URILDI:</b> #{sig.symbol}\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"Yo'nalish: <b>BUY</b> | Narx: <code>{current_price:.2f}</code> (+{pips:.0f} pips)\n"
                            f"🔔 <b>QAT'IY QOIDA:</b>\n"
                            f"1. Stop-Lossni Kirish narxiga (<code>{sig.entry_price:.2f}</code> — 0 ga) suring!\n"
                            f"2. Pozitsiyaning 50% qismini fiksatsiya qiling (+0.75R daromad olindi).\n"
                            f"Qolgan 50% qismi TP2 maqsadiga xavfsiz qoldiriladi."
                        ),
                    })

                # Condition C: Retrace to Breakeven (after TP1 was hit)
                if sig.breakeven_active and current_price <= sig.entry_price:
                    sig.closed = True
                    sig.close_reason = "TP1_BE"
                    sig.close_price = current_price
                    sig.profit_r = 0.75  # Kept the 50% from TP1
                    self.closed_signals.append(sig)
                    db.close_signal(sig.id, "TP1_BE", current_price, sig.profit_r, sig.highest_pips)
                    alerts.append({
                        "type": "BREAKEVEN_HIT",
                        "signal": sig,
                        "message": (
                            f"🛡️ <b>BREAKEVEN (0 GA) YOPILDI:</b> #{sig.symbol}\n"
                            f"Yo'nalish: <b>BUY</b> | Qaytdi: <code>{current_price:.2f}</code>\n"
                            f"Natija: <b>+0.75R SOF FOYDA</b> (TP1 da 50% foyda olingan, qolgani zararsiz yopildi)."
                        ),
                    })
                    continue

                # Condition D: Direct Stop Loss Hit (before TP1)
                if not sig.breakeven_active and current_price <= sig.stop_loss:
                    sig.closed = True
                    sig.close_reason = "SL_LOSS"
                    sig.close_price = current_price
                    sig.profit_r = -1.0
                    self.closed_signals.append(sig)
                    db.close_signal(sig.id, "SL_LOSS", current_price, -1.0, sig.highest_pips)
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

            # -------------------------------------------------------------
            # 3. Sell Trades Execution
            # -------------------------------------------------------------
            elif sig.direction == "SELL":
                # Condition A: TP2 Hit (Target Achieved)
                if current_price <= sig.take_profit_2:
                    sig.tp2_hit = True
                    sig.closed = True
                    sig.close_reason = "TP2_WIN"
                    sig.close_price = current_price
                    sig.profit_r = 2.0
                    self.closed_signals.append(sig)
                    db.close_signal(sig.id, "TP2_WIN", current_price, sig.profit_r, sig.highest_pips)
                    alerts.append({
                        "type": "TP2_HIT",
                        "signal": sig,
                        "message": (
                            f"🎯🎯 <b>MUVAFFAQIYAT! TP2 TO'LIQ URILDI:</b> #{sig.symbol}\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"Yo'nalish: <b>SELL</b> | Narx: <code>{current_price:.2f}</code>\n"
                            f"💰 <b>Natija: +2.0R (+{pips:.0f} pips) SOF FOYDA!</b>\n"
                            f"Savdo reja bo'yicha to'liq yakunlandi va yopildi. Tabriklaymiz! 🏆"
                        ),
                    })
                    continue

                # Condition B: TP1 Hit
                if current_price <= sig.take_profit_1 and not sig.tp1_hit:
                    sig.tp1_hit = True
                    sig.breakeven_active = True
                    alerts.append({
                        "type": "TP1_HIT",
                        "signal": sig,
                        "message": (
                            f"⚡ <b>TP1 URILDI:</b> #{sig.symbol}\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"Yo'nalish: <b>SELL</b> | Narx: <code>{current_price:.2f}</code> (+{pips:.0f} pips)\n"
                            f"🔔 <b>QAT'IY QOIDA:</b>\n"
                            f"1. Stop-Lossni Kirish narxiga (<code>{sig.entry_price:.2f}</code> — 0 ga) suring!\n"
                            f"2. Pozitsiyaning 50% qismini fiksatsiya qiling (+0.75R daromad olindi).\n"
                            f"Qolgan 50% qismi TP2 maqsadiga xavfsiz qoldiriladi."
                        ),
                    })

                # Condition C: Retrace to Breakeven
                if sig.breakeven_active and current_price >= sig.entry_price:
                    sig.closed = True
                    sig.close_reason = "TP1_BE"
                    sig.close_price = current_price
                    sig.profit_r = 0.75
                    self.closed_signals.append(sig)
                    db.close_signal(sig.id, "TP1_BE", current_price, sig.profit_r, sig.highest_pips)
                    alerts.append({
                        "type": "BREAKEVEN_HIT",
                        "signal": sig,
                        "message": (
                            f"🛡️ <b>BREAKEVEN (0 GA) YOPILDI:</b> #{sig.symbol}\n"
                            f"Yo'nalish: <b>SELL</b> | Qaytdi: <code>{current_price:.2f}</code>\n"
                            f"Natija: <b>+0.75R SOF FOYDA</b> (TP1 da 50% foyda olingan, qolgani zararsiz yopildi)."
                        ),
                    })
                    continue

                # Condition D: Direct Stop Loss Hit
                if not sig.breakeven_active and current_price >= sig.stop_loss:
                    sig.closed = True
                    sig.close_reason = "SL_LOSS"
                    sig.close_price = current_price
                    sig.profit_r = -1.0
                    self.closed_signals.append(sig)
                    db.close_signal(sig.id, "SL_LOSS", current_price, -1.0, sig.highest_pips)
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
