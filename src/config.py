"""
Cyber Trade - Configuration Module
==================================
Central configuration settings for Multi-Agent AI Signal & Analysis Bot.
Optimized for 24/7 execution on free cloud environments (Render, Koyeb, Railway, Linux VPS).
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional
try:
    from dotenv import load_dotenv
    BASE_DIR = Path(__file__).resolve().parent.parent
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent.parent

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


@dataclass
class MarketConfig:
    """Market symbols and data source configurations."""
    # Default monitored symbols (Focused on Gold XAUUSD)
    symbols: List[str] = field(default_factory=lambda: [s.strip() for s in os.getenv("MONITORED_SYMBOLS", "XAUUSD").split(",") if s.strip()])
    
    # Macro symbols for correlation analysis
    dxy_symbol: str = "DX-Y.NYB"  # US Dollar Index (Yahoo Finance)
    gold_symbol_yf: str = "GC=F"   # COMEX Front-Month Gold Futures on Yahoo Finance
    
    # Timeframes to monitor
    primary_timeframe: str = "15m"   # Trigger timeframe
    trend_timeframe: str = "1h"       # Structure & OB timeframe
    macro_timeframe: str = "4h"       # Big picture trend
    
    # Candle history lookback
    history_bars: int = 500


@dataclass
class AIModelConfig:
    """ML and HMM model paths and confidence thresholds."""
    xgboost_path: Path = BASE_DIR / "models" / "xgboost_model.pkl"
    hmm_path: Path = BASE_DIR / "models" / "hmm_regime.pkl"
    
    # Base confidence threshold for BUY / SELL
    base_confidence_threshold: float = 0.65
    min_confidence_threshold: float = 0.55
    max_confidence_threshold: float = 0.80


@dataclass
class RiskSignalConfig:
    """Risk and target reward parameters."""
    min_risk_reward: float = 2.0      # Minimum R:R ratio required for a signal
    tp1_rr: float = 1.5              # TP1 target (Trigger to move SL to BE)
    tp2_rr: float = 2.5              # TP2 target (Main profit zone)
    tp3_rr: float = 4.0              # TP3 target (Runner / Trend extension)
    
    # ATR multipliers for buffer
    atr_sl_multiplier: float = 1.5
    atr_tp_multiplier: float = 3.0


@dataclass
class TelegramConfig:
    """Telegram bot settings."""
    bot_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    channel_id: str = field(default_factory=lambda: os.getenv("TELEGRAM_CHANNEL_ID", ""))
    admin_chat_ids: List[str] = field(default_factory=lambda: [
        cid.strip() for cid in os.getenv("TELEGRAM_ADMIN_CHAT_ID", "").split(",") if cid.strip()
    ])


@dataclass
class LLMConfig:
    """AI Conversational Agent settings (Gemini + Groq Hybrid Architecture)."""
    # Google Gemini
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    gemini_primary_model: str = field(default_factory=lambda: os.getenv("AI_MODEL_PRIMARY", "gemini-3.8-flash"))
    gemini_lite_model: str = field(default_factory=lambda: os.getenv("AI_MODEL_LITE", "gemini-3.5-flash-lite"))
    gemini_complex_model: str = field(default_factory=lambda: os.getenv("AI_MODEL_COMPLEX", "gemini-3.1-pro-preview"))
    
    # Groq LPU Ultra-Fast Inference
    groq_api_key: str = field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))
    groq_model_name: str = field(default_factory=lambda: os.getenv("GROQ_MODEL_NAME", "llama-3.3-70b-versatile"))

    # Legacy fallback field
    model_name: str = field(default_factory=lambda: os.getenv("AI_MODEL_NAME", "llama-3.3-70b-versatile"))


@dataclass
class MT5Config:
    """MetaTrader 5 / Broker Direct API connection settings."""
    enabled: bool = field(default_factory=lambda: os.getenv("MT5_ENABLED", "true").lower() in ("true", "1", "yes"))
    login: int = field(default_factory=lambda: int(os.getenv("MT5_LOGIN", "0") or "0"))
    password: str = field(default_factory=lambda: os.getenv("MT5_PASSWORD", ""))
    server: str = field(default_factory=lambda: os.getenv("MT5_SERVER", "XMGlobal-MT5 5"))
    path: str = field(default_factory=lambda: os.getenv("MT5_PATH", "C:\\Program Files\\MetaTrader 5\\terminal64.exe"))
    symbol: str = field(default_factory=lambda: os.getenv("MT5_SYMBOL", "GOLD"))


@dataclass
class AppConfig:
    """Master application configuration."""
    market: MarketConfig = field(default_factory=MarketConfig)
    ai: AIModelConfig = field(default_factory=AIModelConfig)
    risk: RiskSignalConfig = field(default_factory=RiskSignalConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    mt5: MT5Config = field(default_factory=MT5Config)
    
    # Loop intervals in seconds (e.g. 60s check or on new M15 candle)
    poll_interval_seconds: int = 60
    
    # Feature flags
    enable_chart_generation: bool = True
    enable_news_filter: bool = True
    enable_macro_filter: bool = True


# Global config instance
def get_config() -> AppConfig:
    return AppConfig()
