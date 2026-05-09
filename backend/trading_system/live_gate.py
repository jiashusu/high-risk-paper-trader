from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from .config import Settings
from .models import BrokerOrderDraft, DataSourceStatus, GateCriterion, LiveReadinessGate, OptionContractCandidate, SignalAction, StrategySignal


def build_live_readiness(
    settings: Settings,
    ledger_summary: dict,
    source_statuses: list[DataSourceStatus],
    data_anomalies: list[str],
) -> LiveReadinessGate:
    completed_weeks = float(ledger_summary.get("completed_forward_weeks", 0.0))
    critical_sources_ok = all(
        status.healthy
        for status in source_statuses
        if status.enabled and status.name in {"massive", "options_snapshot", "options_opportunity_scan", "market_freshness", "selected_option_quality", "price_cross_check"}
    )
    criteria = [
        GateCriterion(
            name="4_week_forward_ledger",
            passed=completed_weeks >= settings.live_min_forward_weeks,
            detail=f"{completed_weeks:.2f}/{settings.live_min_forward_weeks} forward paper weeks complete.",
        ),
        GateCriterion(
            name="order_draft_only",
            passed=True,
            detail="Broker order draft stage is enabled; live submission is hard-disabled.",
        ),
        GateCriterion(
            name="onboarding_complete",
            passed=settings.onboarding_completed,
            detail="First-start onboarding must be completed before any live readiness discussion.",
        ),
        GateCriterion(
            name="watch_only_mode",
            passed=not settings.watch_only_mode,
            detail="Watch-only mode must be turned off before the system can open paper entries or draft live orders.",
        ),
        GateCriterion(
            name="critical_data_sources",
            passed=critical_sources_ok,
            detail="Critical price/options/source checks must all be healthy.",
        ),
        GateCriterion(
            name="no_data_anomalies",
            passed=not data_anomalies,
            detail=f"{len(data_anomalies)} current data anomaly/anomalies.",
        ),
        GateCriterion(
            name="forward_drawdown",
            passed=float(ledger_summary.get("max_drawdown_pct", 0.0)) < settings.max_weekly_loss_pct,
            detail=f"Forward max drawdown {float(ledger_summary.get('max_drawdown_pct', 0.0)):.2f}% vs {settings.max_weekly_loss_pct:.2f}% weekly fuse.",
        ),
        GateCriterion(
            name="daily_loss_fuse",
            passed=float(ledger_summary.get("daily_loss_pct", 0.0)) < settings.max_daily_loss_pct,
            detail=f"Daily loss {float(ledger_summary.get('daily_loss_pct', 0.0)):.2f}% vs {settings.max_daily_loss_pct:.2f}% fuse.",
        ),
        GateCriterion(
            name="weekly_loss_fuse",
            passed=float(ledger_summary.get("weekly_loss_pct", 0.0)) < settings.max_weekly_loss_pct,
            detail=f"Weekly loss {float(ledger_summary.get('weekly_loss_pct', 0.0)):.2f}% vs {settings.max_weekly_loss_pct:.2f}% fuse.",
        ),
    ]
    blockers = [criterion.detail for criterion in criteria if not criterion.passed]
    return LiveReadinessGate(
        ready_for_live=not blockers,
        required_forward_weeks=settings.live_min_forward_weeks,
        completed_forward_weeks=round(completed_weeks, 2),
        can_create_order_draft=True,
        blockers=blockers,
        criteria=criteria,
    )


def build_order_draft(
    settings: Settings,
    signal: StrategySignal,
    contract: OptionContractCandidate | None,
    ledger_summary: dict,
    source_statuses: list[DataSourceStatus],
    data_anomalies: list[str],
) -> BrokerOrderDraft | None:
    if signal.action != SignalAction.BUY:
        return None
    if not contract and not settings.allow_options:
        return None

    checks: list[GateCriterion] = []
    blocking: list[str] = []
    equity = float(ledger_summary.get("latest_equity", settings.paper_initial_cash))

    if contract:
        quantity = max(0, signal.contract_quantity or 0)
        estimated_fee = quantity * 0.65
        estimated_notional = quantity * contract.ask * contract.multiplier
        max_loss = estimated_notional + estimated_fee
        limit_price = contract.ask
        expiry_risk_exit_at = contract.expiration_date - timedelta(days=2)
        instrument_type = "option"
        symbol = contract.ticker
        underlying = contract.underlying
        option_policy_ok = contract.contract_type in {"call", "put"} and quantity >= 1
        spread_pct = contract.spread_pct or (contract.ask - contract.bid) / max(contract.mid, 0.01) * 100
        historical_spread_pct = contract.historical_spread_pct or spread_pct
        checks.extend(
            [
                GateCriterion(name="options_allowed", passed=settings.allow_options, detail="Options trading must be explicitly enabled in onboarding."),
                GateCriterion(name="defined_risk_only", passed=option_policy_ok, detail="Only long call/put drafts are allowed before live mode."),
                GateCriterion(name="limit_order_required", passed=True, detail=f"Limit price fixed at current estimated ask {limit_price:.4f}."),
                GateCriterion(name="max_slippage", passed=spread_pct <= settings.max_order_slippage_pct, detail=f"Current spread/slippage {spread_pct:.2f}% <= {settings.max_order_slippage_pct:.2f}%."),
                GateCriterion(name="historical_spread_floor", passed=historical_spread_pct <= max(settings.max_order_slippage_pct, 18.0), detail=f"Historical spread floor {historical_spread_pct:.2f}% must stay tradable."),
                GateCriterion(name="liquidity_score", passed=contract.liquidity_score >= 0.25, detail=f"Option liquidity score {contract.liquidity_score:.2f} >= 0.25."),
                GateCriterion(name="slippage_tier", passed=contract.slippage_tier in {"tight", "normal", "wide"}, detail=f"Contract slippage tier is {contract.slippage_tier}; avoid-tier contracts are blocked."),
                GateCriterion(name="dte_risk", passed=contract.dte_risk in {"normal", "accelerating"} and contract.dte > 2, detail=f"DTE risk is {contract.dte_risk}; exit required by {expiry_risk_exit_at.isoformat()} before expiration risk window."),
                GateCriterion(name="iv_crush_risk", passed=contract.iv_crush_risk != "high", detail=f"IV crush risk is {contract.iv_crush_risk} with expected crush {contract.expected_iv_crush_pct:.1f}%."),
            ]
        )
    else:
        quantity = 0
        estimated_fee = 0.0
        estimated_notional = signal.target_notional
        max_loss = estimated_notional * signal.stop_loss_pct
        limit_price = 0.0
        expiry_risk_exit_at = None
        instrument_type = signal.instrument_type
        symbol = signal.symbol
        underlying = signal.underlying_symbol
        checks.append(GateCriterion(name="defined_risk_only", passed=False, detail="No valid option contract selected for a broker draft."))

    position_cap = equity * settings.max_position_pct / 100
    checks.extend(
        [
            GateCriterion(name="single_trade_loss", passed=max_loss <= equity * settings.max_single_trade_loss_pct / 100, detail=f"Max loss ${max_loss:.2f} <= {settings.max_single_trade_loss_pct:.1f}% of equity."),
            GateCriterion(name="position_cap", passed=estimated_notional <= position_cap, detail=f"Draft notional ${estimated_notional:.2f} <= ${position_cap:.2f} position cap."),
            GateCriterion(name="daily_loss_fuse", passed=float(ledger_summary.get("daily_loss_pct", 0.0)) < settings.max_daily_loss_pct, detail=f"Daily loss {float(ledger_summary.get('daily_loss_pct', 0.0)):.2f}% < {settings.max_daily_loss_pct:.2f}%."),
            GateCriterion(name="weekly_loss_fuse", passed=float(ledger_summary.get("weekly_loss_pct", 0.0)) < settings.max_weekly_loss_pct, detail=f"Weekly loss {float(ledger_summary.get('weekly_loss_pct', 0.0)):.2f}% < {settings.max_weekly_loss_pct:.2f}%."),
            GateCriterion(name="api_anomaly_fuse", passed=not data_anomalies, detail=f"{len(data_anomalies)} data anomaly/anomalies currently active."),
            GateCriterion(name="onboarding_complete", passed=settings.onboarding_completed, detail="First-start onboarding is complete."),
            GateCriterion(name="watch_only_mode", passed=not settings.watch_only_mode, detail="Watch-only mode blocks new paper entries and broker drafts."),
            GateCriterion(name="live_submission_disabled", passed=True, detail="Draft cannot be submitted live from this app."),
        ]
    )

    for status in source_statuses:
        if status.enabled and status.name in {"market_freshness", "selected_option_quality", "price_cross_check"} and not status.healthy:
            checks.append(GateCriterion(name=f"source_{status.name}", passed=False, detail=status.detail))

    blocking = [check.detail for check in checks if not check.passed]
    return BrokerOrderDraft(
        draft_id=str(uuid4()),
        created_at=datetime.now(UTC),
        broker="alpaca",
        account_mode="paper_draft_only",
        live_submission_enabled=False,
        symbol=symbol,
        underlying_symbol=underlying,
        instrument_type=instrument_type,
        side=SignalAction.BUY,
        quantity=quantity,
        order_type="limit",
        limit_price=round(limit_price, 4),
        estimated_notional=round(estimated_notional, 2),
        estimated_fee=round(estimated_fee, 2),
        max_loss=round(max_loss, 2),
        max_slippage_pct=settings.max_order_slippage_pct,
        position_cap_pct=settings.max_position_pct,
        time_in_force="day",
        expiry_risk_exit_at=expiry_risk_exit_at,
        strategy_id=signal.strategy_id,
        reason=signal.reason,
        checks=checks,
        blocking_reasons=blocking,
        paper_trade_allowed=not blocking,
    )
