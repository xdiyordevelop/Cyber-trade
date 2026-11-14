"""
Cyber Trade - Telegram Bot & Broadcast Engine
=============================================
Pure async HTTP Telegram client (aiohttp-based).
No heavy external wrappers - lightweight, fast, 100% free cloud compatible.
Features:
- Broadcasts A+ signals with dark-mode chart photos
- Real-time trailing alerts (TP1 hit -> Move SL to BE)
- Interactive commands: /start, /status, /analyze, /signals, /stats
- Integrated Conversational AI Assistant for real-time market queries
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
    ) -> bool:
        """Send a text message via Telegram Bot API."""
        if not self.token or not chat_id:
            return False

        url = f"{self.api_url}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_web_page_preview,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        return True
                    err = await resp.text()
                    logger.warning(f"Telegram sendMessage error ({resp.status}): {err}")
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
    ) -> bool:
        """Send a chart photo with caption via multipart/form-data."""
        if not self.token or not chat_id or not photo_path:
            return False

        path = Path(photo_path)
        if not path.exists():
            logger.warning(f"Chart photo file not found: {photo_path}")
            return await self.send_message(chat_id, caption, parse_mode=parse_mode)

        url = f"{self.api_url}/sendPhoto"
        try:
            data = aiohttp.FormData()
            data.add_field("chat_id", str(chat_id))
            data.add_field("caption", caption)
            data.add_field("parse_mode", parse_mode)
            data.add_field("photo", open(path, "rb"), filename=path.name, content_type="image/png")

            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data) as resp:
                    if resp.status == 200:
                        return True
                    err = await resp.text()
                    logger.warning(f"Telegram sendPhoto error ({resp.status}): {err}")
                    return False
        except Exception as e:
            logger.error(f"Failed to send Telegram photo: {e}")
            return False

    # -------------------------------------------------------------------------
    # Broadcasting Methods
    # -------------------------------------------------------------------------
    async def broadcast_signal(self, signal: GeneratedSignal):
        """Broadcast a newly formed signal to channel and admin chats."""
        msg = signal.format_telegram_message()
        targets = []
        if self.channel_id:
            targets.append(self.channel_id)
        targets.extend(self.admin_chat_ids)
        targets = list(set(targets))

        for target in targets:
            if signal.chart_image_path and Path(signal.chart_image_path).exists():
                await self.send_photo(target, signal.chart_image_path, caption=msg)
            else:
                await self.send_message(target, msg)

    async def broadcast_alert(self, alert_text: str):
        """Broadcast live trailing updates (TP1 hit, TP2 hit, SL hit)."""
        targets = []
        if self.channel_id:
            targets.append(self.channel_id)
        targets.extend(self.admin_chat_ids)
        targets = list(set(targets))

        for target in targets:
            await self.send_message(target, alert_text)

    # -------------------------------------------------------------------------
    # Interactive Command & Chat Handler
    # -------------------------------------------------------------------------
    async def _handle_update(self, update: Dict[str, Any]):
        """Process incoming user updates (commands and chat queries)."""
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

        # Command: /start
        if text.startswith("/start"):
            welcome = (
                "👋 <b>Assalomu alaykum! Cyber Trade AI tizimiga xush kelibsiz.</b>\n\n"
                "Men ko'p agentli sun'iy intellekt va Smart Money Concepts (SMC) orqali "
                "Oltin (XAUUSD), Bitcoin (BTC), Ethereum (ETH) va boshqa aktivlarni 24/7 tahlil qilaman.\n\n"
                "📌 <b>Mavjud buyruqlar:</b>\n"
                "• <code>/status</code> — Bozor holati va joriy rejim\n"
                "• <code>/mode</code> — Signallar chastotasi va filtri (50%, 60%, 70%)\n"
                "• <code>/analyze XAUUSD</code> — Oltinni zudlik bilan to'liq tahlil qilish\n"
                "• <code>/analyze BTC</code> — Bitcoinni to'liq tahlil qilish\n"
                "• <code>/signals</code> — Hozirgi aktiv signallar ro'yxati\n"
                "• <code>/stats</code> — Tizimning umumiy Win-Rate statistikasi\n"
                "• <code>/help</code> — To'liq yo'riqnoma va tushuntirishlar\n\n"
                "💬 <i>Shuningdek, menga oddiy savol berishingiz ham mumkin (masalan: 'Oltinda nima kutilyapti?').</i>"
            )
            await self.send_message(chat_id, welcome)
            return

        # Command: /mode [aggressive|standard|conservative|1|2|3]
        if text.startswith("/mode"):
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

            # Display Mode Menu
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
                f"⚖️ <b>Standart Rejim (60%+):</b>\n"
                f"• Oltin o'rtalik (Tavsiya etiladi)\n"
                f"• Mustahkam tasdiq bilan ishonchli signallar\n\n"
                f"3️⃣ <code>/mode 3</code> yoki <code>/mode conservative</code>\n"
                f"🛡️ <b>Konservativ Rejim (70%+):</b>\n"
                f"• Sniper rejim (Kam, lekin eng xavfsiz A+ signallar)\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"<i>Rejimni o'zgartirish uchun masalan <code>/mode 1</code> deb yuboring!</i>"
            )
            await self.send_message(chat_id, mode_menu)
            return

        # Command: /status
        if text.startswith("/status"):
            session = self._latest_context.get("session", "Off Hours")
            regime = self._latest_context.get("regime", "Trending")
            news = self._latest_context.get("news", "Bozor tinch")
            from src.signal_engine import SIGNAL_MODES
            curr_mode_id = self.signal_engine.active_mode if self.signal_engine else "standard"
            mode_name = SIGNAL_MODES.get(curr_mode_id, {}).get("name", "Standart (60%+)")
            is_weekend = self.signal_engine.session_filter.is_weekend() if self.signal_engine else False
            weekend_note = "\n🔴 <b>Dam Olish Kuni:</b> Oltin va Forex birjalari yopiq (Dushanba tongigacha). Kriptovalyuta bozori 24/7 ochiq!" if is_weekend else ""

            status_msg = (
                f"📊 <b>CYBER TRADE — TIZIM HOLATI</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"⚙️ <b>Signal Rejimi:</b> <b>{mode_name}</b>\n"
                f"🕒 <b>Aktiv Sessiya:</b> {session}\n"
                f"🌊 <b>Bozor Rejimi:</b> {regime}\n"
                f"📰 <b>Yangiliklar Qalqoni:</b> {news}{weekend_note}\n"
                f"⚡ <b>AI Council:</b> Faol va kuzatuvda (24/7)\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"<i>Signallar chastotasini o'zgartirish uchun <code>/mode</code> buyrug'idan foydalaning.</i>"
            )
            await self.send_message(chat_id, status_msg)
            return

        # Command: /stats
        if text.startswith("/stats"):
            if self.signal_tracker:
                perf = self.signal_tracker.get_performance_summary()
                stats_msg = (
                    f"📈 <b>CYBER TRADE — NATIJALAR VA STATISTIKA</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🎯 <b>Jami Signallar:</b> {perf['total_signals']} ta\n"
                    f"🏆 <b>Win Rate:</b> <code>{perf['win_rate']:.1f}%</code>\n"
                    f"💰 <b>Sof Daromad (R:R):</b> <code>+{perf['total_r']:.1f}R</code>\n"
                    f"✅ <b>Take-Profitlar:</b> {perf['tp_count']} ta\n"
                    f"🛑 <b>Stop-Losslar:</b> {perf['sl_count']} ta\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"<i>Har bir signalda Risk:Reward minimal 1:2.0 hisoblanadi.</i>"
                )
            else:
                stats_msg = "ℹ️ Statistika moduli ishga tushirilmoqda..."
            await self.send_message(chat_id, stats_msg)
            return

        # Command: /close or /clear
        if text.startswith("/close") or text.startswith("/clear"):
            if self.signal_tracker:
                count = self.signal_tracker.clear_all_signals()
                if count > 0:
                    close_msg = (
                        f"🛑 <b>OCHIQ SIGNALLAR QO'LDA YOPILDI:</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"Jami <b>{count} ta</b> faol signal muvaffaqiyatli yopildi va arxivga olindi.\n"
                        f"Bozor yangi A+ kirish nuqtalari uchun qaytadan toza monitoring qilinmoqda."
                    )
                else:
                    close_msg = "ℹ️ Hozirda yopish uchun faol ochiq signallar yo'q."
            else:
                close_msg = "ℹ️ Signal kuzatuvchi modul faol emas."
            await self.send_message(chat_id, close_msg)
            return

        # Command: /help
        if text.startswith("/help"):
            help_msg = (
                "📖 <b>CYBER TRADE — TO'LIQ YO'RIQNOMA VA QO'LLANMA</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "Cyber Trade — ko'p agentli AI va Smart Money Concepts (SMC) "
                "asosida ishlovchi bozor tahlilchisi va signal beruvchi aqlli tizim.\n\n"
                "📌 <b>ASOSIY BUYRUQLAR:</b>\n"
                "• <code>/status</code> — Bozor holati, faol rejim va joriy sessiya\n"
                "• <code>/mode</code> — Signallar filtri (50% Agressiv, 60% Standart, 70% Konservativ)\n"
                "• <code>/signals</code> — Hozirgi ochiq signallar va jonli pips foydasi\n"
                "• <code>/close</code> — Barcha ochiq signallarni qo'lda tozalash/yopish\n"
                "• <code>/analyze XAUUSD</code> — Oltinni ayni soniyada to'liq AI tahlil qilish\n"
                "• <code>/analyze BTC</code> — Bitcoinni to'liq tahlil qilish\n"
                "• <code>/analyze ETH</code> — Ethereum bo'yicha tahlil\n"
                "• <code>/stats</code> — Tizimning umumiy Win-Rate va foyda ko'rsatkichlari\n"
                "• <code>/help</code> — Ushbu qo'llanmani ko'rsatish\n\n"
                "🎯 <b>SIGNALLAR QACHON VA QANDAY YOPILADI?</b>\n"
                "1. <b>TP2 urilganda:</b> Asosiy maqsad bajarildi deb to'liq foyda bilan yopiladi.\n"
                "2. <b>Stop-Loss urilganda:</b> Risk nazorat qilingan holda -1R bilan yopiladi.\n"
                "3. <b>TP1 urilganda:</b> Bot 50% foydani olishni va Stop-Lossni 0 ga (Breakeven) surishni tavsiya qiladi.\n"
                "4. <b>24 soat o'tganda:</b> Harakatsiz qolgan signallar muddati tugab avtomatik yopiladi.\n"
                "5. <b>Qo'lda yopish:</b> <code>/close</code> buyrug'i orqali istalgan vaqtda yopishingiz mumkin.\n\n"
                "🚨 <b>YANGILIKLAR VA SESSIYALAR XABARNOMASI:</b>\n"
                "• Muhim iqtisodiy yangiliklar (CPI, NFP, FOMC) chiqishidan 15-30 daqiqa oldin bot ogohlantirish yo'llaydi.\n"
                "• London (13:00) va London-NY Overlap (18:00) ochilganda avtomatik xabar beradi.\n"
                "• Shanba 03:00 da Forex/Oltin yopilishi va Dushanba ochilishi e'lon qilinadi.\n\n"
                "💬 <b>AI CHAT BILAN GAPLASHISH:</b>\n"
                "Botga istalgan savolingizni yozing (masalan: <i>'Bozorda vaziyat qanday?'</i>). "
                "AI tahlilchi darhol javob beradi!"
            )
            await self.send_message(chat_id, help_msg)
            return

        # Command: /signals
        if text.startswith("/signals"):
            if self.signal_tracker and self.signal_tracker.active_signals:
                sig_lines = []
                for s in self.signal_tracker.active_signals:
                    pips = s.last_pips
                    pips_str = f"+{pips:.0f} pips" if pips >= 0 else f"{pips:.0f} pips"
                    sig_lines.append(
                        f"• <b>#{s.symbol}</b> ({s.direction})\n"
                        f"  📥 Kirish: <code>{s.entry_price:.2f}</code> | SL: <code>{s.stop_loss:.2f}</code>\n"
                        f"  🎯 TP1: <code>{s.take_profit_1:.2f}</code> | TP2: <code>{s.take_profit_2:.2f}</code>\n"
                        f"  📈 <b>Hozirgi Harakat:</b> <code>{pips_str}</code> (Maks: +{s.highest_pips:.0f} pips)\n"
                    )
                msg = "⚡ <b>HOZIRGI AKTIV SIGNALLAR:</b>\n\n" + "\n".join(sig_lines)
            else:
                msg = "ℹ️ Hozirda faol ochiq signal yo'q. Bozor yangi tasdiqni kutmoqda."
            await self.send_message(chat_id, msg)
            return

        # Command: /analyze <symbol>
        if text.startswith("/analyze"):
            parts = text.split()
            sym = parts[1].upper() if len(parts) > 1 else "XAUUSD"
            await self.send_message(chat_id, f"⏳ <b>{sym}</b> bo'yicha to'liq AI tahlil o'tkazilmoqda...")

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

                    is_crypto = any(c in sym for c in ["BTC", "ETH", "SOL", "USDT"])
                    is_weekend = self.signal_engine.session_filter.is_weekend() if self.signal_engine else False
                    weekend_warning = ""
                    if not is_crypto and is_weekend:
                        weekend_warning = "🔴 <b>Dam olish kuni:</b> Oltin/Forex bozori yopiq. Narx Juma kungi yopilish holatida!\n━━━━━━━━━━━━━━━━━━━━━━\n"

                    res_msg = (
                        f"📊 <b>{sym} (M15) AI TAHLIL NATIJASI:</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"{weekend_warning}"
                        f"💵 <b>Narx (Yopilish):</b> <code>{cur_p:.2f}</code>\n"
                        f"🧠 <b>AI Xulosasi:</b> <b>{ml_sig}</b> ({conf*100:.1f}%)\n"
                        f"🌊 <b>Bozor Rejimi:</b> {regime}\n"
                        f"🌐 <b>Makro DXY Ta'siri:</b> {macro}\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    )
                    if sig:
                        res_msg += "✅ <b>A+ SIGNAL TOPILDI!</b> Asosiy kanalga yuborildi."
                        await self.broadcast_signal(sig)
                    else:
                        res_msg += "ℹ️ <i>Hozircha xavfsiz A+ kirish shartlari to'liq qanoatlantirilmadi (Kutilmoqda).</i>"

                    await self.send_message(chat_id, res_msg)
                else:
                    await self.send_message(chat_id, f"❌ {sym} bo'yicha ma'lumotlarni yuklab bo'lmadi.")
            except Exception as e:
                logger.error(f"Error handling /analyze: {e}")
                await self.send_message(chat_id, f"❌ Xatolik yuz berdi: {e}")
            return

        # Default: Route to Conversational AI Assistant (Real-Time Grounded)
        try:
            ai_reply = await self.ai_assistant.answer_user_query(
                user_message=text,
                market_context=self._latest_context,
                signal_engine=self.signal_engine,
                data_fetcher=self.data_fetcher,
            )
            await self.send_message(chat_id, ai_reply)
        except Exception as e:
            logger.error(f"Error handling AI chat: {e}")

    async def set_bot_commands(self):
        """Register command menu with Telegram Bot API so typing / shows the list."""
        url = f"{self.api_url}/setMyCommands"
        commands = [
            {"command": "status", "description": "📊 Bozor holati va joriy rejim"},
            {"command": "mode", "description": "⚙️ Signallar filtri (50%, 60%, 70%)"},
            {"command": "signals", "description": "⚡ Ochiq signallar va jonli pips"},
            {"command": "close", "description": "🛑 Ochiq signallarni qo'lda yopish"},
            {"command": "analyze", "description": "🔍 Aktivni to'liq tahlil qilish (masalan /analyze BTC)"},
            {"command": "stats", "description": "📈 Umumiy Win-Rate va natijalar"},
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
        """Asynchronous Telegram long polling loop."""
        if not self.token:
            logger.warning("Telegram Bot Token is not set. Bot polling will not start.")
            return

        self._running = True
        logger.info("Telegram Bot Polling started...")

        # Register commands so typing / displays the menu
        await self.set_bot_commands()

        while self._running:
            url = f"{self.api_url}/getUpdates"
            params = {
                "offset": self._last_update_id + 1,
                "timeout": 20,
            }

            try:
                timeout = aiohttp.ClientTimeout(total=25)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, params=params) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            updates = data.get("result", [])
                            for up in updates:
                                self._last_update_id = up.get("update_id", self._last_update_id)
                                asyncio.create_task(self._handle_update(up))
                        else:
                            await asyncio.sleep(5)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Telegram polling exception: {e}")
                await asyncio.sleep(5)

    def stop(self):
        """Stop polling loop."""
        self._running = False
