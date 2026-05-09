from datetime import UTC, date, datetime

from trading_system.config import Settings
from trading_system.live_gate import build_live_readiness, build_order_draft
from trading_system.models import DataSourceStatus, OptionContractCandidate, SignalAction, StrategySignal


def make_signal(contract: OptionContractCandidate) -> StrategySignal:
    return StrategySignal(
        strategy_id="momentum_breakout_options",
        strategy_name="Momentum Breakout Options Overlay",
        symbol=contract.ticker,
        action=SignalAction.BUY,
        confidence=0.8,
        target_notional=250,
        stop_loss_pct=0.45,
        take_profit_pct=1.1,
        invalidation="test",
        reason="test",
        data_sources=["options"],
        generated_at=datetime.now(UTC),
        instrument_type="option",
        underlying_symbol=contract.underlying,
        multiplier=100,
        option_contract=contract,
        contract_quantity=1,
    )


def make_contract() -> OptionContractCandidate:
    return OptionContractCandidate(
        ticker="O:TQQQ260522C00080000",
        underlying="TQQQ",
        contract_type="call",
        expiration_date=date(2026, 5, 22),
        strike=80,
        premium=2.28,
        bid=2.14,
        ask=2.42,
        mid=2.28,
        delta=0.38,
        theta=-0.13,
        implied_volatility=0.62,
        volume=2288,
        open_interest=771,
        dte=13,
        score=100,
        spread_pct=12.28,
        historical_spread_pct=11.2,
        liquidity_score=0.52,
        slippage_tier="normal",
        chain_rank=2,
        chain_candidates=14,
        theta_daily=-0.13,
        dte_risk="normal",
        earnings_risk="none",
        iv_crush_risk="low",
        expected_iv_crush_pct=0,
    )


def test_order_draft_is_limit_defined_risk_and_live_disabled() -> None:
    settings = Settings(onboarding_completed=True, allow_options=True, watch_only_mode=False)
    contract = make_contract()
    draft = build_order_draft(
        settings,
        make_signal(contract),
        contract,
        {"latest_equity": 500, "daily_loss_pct": 0, "weekly_loss_pct": 0},
        [DataSourceStatus(name="market_freshness", enabled=True, healthy=True, detail="ok")],
        [],
    )

    assert draft is not None
    assert draft.order_type == "limit"
    assert draft.live_submission_enabled is False
    assert draft.max_loss > draft.estimated_notional
    assert draft.paper_trade_allowed


def test_live_gate_blocks_before_four_forward_weeks() -> None:
    gate = build_live_readiness(
        Settings(live_min_forward_weeks=4),
        {"completed_forward_weeks": 1.5, "max_drawdown_pct": 0, "daily_loss_pct": 0, "weekly_loss_pct": 0},
        [
            DataSourceStatus(name="massive", enabled=True, healthy=True, detail="ok"),
            DataSourceStatus(name="options_snapshot", enabled=True, healthy=True, detail="ok"),
            DataSourceStatus(name="options_opportunity_scan", enabled=True, healthy=True, detail="ok"),
            DataSourceStatus(name="market_freshness", enabled=True, healthy=True, detail="ok"),
            DataSourceStatus(name="selected_option_quality", enabled=True, healthy=True, detail="ok"),
            DataSourceStatus(name="price_cross_check", enabled=True, healthy=True, detail="ok"),
        ],
        [],
    )

    assert not gate.ready_for_live
    assert any("forward paper weeks" in blocker for blocker in gate.blockers)
