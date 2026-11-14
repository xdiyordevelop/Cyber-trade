"""
Cyber Trade - Live Signal Tracker & Performance Monitor
========================================================
Continuously monitors active trading signals:
- Prevents duplicate signals for the same symbol
- Calculates floating pips and profit progress in real time
- Emits milestone alerts (+30 pips, +60 pips, +100 pips)
- Detects when TP1 is hit -> Emits "Move SL to Breakeven (0)" alert
- Detects when TP2 / TP3 is hit -> Emits profit milestones
- Detects Stop-Loss hit -> Marks trade closed
- Logs all historical performance and win-rate metrics
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
    return diff * 10000.0         # Standart Forex (EURUSD va b.)


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
    tp2_hit: bool = False
    tp3_hit: bool = False
    closed: bool = False
    close_reason: str = ""      # "TP1", "TP2", "TP3", "SL", "EXPIRED"
    close_price: float = 0.0
    profit_r: float = 0.0
    last_pips: float = 0.0
    highest_pips: float = 0.0
    last_alert_milestone: int = 0


class SignalTracker:
    """
    Manages and tracks active signals in real time.
    Persists state to data/signals_state.json.
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
                "closed": [asdict(s) for s in self.closed_signals[-100:]],  # Keep last 100 closed
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
        # Double check duplicate
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
            db.close_signal(s.id, "MANUAL_CLOSE", s.entry_price, 0.0, s.highest_pips)
        self.active_signals = []
        self._save_state()
        return count

    def update_price(self, symbol: str, current_price: float) -> List[Dict[str, Any]]:
        """
        Check active signals for this symbol against current market price.
        Returns a list of alert notifications to broadcast via Telegram.
        """
        alerts = []
        remaining_signals = []
        now_utc = datetime.now(timezone.utc)

        for sig in self.active_signals:
            if sig.symbol != symbol or sig.closed:
                remaining_signals.append(sig)
                continue

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
                    self.closed_signals.append(sig)
                    alerts.append({
                        "type": "SIGNAL_EXPIRED",
                        "signal": sig,
                        "message": (
                            f"⏱️ <b>SIGNAL MUDDATI TUGADI (24h):</b> #{sig.symbol}\n"
                            f"Yo'nalish: <b>{sig.direction}</b> | Joriy: <code>{current_price:.2f}</code>\n"
                            f"Signal 24 soat davomida ochiq turdi. Pozitsiyani yopish tavsiya etiladi."
                        ),
                    })
                    continue
            except Exception:
                pass

            risk = abs(sig.entry_price - sig.stop_loss)
            if risk <= 0:
                risk = 0.001

            # Calculate floating pips
            pips = calculate_pips(sig.symbol, sig.entry_price, current_price, sig.direction)
            sig.last_pips = pips
            sig.highest_pips = max(sig.highest_pips, pips)

            # -------------------------------------------------------------
            # 1. Milestone Progress Notification (Har 30-50 pip harakatda)
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
                            f"<i>Signal muvaffaqiyatli ishlamoqda.</i>"
                        ),
                    })
                    break

            # -------------------------------------------------------------
            # 2. Buy Trades Check
            # -------------------------------------------------------------
            if sig.direction == "BUY":
                # Check Stop Loss
                if current_price <= sig.stop_loss:
                    sig.closed = True
                    sig.close_reason = "SL"
                    sig.close_price = current_price
                    sig.profit_r = -1.0
                    self.closed_signals.append(sig)
                    alerts.append({
                        "type": "SL_HIT",
                        "signal": sig,
                        "message": (
                            f"🛑 <b>STOP-LOSS URILDI:</b> #{sig.symbol}\n"
                            f"Yo'nalish: <b>BUY</b>\n"
                            f"Kirish: <code>{sig.entry_price:.2f}</code> | SL: <code>{sig.stop_loss:.2f}</code>\n"
                            f"Natija: -1.0R (Risk qat'iy nazorat qilindi)."
                        ),
                    })
                    continue

                # Check TP2 (Asosiy maqsad urilganda signal muvaffaqiyatli yopiladi)
                if current_price >= sig.take_profit_2:
                    sig.tp2_hit = True
                    sig.closed = True
                    sig.close_reason = "TP2"
                    sig.close_price = current_price
                    r_gain = abs(sig.take_profit_2 - sig.entry_price) / risk
                    sig.profit_r = r_gain
                    self.closed_signals.append(sig)
                    alerts.append({
                        "type": "TP2_HIT",
                        "signal": sig,
                        "message": (
                            f"🎯🎯 <b>MUVAFFAQIYAT! TP2 TO'LIQ URILDI:</b> #{sig.symbol}\n"
                            f"Yo'nalish: <b>BUY</b> | Narx: <code>{current_price:.2f}</code>\n"
                            f"Natija: <b>+{r_gain:.1f}R (+{pips:.0f} pips) SOF FOYDA!</b>\n"
                            f"Savdo to'liq yakunlandi va yopildi. Tabriklaymiz! 💰"
                        ),
                    })
                    continue

                # Check TP1
                if current_price >= sig.take_profit_1 and not sig.tp1_hit:
                    sig.tp1_hit = True
                    alerts.append({
                        "type": "TP1_HIT",
                        "signal": sig,
                        "message": (
                            f"⚡ <b>TP1 URILDI:</b> #{sig.symbol}\n"
                            f"Yo'nalish: <b>BUY</b> | Narx: <code>{current_price:.2f}</code> (+{pips:.0f} pips)\n"
                            f"🔔 <b>MUHIM AMAL:</b>\n"
                            f"1. Stop-Lossni Kirish narxiga (Breakeven / 0 ga) suring!\n"
                            f"2. Foydaning 50% qismini fiksatsiya qiling."
                        ),
                    })

            # -------------------------------------------------------------
            # 3. Sell Trades Check
            # -------------------------------------------------------------
            elif sig.direction == "SELL":
                # Check Stop Loss
                if current_price >= sig.stop_loss:
                    sig.closed = True
                    sig.close_reason = "SL"
                    sig.close_price = current_price
                    sig.profit_r = -1.0
                    self.closed_signals.append(sig)
                    alerts.append({
                        "type": "SL_HIT",
                        "signal": sig,
                        "message": (
                            f"🛑 <b>STOP-LOSS URILDI:</b> #{sig.symbol}\n"
                            f"Yo'nalish: <b>SELL</b>\n"
                            f"Kirish: <code>{sig.entry_price:.2f}</code> | SL: <code>{sig.stop_loss:.2f}</code>\n"
                            f"Natija: -1.0R (Risk qat'iy nazorat qilindi)."
                        ),
                    })
                    continue

                # Check TP2 (Asosiy maqsad urilganda signal muvaffaqiyatli yopiladi)
                if current_price <= sig.take_profit_2:
                    sig.tp2_hit = True
                    sig.closed = True
                    sig.close_reason = "TP2"
                    sig.close_price = current_price
                    r_gain = abs(sig.entry_price - sig.take_profit_2) / risk
                    sig.profit_r = r_gain
                    self.closed_signals.append(sig)
                    alerts.append({
                        "type": "TP2_HIT",
                        "signal": sig,
                        "message": (
                            f"🎯🎯 <b>MUVAFFAQIYAT! TP2 TO'LIQ URILDI:</b> #{sig.symbol}\n"
                            f"Yo'nalish: <b>SELL</b> | Narx: <code>{current_price:.2f}</code>\n"
                            f"Natija: <b>+{r_gain:.1f}R (+{pips:.0f} pips) SOF FOYDA!</b>\n"
                            f"Savdo to'liq yakunlandi va yopildi. Tabriklaymiz! 💰"
                        ),
                    })
                    continue

                # Check TP1
                if current_price <= sig.take_profit_1 and not sig.tp1_hit:
                    sig.tp1_hit = True
                    alerts.append({
                        "type": "TP1_HIT",
                        "signal": sig,
                        "message": (
                            f"⚡ <b>TP1 URILDI:</b> #{sig.symbol}\n"
                            f"Yo'nalish: <b>SELL</b> | Narx: <code>{current_price:.2f}</code> (+{pips:.0f} pips)\n"
                            f"🔔 <b>MUHIM AMAL:</b>\n"
                            f"1. Stop-Lossni Kirish narxiga (Breakeven / 0 ga) suring!\n"
                            f"2. Foydaning 50% qismini fiksatsiya qiling."
                        ),
                    })

            remaining_signals.append(sig)

        self.active_signals = remaining_signals
        if alerts:
            self._save_state()

        return alerts

    def get_performance_summary(self) -> Dict[str, Any]:
        """Calculate historical win rate and profit statistics."""
        total = len(self.closed_signals)
        if total == 0:
            return {
                "total_signals": 0,
                "win_rate": 0.0,
                "total_r": 0.0,
                "tp_count": 0,
                "sl_count": 0,
            }

        tp_count = sum(1 for s in self.closed_signals if s.close_reason in ["TP1", "TP2", "TP3"])
        sl_count = sum(1 for s in self.closed_signals if s.close_reason == "SL")
        total_r = sum(s.profit_r for s in self.closed_signals)
        win_rate = (tp_count / total) * 100.0

        return {
            "total_signals": total,
            "win_rate": win_rate,
            "total_r": total_r,
            "tp_count": tp_count,
            "sl_count": sl_count,
        }
