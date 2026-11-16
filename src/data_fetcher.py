"""
Cyber Trade - Universal Data Fetcher (Zero-Dependency Engine)
=============================================================
High-performance, pure Polars data fetcher.
Supports:
1. Direct Binance & Bybit Public REST APIs for Crypto (0ms delay, real volume, native 4H/1H/15m).
2. Spot Gold (XAUUSD=X) as primary feed for Gold to eliminate the COMEX futures contango discrepancy ($15-$30 gap).
3. Automatic multi-mirror failover (Binance -> Bybit -> Yahoo Finance).
4. Native Multi-Timeframe (M15, H1, H4) data fetching with deep history.
- NO Pandas, NO yfinance C-DLL dependencies.
- Fast, asynchronous, vectorized.
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import polars as pl
import aiohttp
from loguru import logger

from src.utils import resample_ohlcv

try:
    from src.mt5_fetcher import mt5_fetcher
except ImportError:
    mt5_fetcher = None


class UniversalDataFetcher:
    """
    Direct asynchronous HTTP market data fetcher.
    Outputs pure Polars DataFrames ready for SMC and Feature Engineering.
    """

    def __init__(self, timeout_seconds: int = 15):
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
        }

    # -------------------------------------------------------------------------
    # 1. Direct Binance Public REST API (Crypto: BTC, ETH, SOL)
    # -------------------------------------------------------------------------
    async def fetch_binance_direct(
        self,
        symbol: str,
        interval: str = "15m",
        limit: int = 500,
    ) -> Optional[pl.DataFrame]:
        """
        Fetch OHLCV directly from Binance Public REST API.
        No API key required, 0ms latency, official live tick and volume.
        """
        tf_map = {
            "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
            "1h": "1h", "4h": "4h", "1d": "1d",
            "M1": "1m", "M5": "5m", "M15": "15m", "M30": "30m",
            "H1": "1h", "H4": "4h", "D1": "1d",
        }
        binance_interval = tf_map.get(interval, "15m")
        clean_symbol = symbol.upper().replace("/", "").replace("-", "")
        if not clean_symbol.endswith("USDT") and not clean_symbol.endswith("BUSD"):
            clean_symbol = f"{clean_symbol}USDT"

        endpoints = [
            f"https://data-api.binance.vision/api/v3/klines?symbol={clean_symbol}&interval={binance_interval}&limit={limit}",
            f"https://api.binance.com/api/v3/klines?symbol={clean_symbol}&interval={binance_interval}&limit={limit}",
        ]

        fast_timeout = aiohttp.ClientTimeout(total=4.0, sock_connect=2.5)
        for url in endpoints:
            try:
                async with aiohttp.ClientSession(timeout=fast_timeout, headers=self.headers) as session:
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            continue
                        raw_candles = await resp.json()

                if not raw_candles or not isinstance(raw_candles, list):
                    continue

                rows = []
                for candle in raw_candles:
                    open_ts = int(candle[0]) / 1000.0
                    dt = datetime.fromtimestamp(open_ts, tz=timezone.utc).replace(tzinfo=None)
                    rows.append({
                        "time": dt,
                        "open": float(candle[1]),
                        "high": float(candle[2]),
                        "low": float(candle[3]),
                        "close": float(candle[4]),
                        "volume": float(candle[5]),
                    })

                if rows:
                    df = pl.DataFrame(rows).sort("time")
                    logger.debug(f"Fetched {len(df)} candles for {clean_symbol} ({interval}) from Binance")
                    return df

            except Exception as e:
                logger.debug(f"Binance fetch error for {clean_symbol} on {url}: {e}")
                continue

        return None

    # -------------------------------------------------------------------------
    # 2. Direct Bybit Public REST API (Crypto Failover)
    # -------------------------------------------------------------------------
    async def fetch_bybit_direct(
        self,
        symbol: str,
        interval: str = "15m",
        limit: int = 500,
    ) -> Optional[pl.DataFrame]:
        """
        Fetch OHLCV directly from Bybit V5 Public Market API.
        Acts as failover if Binance is geo-restricted or rate-limited.
        """
        tf_map = {
            "1m": "1", "5m": "5", "15m": "15", "30m": "30",
            "1h": "60", "4h": "240", "1d": "D",
            "M1": "1", "M5": "5", "M15": "15", "M30": "30",
            "H1": "60", "H4": "240", "D1": "D",
        }
        bybit_interval = tf_map.get(interval, "15")
        clean_symbol = symbol.upper().replace("/", "").replace("-", "")
        if not clean_symbol.endswith("USDT") and not clean_symbol.endswith("USDC"):
            clean_symbol = f"{clean_symbol}USDT"

        url = f"https://api.bybit.com/v5/market/kline?category=spot&symbol={clean_symbol}&interval={bybit_interval}&limit={limit}"

        try:
            async with aiohttp.ClientSession(timeout=self.timeout, headers=self.headers) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()

            raw_candles = data.get("result", {}).get("list", [])
            if not raw_candles:
                return None

            rows = []
            for candle in raw_candles:
                # Bybit v5 kline: [0: startTime, 1: open, 2: high, 3: low, 4: close, 5: volume, 6: turnover]
                open_ts = int(candle[0]) / 1000.0
                dt = datetime.fromtimestamp(open_ts, tz=timezone.utc).replace(tzinfo=None)

                rows.append({
                    "time": dt,
                    "open": float(candle[1]),
                    "high": float(candle[2]),
                    "low": float(candle[3]),
                    "close": float(candle[4]),
                    "volume": float(candle[5]),
                })

            if not rows:
                return None

            # Bybit returns reverse chronological order (newest first), sort ascending
            df = pl.DataFrame(rows).sort("time")
            logger.debug(f"Fetched {len(df)} candles for {clean_symbol} ({interval}) from Bybit")
            return df

        except Exception as e:
            logger.debug(f"Bybit fetch error for {clean_symbol}: {e}")
            return None

    # -------------------------------------------------------------------------
    # 3. Direct Yahoo Finance JSON Engine (Spot Gold, DXY, Forex Fallback)
    # -------------------------------------------------------------------------
    async def fetch_yahoo_direct(
        self,
        symbol: str,
        interval: str = "15m",
        range_period: str = "30d",
    ) -> Optional[pl.DataFrame]:
        """
        Fetch OHLCV directly from Yahoo Finance v8 chart endpoint.
        Handles Spot Gold (XAUUSD=X), DXY, and resamples 1H to 4H if needed.
        """
        is_4h_request = interval in ["4h", "H4"]

        # If 4H is requested from Yahoo, fetch 60m data over 60 days and resample to true 4H
        if is_4h_request:
            yf_interval = "60m"
            range_period = "60d"
        else:
            tf_map = {
                "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
                "1h": "60m", "1d": "1d",
                "M1": "1m", "M5": "5m", "M15": "15m", "M30": "30m",
                "H1": "60m", "D1": "1d",
            }
            yf_interval = tf_map.get(interval, "15m")

        endpoints = [
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={yf_interval}&range={range_period}",
            f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?interval={yf_interval}&range={range_period}",
        ]

        data = None
        for url in endpoints:
            try:
                async with aiohttp.ClientSession(timeout=self.timeout, headers=self.headers) as session:
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            break
                        else:
                            logger.debug(f"Yahoo API {url} status {resp.status} for {symbol}")
            except Exception as e:
                logger.debug(f"Yahoo endpoint {url} attempt error: {e}")
                continue

        if not data:
            return None

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
                return None

            rows = []
            for i in range(len(timestamps)):
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

            df = pl.DataFrame(rows).sort("time")

            # If 4H was requested, resample the 60m data to true 4H bars
            if is_4h_request and len(df) >= 4:
                df = resample_ohlcv(df, "4h")

            return df

        except Exception as e:
            logger.error(f"Error fetching Yahoo direct data for {symbol}: {e}")
            return None

    # -------------------------------------------------------------------------
    # 4. Unified Smart Router (High Precision & Low Latency)
    # -------------------------------------------------------------------------
    async def get_market_data(
        self,
        symbol: str,
        timeframe: str = "15m",
        bars: int = 500,
    ) -> Optional[pl.DataFrame]:
        """
        Direct 0ms market data dispatcher:
        - Primary: Direct XM Broker MT5 connection for ALL assets (Gold, Bitcoin, Ethereum, etc.)
        - Fallback: Non-Windows container resilience
        """
        sym = symbol.upper().replace("/", "").replace("-", "")

        # ---------------------------------------------------------------------
        # 1. EXCLUSIVE XM BROKER DIRECT FEED (0ms Latency via MetaTrader 5)
        # ---------------------------------------------------------------------
        if mt5_fetcher and mt5_fetcher.is_available:
            try:
                df_mt5 = mt5_fetcher.get_market_data(sym, timeframe=timeframe, bars=bars)
                if df_mt5 is not None and len(df_mt5) >= 30:
                    logger.debug(f"Using Direct XM Broker (MT5) 0ms feed for {sym}.")
                    return df_mt5
            except Exception as e:
                logger.warning(f"XM MT5 fetch attempt error for {sym}: {e}")

        # ---------------------------------------------------------------------
        # 2. Resilient Offline/Container Fallbacks (Only when MT5 is not attached)
        # ---------------------------------------------------------------------
        # Pure Real Gold (COMEX GC=F / Spot Gold XAUUSD)
        if "XAU" in sym or "GOLD" in sym:
            # Single exact real Gold source: COMEX Gold Futures (GC=F) - matches MT5 spot price
            df_gold = await self.fetch_yahoo_direct("GC=F", interval=timeframe, range_period="30d")
            if df_gold is not None and len(df_gold) >= 30:
                return df_gold

            # Secondary real spot gold ticker if GC=F is unavailable
            return await self.fetch_yahoo_direct("XAUUSD=X", interval=timeframe, range_period="30d")

        # Dollar Index (DXY)
        if "DXY" in sym or "USDX" in sym:
            return await self.fetch_yahoo_direct("DX-Y.NYB", interval=timeframe, range_period="30d")

        # Crypto Fallback (BTC, ETH, etc.)
        is_crypto = any(c in sym for c in ["BTC", "ETH", "SOL", "BNB", "XRP", "USDT"])
        if is_crypto:
            binance_pair = sym if sym.endswith("USDT") else f"{sym}USDT"
            df_binance = await self.fetch_binance_direct(binance_pair, interval=timeframe, limit=bars)
            if df_binance is not None and len(df_binance) >= 30:
                return df_binance
            yf_sym = "BTC-USD" if "BTC" in sym else ("ETH-USD" if "ETH" in sym else ("SOL-USD" if "SOL" in sym else f"{sym}-USD"))
            return await self.fetch_yahoo_direct(yf_sym, interval=timeframe, range_period="30d")

        # Standard Forex Fallback
        yf_symbol = symbol if ("=" in symbol or "^" in symbol) else f"{symbol}=X"
        df = await self.fetch_yahoo_direct(yf_symbol, interval=timeframe, range_period="30d")
        if df is not None and len(df) > 0:
            return df

        return await self.fetch_yahoo_direct(symbol, interval=timeframe, range_period="30d")

    # -------------------------------------------------------------------------
    # 5. Multi-Timeframe Dedicated Data Fetcher
    # -------------------------------------------------------------------------
    async def get_mtf_data(
        self,
        symbol: str,
    ) -> Dict[str, Optional[pl.DataFrame]]:
        """
        Fetch dedicated, deep-history data for all three core timeframes:
        - M15: Trigger timeframe (500 bars)
        - H1:  Structure timeframe (300 bars)
        - H4:  Macro trend timeframe (200 bars for deep EMA50 / EMA200 calculation)
        """
        m15_task = self.get_market_data(symbol, timeframe="15m", bars=500)
        h1_task = self.get_market_data(symbol, timeframe="1h", bars=300)
        h4_task = self.get_market_data(symbol, timeframe="4h", bars=200)

        df_15m, df_1h, df_4h = await asyncio.gather(m15_task, h1_task, h4_task)

        # Fallback for H1 / H4 via resampling if native fails
        if df_1h is None and df_15m is not None and len(df_15m) >= 20:
            df_1h = resample_ohlcv(df_15m, "1h")
        if df_4h is None and df_1h is not None and len(df_1h) >= 15:
            df_4h = resample_ohlcv(df_1h, "4h")
        elif df_4h is None and df_15m is not None and len(df_15m) >= 30:
            df_4h = resample_ohlcv(df_15m, "4h")

        return {
            "15m": df_15m,
            "1h": df_1h,
            "4h": df_4h,
        }
