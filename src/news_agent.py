"""
Cyber Trade - News & Economic Calendar Sentinel
================================================
Monitors high-impact macroeconomic events:
- CPI (Inflation)
- NFP (Non-Farm Payrolls)
- FOMC / Fed Interest Rate Decisions
- GDP & PPI

Enforces a 30-minute pre/post-news Danger Window to prevent slippage and false breakouts.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict
import aiohttp
from loguru import logger


@dataclass
class EconomicEvent:
    title: str
    country: str
    impact: str         # "High", "Medium", "Low"
    time_utc: datetime
    forecast: str = ""
    previous: str = ""


@dataclass
class NewsStatus:
    is_safe: bool
    status: str         # "SAFE", "CAUTION", "DANGER"
    next_event: Optional[EconomicEvent] = None
    time_to_event_minutes: Optional[float] = None
    warning_text: str = ""


class NewsSentinel:
    """
    Asynchronous news monitor for Forex and Commodities.
    Uses free public economic calendar endpoints.
    """

    def __init__(self, danger_window_minutes: int = 30):
        self.danger_window = danger_window_minutes
        self._cached_events: List[EconomicEvent] = []
        self._last_fetch_time: Optional[datetime] = None

    async def fetch_calendar_events(self) -> List[EconomicEvent]:
        """
        Fetch calendar events from public ForexFactory calendar API.
        """
        now = datetime.now(timezone.utc)
        # Cache for 1 hour to prevent excessive requests
        if self._last_fetch_time and (now - self._last_fetch_time).total_seconds() < 3600 and self._cached_events:
            return self._cached_events

        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        events = []

        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for item in data:
                            impact = item.get("impact", "Low")
                            country = item.get("country", "")
                            # We care most about USD, EUR, GBP events
                            if country in ["USD", "EUR", "GBP"] and impact in ["High", "Medium"]:
                                dt_str = item.get("date")  # e.g. "2026-11-14T08:30:00-05:00"
                                try:
                                    dt = datetime.fromisoformat(dt_str)
                                    events.append(EconomicEvent(
                                        title=item.get("title", ""),
                                        country=country,
                                        impact=impact,
                                        time_utc=dt.astimezone(timezone.utc),
                                        forecast=item.get("forecast", ""),
                                        previous=item.get("previous", ""),
                                    ))
                                except Exception:
                                    continue
                        self._cached_events = events
                        self._last_fetch_time = now
                        logger.info(f"Loaded {len(events)} economic calendar events.")
        except Exception as e:
            logger.warning(f"Could not fetch live calendar ({e}). Using safety fallback.")

        return self._cached_events

    async def check_news_safety(self, currency: str = "USD") -> NewsStatus:
        """
        Check if we are within the Danger Window of any high-impact event.
        """
        events = await self.fetch_calendar_events()
        now = datetime.now(timezone.utc)

        # Filter high impact events
        high_impact = [
            e for e in events 
            if e.impact == "High" and (currency == "ALL" or e.country == currency)
        ]

        for ev in high_impact:
            diff_minutes = (ev.time_utc - now).total_seconds() / 60.0

            # Danger window: 30 minutes before until 30 minutes after event
            if -self.danger_window <= diff_minutes <= self.danger_window:
                warning = (
                    f"⚠️ XAVFLI ZONA: {ev.country} bo'yicha '{ev.title}' yangiligi "
                    f"({int(abs(diff_minutes))} daqiqa {'qoldi' if diff_minutes > 0 else 'avval chiqdi'}). "
                    f"Spred va manipulyatsiya xavfi yuqori!"
                )
                return NewsStatus(
                    is_safe=False,
                    status="DANGER",
                    next_event=ev,
                    time_to_event_minutes=diff_minutes,
                    warning_text=warning,
                )

            # Caution window: 30 to 60 minutes before
            elif 0 < diff_minutes <= 60:
                warning = f"ℹ️ DIQQAT: {diff_minutes:.0f} daqiqadan so'ng {ev.country} - '{ev.title}' yangiligi kutilmoqda."
                return NewsStatus(
                    is_safe=True,
                    status="CAUTION",
                    next_event=ev,
                    time_to_event_minutes=diff_minutes,
                    warning_text=warning,
                )

        return NewsStatus(
            is_safe=True,
            status="SAFE",
            next_event=None,
            time_to_event_minutes=None,
            warning_text="Bozor iqtisodiy yangiliklar jihatidan tinch.",
        )
