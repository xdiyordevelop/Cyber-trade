"""
Cyber Trade - Visual Chart Generator
====================================
Generates sleek, dark-themed, high-resolution candlestick charts
with Entry, Stop Loss, Take-Profit levels, and SMC zones plotted.
Headless rendering (matplotlib 'Agg' backend) - zero GPU or GUI needed.
Perfect for Telegram photo broadcast.
"""

import os
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
import numpy as np
import polars as pl
from loguru import logger

# Headless matplotlib configuration
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches


class ChartGenerator:
    """
    Renders candlestick charts with annotated signal zones.
    """

    def __init__(self, output_dir: str = "charts"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_signal_chart(
        self,
        df: pl.DataFrame,
        symbol: str,
        timeframe: str,
        direction: str,  # "BUY" or "SELL"
        entry_price: float,
        stop_loss: float,
        take_profit_1: float,
        take_profit_2: float,
        ai_confidence: float = 0.0,
        smc_reasons: Optional[list] = None,
        lookback_bars: int = 40,
    ) -> Optional[str]:
        """
        Create a candlestick chart with SL, Entry, and TP lines.
        Returns the absolute path to the saved PNG image.
        """
        try:
            # Take recent bars
            recent_df = df.tail(lookback_bars)
            n_bars = len(recent_df)
            if n_bars < 10:
                logger.warning("Not enough candles to generate chart")
                return None

            opens = recent_df["open"].to_numpy()
            highs = recent_df["high"].to_numpy()
            lows = recent_df["low"].to_numpy()
            closes = recent_df["close"].to_numpy()

            # Set up dark theme aesthetic
            plt.style.use("dark_background")
            fig, ax = plt.subplots(figsize=(10, 5.5), dpi=120)
            fig.patch.set_facecolor("#0b0e14")
            ax.set_facecolor("#11151c")

            # Candlestick plotting
            indices = np.arange(n_bars)
            width = 0.6
            wick_width = 1.0

            bullish_color = "#00e676"  # Cyber green
            bearish_color = "#ff1744"  # Cyber red

            for i in range(n_bars):
                o, h, l, c = opens[i], highs[i], lows[i], closes[i]
                color = bullish_color if c >= o else bearish_color

                # High/Low Wick
                ax.plot([indices[i], indices[i]], [l, h], color=color, linewidth=wick_width, zorder=2)
                # Candle Body
                lower_body = min(o, c)
                body_height = max(abs(c - o), (highs[i] - lows[i]) * 0.02)
                rect = patches.Rectangle(
                    (indices[i] - width / 2, lower_body),
                    width,
                    body_height,
                    facecolor=color,
                    edgecolor=color,
                    alpha=0.9,
                    zorder=3,
                )
                ax.add_patch(rect)

            # Draw Signal Lines
            xmin, xmax = 0, n_bars + 8
            ax.set_xlim(xmin - 1, xmax)

            # 1. Entry Line (Cyan / White)
            ax.axhline(entry_price, color="#00e5ff", linestyle="--", linewidth=1.5, alpha=0.9, zorder=4)
            ax.text(xmax - 7, entry_price, f" ENTRY: {entry_price:.2f}", color="#00e5ff", fontweight="bold", va="center", fontsize=8)

            # 2. Stop Loss Line (Red)
            ax.axhline(stop_loss, color="#ff1744", linestyle="-", linewidth=1.8, alpha=0.9, zorder=4)
            ax.text(xmax - 7, stop_loss, f" SL: {stop_loss:.2f}", color="#ff1744", fontweight="bold", va="center", fontsize=8)

            # 3. Take Profit 1 (Light Green)
            ax.axhline(take_profit_1, color="#76ff03", linestyle="--", linewidth=1.5, alpha=0.9, zorder=4)
            ax.text(xmax - 7, take_profit_1, f" TP1: {take_profit_1:.2f}", color="#76ff03", fontweight="bold", va="center", fontsize=8)

            # 4. Take Profit 2 (Green)
            ax.axhline(take_profit_2, color="#00e676", linestyle="-", linewidth=1.8, alpha=0.9, zorder=4)
            ax.text(xmax - 7, take_profit_2, f" TP2: {take_profit_2:.2f}", color="#00e676", fontweight="bold", va="center", fontsize=8)

            # Title & Metadata
            dir_str = "BUY" if direction.upper() == "BUY" else "SELL"
            title_text = f"CYBER TRADE | {symbol} {timeframe} — [{dir_str}] SIGNAL"
            subtitle = f"AI Confidence: {ai_confidence*100:.1f}% | R:R: 1:{abs(take_profit_2 - entry_price)/max(0.001, abs(entry_price - stop_loss)):.1f}"
            
            ax.set_title(f"{title_text}\n{subtitle}", loc="left", fontsize=11, fontweight="bold", color="#f0f6fc", pad=12)

            # Styling grid & spines
            ax.grid(True, linestyle=":", alpha=0.2, color="#8b949e")
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            ax.spines["left"].set_color("#30363d")
            ax.spines["bottom"].set_color("#30363d")
            ax.tick_params(colors="#8b949e", labelsize=8)

            # Save chart to file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"signal_{symbol}_{timeframe}_{direction}_{timestamp}.png"
            filepath = self.output_dir / filename

            plt.tight_layout()
            plt.savefig(filepath, facecolor=fig.get_facecolor(), edgecolor="none")
            plt.close(fig)

            logger.info(f"Generated signal chart: {filepath}")
            return str(filepath.resolve())

        except Exception as e:
            logger.error(f"Failed to generate signal chart: {e}")
            return None
