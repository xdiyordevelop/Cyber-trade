"""
Cyber Trade - Telegram Bot & Broadcast Engine
=============================================
Pure async HTTP Telegram client (aiohttp-based).
No heavy external wrappers - lightweight, fast, 100% free cloud compatible.

Features:
- Sleek, intuitive persistent reply menu & command palette
- Multi-Timeframe (H4 / H1 / M15) market status & conflict reporting
- Transparent Diagnostic Auditor (/why <symbol>)
- Pre-News Sentinel alerts & live economic calendar status (/news)
- Precision virtual prop-firm performance accounting (/stats)
- Real-time trailing alerts (TP1 hit -> Move SL to BE)
- Integrated Hybrid Conversational AI Assistant (Gemini 3.8 / 3.5 Lite + Groq)
"""

import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any
import aiohttp
from loguru import logger

from src.signal_engine import GeneratedSignal, SignalEngine
from src.signal_tracker import SignalTracker
from src.ai_chat import MarketAIAssistant
from src.data_fetcher import UniversalDataFetcher
from src.database import db

# Persistent Interactive Reply Menu
DEFAULT_KEYBOARD = {
    "keyboard": [
        [{"text": "📊 Bozor Holati (/status)"}, {"text": "⚡ Signallar (/signals)"}],
        [{"text": "🔍 Oltin Nega? (/why XAUUSD)"}, {"text": "🔍 BTC Nega? (/why BTC)"}],
        [{"text": "⚙️ Rejim (/mode)"}, {"text": "📈 Statistika (/stats)"}],
        [{"text": "📰 Yangiliklar (/news)"}, {"text": "📖 Qo'llanma (/help)"}],
    ],
    "resize_keyboard": True,
    "persistent": True,
}


class CyberTelegramBot:
    """
    Lightweight, resilient Telegram Bot & Broadcast Engine.
    """

    def __init__(
        self,
        token: str,
        channel_id: str = "",
        admin_chat_ids: Optional[List[str]] = None,
        signal_engine: Optional[SignalEngine] = None,
        signal_tracker: Optional[SignalTracker] = None,
        data_fetcher: Optional[UniversalDataFetcher] = None,
        ai_assistant: Optional[MarketAIAssistant] = None,
    ):
        self.token = token
        self.api_url = f"https://api.telegram.org/bot{self.token}"
        self.channel_id = channel_id
        self.admin_chat_ids = list(set(admin_chat_ids or []))
        # Merge saved subscribers from SQLite database
        for sub in db.get_all_subscribers():
            if sub not in self.admin_chat_ids:
                self.admin_chat_ids.append(sub)
        self.signal_engine = signal_engine
        self.signal_tracker = signal_tracker
        self.data_fetcher = data_fetcher or UniversalDataFetcher()
        self.ai_assistant = ai_assistant or MarketAIAssistant()
        self._last_update_id = 0
        self._running = False
        self._latest_context: Dict[str, Any] = {}

    def set_latest_context(self, ctx: Dict[str, Any]):
        """Cache latest market analysis context for the AI chat assistant."""
        self._latest_context.update(ctx)

    # -------------------------------------------------------------------------
    # Core HTTP Telegram API Methods
    # -------------------------------------------------------------------------
    async def send_message(
        self,
        chat_id: str,
        text: str,
        parse_mode: str = "HTML",
        disable_web_page_preview: bool = True,
        reply_markup: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Send a text message via Telegram Bot API with clean markup fallback."""
        if not self.token or not chat_id:
            return False

        # Attach default reply menu for individual user private chats
        markup = reply_markup
        if markup is None and not str(chat_id).startswith("-") and not str(chat_id).startswith("@"):
            markup = DEFAULT_KEYBOARD

        url = f"{self.api_url}/sendMessage"
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_web_page_preview,
        }
        if markup:
            payload["reply_markup"] = markup

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        return True
                    err = await resp.text()
                    logger.warning(f"Telegram sendMessage error ({resp.status}): {err}")
                    # Auto fallback to plain text if HTML parsing fails (prevents silent message drops)
                    if parse_mode == "HTML" and resp.status == 400:
                        logger.info(f"Retrying message delivery to {chat_id} in plain text mode...")
                        plain_payload = dict(payload)
                        plain_payload.pop("parse_mode", None)
                        async with session.post(url, json=plain_payload) as retry_resp:
                            return retry_resp.status == 200
                    return False
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False

    async def send_photo(
        self,
        chat_id: str,
        photo_path: str,
        caption: str = "",
        parse_mode: str = "HTML",
        reply_markup: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Upload and send a chart photo directly to Telegram."""
        if not self.token or not chat_id:
            return False

        path = Path(photo_path)
        if not path.exists():
            logger.warning(f"Chart photo file not found: {photo_path}. Sending text caption instead.")
            return await self.send_message(chat_id, caption, parse_mode=parse_mode, reply_markup=reply_markup)

        url = f"{self.api_url}/sendPhoto"
        try:
            data = aiohttp.FormData()
            data.add_field("chat_id", str(chat_id))
            data.add_field("caption", caption)
            data.add_field("parse_mode", parse_mode)
            if reply_markup:
                import json
                data.add_field("reply_markup", json.dumps(reply_markup))

            with open(path, "rb") as f:
                photo_bytes = f.read()

            data.add_field(
                "photo",
                photo_bytes,
                filename=path.name,
                content_type="image/png",
            )

            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data) as resp:
                    if resp.status == 200:
                        return True
                    err = await resp.text()
                    logger.warning(f"Telegram sendPhoto error ({resp.status}): {err}")
                    # Fallback to plain message
                    return await self.send_message(chat_id, caption, parse_mode=parse_mode, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Failed to send Telegram photo: {e}")
            return await self.send_message(chat_id, caption, parse_mode=parse_mode, reply_markup=reply_markup)

    async def broadcast_signal(self, signal: GeneratedSignal):
        """Broadcast newly generated A+ signal with chart snapshot."""
        text = signal.to_telegram_message()

        targets = list(self.admin_chat_ids)
        if self.channel_id and self.channel_id not in targets:
            targets.append(self.channel_id)

        for target in targets:
            if signal.chart_image_path:
                await self.send_photo(target, signal.chart_image_path, caption=text)
            else:
                await self.send_message(target, text)
            await asyncio.sleep(0.05)

    async def broadcast_alert(self, alert_text: str):
        """Broadcast live trailing, breakeven, or news alerts to all subscribers."""
        targets = list(self.admin_chat_ids)
        if self.channel_id and self.channel_id not in targets:
            targets.append(self.channel_id)

        for target in targets:
            await self.send_message(target, alert_text)
            await asyncio.sleep(0.05)

    # -------------------------------------------------------------------------
    # Interactive Command & Chat Handler
    # -------------------------------------------------------------------------
    async def _handle_update(self, update: Dict[str, Any]):
        """Process incoming user updates (commands, button presses, and AI queries)."""
        message = update.get("message")
        if not message:
            return

        chat = message.get("chat", {})
        chat_id = str(chat.get("id"))
        username = chat.get("username", "")
        first_name = chat.get("first_name", "")
        text = message.get("text", "").strip()

        if not text:
            return

        # Auto-register user in SQLite DB so broadcasts reach this user permanently
        db.register_user(chat_id, username=username, first_name=first_name)
        if chat_id not in self.admin_chat_ids:
            self.admin_chat_ids.append(chat_id)
            logger.info(f"Registered subscriber {chat_id} (@{username}) in DB.")

        logger.info(f"Received Telegram message from {chat_id}: {text}")
        t_low = text.lower()

        # ---------------------------------------------------------------------
        # Command: /start
        # ---------------------------------------------------------------------
        if text.startswith("/start"):
            welcome = (
                "👋 <b>Assalomu alaykum! Cyber Trade Multi-Agent AI tizimiga xush kelibsiz.</b>\n\n"
                "Men Oltin (XAUUSD), Bitcoin (BTC), Ethereum (ETH) va boshqa bozorlarni "
                "<b>Multi-Timeframe (H4/H1/M15)</b>, <b>Smart Money Concepts (SMC)</b> va <b>XGBoost AI</b> "
                "yordamida 24/7 monitoring qiluvchi avtonom tahlilchiman.\n\n"
                "📌 <b>ASOSIY BUYRUQLAR:</b>\n"
                "• <code>/status</code> — Bozor holati va MTF sessiyalar\n"
                "• <code>/signals</code> — Hozirgi ochiq signallar va jonli pips\n"
                "• <code>/why XAUUSD</code> — <b>Nega signal yo'q?</b> (To'liq audit hisoboti)\n"
                "• <code>/analyze BTC</code> — Aktivni ayni soniyada to'liq tekshirish\n"
                "• <code>/news</code> — Iqtisodiy taqvim va yaqinlashayotgan yangiliklar\n"
                "• <code>/mode</code> — Signallar chastotasi filtri (50%, 58%, 68%)\n"
                "• <code>/stats</code> — Aniq Win-Rate va foyda statistikasi\n"
                "• <code>/help</code> — To'liq tizim yo'riqnomasi\n\n"
                "💬 <b>AI CHAT:</b> Pastdagi tugmalardan foydalaning yoki menga to'g'ridan-to'g'ri istalgan savolingizni yozing "
                "(masalan: <i>'Oltinda vaziyat qanday?'</i>) — sun'iy intellekt zudlik bilan javob beradi!"
            )
            await self.send_message(chat_id, welcome, reply_markup=DEFAULT_KEYBOARD)
            return

        # ---------------------------------------------------------------------
        # Command: /why or button clicks (Oltin Nega? / BTC Nega?)
        # ---------------------------------------------------------------------
        if text.startswith("/why") or "nega" in t_low:
            sym = "XAUUSD"
            if "btc" in t_low or "bitcoin" in t_low:
                sym = "BTCUSDT"
            elif "eth" in t_low or "efir" in t_low:
                sym = "ETHUSDT"
            elif "sol" in t_low:
                sym = "SOLUSDT"
            elif len(text.split()) > 1:
                sym = text.split()[1].upper()

            await self.send_message(chat_id, f"🔍 <b>#{sym}</b> bo'yicha sifat nazorati va MTF auditi o'tkazilmoqda...")
            try:
                if self.signal_engine:
                    audit_msg = await self.signal_engine.get_diagnostic_audit(sym, self.data_fetcher)
                    await self.send_message(chat_id, audit_msg)
                else:
                    await self.send_message(chat_id, "ℹ️ Tahlil dvigateli ishga tushirilmoqda...")
            except Exception as e:
                logger.error(f"Error handling /why: {e}")
                await self.send_message(chat_id, f"❌ Audit tekshiruvida xatolik: {e}")
            return

        # ---------------------------------------------------------------------
        # Command: /news or button "Yangiliklar"
        # ---------------------------------------------------------------------
        if text.startswith("/news") or "yangiliklar" in t_low:
            if self.signal_engine:
                news_status = await self.signal_engine.news_sentinel.check_news_safety("USD")
                online_badge = "🟢 ONLINE" if news_status.calendar_online else "🔴 OFFLINE (Keshdan olinmoqda)"
                schedule_text = self.signal_engine.news_sentinel.get_forexfactory_schedule(limit=6)

                msg = (
                    f"📰 <b>FOREX FACTORY — IQTISODIY YANGILIKLAR TAQVIMI</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🌐 <b>Taqvim Oqimi:</b> {online_badge}\n"
                    f"🛡️ <b>Hozirgi Holat:</b> <b>{news_status.status}</b>\n"
                    f"ℹ️ <b>Tahlil:</b> {news_status.warning_text}\n\n"
                    f"📅 <b>FOREXFACTORY REJALASHTIRILGAN VOQEALAR:</b>\n\n"
                    f"{schedule_text}\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"<i>🔴 Qizil: Yuqori ta'sirli (High Impact) | 🟠 To'q sariq: O'rtacha (Medium)\n"
                    f"⚠️ Qoida: 🔴 High yangiliklardan 30 daqiqa oldin signallar avtomatik bloklanadi.</i>"
                )
            else:
                msg = "ℹ️ Yangiliklar moduli yuklanmoqda..."
            await self.send_message(chat_id, msg)
            return

        # ---------------------------------------------------------------------
        # Command: /mode [aggressive|standard|conservative|1|2|3]
        # ---------------------------------------------------------------------
        if text.startswith("/mode") or "rejim" in t_low:
            from src.signal_engine import SIGNAL_MODES
            parts = text.split()
            current_mode = self.signal_engine.active_mode if self.signal_engine else "standard"

            if len(parts) > 1:
                arg = parts[1].lower()
                target_mode = None
                if arg in ["1", "aggressive", "agressive", "scalp", "tezkor"]:
                    target_mode = "aggressive"
                elif arg in ["2", "standard", "standart", "normal", "balansli"]:
                    target_mode = "standard"
                elif arg in ["3", "conservative", "konservativ", "sniper"]:
                    target_mode = "conservative"

                if target_mode and self.signal_engine:
                    self.signal_engine.apply_mode(target_mode)
                    db.set_setting("signal_mode", target_mode)
                    cfg = SIGNAL_MODES[target_mode]
                    confirm_msg = (
                        f"✅ <b>REJIM O'ZGARTIRILDI:</b> {cfg['name']}\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🎯 <b>Minimal Ishonch:</b> <code>{cfg['threshold']*100:.0f}%</code>\n"
                        f"⚖️ <b>Minimal R:R:</b> <code>1:{cfg['min_rr']:.1f}</code>\n"
                        f"ℹ️ <i>{cfg['desc']}</i>\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"Endi bot yangi shartlar asosida signallarni chiqaradi!"
                    )
                    await self.send_message(chat_id, confirm_msg)
                    return

            cfg_now = SIGNAL_MODES.get(current_mode, SIGNAL_MODES["standard"])
            mode_menu = (
                f"⚙️ <b>CYBER TRADE — REJIMNI TANLASH (FILTR)</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Hozirgi faol rejim: <b>{cfg_now['name']}</b>\n\n"
                f"O'zgartirish uchun quyidagi buyruqlardan birini bosing:\n\n"
                f"1️⃣ <code>/mode 1</code> yoki <code>/mode aggressive</code>\n"
                f"⚡ <b>Agressiv Rejim (50%+):</b>\n"
                f"• Ko'p signallar (Scalping)\n"
                f"• Kichik ehtimollikda ham tezkor kirish-chiqishlar\n\n"
                f"2️⃣ <code>/mode 2</code> yoki <code>/mode standard</code>\n"
                f"⚖️ <b>Standart Rejim (58%+):</b>\n"
                f"• Oltin o'rtalik (Tavsiya etiladi)\n"
                f"• Mustahkam tasdiq bilan ishonchli A+ signallar\n\n"
                f"3️⃣ <code>/mode 3</code> yoki <code>/mode conservative</code>\n"
                f"🛡️ <b>Konservativ Rejim (68%+):</b>\n"
                f"• Sniper rejim (Faqat eng yuqori ishonchli A+ signallar)\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"<i>Rejimni o'zgartirish uchun masalan <code>/mode 1</code> deb yuboring!</i>"
            )
            await self.send_message(chat_id, mode_menu)
            return

        # ---------------------------------------------------------------------
        # Command: /status or button "Bozor Holati"
        # ---------------------------------------------------------------------
        if text.startswith("/status") or "bozor holati" in t_low:
            session = self._latest_context.get("session", "Off Hours")
            regime = self._latest_context.get("regime", "Trending")
            news = self._latest_context.get("news", "Bozor tinch")
            h4_trend = self._latest_context.get("h4_trend", "NEUTRAL")
            h1_trend = self._latest_context.get("htf_trend", "NEUTRAL")
            from src.signal_engine import SIGNAL_MODES
            curr_mode_id = self.signal_engine.active_mode if self.signal_engine else "standard"
            mode_name = SIGNAL_MODES.get(curr_mode_id, {}).get("name", "Standart (58%+)")
            is_weekend = self.signal_engine.session_filter.is_weekend() if self.signal_engine else False
            weekend_note = "\n🔴 <b>Dam Olish Kuni:</b> Oltin va Forex birjalari yopiq. Kriptovalyuta bozori 24/7 ochiq!" if is_weekend else ""

            status_msg = (
                f"📊 <b>CYBER TRADE — TIZIM VA BOZOR HOLATI</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"⚙️ <b>Signal Rejimi:</b> <b>{mode_name}</b>\n"
                f"🕒 <b>Aktiv Sessiya:</b> {session}\n"
                f"🌊 <b>Bozor Rejimi (HMM):</b> {regime}\n"
                f"📈 <b>MTF Kontekst:</b> H4 [{h4_trend}] | H1 [{h1_trend}]\n"
                f"📰 <b>Yangiliklar Qalqoni:</b> {news}{weekend_note}\n"
                f"⚡ <b>AI Council & Sentinel:</b> 24/7 Faol\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"<i>Nega signal yo'qligini bilish uchun <code>/why XAUUSD</code> deb yozing.</i>"
            )
            await self.send_message(chat_id, status_msg)
            return

        # ---------------------------------------------------------------------
        # Command: /stats or button "Statistika"
        # ---------------------------------------------------------------------
        if text.startswith("/stats") or "statistika" in t_low:
            if self.signal_tracker:
                perf = self.signal_tracker.get_performance_summary()
                stats_msg = (
                    f"📈 <b>CYBER TRADE — ANIQ STATISTIKA VA NATIJALAR</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🎯 <b>Jami Yakunlangan Savdolar:</b> {perf['total_signals']} ta\n"
                    f"🏆 <b>Win Rate:</b> <code>{perf['win_rate']:.1f}%</code>\n"
                    f"💰 <b>Sof Daromad (R:R):</b> <code>+{perf['total_r']:.2f}R</code>\n"
                    f"📊 <b>Profit Factor:</b> <code>{perf['profit_factor']:.2f}</code>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🎯 <b>To'liq TP2 Foyda (+2.0R):</b> {perf['tp2_count']} ta\n"
                    f"🛡️ <b>TP1 + Breakeven (+0.75R):</b> {perf['be_win_count']} ta\n"
                    f"🛑 <b>Stop-Loss (-1.0R):</b> {perf['sl_count']} ta\n"
                    f"⏱️ <b>24h Muddati Tugagan:</b> {perf['expired_count']} ta\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"<i>Hisob-kitob qat'iy prop-firm qoidasi (TP1 -> BE -> TP2) asosida yuritiladi.</i>"
                )
            else:
                stats_msg = "ℹ️ Statistika moduli ishga tushirilmoqda..."
            await self.send_message(chat_id, stats_msg)
            return

        # ---------------------------------------------------------------------
        # Command: /close or /clear
        # ---------------------------------------------------------------------
        if text.startswith("/close") or text.startswith("/clear"):
            if self.signal_tracker:
                count = self.signal_tracker.clear_all_signals()
                if count > 0:
                    close_msg = (
                        f"🛑 <b>OCHIQ SIGNALLAR QO'LDA YOPILDI:</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"Jami <b>{count} ta</b> faol signal muvaffaqiyatli yopildi va arxivga olindi.\n"
                        f"Bozor yangi A+ kirish nuqtalari uchun toza monitoring qilinmoqda."
                    )
                else:
                    close_msg = "ℹ️ Hozirda yopish uchun faol ochiq signallar yo'q."
            else:
                close_msg = "ℹ️ Signal kuzatuvchi modul faol emas."
            await self.send_message(chat_id, close_msg)
            return

        # ---------------------------------------------------------------------
        # Command: /help or button "Qo'llanma"
        # ---------------------------------------------------------------------
        if text.startswith("/help") or "qo'llanma" in t_low:
            help_msg = (
                "📖 <b>CYBER TRADE — TO'LIQ YO'RIQNOMA VA QO'LLANMA</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "Cyber Trade — ko'p agentli sun'iy intellekt va Smart Money Concepts (SMC) "
                "asosida ishlovchi professional bozor tahlilchisi va signallar tizimi.\n\n"
                "📌 <b>BUYRUQLAR RO'YXATI:</b>\n"
                "• <code>/status</code> — Bozor holati va sessiya ma'lumoti\n"
                "• <code>/signals</code> — Hozirgi ochiq signallar va jonli pips\n"
                "• <code>/why XAUUSD</code> — Nega signal yo'qligi bo'yicha to'liq audit\n"
                "• <code>/analyze BTC</code> — Aktivni hozirgi soniyada tahlil qilish\n"
                "• <code>/news</code> — Iqtisodiy taqvim va xavfli yangiliklar\n"
                "• <code>/mode</code> — Signallar chastotasi filtri (1: 50%, 2: 58%, 3: 68%)\n"
                "• <code>/stats</code> — Aniq Win-Rate va umumiy daromad statistikasi\n"
                "• <code>/close</code> — Ochiq signallarni qo'lda tozalash\n\n"
                "🎯 <b>VIRTUAL SIGNAL HISOBLASH QOIDASI:</b>\n"
                "1. <b>TP1 urilganda:</b> Bot 50% foydani olishni va Stop-Lossni Kirish narxiga (0 ga) surishni e'lon qiladi (+0.75R daromad zaxiralandi).\n"
                "2. <b>TP2 urilganda:</b> Qolgan 50% foyda bilan yopiladi (Jami: +2.0R).\n"
                "3. <b>Narx 0 ga qaytsa:</b> Qolgan 50% zararsiz yopiladi (Jami: +0.75R foyda).\n"
                "4. <b>Stop-Loss urilsa:</b> Qat'iy -1.0R risk bilan yopiladi.\n"
                "5. <b>24 soat o'tganda:</b> Harakatsiz signallar avtomatik yakunlanadi.\n\n"
                "💬 <b>AI SUHBAT:</b> Istalgan vaqt botga savol bering (masalan: <i>'Bitcoin olsam bo'ladimi?'</i>). "
                "AI tahlilchi ayni soniyadagi narxga tayanib javob beradi!"
            )
            await self.send_message(chat_id, help_msg)
            return

        # ---------------------------------------------------------------------
        # Command: /signals or button "Signallar"
        # ---------------------------------------------------------------------
        if text.startswith("/signals") or "signallar" in t_low:
            if self.signal_tracker and self.signal_tracker.active_signals:
                sig_lines = []
                for s in self.signal_tracker.active_signals:
                    pips = s.last_pips
                    pips_str = f"+{pips:.0f} pips" if pips >= 0 else f"{pips:.0f} pips"
                    be_str = " [🛡️ SL: Breakeven (0)]" if s.breakeven_active else ""
                    sig_lines.append(
                        f"• <b>#{s.symbol}</b> ({s.direction}){be_str}\n"
                        f"  📥 Kirish: <code>{s.entry_price:.2f}</code> | SL: <code>{s.stop_loss:.2f}</code>\n"
                        f"  🎯 TP1: <code>{s.take_profit_1:.2f}</code> | TP2: <code>{s.take_profit_2:.2f}</code>\n"
                        f"  📈 <b>Hozirgi Harakat:</b> <code>{pips_str}</code> (Maks: +{s.highest_pips:.0f} pips)\n"
                    )
                msg = "⚡ <b>HOZIRGI AKTIV SIGNALLAR:</b>\n\n" + "\n".join(sig_lines)
            else:
                msg = "ℹ️ Hozirda faol ochiq signal yo'q. Bozor yangi A+ tasdiqni kutmoqda.\nSababini bilish uchun <code>/why XAUUSD</code> deb yozing."
            await self.send_message(chat_id, msg)
            return

        # ---------------------------------------------------------------------
        # Command: /analyze <symbol>
        # ---------------------------------------------------------------------
        if text.startswith("/analyze"):
            parts = text.split()
            sym = parts[1].upper() if len(parts) > 1 else "XAUUSD"
            await self.send_message(chat_id, f"⏳ <b>{sym}</b> bo'yicha MTF va AI tahlil o'tkazilmoqda...")

            try:
                df = await self.data_fetcher.get_market_data(sym, "15m")
                dxy_df = await self.data_fetcher.get_market_data("DXY", "15m")
                if df is not None and self.signal_engine:
                    sig, meta = await self.signal_engine.analyze_and_generate_signal(sym, df, dxy_df)
                    cur_p = meta.get("current_price", 0.0)
                    ml_sig = meta.get("ml_signal", "HOLD")
                    conf = meta.get("ml_confidence", 0.0)
                    regime = meta.get("regime", "Noma'lum")
                    macro = meta.get("macro", "Neytral")
                    h4 = meta.get("h4_trend", "NEUTRAL")
                    h1 = meta.get("htf_trend", "NEUTRAL")

                    is_crypto = any(c in sym for c in ["BTC", "ETH", "SOL", "USDT"])
                    is_weekend = self.signal_engine.session_filter.is_weekend() if self.signal_engine else False
                    weekend_warning = ""
                    if not is_crypto and is_weekend:
                        weekend_warning = "🔴 <b>Dam olish kuni:</b> Oltin/Forex bozori yopiq (Juma yopilish narxi)!\n━━━━━━━━━━━━━━━━━━━━━━\n"

                    res_msg = (
                        f"📊 <b>{sym} (M15) AI & MTF TAHLIL NATIJASI:</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"{weekend_warning}"
                        f"💵 <b>Narx:</b> <code>${cur_p:,.2f}</code>\n"
                        f"📈 <b>MTF Kontekst:</b> H4 [{h4}] | H1 [{h1}]\n"
                        f"🧠 <b>AI Xulosasi:</b> <b>{ml_sig}</b> ({conf*100:.1f}%)\n"
                        f"🌊 <b>Bozor Rejimi:</b> {regime}\n"
                        f"🌐 <b>Makro DXY:</b> {macro}\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    )
                    if sig:
                        res_msg += f"✅ <b>{sig.grade} SIGNAL TOPILDI!</b> Asosiy kanalga yuborildi."
                        await self.broadcast_signal(sig)
                    else:
                        gate_r = meta.get("gate_reason", "Xavfsiz kirish shartlari to'liq qanoatlantirilmadi")
                        res_msg += f"ℹ️ <i>Kirish holati: {gate_r}</i>\nBatafsil audit uchun <code>/why {sym}</code> buyrug'idan foydalaning."

                    await self.send_message(chat_id, res_msg)
                else:
                    await self.send_message(chat_id, f"❌ {sym} bo'yicha ma'lumotlarni yuklab bo'lmadi.")
            except Exception as e:
                logger.error(f"Error handling /analyze: {e}")
                await self.send_message(chat_id, f"❌ Xatolik yuz berdi: {e}")
            return

        # ---------------------------------------------------------------------
        # Default: Route to Conversational AI Assistant (Real-Time Grounded)
        # ---------------------------------------------------------------------
        try:
            ai_reply = await self.ai_assistant.answer_user_query(
                user_message=text,
                market_context=self._latest_context,
                signal_engine=self.signal_engine,
                data_fetcher=self.data_fetcher,
                chat_id=chat_id,
            )
            await self.send_message(chat_id, ai_reply)
        except Exception as e:
            logger.error(f"Error handling AI chat: {e}")

    async def set_bot_commands(self):
        """Register command menu with Telegram Bot API so typing / shows the list."""
        url = f"{self.api_url}/setMyCommands"
        commands = [
            {"command": "status", "description": "📊 Bozor holati va MTF sessiyalar"},
            {"command": "signals", "description": "⚡ Ochiq signallar va jonli pips"},
            {"command": "why", "description": "🔍 Nega signal yo'qligi auditi (masalan /why XAUUSD)"},
            {"command": "analyze", "description": "🔬 Aktivni to'liq tahlil qilish (masalan /analyze BTC)"},
            {"command": "news", "description": "📰 Iqtisodiy taqvim va xavfli yangiliklar"},
            {"command": "mode", "description": "⚙️ Signallar filtri (50%, 58%, 68%)"},
            {"command": "stats", "description": "📈 Aniq Win-Rate va prop-firm statistikasi"},
            {"command": "close", "description": "🛑 Ochiq signallarni qo'lda tozalash"},
            {"command": "help", "description": "📖 To'liq yo'riqnoma va qo'llanma"},
        ]
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json={"commands": commands}) as resp:
                    if resp.status == 200:
                        logger.info("Telegram command menu registered successfully.")
        except Exception as e:
            logger.warning(f"Could not set Telegram commands: {e}")

    # -------------------------------------------------------------------------
    # Polling Loop
    # -------------------------------------------------------------------------
    async def start_polling(self):
        """Long-polling update loop for Telegram Bot."""
        if not self.token:
            logger.warning("TELEGRAM_BOT_TOKEN not provided. Bot polling disabled.")
            return

        self._running = True
        logger.info("Starting Telegram Bot long-polling loop...")

        # Register bot commands with Telegram
        await self.set_bot_commands()

        # Send startup notification to all admins
        startup_msg = (
            "⚡ <b>CYBER TRADE AI TIZIMI ISHGA TUSHDI!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "• Multi-Timeframe Tahlili (H4 / H1 / M15): FAOL\n"
            "• Ma'lumot Sifati & Eskirganlik Nazorati: FAOL\n"
            "• Yangiliklar Qalqoni (News Sentinel): FAOL\n"
            "• Aniq Virtual Statistik Hisob-kitob: FAOL\n"
            "• Dual-Engine AI Chat (Gemini + Groq): FAOL\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "<i>Bozorlar 24/7 rejimida professional monitoring qilinmoqda.</i>"
        )
        for admin in self.admin_chat_ids:
            await self.send_message(admin, startup_msg, reply_markup=DEFAULT_KEYBOARD)

        offset = 0
        while self._running:
            url = f"{self.api_url}/getUpdates"
            params = {"offset": offset, "timeout": 20}

            try:
                timeout = aiohttp.ClientTimeout(total=25)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, params=params) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            results = data.get("result", [])
                            for update in results:
                                offset = update["update_id"] + 1
                                # Process each update concurrently
                                asyncio.create_task(self._handle_update(update))
                        elif resp.status == 409:
                            logger.warning("Telegram conflict: another bot instance is polling.")
                            await asyncio.sleep(5)
                        else:
                            await asyncio.sleep(2)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in Telegram polling loop: {e}")
                await asyncio.sleep(3)

    def stop(self):
        """Stop polling loop."""
        self._running = False
        logger.info("Telegram Bot polling stopped.")
