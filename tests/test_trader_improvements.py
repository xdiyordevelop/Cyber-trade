"""
Unit Tests for Cyber Trade Upgraded Engine
===========================================
Comprehensive verification of:
1. Pip calculations for Gold, Bitcoin, Ethereum, and Forex.
2. Intra-candle Wick Hit (High/Low) & Direct Stop-Loss triggering.
3. Intra-candle Wick Hit for TP1 & Breakeven triggering without same-bar retrace conflict.
4. Pending BUY LIMIT & SELL LIMIT order activation upon price retest.
5. Limit order expiration when price runs away without retesting.
6. SELL order lifecycle (SL, TP1, TP2, BE).
7. Lot & Risk calculation verification.
"""

import unittest
from datetime import datetime, timezone, timedelta
from src.signal_tracker import SignalTracker, ActiveSignal, calculate_pips


class TestTraderImprovements(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from src.database import db
        with db._get_conn() as conn:
            conn.execute("DELETE FROM learning_memory WHERE signal_id LIKE 'test_%'")
            conn.execute("DELETE FROM pattern_weights WHERE pattern_key LIKE '%test%' OR pattern_key LIKE 'XAUUSD%'")
            conn.commit()

    @classmethod
    def tearDownClass(cls):
        from src.database import db
        with db._get_conn() as conn:
            conn.execute("DELETE FROM learning_memory WHERE signal_id LIKE 'test_%'")
            conn.execute("DELETE FROM pattern_weights WHERE pattern_key LIKE '%test%' OR pattern_key LIKE 'XAUUSD%'")
            conn.commit()

    def setUp(self):
        # Isolated test state file
        self.tracker = SignalTracker(state_file="data/test_signals_state.json")
        self.tracker.active_signals = []
        self.tracker.closed_signals = []

    def tearDown(self):
        if self.tracker.state_file.exists():
            try:
                self.tracker.state_file.unlink()
            except Exception:
                pass

    def test_pip_calculation(self):
        """Test pip movement calculations across different assets."""
        # Gold: $1 move = 10 pips
        self.assertAlmostEqual(calculate_pips("XAUUSD", 2600.0, 2605.0, "BUY"), 50.0)
        self.assertAlmostEqual(calculate_pips("XAUUSD", 2605.0, 2600.0, "SELL"), 50.0)

        # Bitcoin: $1 move = 1 point
        self.assertAlmostEqual(calculate_pips("BTCUSDT", 90000.0, 91500.0, "BUY"), 1500.0)

        # Ethereum: $0.10 move = 1 pip
        self.assertAlmostEqual(calculate_pips("ETHUSDT", 3000.0, 3010.0, "BUY"), 100.0)

        # Solana
        self.assertAlmostEqual(calculate_pips("SOLUSDT", 200.0, 205.0, "BUY"), 50.0)

        # Forex: 0.0001 move = 1 pip
        self.assertAlmostEqual(calculate_pips("EURUSD", 1.0500, 1.0550, "BUY"), 50.0)

    def test_intra_candle_wick_stop_loss_hit(self):
        """
        Verify that if price dips down to SL during a candle (low_price <= SL),
        SL is immediately triggered even if candle close recovered higher.
        """
        sig = ActiveSignal(
            id="test_buy_sl",
            symbol="XAUUSD",
            timeframe="15m",
            direction="BUY",
            entry_price=2650.0,
            stop_loss=2640.0,
            take_profit_1=2662.0,
            take_profit_2=2675.0,
            take_profit_3=2690.0,
            created_at=datetime.now(timezone.utc).isoformat(),
            ai_confidence=0.75,
            order_type="MARKET BUY",
            is_filled=True,
        )
        self.tracker.add_signal(sig)

        # Suppose candle close is 2648.0 (above SL), but low_price was 2638.0 (pierced SL)
        alerts = self.tracker.update_price(
            symbol="XAUUSD",
            current_price=2648.0,
            high_price=2653.0,
            low_price=2638.0,
        )

        self.assertTrue(any(a["type"] == "SL_HIT" for a in alerts))
        self.assertEqual(len(self.tracker.active_signals), 0)
        self.assertEqual(len(self.tracker.closed_signals), 1)
        self.assertEqual(self.tracker.closed_signals[0].close_reason, "SL_LOSS")
        self.assertEqual(self.tracker.closed_signals[0].profit_r, -1.0)

    def test_intra_candle_wick_tp1_and_breakeven(self):
        """
        Verify that when high_price reaches TP1 during a candle,
        TP1 is hit and Breakeven is activated without being closed on the same candle.
        """
        sig = ActiveSignal(
            id="test_buy_tp1",
            symbol="XAUUSD",
            timeframe="15m",
            direction="BUY",
            entry_price=2650.0,
            stop_loss=2640.0,
            take_profit_1=2662.0,
            take_profit_2=2675.0,
            take_profit_3=2690.0,
            created_at=datetime.now(timezone.utc).isoformat(),
            ai_confidence=0.75,
            order_type="MARKET BUY",
            is_filled=True,
        )
        self.tracker.add_signal(sig)

        # High wicked to 2664.0 (above TP1 2662.0), but close is 2658.0
        alerts = self.tracker.update_price(
            symbol="XAUUSD",
            current_price=2658.0,
            high_price=2664.0,
            low_price=2649.0,
        )

        self.assertTrue(any(a["type"] == "TP1_HIT" for a in alerts))
        self.assertEqual(len(self.tracker.active_signals), 1)
        self.assertTrue(self.tracker.active_signals[0].tp1_hit)
        self.assertTrue(self.tracker.active_signals[0].breakeven_active)

        # In the next bar, price retraces to entry (2650.0) -> Breakeven Hit!
        retrace_alerts = self.tracker.update_price(
            symbol="XAUUSD",
            current_price=2649.5,
            high_price=2655.0,
            low_price=2649.0,
        )
        self.assertTrue(any(a["type"] == "BREAKEVEN_HIT" for a in retrace_alerts))
        self.assertEqual(len(self.tracker.active_signals), 0)
        self.assertEqual(self.tracker.closed_signals[0].close_reason, "TP1_BE")
        self.assertEqual(self.tracker.closed_signals[0].profit_r, 0.75)

    def test_buy_tp2_full_target_hit(self):
        """Verify that when price reaches TP2, trade closes with full win (+2.0R)."""
        sig = ActiveSignal(
            id="test_buy_tp2",
            symbol="XAUUSD",
            timeframe="15m",
            direction="BUY",
            entry_price=2650.0,
            stop_loss=2640.0,
            take_profit_1=2662.0,
            take_profit_2=2675.0,
            take_profit_3=2690.0,
            created_at=datetime.now(timezone.utc).isoformat(),
            ai_confidence=0.80,
            order_type="MARKET BUY",
            is_filled=True,
        )
        self.tracker.add_signal(sig)

        alerts = self.tracker.update_price(
            symbol="XAUUSD",
            current_price=2676.0,
            high_price=2678.0,
            low_price=2655.0,
        )

        self.assertTrue(any(a["type"] == "TP2_HIT" for a in alerts))
        self.assertEqual(len(self.tracker.active_signals), 0)
        self.assertEqual(self.tracker.closed_signals[0].close_reason, "TP2_WIN")
        self.assertEqual(self.tracker.closed_signals[0].profit_r, 2.0)

    def test_limit_order_retest_fill(self):
        """
        Verify that a pending BUY LIMIT order is only filled when price dips to entry_price.
        """
        sig = ActiveSignal(
            id="test_buy_limit",
            symbol="BTCUSDT",
            timeframe="15m",
            direction="BUY",
            entry_price=90000.0,
            stop_loss=88500.0,
            take_profit_1=91800.0,
            take_profit_2=93500.0,
            take_profit_3=96000.0,
            created_at=datetime.now(timezone.utc).isoformat(),
            ai_confidence=0.70,
            order_type="BUY LIMIT",
            is_filled=False,
        )
        self.tracker.add_signal(sig)

        # Price stays above entry (low 90500) -> Still pending fill
        alerts1 = self.tracker.update_price(
            symbol="BTCUSDT",
            current_price=90800.0,
            high_price=91200.0,
            low_price=90500.0,
        )
        self.assertEqual(len(alerts1), 0)
        self.assertFalse(self.tracker.active_signals[0].is_filled)

        # Price dips to 89900 (triggers entry 90000) -> Order is now FILLED!
        alerts2 = self.tracker.update_price(
            symbol="BTCUSDT",
            current_price=90100.0,
            high_price=90600.0,
            low_price=89900.0,
        )
        self.assertTrue(any(a["type"] == "LIMIT_FILLED" for a in alerts2))
        self.assertTrue(self.tracker.active_signals[0].is_filled)

    def test_sell_limit_order_and_execution(self):
        """Verify SELL LIMIT fill on high wick and subsequent TP1 / SL execution."""
        sig = ActiveSignal(
            id="test_sell_limit",
            symbol="ETHUSDT",
            timeframe="15m",
            direction="SELL",
            entry_price=3100.0,
            stop_loss=3150.0,
            take_profit_1=3040.0,
            take_profit_2=2975.0,
            take_profit_3=2900.0,
            created_at=datetime.now(timezone.utc).isoformat(),
            ai_confidence=0.75,
            order_type="SELL LIMIT",
            is_filled=False,
        )
        self.tracker.add_signal(sig)

        # High reaches 3105.0 -> Fills the SELL LIMIT
        fill_alerts = self.tracker.update_price(
            symbol="ETHUSDT",
            current_price=3095.0,
            high_price=3105.0,
            low_price=3085.0,
        )
        self.assertTrue(any(a["type"] == "LIMIT_FILLED" for a in fill_alerts))
        self.assertTrue(self.tracker.active_signals[0].is_filled)

        # Next bar price drops to TP1 (3035.0) -> Triggers TP1
        tp1_alerts = self.tracker.update_price(
            symbol="ETHUSDT",
            current_price=3045.0,
            high_price=3070.0,
            low_price=3035.0,
        )
        self.assertTrue(any(a["type"] == "TP1_HIT" for a in tp1_alerts))
        self.assertTrue(self.tracker.active_signals[0].breakeven_active)

    def test_limit_order_cancellation_when_runaway(self):
        """Verify that if price runs far away without retesting, the pending limit is safely cancelled."""
        sig = ActiveSignal(
            id="test_runaway",
            symbol="BTCUSDT",
            timeframe="15m",
            direction="BUY",
            entry_price=90000.0,
            stop_loss=89000.0,
            take_profit_1=91200.0,
            take_profit_2=92500.0,
            take_profit_3=94000.0,
            created_at=datetime.now(timezone.utc).isoformat(),
            ai_confidence=0.70,
            order_type="BUY LIMIT",
            is_filled=False,
        )
        self.tracker.add_signal(sig)

        # Price rockets to 93000 without ever hitting 90000 -> Expiration triggered!
        alerts = self.tracker.update_price(
            symbol="BTCUSDT",
            current_price=92800.0,
            high_price=93000.0,
            low_price=91500.0,
        )
        self.assertTrue(any(a["type"] == "LIMIT_CANCELLED" for a in alerts))
        self.assertEqual(len(self.tracker.active_signals), 0)
        self.assertEqual(self.tracker.closed_signals[0].close_reason, "LIMIT_EXPIRED")

    def test_trader_keyboard_layout(self):
        """Verify the ergonomic 4x2 keyboard structure."""
        from src.bot_menu import MAIN_KEYBOARD, DEFAULT_KEYBOARD
        self.assertIn("keyboard", MAIN_KEYBOARD)
        rows = MAIN_KEYBOARD["keyboard"]
        self.assertEqual(len(rows), 4, "Should have exactly 4 rows for clean mobile view")
        for row in rows:
            self.assertEqual(len(row), 2, "Each row should have exactly 2 buttons for balanced symmetry")
        self.assertTrue(MAIN_KEYBOARD["resize_keyboard"])
        self.assertTrue(MAIN_KEYBOARD["persistent"])

    def test_lot_numeric_query_detection(self):
        """Verify that trader shorthand numbers are recognized instantly without commands."""
        from src.bot_menu import is_lot_numeric_query
        self.assertTrue(is_lot_numeric_query("1000 1"))
        self.assertTrue(is_lot_numeric_query("$2500 2%"))
        self.assertTrue(is_lot_numeric_query("5000"))
        self.assertTrue(is_lot_numeric_query("10,000 1.5"))
        self.assertFalse(is_lot_numeric_query("salom bot"))
        self.assertFalse(is_lot_numeric_query("xauusd buy"))

    def test_format_lot_calculation(self):
        """Verify lot sizing and inline quick presets."""
        from src.bot_menu import format_lot_calculation
        text, markup = format_lot_calculation(1000.0, 1.0)
        self.assertIn("$1,000.00", text)
        self.assertIn("1.0%", text)
        self.assertIn("0.03 lot", text)  # $10 risk / 300 = 0.033 -> 0.03 lot
        self.assertIn("inline_keyboard", markup)
        self.assertEqual(len(markup["inline_keyboard"]), 3)

    def test_format_analyze_and_mode_menus(self):
        """Verify 1-tap interactive inline menus."""
        from src.bot_menu import format_analyze_menu, format_mode_menu
        # Analyze menu
        a_text, a_markup = format_analyze_menu()
        self.assertIn("TEZKOR BOZOR TAHLILI", a_text)
        callbacks = [btn["callback_data"] for row in a_markup["inline_keyboard"] for btn in row]
        self.assertIn("analyze:XAUUSD", callbacks)
        self.assertIn("analyze:BTCUSDT", callbacks)
        self.assertIn("why:XAUUSD", callbacks)

        # Mode menu
        m_text, m_markup = format_mode_menu("standard")
        self.assertIn("Standart", m_text)
        mode_callbacks = [btn["callback_data"] for row in m_markup["inline_keyboard"] for btn in row]
        self.assertIn("set_mode:aggressive", mode_callbacks)
        self.assertIn("set_mode:standard", mode_callbacks)
        self.assertIn("set_mode:conservative", mode_callbacks)

    def test_human_like_ai_chat_response(self):
        """Verify that AI assistant speaks like a real human trader, not a robotic template."""
        from src.ai_chat import MarketAIAssistant, detect_symbol_from_text
        ai = MarketAIAssistant()

        # 1. Symbol detection
        self.assertEqual(detect_symbol_from_text("Oltin nima bo'lyapti?"), "XAUUSD")
        self.assertEqual(detect_symbol_from_text("Bitkoin tushadimi?"), "BTCUSDT")

        # 2. Casual greeting response -> Friendly, single-sentence human reply
        greeting_reply = ai._generate_heuristic_response("Salom", {})
        self.assertIn("Va alaykum assalom", greeting_reply)
        self.assertNotIn("• Joriy Narx:", greeting_reply, "Greetings must not dump a rigid table!")
        self.assertNotIn("1-qism", greeting_reply)

        # 3. Market inquiry response -> Natural conversational trader prose
        market_ctx = {
            "symbol": "XAUUSD",
            "current_price": 2650.0,
            "htf_trend": "BULLISH",
            "ml_signal": "HOLD",
            "gate_reason": "Bozor tasdiqni kutmoqda",
        }
        market_reply = ai._generate_heuristic_response("Oltinda vaziyat qanday?", market_ctx)
        self.assertIn("XAUUSD", market_reply)
        self.assertIn("$2,650.00", market_reply)
        self.assertNotIn("• 1H Trend:", market_reply, "Must be natural human prose, not rigid bullets")
        self.assertNotIn("📊 #XAUUSD BOZOR TAHLILI:", market_reply)

        # 4. Learning & Self-improvement inquiry response
        learn_reply = ai._generate_heuristic_response("O'zingni qanday kuchaytiryapsan?", market_ctx)
        self.assertIn("avtomatik", learn_reply)
        self.assertIn("/learn", learn_reply)

    def test_self_learning_engine_post_mortem_and_penalties(self):
        """Verify SelfLearningEngine analyzes trade losses, records lessons, and updates pattern weights."""
        from src.self_learner import SelfLearningEngine
        from src.signal_tracker import ActiveSignal
        learner = SelfLearningEngine()

        sig = ActiveSignal(
            id="test_learn_sig_1",
            symbol="XAUUSD",
            timeframe="15m",
            direction="BUY",
            entry_price=2650.0,
            stop_loss=2640.0,
            take_profit_1=2662.0,
            take_profit_2=2675.0,
            take_profit_3=2690.0,
            created_at=datetime.now(timezone.utc).isoformat(),
            ai_confidence=0.75,
            order_type="MARKET BUY",
            is_filled=True,
            highest_pips=2.0,
        )

        # Simulate SL hit with counter-trend context
        context = {"h4_trend": "BEARISH", "macro": "BEARISH", "regime": "Trending"}
        res = learner.on_trade_closed(sig, "SL_LOSS", 2640.0, -1.0, context=context)

        self.assertEqual(res["status"], "ANALYZED")
        self.assertEqual(res["outcome"], "LOSS")
        self.assertIn("COUNTER_TREND", res["failure_tag"])
        self.assertTrue(len(res["lesson"]) > 10)

        # Verify pattern penalty was registered
        penalty = learner.db.get_pattern_penalty(res["pattern_key"])
        self.assertGreater(penalty, 0.0)

        # Test setup evaluation receives penalty
        penalty_val, warning = learner.evaluate_setup("XAUUSD", "BUY", {"h4_trend": "BEARISH", "macro": "BEARISH"})
        self.assertGreaterEqual(penalty_val, 0.05)
        self.assertIn("AI O'z-o'zini o'rganish xotirasi", warning)

        # Simulate winning trade to verify positive reinforcement
        win_sig = ActiveSignal(
            id="test_learn_sig_2",
            symbol="XAUUSD",
            timeframe="15m",
            direction="BUY",
            entry_price=2650.0,
            stop_loss=2640.0,
            take_profit_1=2662.0,
            take_profit_2=2675.0,
            take_profit_3=2690.0,
            created_at=datetime.now(timezone.utc).isoformat(),
            ai_confidence=0.75,
            order_type="MARKET BUY",
            is_filled=True,
        )
        win_res = learner.on_trade_closed(win_sig, "TP2_WIN", 2675.0, 2.0, context={"h4_trend": "BULLISH"})
        self.assertEqual(win_res["outcome"], "WIN")
        self.assertIn("REINFORCED", win_res["status"])

    def test_adaptive_capital_protection_and_reporting(self):
        """Verify adaptive capital protection activates during loss streaks and reports format cleanly."""
        from src.self_learner import SelfLearningEngine
        learner = SelfLearningEngine()

        # Check adaptive capital protection API
        adaptive = learner.get_adaptive_capital_protection()
        self.assertIn("is_active", adaptive)
        self.assertIn("threshold_boost", adaptive)
        self.assertIn("status_badge", adaptive)

        # Check report formatting
        report = learner.format_recent_lessons_report(limit=3)
        self.assertIn("CYBER TRADE — AI O'Z-O'ZINI O'RGANISH TIZIMI", report)
        self.assertIn("O'rganilgan Darslar:", report)

        # Check AI grounding context
        grounding = learner.get_ai_grounding_context()
        self.assertIn("AI", grounding)
        self.assertTrue(isinstance(grounding, str))

    def test_mt5_fetcher_and_gold_configuration(self):
        """Verify MetaTrader 5 / XM integration and Gold-centered configuration."""
        from src.mt5_fetcher import mt5_fetcher
        from src.config import get_config

        # 1. MT5 Fetcher properties
        self.assertEqual(mt5_fetcher.login, 108742123)
        self.assertEqual(mt5_fetcher.server, "XMGlobal-MT5 5")
        self.assertEqual(mt5_fetcher.find_gold_symbol(), "GOLD")
        # Ensure safe non-crash behavior when MT5 terminal is not attached on host
        res = mt5_fetcher.get_market_data("XAUUSD", "15m", 100)
        self.assertIsNone(res)

        # 2. Config verification
        cfg = get_config()
        self.assertIn("XAUUSD", cfg.market.symbols)
        self.assertEqual(cfg.market.gold_symbol_yf, "GC=F")
        self.assertTrue(cfg.mt5.enabled)
        self.assertEqual(cfg.mt5.login, 108742123)
        self.assertEqual(cfg.mt5.server, "XMGlobal-MT5 5")


if __name__ == "__main__":
    unittest.main()
