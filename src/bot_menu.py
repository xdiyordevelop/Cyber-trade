"""
Cyber Trade - Bot Menu & Trader UI Architecture
===============================================
Ergonomic, modern Telegram UI components for active prop & retail traders.
Designed for 1-tap operation without typing commands:
- 4x2 persistent reply keyboard (balanced on mobile and desktop)
- Interactive inline callback keyboards for fast asset selection and mode filtering
- Instant lot calculation for Gold, BTC, ETH, and Forex
"""

from typing import Dict, Any, Tuple


# -----------------------------------------------------------------------------
# Trade Signal Modes Configuration
# -----------------------------------------------------------------------------
SIGNAL_MODES = {
    "aggressive": {
        "id": "aggressive",
        "name": "⚡ Agressiv (Scalp 50%+)",
        "threshold": 0.50,
        "min_rr": 1.5,
        "desc": "Ko'proq signallar, tezkor kirish-chiqishlar (50%+)",
    },
    "standard": {
        "id": "standard",
        "name": "⚖️ Standart (Balansli 58%+)",
        "threshold": 0.58,
        "min_rr": 1.8,
        "desc": "Oltin o'rtalik: A+ va sifatli Trend signallar (58%+)",
    },
    "conservative": {
        "id": "conservative",
        "name": "🛡️ Konservativ (Sniper 68%+)",
        "threshold": 0.68,
        "min_rr": 2.2,
        "desc": "Faqat eng yuqori ishonchli A+ Sniper signallar (68%+)",
    },
}

# -----------------------------------------------------------------------------
# Asset Selection Configuration (User-Controlled Signals)
# -----------------------------------------------------------------------------
ASSET_MODES = {
    "gold": {
        "id": "gold",
        "name": "🟡 Faqat Oltin (XAUUSD / GOLD)",
        "symbols": ["XAUUSD"],
        "desc": "Faqat Oltin signallari (Asosiy XM Broker 0ms fokusi)",
    },
    "crypto": {
        "id": "crypto",
        "name": "🪙 Faqat Kripto (Bitcoin & Ethereum)",
        "symbols": ["BTCUSDT", "ETHUSDT"],
        "desc": "Faqat BTC va ETH signallari (XM Broker 24/7)",
    },
    "all": {
        "id": "all",
        "name": "⚡ Barcha Aktivlar (Oltin + Kripto)",
        "symbols": ["XAUUSD", "BTCUSDT", "ETHUSDT"],
        "desc": "Oltin va barcha faol Kripto signallari birgalikda",
    },
}


# -----------------------------------------------------------------------------
# Modern, Ergonomic Persistent Reply Menu for Traders (5 rows x 2 columns)
# -----------------------------------------------------------------------------
MAIN_KEYBOARD: Dict[str, Any] = {
    "keyboard": [
        [{"text": "⚡ Signallar"}, {"text": "📊 Bozor & Status"}],
        [{"text": "🔍 Tezkor Tahlil"}, {"text": "🧮 Lot Kalkulyator"}],
        [{"text": "🎯 Aktiv Tanlash"}, {"text": "⚙️ Savdo Rejimi"}],
        [{"text": "📰 Yangiliklar"}, {"text": "📈 Statistika"}],
        [{"text": "📖 Qo'llanma"}],
    ],
    "resize_keyboard": True,
    "persistent": True,
}
DEFAULT_KEYBOARD = MAIN_KEYBOARD


def is_lot_numeric_query(text: str) -> bool:
    """
    Detect if user entered raw numbers for quick lot calculation (e.g. '1000 1' or '$2500 2%').
    Allows instant calculation without typing /calc or /risk.
    """
    clean = text.replace("$", "").replace("%", "").replace(",", "").strip()
    parts = clean.split()
    if 1 <= len(parts) <= 2:
        try:
            val1 = float(parts[0])
            if val1 > 0:
                if len(parts) == 2:
                    val2 = float(parts[1])
                    return 0.0 < val2 <= 100.0
                return True
        except ValueError:
            return False
    return False


def format_lot_calculation(deposit: float, risk_pct: float) -> Tuple[str, Dict[str, Any]]:
    """Generate professional lot & risk management breakdown with 1-tap quick buttons."""
    risk_amount = deposit * (risk_pct / 100.0)
    # SL Distances: Gold ~$3.0 (30 pips), BTC ~$500, ETH ~$25, FX ~20 pips
    gold_lot = max(0.01, round(risk_amount / 300.0, 2))
    btc_lot = max(0.001, round(risk_amount / 500.0, 3))
    eth_lot = max(0.01, round(risk_amount / 25.0, 2))
    fx_lot = max(0.01, round(risk_amount / 200.0, 2))

    msg = (
        f"🧮 <b>PROFESSIONAL RISK & LOT KALKULYATORI</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 <b>Depozit Miqdori:</b> <code>${deposit:,.2f}</code>\n"
        f"⚖️ <b>Xavf (Risk):</b> <code>{risk_pct:.1f}%</code> (Maksimal yo'qotish: <b>${risk_amount:.2f}</b>)\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>TAVSIYA ETILGAN ANIQ LOT HAJMLARI:</b>\n\n"
        f"🟡 <b>Oltin (XAUUSD):</b> <code>{gold_lot:.2f} lot</code> (~$3.0 SL bilan)\n"
        f"🪙 <b>Bitcoin (BTC):</b> <code>{btc_lot:.3f} BTC</code> (~$500 SL bilan)\n"
        f"💎 <b>Ethereum (ETH):</b> <code>{eth_lot:.2f} ETH</code> (~$25 SL bilan)\n"
        f"💱 <b>Forex Juftliklar:</b> <code>{fx_lot:.2f} lot</code> (~20 pip SL bilan)\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 <i>Quyidagi tezkor depozit tugmalaridan birini bosing yoki o'z depozitingizni yozing (masalan: <code>2500 1.5</code>):</i>"
    )

    markup = {
        "inline_keyboard": [
            [
                {"text": "💵 $500 (1%)", "callback_data": "calc:500:1.0"},
                {"text": "💵 $1,000 (1%)", "callback_data": "calc:1000:1.0"},
            ],
            [
                {"text": "💵 $5,000 (1%)", "callback_data": "calc:5000:1.0"},
                {"text": "💵 $10,000 (1%)", "callback_data": "calc:10000:1.0"},
            ],
            [
                {"text": "🏆 $25,000 (Prop)", "callback_data": "calc:25000:1.0"},
                {"text": "🏆 $50,000 (Prop)", "callback_data": "calc:50000:1.0"},
            ],
        ]
    }
    return msg, markup


def format_analyze_menu() -> Tuple[str, Dict[str, Any]]:
    """Generate 1-tap asset selection menu for live MTF analysis and signal audit."""
    msg = (
        "🔍 <b>TEZKOR BOZOR TAHLILI VA AUDIT</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "Qaysi aktiv bo'yicha Multi-Timeframe (H4/H1/M15), Smart Money (SMC) va "
        "AI modellarining hozirgi xulosasini ko'rmoqchisiz?\n\n"
        "Kerakli bozor tugmasini bosing:"
    )
    markup = {
        "inline_keyboard": [
            [
                {"text": "🟡 Oltin (XAUUSD)", "callback_data": "analyze:XAUUSD"},
                {"text": "🪙 Bitcoin (BTC)", "callback_data": "analyze:BTCUSDT"},
            ],
            [
                {"text": "💎 Ethereum (ETH)", "callback_data": "analyze:ETHUSDT"},
                {"text": "🟣 Solana (SOL)", "callback_data": "analyze:SOLUSDT"},
            ],
            [
                {"text": "❓ Nega Oltinda Signal Yo'q? (Audit)", "callback_data": "why:XAUUSD"},
            ],
            [
                {"text": "❓ Nega BTCda Signal Yo'q? (Audit)", "callback_data": "why:BTCUSDT"},
            ],
        ]
    }
    return msg, markup


def format_asset_menu(current_asset_mode: str = "gold") -> Tuple[str, Dict[str, Any]]:
    """Generate 1-tap interactive asset selection menu (Gold only, Crypto only, or All)."""
    cfg = ASSET_MODES.get(current_asset_mode, ASSET_MODES["gold"])
    msg = (
        "🎯 <b>CYBER TRADE — SIGNALLAR UCHUN AKTIV TANLASH</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Hozirgi faol tanlov: <b>{cfg['name']}</b>\n"
        f"📊 <b>Kuzatilayotgan Tikerlar:</b> <code>{', '.join(cfg['symbols'])}</code>\n"
        f"ℹ️ <i>{cfg['desc']}</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        "Barcha narx va shamlar to'g'ridan-to'g'ri <b>XM Broker (MT5)</b> dan 0 ms kechikish bilan olinadi.\n\n"
        "Qaysi aktivlar bo'yicha signal olmoqchisiz? Quyidagi tugmalardan birini bosing:"
    )
    markup = {
        "inline_keyboard": [
            [{"text": f"{'✅ ' if current_asset_mode == 'gold' else ''}🟡 1. Faqat Oltin (XAUUSD / GOLD)", "callback_data": "set_assets:gold"}],
            [{"text": f"{'✅ ' if current_asset_mode == 'crypto' else ''}🪙 2. Faqat Kripto (BTC & ETH)", "callback_data": "set_assets:crypto"}],
            [{"text": f"{'✅ ' if current_asset_mode == 'all' else ''}⚡ 3. Barcha Aktivlar (Oltin + Kripto)", "callback_data": "set_assets:all"}],
        ]
    }
    return msg, markup


def format_mode_menu(current_mode: str) -> Tuple[str, Dict[str, Any]]:
    """Generate interactive 1-tap mode selection menu."""
    cfg = SIGNAL_MODES.get(current_mode, SIGNAL_MODES["standard"])
    msg = (
        f"⚙️ <b>CYBER TRADE — SAVDO REJIMI (FILTR)</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Hozirgi faol rejim: <b>{cfg['name']}</b>\n"
        f"🎯 Minimal Ishonch: <code>{cfg['threshold']*100:.0f}%</code> | ⚖️ Min R:R: <code>1:{cfg['min_rr']:.1f}</code>\n"
        f"ℹ️ <i>{cfg['desc']}</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"O'zgartirish uchun pastdagi tugmalardan birini bosing:"
    )
    markup = {
        "inline_keyboard": [
            [{"text": "⚡ 1. Agressiv (50%+ — Tezkor scalping)", "callback_data": "set_mode:aggressive"}],
            [{"text": "⚖️ 2. Standart (58%+ — Tavsiya etiladi)", "callback_data": "set_mode:standard"}],
            [{"text": "🛡️ 3. Konservativ (68%+ — Sniper A+)", "callback_data": "set_mode:conservative"}],
        ]
    }
    return msg, markup


def format_help_guide() -> str:
    """Generate comprehensive trader guide."""
    return (
        "📖 <b>CYBER TRADE — TO'LIQ YO'RIQNOMA VA QO'LLANMA</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "Cyber Trade — ko'p agentli sun'iy intellekt va Smart Money Concepts (SMC) "
        "asosida ishlovchi professional bozor tahlilchisi va signallar tizimi.\n\n"
        "📱 <b>ASOSIY TUGMALAR VA FUNKSIYALAR:</b>\n"
        "• <b>⚡ Signallar:</b> Hozirgi ochiq bitimlar, kutilayotgan limitlar va jonli pips foyda\n"
        "• <b>📊 Bozor & Status:</b> Tizim holati, serverlar, API oqimi va nosozliklar auditi\n"
        "• <b>🔍 Tezkor Tahlil:</b> Oltin, BTC, ETH va boshqa aktivlarni 1-bosishda tahlil qilish\n"
        "• <b>🧮 Lot Kalkulyator:</b> Depozit va riskka ko'ra aniq lotni hisoblash (masalan: <code>1000 1</code>)\n"
        "• <b>📰 Yangiliklar:</b> ForexFactory iqtisodiy taqvimi va yuqori xavfli soatlar\n"
        "• <b>⚙️ Savdo Rejimi:</b> Filtrlash darajasi (Standart 58%+, Agressiv 50%+, Konservativ 68%+)\n"
        "• <b>📈 Statistika:</b> Win-Rate, R:R va sof daromad balansi\n"
        "• <b>🧠 O'rganish Tarixi (/learn):</b> AI savdolardan chiqargan xulosalari va o'zini kuchaytirish hisoboti\n\n"
        "🎯 <b>SIGNAL VA FOYDANI BOSHQARISH QOIDASI:</b>\n"
        "1. <b>TP1 urilganda:</b> Bot 50% foydani olishni va Stop-Lossni Kirish narxiga surishni bildiradi (+0.75R zaxira).\n"
        "2. <b>TP2 urilganda:</b> Qolgan 50% asosiy likvidlik maqsadida to'liq foyda bilan yopiladi (+2.0R).\n"
        "3. <b>Narx kirishga qaytsa:</b> Qolgan 50% zararsiz (0 ga) yopiladi (+0.75R sof foyda kafolatlangan).\n"
        "4. <b>Stop-Loss:</b> Qat'iy -1.0R risk bilan chegaralangan.\n\n"
        "💬 <b>AI CHAT:</b> Istalgan savolingizni shunchaki chatga yozing — AI bozorning ayni "
        "soniyadagi holatidan kelib chiqib professional javob beradi!"
    )


def format_start_welcome() -> str:
    """Generate welcome message with visual layout."""
    return (
        "👋 <b>Assalomu alaykum! Cyber Trade Multi-Agent AI tizimiga xush kelibsiz.</b>\n\n"
        "Men sizning professional treyding tahlilchingizman. Bozorlarni "
        "<b>Multi-Timeframe (H4/H1/M15)</b>, <b>Smart Money (SMC)</b> va <b>Machine Learning</b> "
        "yordamida 24/7 tahlil qilaman.\n\n"
        "📱 <b>QUYIDAGI QULAY MENYUDAN FOYDALANING:</b>\n\n"
        "⚡ <b>Signallar</b> — Faol signallar, kutilayotgan limitlar va jonli pips\n"
        "📊 <b>Bozor & Status</b> — Tizim salomatligi, nosozliklar auditi va ochiq sessiyalar\n"
        "🔍 <b>Tezkor Tahlil</b> — Oltin, BTC, ETH tahlili va 1-klikda audit\n"
        "🧮 <b>Lot Kalkulyator</b> — Depozit va risk bo'yicha aniq lot hisoblash\n"
        "📰 <b>Yangiliklar</b> — ForexFactory iqtisodiy taqvimi va xavfli soatlar\n"
        "📈 <b>Statistika</b> — Aniq Win-Rate va umumiy R:R foyda hisoboti\n"
        "🧠 <b>O'rganish (/learn)</b> — AI xatolardan chiqargan xulosalari va o'zini rivojlantirish xotirasi\n"
        "⚙️ <b>Savdo Rejimi</b> — Signallar filtri (Standart, Agressiv, Konservativ)\n"
        "📖 <b>Qo'llanma</b> — To'liq foydalanish yo'riqnomasi\n\n"
        "💬 <b>AI CHAT:</b> Istalgan savolingizni yozing (masalan: <i>'Oltinda vaziyat qanday?'</i>) "
        "yoki shunchaki depozit yozing (masalan: <i>'1000 1'</i>) — AI zudlik bilan javob beradi!"
    )
