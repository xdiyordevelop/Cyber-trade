"""
Cyber Trade - Next-Gen Conversational AI Assistant (Groq & DeepSeek/Qwen Engine)
================================================================================
Powered by Groq's Ultra-Fast LPU Inference Engine.
Grounded in 100% Real-Time Live Market Data (Yahoo Finance + SMC + ML Models).

Features:
1. Dynamic Asset Detection: Automatically identifies mentioned assets (BTC, ETH, XAUUSD, SOL, DXY).
2. On-Demand Live Analysis: Computes real-time price, XGBoost ML signal, HMM regime, RSI, and Order Blocks.
3. Anti-Hallucination Guardrails: Strictly forces current 2026 real prices; zero fabricated outdated prices.
4. Human-Centric Practical Uzbek: Concise, direct, and actionable advice for traders.
"""

import os
from pathlib import Path
from datetime import datetime, timezone
import aiohttp
from typing import Dict, Any, Optional
from loguru import logger
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def detect_symbol_from_text(text: str) -> Optional[str]:
    """Detect which cryptocurrency or market asset the user is referring to."""
    t = text.lower()
    if any(w in t for w in ["btc", "bitcoin", "bitkoin", "bit coin"]):
        return "BTCUSDT"
    if any(w in t for w in ["eth", "ethereum", "efir", "ether"]):
        return "ETHUSDT"
    if any(w in t for w in ["xau", "xauusd", "gold", "oltin", "tilla"]):
        return "XAUUSD"
    if any(w in t for w in ["sol", "solana"]):
        return "SOLUSDT"
    if any(w in t for w in ["dxy", "dollar", "aqsh dollari", "usd"]):
        return "DXY"
    return None


class MarketAIAssistant:
    """
    High-IQ Market Intelligence & Trading Reasoning Agent.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "openai/gpt-oss-120b",
    ):
        self.api_key = api_key or os.getenv("GROQ_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")
        self.model_name = os.getenv("AI_MODEL_NAME", "openai/gpt-oss-120b")
        self.api_url = "https://api.groq.com/openai/v1/chat/completions"

        self.system_prompt = (
            "Sen 'Cyber Trade' professional sun'iy intellekt bozor tahlilchisisan.\n\n"
            "Sening vazifang — foydalanuvchiga bozor holatini (BTC, ETH, XAUUSD va b.) botning REAL JONLI TAHLILI asosida tushuntirish.\n\n"
            "QAT'IY QOIDALAR (BUZILMASIN):\n"
            "1. JONLI HAQIQATGA ASOSLAN: Senga quyida berilgan ANIQ JONLI NARX va BOT HISOB-KITOBLARIDAN FOYDALAN. "
            "Eski o'tmishdagi (2022-2023 yillardagi Bitcoin $30,000 larini) umuman tilga olma va o'zingdan narx to'qima!\n"
            "2. FOYDALANUVCHI FIKRIGA TO'G'RI VA MANTIQIY JAVOB BER: Masalan, agar u 'Bitcoin buyga ketyapti' desa, "
            "botning ML modeli nima deyotganini (BUY, SELL yoki HOLD) va nima sababdan bot kirgani yoki kutayotganini tushuntir.\n"
            "3. DAM OLISH KUNLARINI (SHANBA/YAKSHANBA) INOBATGA OL: Hafta oxirida Oltin va Forex yopiqligini, "
            "Kriptoda esa hajm pastligi tufayli soxta harakatlar (fake breakout) bo'lishini doim eslatib o't.\n"
            "4. IXCHAM VA TUSHUNARLI BO'LSIN: Hech qanday markdown jadvallar (table) TUZMA! Chunki Telegramda jadvallar kesilib qoladi. "
            "Matnni chiroyli va qulay ro'yxat (bullet point) ko'rinishida 3 qismda ber:\n"
            "   • 1-qism: Hozirgi real narx va botning ko'rsatkichi (ML modeli va yo'nalish)\n"
            "   • 2-qism: Asosiy darajalar (Order Block, RSI yoki DXY ta'siri)\n"
            "   • 3-qism: Amaliy xulosa (Hozir kirish kerakmi, ushlab turishmi yoki qaysi zonani kutish lozim?)\n"
            "5. O'zbek tilida samimiy, do'stona va professional tilda yoz."
        )

        if self.api_key:
            logger.info(f"Groq Next-Gen AI Assistant initialized (Model: {self.model_name}).")
        else:
            logger.warning("GROQ_API_KEY is not set. Intelligent heuristic fallback active.")

    async def answer_user_query(
        self,
        user_message: str,
        market_context: Optional[Dict[str, Any]] = None,
        signal_engine = None,
        data_fetcher = None,
    ) -> str:
        """
        Send live-grounded reasoning query to Groq AI.
        Dynamically fetches live analysis for mentioned asset on-the-fly!
        """
        # 1. Detect target asset from query or fallback
        detected_sym = detect_symbol_from_text(user_message)
        active_sym = detected_sym or (market_context.get("symbol") if market_context else None) or "BTCUSDT"

        live_data = dict(market_context or {})
        live_data["symbol"] = active_sym

        # 2. On-demand live analysis if engine and fetcher are available
        if signal_engine and data_fetcher:
            try:
                # Map clean symbol for fetcher
                fetch_sym = active_sym
                if active_sym == "BTCUSDT":
                    fetch_sym = "BTC-USD"
                elif active_sym == "ETHUSDT":
                    fetch_sym = "ETH-USD"
                elif active_sym == "XAUUSD":
                    fetch_sym = "GC=F"
                elif active_sym == "DXY":
                    fetch_sym = "DX-Y.NYB"

                df = await data_fetcher.get_market_data(fetch_sym, timeframe="15m")
                dxy_df = await data_fetcher.get_market_data("DX-Y.NYB", timeframe="15m")

                if df is not None and len(df) >= 30:
                    _, fresh_meta = await signal_engine.analyze_and_generate_signal(active_sym, df, dxy_df)
                    if fresh_meta:
                        live_data.update(fresh_meta)
            except Exception as e:
                logger.warning(f"Could not perform on-demand analysis for {active_sym}: {e}")

        # 3. Calendar & session status
        now_utc = datetime.now(timezone.utc)
        weekday = now_utc.weekday()
        is_weekend = (weekday == 4 and now_utc.hour >= 22) or weekday == 5 or (weekday == 6 and now_utc.hour < 22)
        day_names = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]
        day_str = day_names[weekday]

        cur_price = live_data.get("current_price", 0.0)
        ml_sig = live_data.get("ml_signal", "HOLD")
        ml_conf = live_data.get("ml_confidence", 0.0) * 100
        regime = live_data.get("regime", "medium_volatility")
        macro = live_data.get("macro", "Neytral")
        gate_reason = live_data.get("gate_reason", "Kutilmoqda")
        bull_ob = live_data.get("bullish_ob", "Aniqlanmadi")
        bear_ob = live_data.get("bearish_ob", "Aniqlanmadi")
        rsi_val = live_data.get("rsi", 50.0)

        weekend_note = (
            "DAM OLISH KUNI: Oltin (XAUUSD) va Forex birjalari yopiq! Kriptovalyuta (BTC/ETH) esa ochiq, "
            "lekin dam olish kunlari hajm past bo'lib, manipulyatsiyalar va soxta teskari harakatlar ehtimoli bor."
            if is_weekend else "ISH KUNI: Barcha jahon moliya birjalari jonli faoliyatda."
        )

        user_prompt = (
            f"JONLI BOZOR HAQIQATLARI (2026-yil, REAL VAQTDAGI HISOB-KITOBLAR):\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• Tahlil qilinayotgan Aktiv: {active_sym}\n"
            f"• Aniq Joriy Narx: ${cur_price:,.2f}\n"
            f"• Botning ML Modeli Ko'rsatkichi: {ml_sig} ({ml_conf:.1f}% ishonch)\n"
            f"• Bozor Rejimi: {regime}\n"
            f"• RSI (14) Indikatori: {rsi_val:.1f}\n"
            f"• Yaqin Bullish Order Block (Support / Qo'llab-quvvatlash): {bull_ob}\n"
            f"• Yaqin Bearish Order Block (Resistance / Qarshilik): {bear_ob}\n"
            f"• AQSH Dollari (DXY) Ta'siri: {macro}\n"
            f"• Botning Qarori va Sababi: {gate_reason}\n"
            f"• Kalendar Holati: Bugun {day_str}. {weekend_note}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Foydalanuvchi Fikri / Savoli: \"{user_message}\"\n\n"
            f"Iltimos, ushbu haqiqiy jonli raqamlarga asoslanib, foydalanuvchining savoliga "
            f"to'g'ridan-to'g'ri, samimiy va professional tahlil bilan javob ber. "
            f"Eski $30,000 lik narxlarni aslo yozma! Faqat hozirgi ${cur_price:,.2f} narx va darajalardan kelib chiqib amaliy xulosa ber."
        )

        # 4. Query Groq API
        if self.api_key:
            try:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": self.model_name,
                    "messages": [
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.35,
                    "max_tokens": 800,
                }

                timeout = aiohttp.ClientTimeout(total=20)
                models_to_try = [self.model_name, "openai/gpt-oss-120b", "qwen/qwen3.8-27b"]
                seen = set()
                models_to_try = [m for m in models_to_try if not (m in seen or seen.add(m))]

                for mod in models_to_try:
                    payload["model"] = mod
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        async with session.post(self.api_url, headers=headers, json=payload) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                content = data["choices"][0]["message"]["content"]
                                if "<think>" in content and "</think>" in content:
                                    content = content.split("</think>")[-1].strip()
                                return content.strip()
                            else:
                                err_text = await resp.text()
                                logger.warning(f"Groq API error on model {mod} ({resp.status}): {err_text}")
            except Exception as e:
                logger.error(f"Error querying Groq AI: {e}")

        # Fallback response
        return self._generate_heuristic_response(user_message, live_data)

    def _generate_heuristic_response(
        self,
        msg: str,
        ctx: Optional[Dict[str, Any]],
    ) -> str:
        """Rule-based analytical response fallback."""
        symbol = ctx.get("symbol", "BTCUSDT") if ctx else "BTCUSDT"
        price = ctx.get("current_price", 0.0) if ctx else 0.0
        regime = ctx.get("regime", "medium_volatility") if ctx else "medium_volatility"
        signal = ctx.get("ml_signal", "HOLD") if ctx else "HOLD"
        conf = ctx.get("ml_confidence", 0.0) * 100 if ctx else 0.0
        reason = ctx.get("gate_reason", "Bozor tasdiqni kutmoqda") if ctx else "Bozor tasdiqni kutmoqda"

        return (
            f"📊 <b>{symbol} JONLI BOZOR TAHLILI:</b>\n\n"
            f"• <b>Joriy Narx:</b> <code>${price:,.2f}</code>\n"
            f"• <b>AI Xulosasi:</b> <b>{signal}</b> ({conf:.1f}% ishonch)\n"
            f"• <b>Bozor Rejimi:</b> <i>{regime}</i>\n"
            f"• <b>Botning Qarori:</b> {reason}\n\n"
            f"💡 <b>Tavsiya:</b> Dam olish kunida hajm past bo'lganligi sababli, "
            f"narx asosiy qo'llab-quvvatlash yoki qarshilik zonalarini sinab, hajm bilan tasdiqlamaguncha shoshilmaslik tavsiya etiladi."
        )
