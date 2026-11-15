"""
Cyber Trade - Market Sentinel & Broadcaster
============================================
Proactively monitors market conditions and broadcasts updates:
1. High-Impact Economic News Warnings (ForexFactory):
   - Alerts 15-30 minutes before CPI, NFP, FOMC, Fed Rate Decisions, etc.
   - Advises risk control and breakeven adjustments.
2. Market Trading Session Alerts:
   - Announces London Open (13:00 Tashkent), London-NY Overlap (18:00 Tashkent),
     Weekend Birja yopilishi, va Yangi hafta ochilishi.
3. Periodic Market Digest:
   - Every 4-6 hours broadcasts DXY trend, market regime, and open signals summary.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Set, Optional, Dict, Any
from loguru import logger
import pytz

from src.news_agent import NewsSentinel
from src.session_filter import SessionFilter, TradingSession
from src.data_fetcher import UniversalDataFetcher


class MarketSentinel:
    """
    Background market intelligence broadcaster.
    Runs alongside the orchestrator.
    """

    def __init__(
        self,
        telegram_bot,
        session_filter: Optional[SessionFilter] = None,
        news_sentinel: Optional[NewsSentinel] = None,
        data_fetcher: Optional[UniversalDataFetcher] = None,
        signal_tracker = None,
    ):
        self.bot = telegram_bot
        self.session_filter = session_filter or SessionFilter()
        self.news_sentinel = news_sentinel or NewsSentinel()
        self.data_fetcher = data_fetcher or UniversalDataFetcher()
        self.signal_tracker = signal_tracker
        self.tashkent_tz = pytz.timezone("Asia/Tashkent")

        self._alerted_news: Set[str] = set()
        self._last_announced_session: Optional[str] = None
        self._last_digest_hour: int = -1
        self._running = False

    async def check_news_alerts(self):
        """Check for high-impact economic news coming up in 15-30 minutes."""
        try:
            events, is_online, err_msg = await self.news_sentinel.fetch_calendar_events()
            now_utc = datetime.now(timezone.utc)

            # Check if active trades exist during upcoming news
            has_active_trades = bool(self.signal_tracker and self.signal_tracker.active_signals)
            active_symbols = [f"#{s.symbol}" for s in self.signal_tracker.active_signals] if has_active_trades else []

            for ev in events:
                if ev.impact != "High":
                    continue

                diff_minutes = (ev.time_utc - now_utc).total_seconds() / 60.0
                event_key = f"{ev.country}_{ev.title}_{ev.time_utc.strftime('%Y%m%d_%H%M')}"

                # Alert if within 10 to 35 minutes before the event
                if 10.0 <= diff_minutes <= 35.0 and event_key not in self._alerted_news:
                    self._alerted_news.add(event_key)
                    ev_uzb = ev.time_utc.astimezone(self.tashkent_tz).strftime("%H:%M")

                    active_trade_warning = ""
                    if has_active_trades:
                        active_trade_warning = (
                            f"\n⚡ <b>OCHIQ SIGNALLAR DIQQATIGA ({', '.join(active_symbols)}):</b>\n"
                            f"Yangilik oldidan Stop-Lossni Kirish narxiga (0 ga) ko'chiring yoki foydani fiksatsiya qiling!\n"
                        )

                    msg = (
                        f"🚨 <b>DIQQAT: MUHIM IQTISODIY YANGILIK YAQINLASHMOQDA!</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"💥 <b>Voqea:</b> {ev.title} ({ev.country})\n"
                        f"🕒 <b>Chiqish Vaqti:</b> <b>{ev_uzb}</b> (taxminan {int(diff_minutes)} daqiqa qoldi)\n"
                        f"📊 <b>Kutilma (Forecast):</b> <code>{ev.forecast or 'Nomaʼlum'}</code>\n"
                        f"📉 <b>Oldingi ko'rsatkich:</b> <code>{ev.previous or 'Nomaʼlum'}</code>\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━{active_trade_warning}\n"
                        f"⚠️ <b>Tavsiya:</b> Yuqori narx tebranishlari (volatillik) kutilmoqda. "
                        f"Yangilik o'tib olguncha yangi signallar vaqtincha to'xtatildi."
                    )
                    logger.warning(f"Broadcasting High-Impact News Alert: {ev.title} ({ev.country})")
                    await self.bot.broadcast_alert(msg)

        except Exception as e:
            logger.error(f"Error checking news alerts: {e}")

    async def check_session_alerts(self):
        """Check for market session changes and weekend closures."""
        try:
            sess_enum, sess_cfg = self.session_filter.get_current_session()
            current_name = sess_cfg.name
            now_tashkent = datetime.now(self.tashkent_tz)
            now_str = now_tashkent.strftime("%H:%M")

            if self._last_announced_session is None:
                # Initialize without blasting on cold start
                self._last_announced_session = current_name
                return

            if current_name != self._last_announced_session:
                prev_name = self._last_announced_session
                self._last_announced_session = current_name

                # London Open
                if sess_enum == TradingSession.LONDON:
                    msg = (
                        f"🏛️ <b>BOZOR SESSIYASI OCHILDI: LONDON (YEVROPA)</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🕒 Vaqt: <b>{now_str}</b> (Toshkent vaqti)\n"
                        f"🌊 <b>Holat:</b> Yevropa maydonlari ochildi. Oltin (XAUUSD) va valyutalarda hajm oshmoqda.\n"
                        f"🎯 <b>Fokus:</b> Trend yo'nalishi shakllanadigan asosiy soatlar.\n"
                        f"⚡ <i>AI Council A+ setup'larni tahlil qilmoqda...</i>"
                    )
                    await self.bot.broadcast_alert(msg)

                # London - NY Golden Overlap
                elif sess_enum == TradingSession.OVERLAP_LONDON_NY:
                    msg = (
                        f"🚀 <b>ENG FAOL DAVR: LONDON - NYU-YORK OVERLAP (OLTIN DAVR)</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🕒 Vaqt: <b>{now_str}</b> (Toshkent vaqti)\n"
                        f"🔥 <b>Holat:</b> Sutkaning eng yuqori likvidligi va kuchli harakatlari davri!\n"
                        f"🎯 <b>Fokus:</b> XAUUSD (Oltin) va AQSH Dollari (DXY).\n"
                        f"💰 <i>Muvaffaqiyatli va foydali savdolar tilaymiz!</i>"
                    )
                    await self.bot.broadcast_alert(msg)

                # Weekend Close
                elif "Weekend" in current_name and "Weekend" not in prev_name:
                    msg = (
                        f"🔴 <b>HAFTALIK FOREX VA OLTIN BOZORI YOPILDI</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🕒 Vaqt: <b>{now_str}</b> (Toshkent vaqti)\n"
                        f"🏖️ Oltin (XAUUSD) va an'anaviy birjalar Dushanba tongigacha dam oladi.\n"
                        f"🪙 <b>Kriptovalyuta (BTC, ETH, SOL)</b> bozori 24/7 ochiq va signallar faol ishlaydi!"
                    )
                    await self.bot.broadcast_alert(msg)

                # Week Reopen (Monday morning)
                elif "Weekend" in prev_name and "Weekend" not in current_name:
                    msg = (
                        f"🟢 <b>YANGI SAVDO HAFTASI BOSHLANDI!</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🕒 Vaqt: <b>{now_str}</b> (Toshkent vaqti)\n"
                        f"📈 Oltin va jahon moliya birjalari qayta ochildi.\n"
                        f"⚡ Barcha sun'iy intellekt agentlari to'liq quvvat bilan bozor tahlilini boshladi!"
                    )
                    await self.bot.broadcast_alert(msg)

        except Exception as e:
            logger.error(f"Error checking session alerts: {e}")

    async def check_periodic_digest(self):
        """Broadcast market weather digest every 6 hours (e.g., 08:00, 14:00, 20:00)."""
        try:
            now_tashkent = datetime.now(self.tashkent_tz)
            hour = now_tashkent.hour

            # Check if this is a digest hour (e.g. 8, 14, 20) and not yet sent
            digest_hours = [8, 14, 20]
            if hour in digest_hours and hour != self._last_digest_hour:
                self._last_digest_hour = hour
                now_str = now_tashkent.strftime("%H:%M")

                # Fetch BTC and ETH current price
                btc_df = await self.data_fetcher.get_market_data("BTC-USD", "15m")
                eth_df = await self.data_fetcher.get_market_data("ETH-USD", "15m")
                btc_p = float(btc_df["close"][-1]) if btc_df is not None and len(btc_df) > 0 else 0.0
                eth_p = float(eth_df["close"][-1]) if eth_df is not None and len(eth_df) > 0 else 0.0

                is_weekend = self.session_filter.is_weekend()
                gold_status = "🔴 Birja Yopiq (Dam olish)" if is_weekend else "🟢 Jonli Savdoda"

                active_count = len(self.signal_tracker.active_signals) if self.signal_tracker else 0

                msg = (
                    f"🌐 <b>CYBER TRADE — BOZOR OB-HAVOSI (SVODKA)</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🕒 Vaqt: <b>{now_str}</b> (Toshkent vaqti)\n"
                    f"🪙 <b>Bitcoin (BTC):</b> <code>${btc_p:,.2f}</code>\n"
                    f"💎 <b>Ethereum (ETH):</b> <code>${eth_p:,.2f}</code>\n"
                    f"🟡 <b>Oltin (XAUUSD):</b> {gold_status}\n"
                    f"⚡ <b>Aktiv Ochiq Signallar:</b> {active_count} ta\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"<i>Savdo rejimini tekshirish uchun <code>/status</code> buyrug'idan foydalaning.</i>"
                )
                logger.info(f"Broadcasting Periodic Market Digest at {now_str}")
                await self.bot.broadcast_alert(msg)

        except Exception as e:
            logger.error(f"Error checking periodic digest: {e}")

    async def run_sentinel_loop(self):
        """Continuous background loop for news, sessions, and digests."""
        self._running = True
        logger.info("Market Sentinel Broadcaster loop is active...")

        while self._running:
            try:
                # 1. Check high-impact news warnings
                await self.check_news_alerts()

                # 2. Check session transitions
                await self.check_session_alerts()

                # 3. Check periodic market digest
                await self.check_periodic_digest()

                # Sleep 60 seconds before next check
                await asyncio.sleep(60)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in sentinel loop: {e}")
                await asyncio.sleep(30)

    def stop(self):
        """Stop sentinel broadcaster."""
        self._running = False
