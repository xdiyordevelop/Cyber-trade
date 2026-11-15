"""
Cyber Trade - Next-Gen Hybrid Multi-Agent Conversational AI Assistant
=====================================================================
Dual-Engine Hybrid Architecture (Google Gemini + Groq LPU):

1. Google Gemini Multi-Agent Tier:
   - Gemini 3.8 Flash: Asosiy bozor tahlilchisi va strategik suhbat agenti.
   - Gemini 3.5 Flash-Lite: Tezkor, soniyalik yengil so'rovlar va qisqa xulosalar.
   - Gemini 3.1 Pro Preview: Murakkab ziddiyatlarni (SMC vs ML) yechuvchi chuqur tahlil.
   - Smart Resilience Cascade: gemini-3.8-flash -> gemini-3.5-flash-lite -> gemini-2.5-flash -> gemini-2.0-flash -> gemini-1.5-flash.

2. Groq Ultra-Fast LPU Engine Tier (High-Speed Failover & Parallel Hybrid):
   - Primary: llama-3.3-70b-versatile (Tezkor va yuqori aql-idrokli treyder modeli).
   - Lite/Fast: llama-3.1-8b-instant (0.2 soniyalik javob).
   - Backup: mixtral-8x7b-32768, deepseek-r1-distill-llama-70b.

3. 100% Real-Time Market Grounding (Anti-Hallucination):
   - Jonli narx, 1H trend, SMC zonalar (Order Block, FVG, BOS, Swing High/Low).
   - XGBoost AI signali va ishonch foizi, HMM bozor rejimi, Makro DXY va Yangiliklar taqvimi.

4. Multi-Turn Session Memory (Suhbat xotirasi):
   - Har bir foydalanuvchi suhbat konteksti va oxirgi muhokama qilingan aktivni eslab qoladi.

5. Safe Telegram HTML Sanitizer:
   - Telegram API da 400 Bad Request bo'lmasligi uchun Markdown belgilari toza HTML ga o'giriladi.
"""

import os
import re
import html
from collections import deque
from pathlib import Path
from datetime import datetime, timezone
import aiohttp
from typing import Dict, Any, Optional, List, Deque
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
    if any(w in t for w in ["dxy", "dollar", "aqsh dollari", "usdx"]):
        return "DXY"
    return None


def is_complex_query(text: str) -> bool:
    """Determine if query requires deep reasoning by Gemini 3.1 Pro / LLaMA 70B."""
    t = text.lower()
    triggers = [
        "tahlil", "analiz", "chuqur", "qarama-qarshi", "strategiya",
        "sabab", "nega", "qanday qilib", "xulosa", "hisobot", "prognoz",
        "detailed", "explain", "why", "structure", "reversal", "order block", "fvg"
    ]
    return any(tr in t for tr in triggers) or len(text.split()) > 8


def is_lightweight_query(text: str) -> bool:
    """Determine if query is simple enough for ultra-fast Gemini 3.5 Flash-Lite."""
    t = text.lower().strip()
    lite_triggers = ["salom", "qalesiz", "narx", "price", "status", "holat", "kim bu", "yordam", "help", "rahmat"]
    return any(t == lt or t.startswith(lt) for lt in lite_triggers) or len(text.split()) <= 3


def format_telegram_html(text: str) -> str:
    """
    Convert Markdown formatting into safe Telegram HTML tags.
    Prevents Telegram API 400 'can't parse entities' errors.
    """
    if not text:
        return ""

    out = text

    # Strip reasoning tags if present (e.g. from DeepSeek R1)
    if "<think>" in out and "</think>" in out:
        out = out.split("</think>")[-1].strip()

    # Pre-formatted code blocks ```python ... ``` -> <pre><code>...</code></pre>
    def replace_code_block(match):
        code_content = match.group(2)
        return f"<pre><code>{html.escape(code_content)}</code></pre>"

    out = re.sub(r"```([a-zA-Z0-9_+-]*)\n?(.*?)```", replace_code_block, out, flags=re.DOTALL)

    # Inline code `code` -> <code>code</code>
    def replace_inline_code(match):
        return f"<code>{html.escape(match.group(1))}</code>"

    out = re.sub(r"`([^`]+)`", replace_inline_code, out)

    # Bold **text** or __text__ -> <b>text</b>
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    out = re.sub(r"__(.+?)__", r"<b>\1</b>", out)

    # Markdown Headers (### Header) -> <b>Header</b>
    out = re.sub(r"^[ \t]*#{1,6}\s*(.+)$", r"<b>\1</b>", out, flags=re.MULTILINE)

    # Italic *text* or _text_ -> <i>text</i> (careful not to match inside words)
    out = re.sub(r"(?<!\w)\*([^*]+?)\*(?!\w)", r"<i>\1</i>", out)
    out = re.sub(r"(?<!\w)_([^_]+?)_(?!\w)", r"<i>\1</i>", out)

    # Convert markdown bullet points to clean unicode bullets
    out = re.sub(r"^\s*[\*\-]\s+", "• ", out, flags=re.MULTILINE)

    return out.strip()


class ConversationMemory:
    """
    Multi-Turn Chat Context and Active Asset Memory per Telegram Chat ID.
    Keeps last 6 messages per user to preserve conversational continuity.
    """

    def __init__(self, max_turns: int = 6):
        self.max_turns = max_turns
        self.sessions: Dict[str, Dict[str, Any]] = {}

    def get_session(self, chat_id: str) -> Dict[str, Any]:
        if chat_id not in self.sessions:
            self.sessions[chat_id] = {
                "history": deque(maxlen=self.max_turns),
                "last_symbol": None,
                "updated_at": datetime.now(timezone.utc),
            }
        return self.sessions[chat_id]

    def get_history(self, chat_id: str) -> List[Dict[str, str]]:
        session = self.get_session(chat_id)
        return list(session["history"])

    def add_turn(self, chat_id: str, user_text: str, assistant_text: str, symbol: Optional[str] = None):
        session = self.get_session(chat_id)
        session["history"].append({"role": "user", "content": user_text})
        session["history"].append({"role": "assistant", "content": assistant_text})
        if symbol:
            session["last_symbol"] = symbol
        session["updated_at"] = datetime.now(timezone.utc)

    def get_last_symbol(self, chat_id: str) -> Optional[str]:
        return self.get_session(chat_id).get("last_symbol")


class MarketAIAssistant:
    """
    Next-Gen Hybrid Multi-Agent (Google Gemini + Groq LPU) Trading Assistant.
    """

    def __init__(
        self,
        gemini_api_key: Optional[str] = None,
        groq_api_key: Optional[str] = None,
        api_key: Optional[str] = None,          # Backward compatibility
        model_name: Optional[str] = None,       # Backward compatibility
        primary_model: str = "gemini-3.8-flash",
        lite_model: str = "gemini-3.5-flash-lite",
        complex_model: str = "gemini-3.1-pro-preview",
        groq_model: str = "llama-3.3-70b-versatile",
        **kwargs,
    ):
        # API Keys
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY", "") or (api_key if api_key and not api_key.startswith("gsk_") else "")
        self.groq_api_key = groq_api_key or os.getenv("GROQ_API_KEY", "") or (api_key if api_key and api_key.startswith("gsk_") else "")

        # Gemini Models
        self.primary_model = os.getenv("AI_MODEL_PRIMARY", primary_model)
        self.lite_model = os.getenv("AI_MODEL_LITE", lite_model)
        self.complex_model = os.getenv("AI_MODEL_COMPLEX", complex_model)

        # Groq Models
        self.groq_model = os.getenv("GROQ_MODEL_NAME", groq_model or model_name or "llama-3.3-70b-versatile")

        # Endpoints
        self.gemini_base_url = "https://generativelanguage.googleapis.com/v1beta/models"
        self.groq_base_url = "https://api.groq.com/openai/v1/chat/completions"

        # Multi-Turn Memory
        self.memory = ConversationMemory(max_turns=6)

        # Master System Instructions
        self.system_prompt = (
            "Sen 'Cyber Trade' professional sun'iy intellekt bozor tahlilchisisan (10 yillik tajribali treyder darajasida).\n\n"
            "Sening vazifang — foydalanuvchi savollariga bozorning REAL JONLI MA'LUMOTLARI (SMC, Order Block, FVG, 1H Trend va XGBoost ML) asosida "
            "aniq, xolis, do'stona va professional tahlil berish.\n\n"
            "QAT'IY QOIDALAR:\n"
            "1. JONLI HAQIQATGA ASOSLAN: Quyida berilgan aniq joriy narx va bot hisob-kitoblaridan foydalan. O'zingdan narx to'qima!\n"
            "2. TREYDERONA FIKRLA: Nega narx o'syapti yoki tushyapti, likvidlik qayerda, kirish xavfsizmi yoki yo'qmi — tushuntir.\n"
            "3. DAM OLISH KUNLARINI (SHANBA/YAKSHANBA) INOBATGA OL: Oltin va Forex birjalari yopiqligini, Kriptoda esa hajm pastligini eslat.\n"
            "4. QULAY FORMAT: Hech qanday markdown jadval (table) tuzma! Chiroyli qisqa xulosalar bilan 3 qismda javob ber:\n"
            "   • 1-qism: Hozirgi jonli holat va narx\n"
            "   • 2-qism: Asosiy darajalar (Order Block, FVG, Trend va RSI)\n"
            "   • 3-qism: Aniq amaliy xulosa (Hozir nima qilish kerak?)\n"
            "5. O'zbek tilida ravon, samimiy va professional tilda javob ber."
        )

        # Log system status
        providers = []
        if self.gemini_api_key:
            providers.append(f"Google Gemini ({self.primary_model} / {self.lite_model})")
        if self.groq_api_key:
            providers.append(f"Groq LPU ({self.groq_model})")
        
        if providers:
            logger.info(f"Hybrid AI Assistant initialized: {' + '.join(providers)}")
        else:
            logger.warning("No LLM API keys detected. Intelligent local heuristic engine active.")

    # -------------------------------------------------------------------------
    # 1. Google Gemini REST API Client
    # -------------------------------------------------------------------------
    async def _call_gemini_api(
        self,
        model: str,
        user_prompt: str,
        history: Optional[List[Dict[str, str]]] = None,
        timeout_seconds: int = 10,
    ) -> Optional[str]:
        """Direct asynchronous call to Google Gemini REST API."""
        if not self.gemini_api_key:
            return None

        url = f"{self.gemini_base_url}/{model}:generateContent?key={self.gemini_api_key}"

        # Build contents with conversation history
        contents = []
        if history:
            for turn in history[-4:]:
                role = "user" if turn["role"] == "user" else "model"
                contents.append({"role": role, "parts": [{"text": turn["content"]}]})

        # Append current turn with grounding instructions
        contents.append({
            "role": "user",
            "parts": [{"text": f"{self.system_prompt}\n\n{user_prompt}"}]
        })

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.35,
                "maxOutputTokens": 850,
            }
        }

        try:
            timeout = aiohttp.ClientTimeout(total=timeout_seconds)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        candidates = data.get("candidates", [])
                        if candidates and "content" in candidates[0]:
                            parts = candidates[0]["content"].get("parts", [])
                            if parts and "text" in parts[0]:
                                text = parts[0]["text"].strip()
                                logger.info(f"⚡ [Gemini {model}] Responded successfully.")
                                return text
                    else:
                        err_text = await resp.text()
                        logger.warning(f"Gemini API ({model}) returned {resp.status}: {err_text[:120]}")
        except Exception as e:
            logger.warning(f"Gemini request failed on {model}: {e}")
        return None

    # -------------------------------------------------------------------------
    # 2. Groq LPU Ultra-Fast REST API Client
    # -------------------------------------------------------------------------
    async def _call_groq_api(
        self,
        model: str,
        user_prompt: str,
        history: Optional[List[Dict[str, str]]] = None,
        timeout_seconds: int = 12,
    ) -> Optional[str]:
        """Direct asynchronous call to Groq Ultra-Fast LPU Inference API."""
        if not self.groq_api_key:
            return None

        headers = {
            "Authorization": f"Bearer {self.groq_api_key}",
            "Content-Type": "application/json",
        }

        messages = [{"role": "system", "content": self.system_prompt}]
        if history:
            for turn in history[-4:]:
                messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append({"role": "user", "content": user_prompt})

        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.35,
            "max_tokens": 850,
        }

        try:
            timeout = aiohttp.ClientTimeout(total=timeout_seconds)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self.groq_base_url, headers=headers, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        choices = data.get("choices", [])
                        if choices and "message" in choices[0]:
                            content = choices[0]["message"].get("content", "").strip()
                            if "<think>" in content and "</think>" in content:
                                content = content.split("</think>")[-1].strip()
                            logger.info(f"⚡ [Groq {model}] Responded successfully.")
                            return content
                    else:
                        err_text = await resp.text()
                        logger.warning(f"Groq API ({model}) returned {resp.status}: {err_text[:120]}")
        except Exception as e:
            logger.warning(f"Groq request failed on {model}: {e}")
        return None

    # -------------------------------------------------------------------------
    # 3. Master Hybrid Query Responder
    # -------------------------------------------------------------------------
    async def answer_user_query(
        self,
        user_message: str,
        market_context: Optional[Dict[str, Any]] = None,
        signal_engine = None,
        data_fetcher = None,
        chat_id: Optional[str] = None,
    ) -> str:
        """
        Hybrid multi-agent pipeline:
        1. Context extraction & Real-Time market grounding
        2. Gemini Tier routing (3.8 Flash / 3.5 Lite / 3.1 Pro)
        3. Groq Tier failover (LLaMA 3.3 70B / 8B / Mixtral)
        4. Local deterministic trading intelligence fallback
        5. Safe Telegram HTML formatting & multi-turn memory update
        """
        cid = str(chat_id) if chat_id else "global_chat"

        # 1. Detect target asset (from text or previous conversation turn)
        detected_sym = detect_symbol_from_text(user_message)
        last_sym = self.memory.get_last_symbol(cid)
        active_sym = detected_sym or last_sym or (market_context.get("symbol") if market_context else None) or "BTCUSDT"

        live_data = dict(market_context or {})
        live_data["symbol"] = active_sym

        # 2. On-demand live analysis for real-time grounding
        if signal_engine and data_fetcher:
            try:
                fetch_sym = active_sym
                if "BTC" in active_sym:
                    fetch_sym = "BTC-USD"
                elif "ETH" in active_sym:
                    fetch_sym = "ETH-USD"
                elif "XAU" in active_sym or "GOLD" in active_sym:
                    fetch_sym = "GC=F"

                df = await data_fetcher.get_market_data(fetch_sym, timeframe="15m")
                dxy_df = await data_fetcher.get_market_data("DXY", timeframe="15m")
                if df is not None and len(df) >= 30:
                    _, fresh_meta = await signal_engine.analyze_and_generate_signal(
                        symbol=active_sym,
                        df=df,
                        dxy_df=dxy_df,
                        timeframe="15m",
                    )
                    live_data.update(fresh_meta)
            except Exception as e:
                logger.error(f"Error fetching on-demand live context for {active_sym}: {e}")

        # Extract live indicators
        cur_price = float(live_data.get("current_price", 0.0))
        ml_sig = live_data.get("ml_signal", "HOLD")
        ml_conf = float(live_data.get("ml_confidence", 0.0)) * 100
        regime = live_data.get("regime", "Barqaror")
        macro = live_data.get("macro", "Neytral")
        gate_reason = live_data.get("gate_reason", "Bozor tasdiqini kutmoqda")
        htf_trend = live_data.get("htf_trend", "NEUTRAL")

        # Weekend market awareness
        now_utc = datetime.now(timezone.utc)
        day_str = datetime.now().strftime("%A")
        is_weekend = (now_utc.weekday() == 4 and now_utc.hour >= 22) or (now_utc.weekday() == 5) or (now_utc.weekday() == 6 and now_utc.hour < 22)

        weekend_note = (
            "DAM OLISH KUNI: Oltin (XAUUSD) va Forex birjalari yopiq! Kriptovalyuta (BTC/ETH) esa 24/7 ochiq, "
            "lekin dam olish kunlari hajm pastligi sababli soxta harakatlar (fakeout) xavfi yuqori bo'ladi."
            if is_weekend else "ISH KUNI: Jahon moliya birjalari jonli faoliyatda."
        )

        user_prompt = (
            f"JONLI BOZOR HAQIQATLARI (REAL VAQTDAGI MA'LUMOTLAR):\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• Aktiv: #{active_sym}\n"
            f"• Aniq Joriy Narx: ${cur_price:,.2f}\n"
            f"• Katta 1H Trend: {htf_trend}\n"
            f"• AI Modeli: {ml_sig} ({ml_conf:.1f}% ishonch)\n"
            f"• Bozor Rejimi: {regime}\n"
            f"• Makro DXY Holati: {macro}\n"
            f"• Botning Qarori: {gate_reason}\n"
            f"• Kalendar: Bugun {day_str}. {weekend_note}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Foydalanuvchi Savoli: \"{user_message}\"\n\n"
            f"Yuqoridagi real narx va ko'rsatkichlarga tayanib, foydalanuvchining savoliga "
            f"to'g'ridan-to'g'ri, samimiy va professional tahlil bilan javob ber. "
            f"Hozirgi ${cur_price:,.2f} narx va darajalardan kelib chiqib aniq amaliy tavsiya ber."
        )

        history = self.memory.get_history(cid)
        reply_raw: Optional[str] = None

        # ---------------------------------------------------------------------
        # Tier 1: Google Gemini Multi-Agent Routing
        # ---------------------------------------------------------------------
        if self.gemini_api_key:
            # Route A: Complex analysis -> Gemini 3.1 Pro / 3.8 Flash
            if is_complex_query(user_message):
                complex_cascade = [
                    self.complex_model,       # gemini-3.1-pro-preview
                    self.primary_model,       # gemini-3.8-flash
                    "gemini-2.5-pro",
                    "gemini-pro-latest",
                    "gemini-2.5-flash",
                ]
                for mod in complex_cascade:
                    reply_raw = await self._call_gemini_api(mod, user_prompt, history=history, timeout_seconds=9)
                    if reply_raw:
                        break

            # Route B: Quick / Lite query -> Gemini 3.5 Flash-Lite
            elif is_lightweight_query(user_message):
                lite_cascade = [
                    self.lite_model,          # gemini-3.5-flash-lite
                    "gemini-flash-lite-latest",
                    "gemini-2.5-flash-lite",
                    "gemini-2.5-flash",
                ]
                for mod in lite_cascade:
                    reply_raw = await self._call_gemini_api(mod, user_prompt, history=history, timeout_seconds=7)
                    if reply_raw:
                        break

            # Route C: Primary Trading Agent -> Gemini 3.8 Flash with fast fallback cascade
            if not reply_raw:
                primary_cascade = [
                    self.primary_model,       # gemini-3.8-flash
                    self.lite_model,          # gemini-3.5-flash-lite
                    "gemini-2.5-flash",       # Verified ultra-fast (0.7s)
                    "gemini-flash-latest",
                    "gemini-flash-lite-latest",
                ]
                seen = set()
                unique_cascade = [m for m in primary_cascade if not (m in seen or seen.add(m))]
                for mod in unique_cascade:
                    reply_raw = await self._call_gemini_api(mod, user_prompt, history=history, timeout_seconds=8)
                    if reply_raw:
                        break

        # ---------------------------------------------------------------------
        # Tier 2: Groq Ultra-Fast LPU Engine (Failover / Hybrid Parallel)
        # ---------------------------------------------------------------------
        if not reply_raw and self.groq_api_key:
            logger.info("Failing over to Groq LPU Engine...")
            groq_cascade = [
                self.groq_model,              # llama-3.3-70b-versatile
                "llama-3.1-8b-instant",
                "mixtral-8x7b-32768",
                "deepseek-r1-distill-llama-70b",
            ]
            seen_g = set()
            unique_groq = [m for m in groq_cascade if not (m in seen_g or seen_g.add(m))]
            for gmod in unique_groq:
                reply_raw = await self._call_groq_api(gmod, user_prompt, history=history, timeout_seconds=8)
                if reply_raw:
                    break

        # ---------------------------------------------------------------------
        # Tier 3: Local Deterministic Trading Intelligence Fallback
        # ---------------------------------------------------------------------
        if not reply_raw:
            logger.info("Using local heuristic analytical fallback.")
            reply_raw = self._generate_heuristic_response(user_message, live_data)

        # Format cleanly for Telegram HTML
        final_reply = format_telegram_html(reply_raw)

        # Update multi-turn memory
        self.memory.add_turn(cid, user_message, final_reply, symbol=active_sym)

        return final_reply

    def _generate_heuristic_response(
        self,
        msg: str,
        ctx: Optional[Dict[str, Any]],
    ) -> str:
        """Dynamic rule-based analytical response fallback."""
        symbol = ctx.get("symbol", "BTCUSDT") if ctx else "BTCUSDT"
        price = ctx.get("current_price", 0.0) if ctx else 0.0
        regime = ctx.get("regime", "Barqaror") if ctx else "Barqaror"
        signal = ctx.get("ml_signal", "HOLD") if ctx else "HOLD"
        conf = ctx.get("ml_confidence", 0.0) * 100 if ctx else 0.0
        reason = ctx.get("gate_reason", "Bozor tasdiqni kutmoqda") if ctx else "Bozor tasdiqni kutmoqda"
        trend = ctx.get("htf_trend", "NEUTRAL") if ctx else "NEUTRAL"

        return (
            f"📊 <b>#{symbol} BOZOR TAHLILI:</b>\n\n"
            f"• <b>Joriy Narx:</b> <code>${price:,.2f}</code>\n"
            f"• <b>1H Trend:</b> <code>{trend}</code>\n"
            f"• <b>AI Xulosasi:</b> <b>{signal}</b> ({conf:.1f}% ishonch)\n"
            f"• <b>Bozor Rejimi:</b> <i>{regime}</i>\n"
            f"• <b>Bot Qarori:</b> {reason}\n\n"
            f"💡 <b>Tavsiya:</b> Hozirgi bozor sharoitida narx asosiy zonani tasdiqlamaguncha "
            f"shoshilmaslik va keyingi 15m sham yopilishini kutish maqsadga muvofiq."
        )
