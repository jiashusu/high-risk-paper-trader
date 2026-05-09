from datetime import UTC, datetime

from trading_system.models import SignalAction, StrategySignal
from trading_system.risk import RiskManager


def make_signal() -> StrategySignal:
    return StrategySignal(
        strategy_id="momentum_breakout",
        strategy_name="Momentum Breakout",
        symbol="BTC-USD",
        action=SignalAction.BUY,
        confidence=0.8,
        target_notional=500,
        stop_loss_pct=0.16,
        take_profit_pct=0.55,
        invalidation="test",
        reason="test",
        data_sources=["test"],
        generated_at=datetime.now(UTC),
    )


def test_weekly_loss_fuse_goes_flat() -> None:
    signal, warnings = RiskManager().apply(make_signal(), equity=500, weekly_return_pct=-40, existing_positions=[], liquidity_score=1)
    assert signal.action == SignalAction.FLAT
    assert signal.target_notional == 0
    assert warnings


def test_single_position_cap_reduces_notional() -> None:
    signal, warnings = RiskManager(single_position_cap_pct=50).apply(
        make_signal(), equity=500, weekly_return_pct=0, existing_positions=[], liquidity_score=1
    )
    assert signal.target_notional == 250
    assert "Single-position cap" in warnings[0]

