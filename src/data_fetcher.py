"""
Cyber Trade - Universal Data Fetcher (Zero-Dependency Engine)
=============================================================
High-performance, pure Polars data fetcher.
Uses direct Yahoo Finance & public REST API JSON streams.
- NO Pandas, NO yfinance C-DLL dependencies (100% immune to Windows AppLocker).
- NO VPN needed (works in Uzbekistan and worldwide).
- Fast, asynchronous, vectorized.
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import polars as pl
import aiohttp
from loguru import logger


class UniversalDataFetcher:
    """
    Direct asynchronous HTTP market data fetcher.
    Outputs pure Polars DataFrames ready for SMC and Feature Engineering.
    """

    def __init__(self, timeout_seconds: int = 15):
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    # -------------------------------------------------------------------------
    # Direct Yahoo Finance JSON Engine (Gold, DXY, Crypto, Forex)
    # -------------------------------------------------------------------------
    async def fetch_yahoo_direct(
        self,
        symbol: str,
        interval: str = "15m",
        range_period: str = "14d",
    ) -> Optional[pl.DataFrame]:
        """
        Fetch OHLCV directly from Yahoo Finance v8 chart endpoint.
        Fast, zero third-party dependencies, returns Polars DataFrame.
        """
        # Map timeframes
        tf_map = {
            "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
            "1h": "60m", "4h": "1h", "1d": "1d",
            "M1": "1m", "M5": "5m", "M15": "15m", "M30": "30m",
            "H1": "60m", "H4": "1h", "D1": "1d",
        }
        yf_interval = tf_map.get(interval, "15m")
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={yf_interval}&range={range_period}"

        try:
            async with aiohttp.ClientSession(timeout=self.timeout, headers=self.headers) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        logger.warning(f"Yahoo API returned status {resp.status} for {symbol}")
                        return None
                    data = await resp.json()

            results = data.get("chart", {}).get("result")
            if not results:
                logger.warning(f"No result in Yahoo response for {symbol}")
                return None

            result = results[0]
            timestamps = result.get("timestamp", [])
            indicators = result.get("indicators", {}).get("quote", [{}])[0]

            opens = indicators.get("open", [])
            highs = indicators.get("high", [])
            lows = indicators.get("low", [])
            closes = indicators.get("close", [])
            volumes = indicators.get("volume", [])

            if not timestamps or not closes:
                logger.warning(f"Empty candle list for {symbol}")
                return None

            rows = []
            for i in range(len(timestamps)):
                # Skip any bars with null data (e.g. market closed intervals)
                if (
                    opens[i] is None or highs[i] is None or 
                    lows[i] is None or closes[i] is None
                ):
                    continue

                dt = datetime.fromtimestamp(timestamps[i], tz=timezone.utc).replace(tzinfo=None)
                vol = float(volumes[i]) if (volumes and volumes[i] is not None) else 100.0

                rows.append({
                    "time": dt,
                    "open": float(opens[i]),
                    "high": float(highs[i]),
                    "low": float(lows[i]),
                    "close": float(closes[i]),
                    "volume": vol,
                })

            if not rows:
                return None

            df = pl.DataFrame(rows)
            # Ensure ascending sort by time
            df = df.sort("time")
            return df

        except Exception as e:
            logger.error(f"Error fetching Yahoo direct data for {symbol}: {e}")
            return None

    # -------------------------------------------------------------------------
    # Unified Smart Router
    # -------------------------------------------------------------------------
    async def get_market_data(
        self,
        symbol: str,
        timeframe: str = "15m",
        bars: int = 500,
    ) -> Optional[pl.DataFrame]:
        """
        Smart dispatcher: maps user friendly symbols to direct data sources.
        """
        sym = symbol.upper().replace("/", "").replace("-", "")

        # 1. Gold
        if "XAU" in sym or "GOLD" in sym:
            # Gold futures proxy (GC=F) provides continuous 24/5 liquid data
            df = await self.fetch_yahoo_direct("GC=F", interval=timeframe, range_period="30d")
            if df is not None and len(df) > 0:
                return df
            # Fallback to spot gold
            return await self.fetch_yahoo_direct("XAUUSD=X", interval=timeframe, range_period="30d")

        # 2. Dollar Index (DXY)
        if "DXY" in sym or "USDX" in sym:
            return await self.fetch_yahoo_direct("DX-Y.NYB", interval=timeframe, range_period="30d")

        # 3. Crypto: BTC, ETH, SOL, etc.
        if "BTC" in sym:
            return await self.fetch_yahoo_direct("BTC-USD", interval=timeframe, range_period="30d")
        if "ETH" in sym:
            return await self.fetch_yahoo_direct("ETH-USD", interval=timeframe, range_period="30d")
        if "SOL" in sym:
            return await self.fetch_yahoo_direct("SOL-USD", interval=timeframe, range_period="30d")

        # 4. Standard Yahoo Finance symbol fallback
        return await self.fetch_yahoo_direct(symbol, interval=timeframe, range_period="30d")
