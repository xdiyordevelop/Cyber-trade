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
from dotenv import load_dotenv

# Load .env file if available
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


@dataclass
class MarketConfig:
    """Market symbols and data source configurations."""
    # Default monitored symbols
    symbols: List[str] = field(default_factory=lambda: ["XAUUSD", "BTCUSDT", "ETHUSDT"])
    
    # Macro symbols for correlation analysis
    dxy_symbol: str = "DX-Y.NYB"  # US Dollar Index (Yahoo Finance)
    gold_symbol_yf: str = "GC=F"   # Gold Futures / Spot proxy on Yahoo Finance
    
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
class AppConfig:
    """Master application configuration."""
    market: MarketConfig = field(default_factory=MarketConfig)
    ai: AIModelConfig = field(default_factory=AIModelConfig)
    risk: RiskSignalConfig = field(default_factory=RiskSignalConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    
    # Loop intervals in seconds (e.g. 60s check or on new M15 candle)
    poll_interval_seconds: int = 60
    
    # Feature flags
    enable_chart_generation: bool = True
    enable_news_filter: bool = True
    enable_macro_filter: bool = True


# Global config instance
def get_config() -> AppConfig:
    return AppConfig()
