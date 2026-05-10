import pytest
from datetime import UTC, date, datetime, timedelta

from trading_system.models import Candle, OptionContractCandidate, SignalAction, StrategySignal
from trading_system.market_data import SyntheticMarketDataProvider
from trading_system.strategies import StrategyContext, select_strategy
from trading_system.simulator import option_carry_adjusted_candle, realistic_option_fill_price, replay_options_week, replay_week, simulate_option_limit_fill


@pytest.mark.asyncio
async def test_replay_week_creates_equity_curve() -> None:
    provider = SyntheticMarketDataProvider()
    history = await provider.get_history(["BTC-USD", "ETH-USD", "SOL-USD"], days=30)
    context = StrategyContext(history=history, heat={symbol: 0.8 for symbol in history}, cash=500, equity=500)
    signal = select_strategy(context).generate(context)
    broker = replay_week(500, history, signal)
    assert len(broker.equity_curve) == 7
    assert broker.equity_curve[-1].equity >= 0


def test_replay_options_week_uses_multiplier_and_contract_sizing() -> None:
    start = datetime(2026, 5, 1, tzinfo=UTC)
    candles = [
        Candle(
            symbol="O:NVDA260522C00220000",
            timestamp=start + timedelta(days=idx),
            open=3.0 + idx * 0.2,
            high=3.4 + idx * 0.2,
            low=2.8 + idx * 0.2,
            close=3.2 + idx * 0.2,
            volume=5000,
            source="test_options",
        )
        for idx in range(8)
    ]
    contract = OptionContractCandidate(
        ticker="O:NVDA260522C00220000",
        underlying="NVDA",
        contract_type="call",
        expiration_date=date(2026, 5, 22),
        strike=220,
        premium=3.0,
        bid=2.95,
        ask=3.05,
        mid=3.0,
        delta=0.45,
        theta=-0.18,
        implied_volatility=0.55,
        volume=5000,
        open_interest=25000,
        dte=14,
        score=100,
        spread_pct=3.33,
        historical_spread_pct=4.0,
        liquidity_score=0.95,
        slippage_tier="tight",
        theta_daily=-0.18,
        dte_risk="normal",
        earnings_risk="none",
        iv_crush_risk="low",
        expected_iv_crush_pct=0,
    )
    signal = StrategySignal(
        strategy_id="momentum_breakout_options",
        strategy_name="Momentum Breakout Options Overlay",
        symbol=contract.ticker,
        action=SignalAction.BUY,
        confidence=0.8,
        target_notional=410,
        stop_loss_pct=0.45,
        take_profit_pct=1.1,
        invalidation="test",
        reason="test option execution",
        data_sources=["options"],
        generated_at=start,
        instrument_type="option",
        underlying_symbol="NVDA",
        multiplier=100,
        option_contract=contract,
        contract_quantity=1,
    )

    broker = replay_options_week(500, candles, signal, contract)

    assert broker.trades
    assert broker.trades[0].instrument_type == "option"
    assert broker.trades[0].quantity == 1
    assert broker.trades[0].notional > 300
    assert broker.equity_curve[-1].equity != 500


def test_option_carry_adjusts_for_theta_and_iv_crush() -> None:
    candle = Candle(
        symbol="O:NVDA260522C00220000",
        timestamp=datetime(2026, 5, 8, tzinfo=UTC),
        open=4.0,
        high=4.3,
        low=3.8,
        close=4.1,
        volume=5000,
        source="massive_options",
    )
    contract = OptionContractCandidate(
        ticker=candle.symbol,
        underlying="NVDA",
        contract_type="call",
        expiration_date=date(2026, 5, 22),
        strike=220,
        premium=4.0,
        bid=3.9,
        ask=4.1,
        mid=4.0,
        delta=0.45,
        theta=-0.22,
        implied_volatility=0.9,
        volume=5000,
        open_interest=25000,
        dte=6,
        score=100,
        spread_pct=5,
        liquidity_score=0.9,
        slippage_tier="tight",
        theta_daily=-0.22,
        dte_risk="accelerating",
        earnings_risk="earnings_within_7d",
        iv_crush_risk="medium",
        expected_iv_crush_pct=22,
    )

    adjusted = option_carry_adjusted_candle(candle, contract, days_held=3)

    assert adjusted.close < candle.close
    assert adjusted.low > 0


def test_wide_option_tier_gets_worse_fill_than_tight() -> None:
    candle = Candle(
        symbol="O:TQQQ260522C00080000",
        timestamp=datetime(2026, 5, 8, tzinfo=UTC),
        open=2.0,
        high=2.2,
        low=1.9,
        close=2.05,
        volume=400,
        source="massive_options",
    )
    base = dict(
        ticker=candle.symbol,
        underlying="TQQQ",
        contract_type="call",
        expiration_date=date(2026, 5, 22),
        strike=80,
        premium=2.0,
        bid=1.9,
        ask=2.1,
        mid=2.0,
        delta=0.4,
        theta=-0.08,
        implied_volatility=0.75,
        volume=400,
        open_interest=900,
        dte=14,
        score=50,
        theta_daily=-0.08,
        dte_risk="normal",
        earnings_risk="none",
        iv_crush_risk="low",
        expected_iv_crush_pct=0,
    )
    tight = OptionContractCandidate(**base, spread_pct=5, liquidity_score=0.85, slippage_tier="tight")
    wide = OptionContractCandidate(**base, spread_pct=17, liquidity_score=0.28, slippage_tier="wide")

    tight_fill, _ = realistic_option_fill_price(candle, tight, SignalAction.BUY)
    wide_fill, _ = realistic_option_fill_price(candle, wide, SignalAction.BUY)

    assert wide_fill > tight_fill


def test_option_limit_fill_can_miss_on_liquidity_gap() -> None:
    candle = Candle(
        symbol="O:XYZ260522C00010000",
        timestamp=datetime(2026, 5, 8, tzinfo=UTC),
        open=1.0,
        high=1.02,
        low=0.98,
        close=1.0,
        volume=0,
        source="massive_options",
    )
    contract = OptionContractCandidate(
        ticker=candle.symbol,
        underlying="XYZ",
        contract_type="call",
        expiration_date=date(2026, 5, 22),
        strike=10,
        premium=1.0,
        bid=0.55,
        ask=1.45,
        mid=1.0,
        delta=0.35,
        theta=-0.03,
        implied_volatility=1.2,
        volume=0,
        open_interest=3,
        dte=14,
        score=5,
        spread_pct=90,
        historical_spread_pct=80,
        spread_history_pct=[70, 76, 80],
        liquidity_score=0.04,
        slippage_tier="avoid",
        theta_daily=-0.03,
        dte_risk="normal",
        earnings_risk="none",
        iv_crush_risk="low",
        expected_iv_crush_pct=0,
    )

    decision = simulate_option_limit_fill(candle, contract, SignalAction.BUY)

    assert not decision.filled
    assert decision.liquidity_gap
    assert "Liquidity gap" in (decision.missed_reason or "")


def test_snapshot_fill_uses_last_trade_and_queue_not_auto_touch() -> None:
    timestamp = datetime(2026, 5, 8, tzinfo=UTC)
    candle = Candle(
        symbol="O:NVDA260522C00220000",
        timestamp=timestamp,
        open=3.0,
        high=3.1,
        low=2.9,
        close=3.0,
        volume=1500,
        source="massive_options_snapshot",
    )
    base = dict(
        ticker=candle.symbol,
        underlying="NVDA",
        contract_type="call",
        expiration_date=date(2026, 5, 22),
        strike=220,
        premium=3.0,
        bid=2.95,
        ask=3.05,
        mid=3.0,
        delta=0.45,
        theta=-0.12,
        implied_volatility=0.55,
        volume=1500,
        open_interest=12000,
        dte=14,
        score=90,
        spread_pct=3.3,
        liquidity_score=0.82,
        slippage_tier="tight",
        quote_age_seconds=10,
        microstructure_score=0.9,
        theta_daily=-0.12,
        dte_risk="normal",
        earnings_risk="none",
        iv_crush_risk="low",
        expected_iv_crush_pct=0,
    )
    without_print = OptionContractCandidate(**base)
    with_print = OptionContractCandidate(**base, last_trade_price=3.0, last_trade_size=20, last_trade_timestamp=timestamp)

    missed = simulate_option_limit_fill(candle, without_print, SignalAction.BUY)
    filled = simulate_option_limit_fill(candle, with_print, SignalAction.BUY)

    assert missed.queue_position_pct is not None
    assert not missed.filled
    assert filled.filled
