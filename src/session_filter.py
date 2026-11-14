"""
Trading Session Filter
======================
Filter trades based on market sessions and optimal trading hours.
Timezone: WIB (Waktu Indonesia Barat) - GMT+7 for Batam/Jakarta.

Optimal Trading Hours for XAUUSD:
- London-NY Overlap: 20:00 - 00:00 WIB (BEST)
- London Session: 15:00 - 00:00 WIB
- NY Session: 20:00 - 05:00 WIB

Dangerous Zones:
- Rollover/Spread Wide: 04:00 - 06:00 WIB
- Low Liquidity: 00:00 - 04:00 WIB
- Friday Close: After 23:00 WIB Friday
"""

from datetime import datetime, time, timedelta, timezone
from typing import Tuple, Dict, Optional
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
    """Session trading configuration."""
    name: str
    start_hour: int  # WIB
    start_minute: int
    end_hour: int    # WIB
    end_minute: int
    volatility: str  # "low", "medium", "high", "extreme"
    allow_trading: bool
    position_size_multiplier: float


class SessionFilter:
    """
    Trading session filter for optimal trading hours.

    Configured for XAUUSD aggressive trading during London/NY overlap.
    All times in WIB (GMT+7).
    """

    def __init__(
        self,
        timezone: str = "Asia/Tashkent",  # Tashkent (GMT+5)
        aggressive_mode: bool = True,
    ):
        self.tz = pytz.timezone(timezone)
        self.aggressive_mode = aggressive_mode

        # Define trading windows (Tashkent Time GMT+5)
        self.sessions = {
            # Main sessions
            TradingSession.SYDNEY: SessionConfig(
                name="Sidney (Tinch okeani)",
                start_hour=2, start_minute=0,
                end_hour=11, end_minute=0,
                volatility="low",
                allow_trading=True,
                position_size_multiplier=0.5,
            ),
            TradingSession.TOKYO: SessionConfig(
                name="Osiyo / Tokio",
                start_hour=5, start_minute=0,
                end_hour=14, end_minute=0,
                volatility="medium",
                allow_trading=True,
                position_size_multiplier=0.7,
            ),
            TradingSession.LONDON: SessionConfig(
                name="London (Yevropa)",
                start_hour=13, start_minute=0,
                end_hour=22, end_minute=0,
                volatility="high",
                allow_trading=True,
                position_size_multiplier=1.0,
            ),
            TradingSession.NEW_YORK: SessionConfig(
                name="Nyu-York (AQSH)",
                start_hour=18, start_minute=0,
                end_hour=23, end_minute=59,
                volatility="extreme",
                allow_trading=True,
                position_size_multiplier=1.0,
            ),
            # Overlap sessions (BEST TIMES)
            TradingSession.OVERLAP_TOKYO_LONDON: SessionConfig(
                name="Osiyo - London Kesishuvi",
                start_hour=13, start_minute=0,
                end_hour=14, end_minute=0,
                volatility="high",
                allow_trading=True,
                position_size_multiplier=0.8,
            ),
            TradingSession.OVERLAP_LONDON_NY: SessionConfig(
                name="London - Nyu-York Overlap (Oltin Davr)",
                start_hour=18, start_minute=0,
                end_hour=22, end_minute=0,
                volatility="extreme",
                allow_trading=True,
                position_size_multiplier=1.2,
            ),
        }

        # Danger zones (WIB)
        self.danger_zones = [
            # Rollover - spread extremely wide
            {"name": "Rollover", "start": (4, 0), "end": (6, 0), "reason": "Spread melebar saat rollover"},
            # Low liquidity
            {"name": "Dead Zone", "start": (0, 0), "end": (4, 0), "reason": "Likuiditas rendah, spread tinggi"},
        ]

        # High impact news times to avoid (typical release times in WIB)
        self.news_blackout_times = [
            # NFP - First Friday of month
            {"event": "NFP", "hour": 19, "minute": 30, "buffer_before": 15, "buffer_after": 30},
            # Fed Interest Rate
            {"event": "FOMC", "hour": 1, "minute": 0, "buffer_before": 15, "buffer_after": 45},
            # US CPI
            {"event": "CPI", "hour": 19, "minute": 30, "buffer_before": 15, "buffer_after": 30},
        ]

    def get_current_time_wib(self) -> datetime:
        """Get current time in WIB."""
        return datetime.now(self.tz)

    def get_current_session(self) -> Tuple[TradingSession, SessionConfig]:
        """
        Get the current trading session.

        Returns highest priority session if multiple overlap.
        Priority: Overlap > London/NY > Tokyo > Sydney > Off Hours
        """
        now = self.get_current_time_wib()

        # Check weekend first (Saturday/Sunday market closed)
        if self.is_weekend():
            return TradingSession.OFF_HOURS, SessionConfig(
                name="Weekend (Market Closed)",
                start_hour=0, start_minute=0,
                end_hour=23, end_minute=59,
                volatility="none",
                allow_trading=False,
                position_size_multiplier=0.0,
            )

        hour = now.hour
        minute = now.minute
        current_time = hour * 60 + minute

        # Check overlaps first (highest priority)
        if 20 * 60 <= current_time <= 24 * 60:  # 20:00 - 00:00
            return TradingSession.OVERLAP_LONDON_NY, self.sessions[TradingSession.OVERLAP_LONDON_NY]

        if 15 * 60 <= current_time <= 16 * 60:  # 15:00 - 16:00
            return TradingSession.OVERLAP_TOKYO_LONDON, self.sessions[TradingSession.OVERLAP_TOKYO_LONDON]

        # Check main sessions
        for session, config in self.sessions.items():
            if session in [TradingSession.OVERLAP_LONDON_NY, TradingSession.OVERLAP_TOKYO_LONDON]:
                continue

            start = config.start_hour * 60 + config.start_minute
            end = config.end_hour * 60 + config.end_minute

            if start <= current_time <= end:
                return session, config

        # Off hours
        return TradingSession.OFF_HOURS, SessionConfig(
            name="Off Hours",
            start_hour=0, start_minute=0,
            end_hour=0, end_minute=0,
            volatility="low",
            allow_trading=False,
            position_size_multiplier=0.0,
        )

    def is_danger_zone(self) -> Tuple[bool, str]:
        """Check if current time is in a danger zone."""
        now = self.get_current_time_wib()
        hour = now.hour
        minute = now.minute
        current_time = hour * 60 + minute

        for zone in self.danger_zones:
            start = zone["start"][0] * 60 + zone["start"][1]
            end = zone["end"][0] * 60 + zone["end"][1]

            if start <= current_time < end:
                return True, zone["reason"]

        return False, ""

    def is_friday_close(self) -> bool:
        """Check if approaching Friday market close (Saturday 02:30 Tashkent / 21:30 UTC)."""
        now_utc = datetime.now(timezone.utc)
        # Friday after 21:30 UTC (approaching 22:00 close)
        if now_utc.weekday() == 4 and (now_utc.hour > 21 or (now_utc.hour == 21 and now_utc.minute >= 30)):
            return True
        return False

    def is_weekend(self) -> bool:
        """
        Check if traditional market (Gold / Forex) is closed for the weekend.
        Global Market Close: Friday 22:00 UTC (17:00 EST / Shanba 03:00 Toshkent).
        Global Market Open: Sunday 22:00 UTC (17:00 EST / Dushanba 03:00 Toshkent).
        """
        now_utc = datetime.now(timezone.utc)
        weekday = now_utc.weekday()
        # Friday after 22:00 UTC
        if weekday == 4 and now_utc.hour >= 22:
            return True
        # Saturday all day
        if weekday == 5:
            return True
        # Sunday before 22:00 UTC
        if weekday == 6 and now_utc.hour < 22:
            return True
        return False

    def can_trade(self) -> Tuple[bool, str, float]:
        """
        Check if trading is allowed right now.

        Returns:
            Tuple of (can_trade, reason, position_multiplier)
        """
        now = self.get_current_time_wib()

        # Check weekend
        if self.is_weekend():
            return False, "Market tutup (weekend)", 0.0

        # Check Friday close
        if self.is_friday_close():
            return False, "Mendekati penutupan Jumat - hindari gap weekend", 0.0

        # Check danger zones
        is_danger, danger_reason = self.is_danger_zone()
        if is_danger:
            return False, f"Zona bahaya: {danger_reason}", 0.0

        # Get current session
        session, config = self.get_current_session()

        if not config.allow_trading:
            return False, f"Trading tidak diizinkan saat {config.name}", 0.0

        # In aggressive mode, allow medium+ volatility + Sydney (proven profitable)
        if self.aggressive_mode:
            # Sydney session is ALLOWED - backtest shows 62% WR, $5,934 profit
            if session == TradingSession.SYDNEY:
                return True, f"Trading OK - {config.name} (SAFE MODE: 0.5x lot)", config.position_size_multiplier
            # Only block low volatility sessions
            if config.volatility not in ["medium", "high", "extreme"]:
                return False, f"Mode agresif: tunggu sesi {config.name} (volatilitas {config.volatility})", config.position_size_multiplier

        return True, f"Trading OK - {config.name} ({config.volatility} volatility)", config.position_size_multiplier

    def get_next_trading_window(self) -> Dict:
        """Get when the next optimal trading window starts."""
        now = self.get_current_time_wib()
        current_hour = now.hour

        # Find next London-NY overlap
        if current_hour < 20:
            # Today at 20:00
            next_window = now.replace(hour=20, minute=0, second=0, microsecond=0)
            hours_until = 20 - current_hour
        else:
            # Tomorrow at 20:00
            next_window = (now + timedelta(days=1)).replace(hour=20, minute=0, second=0, microsecond=0)
            hours_until = 24 - current_hour + 20

        return {
            "next_window": next_window.strftime("%Y-%m-%d %H:%M WIB"),
            "hours_until": hours_until,
            "session": "London-NY Overlap",
            "is_weekend": self.is_weekend(),
        }

    def get_status_report(self) -> Dict:
        """Get comprehensive trading session status."""
        now = self.get_current_time_wib()
        session, config = self.get_current_session()
        can_trade, reason, multiplier = self.can_trade()
        is_danger, danger_reason = self.is_danger_zone()

        return {
            "current_time": now.strftime("%Y-%m-%d %H:%M:%S WIB"),
            "day_of_week": now.strftime("%A"),
            "current_session": config.name,
            "volatility": config.volatility,
            "can_trade": can_trade,
            "reason": reason,
            "position_multiplier": multiplier,
            "is_danger_zone": is_danger,
            "danger_reason": danger_reason,
            "is_friday_close": self.is_friday_close(),
            "is_weekend": self.is_weekend(),
            "next_window": self.get_next_trading_window(),
        }


# Convenience function
def create_wib_session_filter(aggressive: bool = True) -> SessionFilter:
    """Create session filter for WIB timezone."""
    return SessionFilter(
        timezone="Asia/Jakarta",
        aggressive_mode=aggressive,
    )


if __name__ == "__main__":
    # Test session filter
    sf = create_wib_session_filter(aggressive=True)

    print("\n" + "=" * 60)
    print("TRADING SESSION STATUS")
    print("=" * 60)

    status = sf.get_status_report()
    for key, value in status.items():
        print(f"{key}: {value}")

    print("\n" + "=" * 60)
    can_trade, reason, multiplier = sf.can_trade()
    print(f"Can Trade: {can_trade}")
    print(f"Reason: {reason}")
    print(f"Position Multiplier: {multiplier}")
