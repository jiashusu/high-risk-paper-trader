from datetime import UTC, datetime, timedelta

from .models import LiveReadinessGate, ReviewDecision, StrategyScore, WeeklyReport
from .simulator import PaperBroker


def choose_decision(portfolio_return: float, drawdown: float, current: StrategyScore, candidates: list[StrategyScore]) -> ReviewDecision:
    if drawdown >= 35 or portfolio_return <= -35:
        return ReviewDecision.GO_FLAT
    challenger = next((candidate for candidate in candidates if candidate.strategy_id != current.strategy_id), None)
    if challenger and challenger.score >= current.score + 8 and challenger.reliability_score >= 0.65:
        return ReviewDecision.SWITCH_STRATEGY
    if portfolio_return >= 25 and drawdown < 18 and current.sample_size >= 14:
        return ReviewDecision.READY_FOR_MANUAL_LIVE
    return ReviewDecision.CONTINUE


def build_weekly_report(
    broker: PaperBroker,
    current: StrategyScore,
    candidates: list[StrategyScore],
    live_readiness: LiveReadinessGate | None = None,
    data_anomalies: list[str] | None = None,
    forward_hit_rate: float = 0.0,
) -> WeeklyReport:
    latest = broker.equity_curve[-1].timestamp if broker.equity_curve else datetime.now(UTC)
    snapshot = broker.mark_to_market({}, latest)
    decision = choose_decision(snapshot.weekly_return_pct, snapshot.max_drawdown_pct, current, candidates)
    headline = {
        ReviewDecision.CONTINUE: "Continue paper trading with the active strategy.",
        ReviewDecision.SWITCH_STRATEGY: "Switch strategy at the next weekly rebalance.",
        ReviewDecision.GO_FLAT: "Risk fuse says go flat and preserve capital.",
        ReviewDecision.READY_FOR_MANUAL_LIVE: "Eligible for a manual-live review, not automatic live trading.",
    }[decision]
    trade_lines = "\n".join(
        f"- {trade.timestamp.date()} {trade.side.value.upper()} {trade.symbol} ${trade.notional:.2f} via {trade.strategy_id}: {trade.reason}"
        for trade in broker.trades
    ) or "- No trades were placed."
    strategy_lines = "\n".join(
        f"- {candidate.name}: score {candidate.score}, return {candidate.weekly_return_pct}%, drawdown {candidate.max_drawdown_pct}%."
        for candidate in candidates
    )
    anomalies = data_anomalies or []
    anomaly_lines = "\n".join(f"- {item}" for item in anomalies) or "- No current data anomalies."
    live_gate_lines = "\n".join(
        f"- {'PASS' if criterion.passed else 'BLOCK'} {criterion.name}: {criterion.detail}"
        for criterion in (live_readiness.criteria if live_readiness else [])
    ) or "- Live readiness gate was not evaluated."
    allowed = "YES" if live_readiness and live_readiness.ready_for_live else "NO"
    markdown = f"""# Weekly Paper Trading Report

Generated: {latest.isoformat()}

## Decision

**{decision.value}** - {headline}

## Portfolio

- Starting cash: ${broker.initial_cash:.2f}
- Current equity: ${snapshot.equity:.2f}
- Forward PnL: ${snapshot.equity - broker.initial_cash:.2f}
- Weekly return: {snapshot.weekly_return_pct:.2f}%
- Max drawdown: {snapshot.max_drawdown_pct:.2f}%
- Forward hit rate: {forward_hit_rate * 100:.1f}%

## Trades

{trade_lines}

## Strategy Ranking

{strategy_lines}

## Data Anomalies

{anomaly_lines}

## Live Trading Gate

Allowed to continue toward live mode: **{allowed}**

{live_gate_lines}

Phase 1 remains paper-only. A real-money workflow requires at least four forward-paper weeks, clean logs, and explicit manual approval.
"""
    return WeeklyReport(
        generated_at=latest,
        period_start=latest - timedelta(days=7),
        period_end=latest,
        decision=decision,
        headline=headline,
        markdown=markdown,
        portfolio=snapshot,
        current_strategy=current,
        candidate_strategies=candidates,
        trades=broker.trades,
        forward_pnl=round(snapshot.equity - broker.initial_cash, 2),
        forward_hit_rate=round(forward_hit_rate, 4),
        data_anomalies=anomalies,
        live_readiness=live_readiness,
    )
