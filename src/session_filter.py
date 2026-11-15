"""
Cyber Trade - Trading Session Filter
====================================
Filter signals based on global market sessions, optimal liquidity hours,
and prevent trades during wide-spread rollover and weekend market closes.

Timezone: Asia/Tashkent (GMT+5) and UTC.
Optimized specifically for Signal Broadcasting (NOT auto-trading).
"""

from datetime import datetime, time, timedelta, timezone
from typing import Tuple, Dict, Optional, Any
from dataclasses import dataclass
from enum import Enum
from loguru import logger
import pytz


class TradingSession(Enum):
    """Market trading sessions."""
    SYDNEY = "sydney"
    TOKYO = "tokyo"
    LONDON = "london"
    NEW_YORK = "new_york"
    OVERLAP_TOKYO_LONDON = "tokyo_london_overlap"
    OVERLAP_LONDON_NY = "london_ny_overlap"
    OFF_HOURS = "off_hours"


@dataclass
class SessionConfig:
    """Session configuration for signal generation."""
    name: str
    start_hour: int      # Tashkent time (GMT+5)
    start_minute: int
    end_hour: int        # Tashkent time (GMT+5)
    end_minute: int
    volatility: str      # "low", "medium", "high", "extreme"
    allow_signals: bool
    quality_score: int   # 0 to 100 liquidity / reliability rating


class SessionFilter:
    """
    Session filter and market schedule sentinel.
    Controls whether market conditions and sessions are favorable for signals.
    """

    def __init__(
        self,
        timezone_str: str = "Asia/Tashkent",
    ):
        self.tz = pytz.timezone(timezone_str)

        # Standard trading sessions in Tashkent Time (GMT+5)
        self.sessions = {
            # London - NY Overlap (The Golden Hours for XAUUSD & Markets)
            TradingSession.OVERLAP_LONDON_NY: SessionConfig(
                name="London - Nyu-York Kesishuvi (Oltin Davr)",
                start_hour=18, start_minute=0,
                end_hour=22, end_minute=0,
                volatility="extreme",
                allow_signals=True,
                quality_score=95,
            ),
            # Tokyo - London Overlap
            TradingSession.OVERLAP_TOKYO_LONDON: SessionConfig(
                name="Tokio - London Kesishuvi",
                start_hour=13, start_minute=0,
                end_hour=14, end_minute=0,
                volatility="high",
                allow_signals=True,
                quality_score=80,
            ),
            # London Session
            TradingSession.LONDON: SessionConfig(
                name="London (Yevropa)",
                start_hour=13, start_minute=0,
                end_hour=22, end_minute=0,
                volatility="high",
                allow_signals=True,
                quality_score=90,
            ),
            # New York Session
            TradingSession.NEW_YORK: SessionConfig(
                name="Nyu-York (AQSH)",
                start_hour=18, start_minute=0,
                end_hour=3, end_minute=0,
                volatility="extreme",
                allow_signals=True,
                quality_score=90,
            ),
            # Tokyo Session
            TradingSession.TOKYO: SessionConfig(
                name="Osiyo / Tokio",
                start_hour=5, start_minute=0,
                end_hour=14, end_minute=0,
                volatility="medium",
                allow_signals=True,
                quality_score=65,
            ),
            # Sydney Session
            TradingSession.SYDNEY: SessionConfig(
                name="Sidney (Tinch okeani)",
                start_hour=2, start_minute=0,
                end_hour=11, end_minute=0,
                volatility="low",
                allow_signals=True,
                quality_score=50,
            ),
        }

        # Danger zones (Tashkent Time GMT+5): Wide spread, rollover, bank clearing
        self.danger_zones = [
            # Daily Rollover (03:00 - 04:15 Tashkent / 22:00 - 23:15 UTC)
            {"name": "Bank Rollover", "start": (3, 0), "end": (4, 15), "reason": "Banklararo kliring va spred kengayishi davri"},
            # Extreme Low Liquidity dead zone (04:15 - 05:00 Tashkent)
            {"name": "Dead Zone", "start": (4, 15), "end": (5, 0), "reason": "Juda past likvidlik va manipulyatsiya xavfi"},
        ]

    def get_current_time_tashkent(self) -> datetime:
        """Get current local time in Tashkent (GMT+5)."""
        return datetime.now(self.tz)

    def is_crypto_symbol(self, symbol: str) -> bool:
        """Check if symbol is 24/7 crypto."""
        sym = symbol.upper()
        return any(c in sym for c in ["BTC", "ETH", "SOL", "USDT", "BNB", "XRP"])

    def is_weekend(self) -> bool:
        """
        Check if traditional market (Gold / Forex) is closed for the weekend.
        Global Market Close: Friday 22:00 UTC (Saturday 03:00 Tashkent).
        Global Market Open: Sunday 22:00 UTC (Monday 03:00 Tashkent).
        """
        now_utc = datetime.now(timezone.utc)
        weekday = now_utc.weekday()
        # Friday after 22:00 UTC
        if weekday == 4 and now_utc.hour >= 22:
            return True
        # Saturday all day (UTC)
        if weekday == 5:
            return True
        # Sunday before 22:00 UTC
        if weekday == 6 and now_utc.hour < 22:
            return True
        return False

    def is_friday_close(self) -> bool:
        """Check if approaching Friday market close (Friday 21:00 UTC / Saturday 02:00 Tashkent)."""
        now_utc = datetime.now(timezone.utc)
        if now_utc.weekday() == 4 and now_utc.hour >= 21:
            return True
        return False

    def is_danger_zone(self) -> Tuple[bool, str]:
        """Check if current Tashkent time falls into high-spread rollover/dead zones."""
        now = self.get_current_time_tashkent()
        hour = now.hour
        minute = now.minute
        current_minutes = hour * 60 + minute

        for zone in self.danger_zones:
            start_min = zone["start"][0] * 60 + zone["start"][1]
            end_min = zone["end"][0] * 60 + zone["end"][1]

            if start_min <= current_minutes < end_min:
                return True, zone["reason"]

        return False, ""

    def get_current_session(self) -> Tuple[TradingSession, SessionConfig]:
        """
        Get the current trading session in Tashkent time.
        Priority: London-NY Overlap > Tokyo-London Overlap > London > NY > Tokyo > Sydney > Off Hours.
        """
        if self.is_weekend():
            return TradingSession.OFF_HOURS, SessionConfig(
                name="Dam olish kuni (Bozor yopiq)",
                start_hour=0, start_minute=0,
                end_hour=23, end_minute=59,
                volatility="none",
                allow_signals=False,
                quality_score=0,
            )

        now = self.get_current_time_tashkent()
        hour = now.hour
        minute = now.minute
        current_minutes = hour * 60 + minute

        # 1. Check London - NY Overlap (18:00 - 22:00 Tashkent)
        if 18 * 60 <= current_minutes < 22 * 60:
            return TradingSession.OVERLAP_LONDON_NY, self.sessions[TradingSession.OVERLAP_LONDON_NY]

        # 2. Check Tokyo - London Overlap (13:00 - 14:00 Tashkent)
        if 13 * 60 <= current_minutes < 14 * 60:
            return TradingSession.OVERLAP_TOKYO_LONDON, self.sessions[TradingSession.OVERLAP_TOKYO_LONDON]

        # 3. Check London Session (13:00 - 22:00 Tashkent)
        if 13 * 60 <= current_minutes < 22 * 60:
            return TradingSession.LONDON, self.sessions[TradingSession.LONDON]

        # 4. Check New York Session (18:00 - 03:00 Tashkent, crosses midnight)
        if current_minutes >= 18 * 60 or current_minutes < 3 * 60:
            return TradingSession.NEW_YORK, self.sessions[TradingSession.NEW_YORK]

        # 5. Check Tokyo Session (05:00 - 14:00 Tashkent)
        if 5 * 60 <= current_minutes < 14 * 60:
            return TradingSession.TOKYO, self.sessions[TradingSession.TOKYO]

        # 6. Check Sydney Session (02:00 - 11:00 Tashkent)
        if 2 * 60 <= current_minutes < 11 * 60:
            return TradingSession.SYDNEY, self.sessions[TradingSession.SYDNEY]

        # Off hours / Quiet night
        return TradingSession.OFF_HOURS, SessionConfig(
            name="Tinch Tungi Soatlar (Osiyo arafasi)",
            start_hour=3, start_minute=0,
            end_hour=5, end_minute=0,
            volatility="low",
            allow_signals=True,
            quality_score=40,
        )

    def is_signal_allowed(self, symbol: str) -> Tuple[bool, str]:
        """
        Primary gatekeeper: Determines whether a signal is allowed for a given symbol right now.

        Returns:
            Tuple of (is_allowed: bool, reason: str)
        """
        is_crypto = self.is_crypto_symbol(symbol)

        # 1. Non-crypto: Traditional weekend check
        if not is_crypto and self.is_weekend():
            return False, "Oltin/Forex birjasi dam olish kunlari sababli yopiq."

        # 2. Non-crypto: Friday close approach
        if not is_crypto and self.is_friday_close():
            return False, "Juma birja yopilishi arafasi — hafta oxiri narx bo'shliqlari (Gap) xavfi tufayli signallar to'xtatildi."

        # 3. Non-crypto: Rollover & dead zones
        if not is_crypto:
            is_danger, danger_reason = self.is_danger_zone()
            if is_danger:
                return False, f"Xavfli vaqt ({danger_reason}) — spred yuqori bo'lgani uchun signal bloklandi."

        # Crypto is 24/7 liquid
        if is_crypto:
            return True, "Kriptovalyuta bozori 24/7 faol."

        # Session validation
        session_enum, session_cfg = self.get_current_session()
        return True, f"Bozor ochiq ({session_cfg.name})"

    def get_status_report(self) -> Dict[str, Any]:
        """Get comprehensive trading session status."""
        now = self.get_current_time_tashkent()
        session, config = self.get_current_session()
        is_danger, danger_reason = self.is_danger_zone()

        return {
            "current_time_tashkent": now.strftime("%Y-%m-%d %H:%M:%S"),
            "day_of_week": now.strftime("%A"),
            "current_session": config.name,
            "volatility": config.volatility,
            "quality_score": config.quality_score,
            "is_weekend": self.is_weekend(),
            "is_friday_close": self.is_friday_close(),
            "is_danger_zone": is_danger,
            "danger_reason": danger_reason,
        }
