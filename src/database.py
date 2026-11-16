"""
Cyber Trade - Lightweight SQLite Database Engine
=================================================
Embedded zero-dependency persistence layer (Python built-in sqlite3).
Zero RAM overhead (< 1MB), no external database server needed.

Persists:
1. Registered Users & Subscribers (Telegram chat IDs survive restarts)
2. Historical & Active Signals (Full audit trail and analytics)
3. Bot Settings (Persisted active mode, e.g. aggressive/standard)
"""

import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
try:
    from loguru import logger
except ImportError:
    from src.logger import logger

DB_PATH = Path("data/cyber_trade.db")


class Database:
    """Thread-safe SQLite helper for Cyber Trade."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_tables()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_tables(self):
        """Create necessary tables if they do not exist."""
        with self._get_conn() as conn:
            cursor = conn.cursor()

            # 1. Users / Subscribers Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    chat_id TEXT PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active INTEGER DEFAULT 1
                )
            """)

            # 2. Signals Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    take_profit_1 REAL NOT NULL,
                    take_profit_2 REAL NOT NULL,
                    take_profit_3 REAL,
                    status TEXT DEFAULT 'ACTIVE',
                    close_reason TEXT,
                    close_price REAL,
                    profit_r REAL DEFAULT 0.0,
                    highest_pips REAL DEFAULT 0.0,
                    ai_confidence REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    closed_at TIMESTAMP
                )
            """)

            # 3. Settings Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 4. AI Self-Learning Memory Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS learning_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id TEXT,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    net_r REAL DEFAULT 0.0,
                    pips REAL DEFAULT 0.0,
                    pattern_key TEXT,
                    loss_reason TEXT,
                    lesson_learned TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 5. Pattern Weights & Repetition Penalties Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pattern_weights (
                    pattern_key TEXT PRIMARY KEY,
                    wins INTEGER DEFAULT 0,
                    losses INTEGER DEFAULT 0,
                    penalty REAL DEFAULT 0.0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            logger.info("SQLite database tables verified/initialized.")

    # -------------------------------------------------------------------------
    # User Management
    # -------------------------------------------------------------------------
    def register_user(self, chat_id: str, username: str = "", first_name: str = "") -> bool:
        """Register or update a Telegram user."""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO users (chat_id, username, first_name, is_active)
                    VALUES (?, ?, ?, 1)
                    ON CONFLICT(chat_id) DO UPDATE SET
                        username = excluded.username,
                        first_name = excluded.first_name,
                        is_active = 1
                """, (str(chat_id), username or "", first_name or ""))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error registering user in DB: {e}")
            return False

    def get_all_subscribers(self) -> List[str]:
        """Get all active subscriber chat IDs."""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT chat_id FROM users WHERE is_active = 1")
                return [row["chat_id"] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting subscribers: {e}")
            return []

    # -------------------------------------------------------------------------
    # Settings Management
    # -------------------------------------------------------------------------
    def get_setting(self, key: str, default: str = "") -> str:
        """Get a setting value by key."""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
                row = cursor.fetchone()
                return row["value"] if row else default
        except Exception:
            return default

    def set_setting(self, key: str, value: str):
        """Set a setting value by key."""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO settings (key, value, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = CURRENT_TIMESTAMP
                """, (key, str(value)))
                conn.commit()
        except Exception as e:
            logger.error(f"Error saving setting {key}: {e}")

    # -------------------------------------------------------------------------
    # Historical Analytics
    # -------------------------------------------------------------------------
    def log_signal(self, sig) -> bool:
        """Save a new signal to the database."""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO signals (
                        id, symbol, direction, entry_price, stop_loss,
                        take_profit_1, take_profit_2, take_profit_3,
                        status, ai_confidence, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, CURRENT_TIMESTAMP)
                """, (
                    getattr(sig, "id", f"{sig.symbol}_{datetime.now().timestamp()}"),
                    sig.symbol,
                    sig.direction,
                    sig.entry_price,
                    sig.stop_loss,
                    sig.take_profit_1,
                    sig.take_profit_2,
                    getattr(sig, "take_profit_3", 0.0),
                    getattr(sig, "ai_confidence", 0.0),
                ))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error logging signal to DB: {e}")
            return False

    def close_signal(self, sig_id: str, close_reason: str, close_price: float, profit_r: float, highest_pips: float):
        """Mark a signal closed with final performance metrics."""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE signals SET
                        status = 'CLOSED',
                        close_reason = ?,
                        close_price = ?,
                        profit_r = ?,
                        highest_pips = ?,
                        closed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (close_reason, close_price, profit_r, highest_pips, sig_id))
                conn.commit()
        except Exception as e:
            logger.error(f"Error closing signal in DB: {e}")

    def get_stats_summary(self) -> Dict[str, Any]:
        """Calculate overall win rate and PnL from SQLite signals history."""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) as total FROM signals WHERE status = 'CLOSED'")
                total = cursor.fetchone()["total"]

                if total == 0:
                    return {"total_signals": 0, "win_rate": 0.0, "total_r": 0.0, "tp_count": 0, "sl_count": 0}

                cursor.execute("SELECT COUNT(*) as wins FROM signals WHERE status = 'CLOSED' AND profit_r > 0")
                wins = cursor.fetchone()["wins"]

                cursor.execute("SELECT COUNT(*) as tps FROM signals WHERE close_reason LIKE '%TP%'")
                tp_count = cursor.fetchone()["tps"]

                cursor.execute("SELECT COUNT(*) as sls FROM signals WHERE close_reason = 'SL'")
                sl_count = cursor.fetchone()["sls"]

                cursor.execute("SELECT SUM(profit_r) as total_r FROM signals WHERE status = 'CLOSED'")
                r_sum = cursor.fetchone()["total_r"] or 0.0

                win_rate = (wins / total) * 100.0 if total > 0 else 0.0
                return {
                    "total_signals": total,
                    "win_rate": win_rate,
                    "total_r": r_sum,
                    "tp_count": tp_count,
                    "sl_count": sl_count,
                }
        except Exception as e:
            logger.error(f"Error getting DB stats summary: {e}")
            return {"total_signals": 0, "win_rate": 0.0, "total_r": 0.0, "tp_count": 0, "sl_count": 0}

    # -------------------------------------------------------------------------
    # AI Self-Learning Memory & Pattern Feedback
    # -------------------------------------------------------------------------
    def record_learned_lesson(
        self,
        signal_id: str,
        symbol: str,
        direction: str,
        outcome: str,
        net_r: float,
        pips: float,
        pattern_key: str,
        loss_reason: str,
        lesson_learned: str,
    ) -> bool:
        """Store an analyzed trade post-mortem and self-learned lesson."""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO learning_memory (
                        signal_id, symbol, direction, outcome, net_r, pips,
                        pattern_key, loss_reason, lesson_learned
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    signal_id, symbol, direction, outcome, net_r, pips,
                    pattern_key, loss_reason, lesson_learned
                ))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error recording learned lesson in DB: {e}")
            return False

    def update_pattern_weight(self, pattern_key: str, is_win: bool, penalty_delta: float):
        """Reinforce winning patterns or penalize recurring failure patterns."""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO pattern_weights (pattern_key, wins, losses, penalty, updated_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(pattern_key) DO UPDATE SET
                        wins = wins + ?,
                        losses = losses + ?,
                        penalty = MAX(0.0, MIN(0.25, penalty + ?)),
                        updated_at = CURRENT_TIMESTAMP
                """, (
                    pattern_key,
                    1 if is_win else 0,
                    0 if is_win else 1,
                    max(0.0, penalty_delta),
                    1 if is_win else 0,
                    0 if is_win else 1,
                    penalty_delta,
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"Error updating pattern weight in DB: {e}")

    def get_pattern_penalty(self, pattern_key: str) -> float:
        """Get accumulated confidence penalty for a recurring high-risk pattern."""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT penalty FROM pattern_weights WHERE pattern_key = ?", (pattern_key,))
                row = cursor.fetchone()
                return float(row["penalty"]) if row else 0.0
        except Exception:
            return 0.0

    def get_recent_lessons(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Fetch latest learned trade post-mortems for AI context and user reports."""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, signal_id, symbol, direction, outcome, net_r, pips,
                           pattern_key, loss_reason, lesson_learned, created_at
                    FROM learning_memory
                    ORDER BY id DESC LIMIT ?
                """, (limit,))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error fetching recent lessons: {e}")
            return []

    def get_learning_stats(self) -> Dict[str, Any]:
        """Get summary metrics on self-learning database."""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) as total FROM learning_memory")
                total_lessons = cursor.fetchone()["total"]

                cursor.execute("SELECT COUNT(*) as penalized FROM pattern_weights WHERE penalty > 0")
                penalized_patterns = cursor.fetchone()["penalized"]

                # Rolling stats on last 15 closed signals
                cursor.execute("""
                    SELECT profit_r, close_reason
                    FROM signals
                    WHERE status = 'CLOSED' AND close_reason != 'LIMIT_EXPIRED'
                    ORDER BY closed_at DESC LIMIT 15
                """)
                recent_trades = cursor.fetchall()

                if not recent_trades:
                    return {
                        "total_lessons": total_lessons,
                        "penalized_patterns": penalized_patterns,
                        "rolling_trades": 0,
                        "rolling_win_rate": 0.0,
                        "loss_streak": 0,
                    }

                total_recent = len(recent_trades)
                wins_recent = sum(1 for t in recent_trades if t["profit_r"] > 0)
                rolling_wr = (wins_recent / total_recent) * 100.0 if total_recent > 0 else 0.0

                # Count current consecutive loss streak
                loss_streak = 0
                for t in recent_trades:
                    if t["profit_r"] <= 0:
                        loss_streak += 1
                    else:
                        break

                return {
                    "total_lessons": total_lessons,
                    "penalized_patterns": penalized_patterns,
                    "rolling_trades": total_recent,
                    "rolling_win_rate": rolling_wr,
                    "loss_streak": loss_streak,
                }
        except Exception as e:
            logger.error(f"Error getting learning stats: {e}")
            return {
                "total_lessons": 0,
                "penalized_patterns": 0,
                "rolling_trades": 0,
                "rolling_win_rate": 0.0,
                "loss_streak": 0,
            }


# Global singleton instance
db = Database()
