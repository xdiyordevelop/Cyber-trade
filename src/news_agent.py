"""
Cyber Trade - News & Economic Calendar Sentinel
================================================
Monitors high-impact macroeconomic events:
- CPI (Inflation)
- NFP (Non-Farm Payrolls)
- FOMC / Fed Interest Rate Decisions
- GDP & PPI

Enforces a 30-minute pre/post-news Danger Window to prevent slippage and false breakouts.
Transparently reports calendar connectivity: if calendar API is offline, it never hides it!
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Tuple
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
    status: str                         # "SAFE", "CAUTION", "DANGER", "CALENDAR_OFFLINE"
    calendar_online: bool = True
    next_event: Optional[EconomicEvent] = None
    time_to_event_minutes: Optional[float] = None
    warning_text: str = ""
    upcoming_events_summary: List[str] = field(default_factory=list)


class NewsSentinel:
    """
    Asynchronous news monitor for Forex, Commodities and Crypto.
    Uses public economic calendar endpoints with full transparency.
    """

    def __init__(self, danger_window_minutes: int = 30):
        self.danger_window = danger_window_minutes
        self._cached_events: List[EconomicEvent] = []
        self._last_fetch_time: Optional[datetime] = None
        self.calendar_online: bool = True
        self.last_fetch_error: Optional[str] = None

    async def fetch_calendar_events(self, force_refresh: bool = False) -> Tuple[List[EconomicEvent], bool, Optional[str]]:
        """
        Fetch calendar events from public ForexFactory calendar API.
        Returns (events_list, is_online, error_message).
        """
        now = datetime.now(timezone.utc)
        # Cache for 45 minutes to prevent excessive requests
        if not force_refresh and self._last_fetch_time and (now - self._last_fetch_time).total_seconds() < 2700 and self._cached_events:
            return self._cached_events, self.calendar_online, self.last_fetch_error

        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        events = []

        try:
            timeout = aiohttp.ClientTimeout(total=8)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for item in data:
                            impact = item.get("impact", "Low")
                            country = item.get("country", "")
                            # Track major currency events (USD, EUR, GBP)
                            if country in ["USD", "EUR", "GBP"] and impact in ["High", "Medium"]:
                                dt_str = item.get("date")
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
                        self.calendar_online = True
                        self.last_fetch_error = None
                        logger.info(f"Loaded {len(events)} economic calendar events.")
                        return self._cached_events, True, None
                    else:
                        err = f"HTTP {resp.status}"
                        self.calendar_online = False
                        self.last_fetch_error = err
                        logger.warning(f"ForexFactory calendar returned {resp.status}")
        except Exception as e:
            self.calendar_online = False
            self.last_fetch_error = str(e)
            logger.warning(f"Could not connect to economic calendar: {e}")

        # If cache exists from earlier today, use it but flag state
        if self._cached_events:
            return self._cached_events, False, f"Serverga ulanib bo'lmadi ({self.last_fetch_error}), keshdan foydalanilmoqda"

        return [], False, f"Iqtisodiy taqvim serveri bilan aloqa yo'q: {self.last_fetch_error}"

    async def check_news_safety(self, currency: str = "USD") -> NewsStatus:
        """
        Check if we are within the Danger Window of any high-impact event.
        Transparently exposes calendar health.
        """
        events, is_online, err_msg = await self.fetch_calendar_events()
        now = datetime.now(timezone.utc)

        # Calendar offline with no cached data
        if not is_online and not events:
            return NewsStatus(
                is_safe=False,
                status="CALENDAR_OFFLINE",
                calendar_online=False,
                next_event=None,
                time_to_event_minutes=None,
                warning_text=(
                    "⚠️ <b>IQTISODIY TAQVIM NOFAOL:</b> Taqvim serveriga ulanib bo'lmadi. "
                    "Yangiliklar xavfi noma'lum bo'lgani sababli yangi signallarga ehtiyotkorlik bilan yondashing."
                ),
                upcoming_events_summary=[],
            )

        # Filter high impact events for the currency
        high_impact = [
            e for e in events 
            if e.impact == "High" and (currency == "ALL" or e.country == currency)
        ]

        upcoming_summary = []
        for ev in high_impact:
            diff = (ev.time_utc - now).total_seconds() / 60.0
            if 0 < diff <= 180:  # Next 3 hours
                upcoming_summary.append(f"• {ev.country} - {ev.title} ({int(diff)} daqiqadan so'ng)")

        for ev in high_impact:
            diff_minutes = (ev.time_utc - now).total_seconds() / 60.0

            # Danger window: 30 minutes before until 30 minutes after event
            if -self.danger_window <= diff_minutes <= self.danger_window:
                warning = (
                    f"🚨 <b>YANGILIKLAR XAVFI:</b> {ev.country} bo'yicha <b>'{ev.title}'</b> muhim yangiligi "
                    f"({int(abs(diff_minutes))} daqiqa {'qoldi' if diff_minutes > 0 else 'avval chiqdi'}). "
                    f"Spred oshishi va kutilmagan manipulyatsiya xavfi sababli signallar vaqtincha bloklandi!"
                )
                return NewsStatus(
                    is_safe=False,
                    status="DANGER",
                    calendar_online=is_online,
                    next_event=ev,
                    time_to_event_minutes=diff_minutes,
                    warning_text=warning,
                    upcoming_events_summary=upcoming_summary,
                )

            # Caution window: 30 to 60 minutes before
            elif 0 < diff_minutes <= 60:
                warning = (
                    f"ℹ️ <b>DIQQAT:</b> {int(diff_minutes)} daqiqadan so'ng {ev.country} - '{ev.title}' "
                    f"yuqori ta'sirli yangiligi chiqadi. Ochiq pozitsiyalarni ehtiyotkorlik bilan boshqaring!"
                )
                return NewsStatus(
                    is_safe=True,
                    status="CAUTION",
                    calendar_online=is_online,
                    next_event=ev,
                    time_to_event_minutes=diff_minutes,
                    warning_text=warning,
                    upcoming_events_summary=upcoming_summary,
                )

        offline_note = " (⚠️ Taqvim yangilanishi keshdan olinmoqda)" if not is_online else ""
        return NewsStatus(
            is_safe=True,
            status="SAFE",
            calendar_online=is_online,
            next_event=None,
            time_to_event_minutes=None,
            warning_text=f"Bozor iqtisodiy yangiliklar jihatidan tinch{offline_note}.",
            upcoming_events_summary=upcoming_summary,
        )

    def get_forexfactory_schedule(self, limit: int = 6) -> str:
        """
        Format upcoming events exactly like ForexFactory.com calendar table:
        Impact folder, currency, title, exact Tashkent time, Forecast, and Previous values.
        """
        import pytz
        tashkent_tz = pytz.timezone("Asia/Tashkent")
        now = datetime.now(timezone.utc)

        # Filter events from now onwards
        future_events = [
            e for e in self._cached_events
            if (e.time_utc - now).total_seconds() > -900  # from 15m ago onwards
        ]
        future_events.sort(key=lambda x: x.time_utc)

        if not future_events:
            return "<i>Bu hafta uchun rejalashtirilgan yuqori ta'sirli yangiliklar topilmadi.</i>"

        lines = []
        for ev in future_events[:limit]:
            ev_tashkent = ev.time_utc.astimezone(tashkent_tz)
            date_str = ev_tashkent.strftime("%d-%b (%a) %H:%M")
            diff_hours = (ev.time_utc - now).total_seconds() / 3600.0

            time_left = f"{int(diff_hours)} soatdan so'ng" if diff_hours >= 1 else f"{int(diff_hours*60)} daqiqadan so'ng"
            if diff_hours < 0:
                time_left = "Ayni paytda chiqmoqda"

            flag = "🇺🇸" if ev.country == "USD" else ("🇪🇺" if ev.country == "EUR" else ("🇬🇧" if ev.country == "GBP" else "🌐"))
            impact_icon = "🔴" if ev.impact == "High" else "🟠"

            forecast_str = f"Kutilma: <code>{ev.forecast}</code>" if ev.forecast else "Kutilma: <i>—</i>"
            prev_str = f"Oldingi: <code>{ev.previous}</code>" if ev.previous else "Oldingi: <i>—</i>"

            lines.append(
                f"{impact_icon} <b>{flag} {ev.country} — {ev.title}</b>\n"
                f"  🕒 <b>Vaqt:</b> <code>{date_str}</code> ({time_left})\n"
                f"  📊 {forecast_str} | 📉 {prev_str}\n"
            )

        return "\n".join(lines)
