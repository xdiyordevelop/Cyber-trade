"""
Cyber Trade - Master Orchestrator
=================================
Runs the 24/7 Multi-Agent Market Analysis & Signal Broadcasting System.
- Scans XAUUSD, BTC, ETH, and Macro DXY
- Coordinates AI Council (SMC + Features + ML + HMM + News + Macro)
- Broadcasts high-confluence A+ signals with chart snapshots
- Live signal trailing (TP1 hit -> Move SL to BE alert)
- Telegram AI Chat & command handling
"""

import asyncio
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from loguru import logger

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from src.config import get_config
from src.data_fetcher import UniversalDataFetcher
from src.signal_engine import SignalEngine
from src.signal_tracker import SignalTracker
from src.ai_chat import MarketAIAssistant
from src.telegram_bot import CyberTelegramBot
from src.market_sentinel import MarketSentinel
from src.database import db

# Configure logging
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>",
    level="INFO",
)
logger.add(
    "logs/cyber_trade_{time:YYYY-MM-DD}.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
    rotation="1 day",
    retention="14 days",
    level="DEBUG",
    encoding="utf-8",
)


class CyberTradeOrchestrator:
    """
    Main system orchestrator.
    """

    def __init__(self):
        self.config = get_config()
        self.data_fetcher = UniversalDataFetcher()
        self.signal_tracker = SignalTracker()
        self.ai_assistant = MarketAIAssistant(
            api_key=self.config.llm.groq_api_key or self.config.llm.gemini_api_key,
            model_name=self.config.llm.model_name,
        )
        self.signal_engine = SignalEngine(
            xgboost_path=str(self.config.ai.xgboost_path),
            hmm_path=str(self.config.ai.hmm_path),
            min_risk_reward=self.config.risk.min_risk_reward,
        )
        saved_mode = db.get_setting("signal_mode", "standard")
        self.signal_engine.apply_mode(saved_mode)
        self.telegram_bot = CyberTelegramBot(
            token=self.config.telegram.bot_token,
            channel_id=self.config.telegram.channel_id,
            admin_chat_ids=self.config.telegram.admin_chat_ids,
            signal_engine=self.signal_engine,
            signal_tracker=self.signal_tracker,
            data_fetcher=self.data_fetcher,
            ai_assistant=self.ai_assistant,
        )
        self.market_sentinel = MarketSentinel(
            telegram_bot=self.telegram_bot,
            session_filter=self.signal_engine.session_filter,
            news_sentinel=self.signal_engine.news_sentinel,
            data_fetcher=self.data_fetcher,
            signal_tracker=self.signal_tracker,
        )
        self._running = False

    async def run_market_loop(self):
        """Continuous market monitoring and signal generation loop."""
        logger.info("Market Monitoring Loop is active...")

        symbols = self.config.market.symbols
        dxy_symbol = self.config.market.dxy_symbol

        while self._running:
            try:
                # 1. Fetch Macro DXY data first
                dxy_df = await self.data_fetcher.get_market_data(dxy_symbol, timeframe="15m")

                # 2. Iterate through each monitored symbol
                for symbol in symbols:
                    # Skip non-crypto symbols on weekends (market is closed!)
                    is_crypto = any(c in symbol.upper() for c in ["BTC", "ETH", "SOL", "USDT"])
                    if not is_crypto and self.signal_engine.session_filter.is_weekend():
                        continue

                    logger.debug(f"Scanning market for {symbol}...")
                    df = await self.data_fetcher.get_market_data(symbol, timeframe=self.config.market.primary_timeframe)

                    if df is None or len(df) < 50:
                        logger.warning(f"Could not retrieve sufficient data for {symbol}")
                        continue

                    current_price = float(df["close"][-1])

                    # 3. Check active signals trailing triggers (TP1 / TP2 / SL)
                    trailing_alerts = self.signal_tracker.update_price(symbol, current_price)
                    for alert in trailing_alerts:
                        logger.info(f"Trailing Alert for {symbol}: {alert['type']}")
                        await self.telegram_bot.broadcast_alert(alert["message"])

                    # 4. Skip signal generation if symbol already has an active trade (No duplicates!)
                    if self.signal_tracker.has_active_signal(symbol):
                        logger.debug(f"{symbol} bo'yicha ochiq signal mavjud. Takroriy signal generatsiya qilinmaydi.")
                        continue

                    # 5. Run AI Council Signal Analysis
                    signal, meta = await self.signal_engine.analyze_and_generate_signal(
                        symbol=symbol,
                        df=df,
                        dxy_df=dxy_df,
                        timeframe=self.config.market.primary_timeframe,
                    )

                    # Update context for Telegram AI Chat
                    self.telegram_bot.set_latest_context(meta)

                    # 5. Broadcast Signal if A+ Confluence achieved
                    if signal:
                        logger.success(f"🚀 A+ SIGNAL GENERATED: {signal.symbol} {signal.direction} @ {signal.entry_price}")
                        # Register in active signals tracker
                        self.signal_tracker.add_signal(signal.to_active_signal())
                        # Broadcast to Telegram channel & admins with photo
                        await self.telegram_bot.broadcast_signal(signal)

                # Wait before next poll interval
                await asyncio.sleep(self.config.poll_interval_seconds)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in market monitoring loop: {e}")
                await asyncio.sleep(10)

    async def start_health_server(self):
        """Lightweight HTTP health check server for Render/Railway cloud deployments."""
        import os
        from aiohttp import web
        port = int(os.getenv("PORT", "8080"))

        async def health_handler(request):
            return web.json_response({
                "status": "online",
                "service": "Cyber Trade Multi-Agent AI",
                "mode": self.signal_engine.active_mode,
                "utc_time": datetime.now(timezone.utc).isoformat(),
            })

        try:
            app = web.Application()
            app.router.add_get("/", health_handler)
            app.router.add_get("/health", health_handler)
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, "0.0.0.0", port)
            await site.start()
            logger.info(f"Cloud health server running on port {port}")
        except Exception as e:
            logger.warning(f"Could not start health server on port {port}: {e}")

    async def start(self):
        """Start both Telegram Bot and Market Monitoring Loop concurrently."""
        self._running = True
        logger.info("=" * 60)
        logger.info("CYBER TRADE — MULTI-AGENT AI SIGNAL BOT STARTED")
        logger.info(f"Monitored symbols: {self.config.market.symbols}")
        logger.info(f"Primary timeframe: {self.config.market.primary_timeframe}")
        logger.info("=" * 60)

        # Start optional cloud HTTP health server
        await self.start_health_server()

        # Run Telegram bot, Market loop, and Market Sentinel concurrently
        bot_task = asyncio.create_task(self.telegram_bot.start_polling())
        market_task = asyncio.create_task(self.run_market_loop())
        sentinel_task = asyncio.create_task(self.market_sentinel.run_sentinel_loop())

        try:
            await asyncio.gather(bot_task, market_task, sentinel_task)
        except asyncio.CancelledError:
            logger.info("Shutting down Cyber Trade tasks...")
        finally:
            self.telegram_bot.stop()
            self.market_sentinel.stop()
            self._running = False


def main():
    orchestrator = CyberTradeOrchestrator()

    # Graceful shutdown handler
    def handle_exit(sig, frame):
        logger.info(f"Received exit signal {sig}, terminating gracefully...")
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    asyncio.run(orchestrator.start())


if __name__ == "__main__":
    main()
