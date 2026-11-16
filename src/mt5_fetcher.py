"""
Cyber Trade - MetaTrader 5 Direct Broker Client
===============================================
Official IPC connection to MetaTrader 5 terminal (XM Global, Exness, FTMO, etc.).
Provides 0ms latency real-time broker ticks, spreads, and OHLCV candle streams.

Features:
- Auto-initialization with broker credentials (login, password, server)
- Dynamic symbol detection (GOLD, GOLD#, GOLDmicro, XAUUSD, XAUUSDm on XM)
- High-speed native rate copying (copy_rates_from_pos) for M15, H1, and H4
- Clean Polars / Pandas / Dict DataFrame conversion
- Graceful fallback when running in non-Windows environments (Render/Linux)
"""

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List

BASE_DIR = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

# Direct zero-dependency .env reader fallback
env_file = BASE_DIR / ".env"
if env_file.exists():
    try:
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k not in os.environ:
                        os.environ[k] = v
    except Exception:
        pass

try:
    from loguru import logger
except ImportError:
    from src.logger import logger

# Safe import for MetaTrader 5 (Windows-only native C++ DLLs)
try:
    import MetaTrader5 as mt5
except (ImportError, Exception):
    mt5 = None

try:
    import polars as pl
except ImportError:
    pl = None


class MetaTrader5Fetcher:
    """
    Direct client for MetaTrader 5 terminal and broker feed.
    """

    def __init__(
        self,
        login: Optional[int] = None,
        password: Optional[str] = None,
        server: Optional[str] = None,
        path: Optional[str] = None,
    ):
        self.login = login or int(os.getenv("MT5_LOGIN", "0") or "0")
        self.password = password or os.getenv("MT5_PASSWORD", "")
        self.server = server or os.getenv("MT5_SERVER", "XMGlobal-MT5 5")
        self.path = path or os.getenv("MT5_PATH", r"C:\Program Files\MetaTrader 5\terminal64.exe")
        self.active_gold_symbol: Optional[str] = None
        self.symbol_cache: Dict[str, str] = {}
        self._is_initialized = False

    @property
    def is_available(self) -> bool:
        """Check if MetaTrader5 module is supported on current platform."""
        return mt5 is not None

    def initialize(self) -> bool:
        """
        Initialize connection to the local MetaTrader 5 terminal and log into broker.
        """
        if not self.is_available:
            logger.debug("MetaTrader5 python module not installed or running on non-Windows host.")
            return False

        if self._is_initialized:
            return True

        init_kwargs: Dict[str, Any] = {}
        if self.path and Path(self.path).exists():
            init_kwargs["path"] = self.path

        if self.login and self.password and self.server:
            init_kwargs["login"] = self.login
            init_kwargs["password"] = self.password
            init_kwargs["server"] = self.server

        try:
            # Initialize terminal
            success = mt5.initialize(**init_kwargs)
            if not success:
                # Retry with basic path initialization
                if "login" in init_kwargs:
                    logger.warning(f"MT5 login failed with credentials. Retrying standard attach: {mt5.last_error()}")
                    success = mt5.initialize(path=self.path) if "path" in init_kwargs else mt5.initialize()

            if not success:
                logger.warning(f"Could not initialize MetaTrader 5 terminal: {mt5.last_error()}")
                return False

            self._is_initialized = True
            acc_info = mt5.account_info()
            if acc_info:
                logger.info(
                    f"✅ MetaTrader 5 connected to XM broker: {acc_info.company} "
                    f"(Server: {acc_info.server}, Login: {acc_info.login}, Currency: {acc_info.currency})"
                )
            else:
                logger.info("MetaTrader 5 terminal attached successfully.")

            return True

        except Exception as e:
            logger.warning(f"Error during MetaTrader 5 initialization: {e}")
            return False

    def resolve_symbol(self, symbol: str) -> str:
        """
        Dynamically map standard tickers (XAUUSD, BTCUSDT, ETHUSDT) to exact XM broker symbols.
        Supports:
        - Gold: GOLD, GOLD#, GOLDmicro, XAUUSD, XAUUSDm
        - Bitcoin: BTCUSD, BTCUSD#, BTCUSDmicro, BTCUSDT
        - Ethereum: ETHUSD, ETHUSD#, ETHUSDmicro, ETHUSDT
        - Solana: SOLUSD, SOLUSD#
        """
        raw = symbol.upper().replace("/", "").replace("-", "")
        if raw in self.symbol_cache:
            return self.symbol_cache[raw]

        if not self.is_available or not self._is_initialized:
            fallback = "GOLD" if ("XAU" in raw or "GOLD" in raw) else ("BTCUSD" if "BTC" in raw else ("ETHUSD" if "ETH" in raw else raw))
            return fallback

        # Candidate mapping per asset class
        if "XAU" in raw or "GOLD" in raw:
            candidates = ["GOLD", "XAUUSD", "GOLD#", "GOLDmicro", "XAUUSDm", "XAUUSD.", "GOLD."]
        elif "BTC" in raw:
            candidates = ["BTCUSD", "BTCUSD#", "BTCUSDmicro", "BTCUSDT", "BTCUSD.", "BITCOIN"]
        elif "ETH" in raw:
            candidates = ["ETHUSD", "ETHUSD#", "ETHUSDmicro", "ETHUSDT", "ETHUSD.", "ETHEREUM"]
        elif "SOL" in raw:
            candidates = ["SOLUSD", "SOLUSD#", "SOLUSDmicro", "SOLUSDT"]
        else:
            candidates = [raw, f"{raw}#", f"{raw}m", f"{raw}.", f"{raw}micro"]

        try:
            # 1. Test candidate list against broker
            for cand in candidates:
                info = mt5.symbol_info(cand)
                if info is not None:
                    mt5.symbol_select(cand, True)
                    self.symbol_cache[raw] = cand
                    logger.info(f"Resolved XM Broker symbol: '{raw}' -> '{cand}'")
                    return cand

            # 2. Search all broker symbols by substring
            search_key = "GOLD" if ("XAU" in raw or "GOLD" in raw) else ("BTC" if "BTC" in raw else ("ETH" if "ETH" in raw else raw))
            symbols = mt5.symbols_get()
            if symbols:
                for s in symbols:
                    if search_key in s.name.upper():
                        mt5.symbol_select(s.name, True)
                        self.symbol_cache[raw] = s.name
                        logger.info(f"Discovered XM Broker symbol: '{raw}' -> '{s.name}'")
                        return s.name

        except Exception as e:
            logger.debug(f"Error resolving XM symbol for {raw}: {e}")

        default_sym = "GOLD" if ("XAU" in raw or "GOLD" in raw) else ("BTCUSD" if "BTC" in raw else raw)
        self.symbol_cache[raw] = default_sym
        return default_sym

    def find_gold_symbol(self) -> str:
        """Backward compatibility for gold resolution."""
        return self.resolve_symbol("XAUUSD")

    def get_market_data(
        self,
        symbol: str = "XAUUSD",
        timeframe: str = "15m",
        bars: int = 500,
    ) -> Optional[Any]:
        """
        Fetch OHLCV historical candle series directly from XM broker via MT5 (0ms latency).
        Returns a Polars DataFrame with columns: [time, open, high, low, close, volume].
        """
        if not self.is_available:
            return None

        if not self._is_initialized:
            if not self.initialize():
                return None

        broker_sym = self.resolve_symbol(symbol)

        # Timeframe mapping
        tf_map = {
            "1m": mt5.TIMEFRAME_M1,
            "5m": mt5.TIMEFRAME_M5,
            "15m": mt5.TIMEFRAME_M15,
            "30m": mt5.TIMEFRAME_M30,
            "1h": mt5.TIMEFRAME_H1,
            "4h": mt5.TIMEFRAME_H4,
            "1d": mt5.TIMEFRAME_D1,
            "M15": mt5.TIMEFRAME_M15,
            "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1,
        }
        mt5_tf = tf_map.get(timeframe, mt5.TIMEFRAME_M15)

        try:
            rates = mt5.copy_rates_from_pos(broker_sym, mt5_tf, 0, bars)
            if rates is None or len(rates) == 0:
                logger.debug(f"MT5 returned 0 rates for {broker_sym} ({timeframe}): {mt5.last_error()}")
                return None

            rows = []
            for r in rates:
                dt = datetime.fromtimestamp(int(r[0]), tz=timezone.utc).replace(tzinfo=None)
                rows.append({
                    "time": dt,
                    "open": float(r[1]),
                    "high": float(r[2]),
                    "low": float(r[3]),
                    "close": float(r[4]),
                    "volume": float(r[5]),  # tick_volume
                })

            if not rows:
                return None

            if pl is not None:
                return pl.DataFrame(rows).sort("time")
            return rows

        except Exception as e:
            logger.debug(f"Error fetching MT5 rates for {broker_sym}: {e}")
            return None

    def get_live_tick(self, symbol: str = "XAUUSD") -> Optional[Dict[str, float]]:
        """Get live bid, ask, and spread directly from XM broker."""
        if not self.is_available or not self._is_initialized:
            return None

        broker_sym = self.resolve_symbol(symbol)
        try:
            tick = mt5.symbol_info_tick(broker_sym)
            if tick is not None:
                spread = round(tick.ask - tick.bid, 2)
                return {
                    "bid": tick.bid,
                    "ask": tick.ask,
                    "spread": spread,
                    "time": tick.time,
                }
        except Exception:
            pass
        return None

    def shutdown(self):
        """Close MT5 connection cleanly."""
        if self.is_available and self._is_initialized:
            try:
                mt5.shutdown()
            except Exception:
                pass
            self._is_initialized = False


# Global singleton instance
mt5_fetcher = MetaTrader5Fetcher()
