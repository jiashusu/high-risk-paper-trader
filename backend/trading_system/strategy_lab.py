from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from statistics import mean

from .models import (
    Candle,
    SignalAction,
    StrategyBacktestSummary,
    StrategyEnvironmentPerformance,
    StrategyForwardPerformance,
    StrategyLabEntry,
    StrategyLabResponse,
    StrategyParameterVersion,
    StrategyScore,
    StrategySignal,
    Trade,
)
from .simulator import PaperBroker
from .strategies import BUILT_IN_STRATEGIES, Strategy, StrategyContext


STRATEGY_METADATA: dict[str, dict] = {
    "momentum_breakout": {
        "version": "mb-v1.4",
        "thesis": "追踪一周内最强势资产，只在热度和短线胜率同时过线时出手。",
        "parameters": {"lookback_days": 5, "min_hit_rate": 0.45, "stop_loss_pct": 0.16, "take_profit_pct": 0.55},
        "data": ["daily bars", "news heat", "liquidity score"],
    },
    "volatility_expansion": {
        "version": "ve-v1.2",
        "thesis": "波动率突然放大时，使用小窗口跟随爆发方向，适合凸性押注。",
        "parameters": {"range_window": 5, "confidence_trigger": 0.55, "stop_loss_pct": 0.18, "take_profit_pct": 0.70},
        "data": ["daily high/low/close", "range expansion", "news heat"],
    },
    "trend_following": {
        "version": "tf-v1.3",
        "thesis": "只跟随 20/50 日趋势结构最干净的资产，牺牲爆发力换稳定性。",
        "parameters": {"fast_ma": 20, "slow_ma": 50, "slope_trigger": 0.8, "stop_loss_pct": 0.14, "take_profit_pct": 0.42},
        "data": ["daily bars", "moving averages"],
    },
    "relative_strength_rotation": {
        "version": "rsr-v1.1",
        "thesis": "每周轮动到一月和一周相对强度同时靠前的资产。",
        "parameters": {"month_lookback": 21, "week_lookback": 5, "strength_trigger": 4.0, "stop_loss_pct": 0.17},
        "data": ["daily bars", "relative strength ranking"],
    },
    "volatility_contraction_breakout": {
        "version": "vcb-v1.0",
        "thesis": "寻找先收缩再突破的结构，避免在已经乱涨乱跌时追高。",
        "parameters": {"contraction_window": 5, "prior_window": 15, "score_trigger": 2.5, "stop_loss_pct": 0.20},
        "data": ["daily bars", "range breakout", "volatility contraction"],
    },
    "event_catalyst_momentum": {
        "version": "ecm-v1.2",
        "thesis": "只在新闻/事件热度足够高且价格没有明显转弱时追随催化。",
        "parameters": {"min_heat": 0.68, "min_weekly_return_pct": -2.0, "stop_loss_pct": 0.22, "take_profit_pct": 0.90},
        "data": ["news heat", "earnings calendar", "daily bars"],
    },
    "mean_reversion_snapback": {
        "version": "mrs-v1.0",
        "thesis": "在中期趋势仍向上时，买入短线过度下跌后的反弹。",
        "parameters": {"trend_ma": 50, "min_snapback_score": 3.0, "stop_loss_pct": 0.12, "take_profit_pct": 0.28},
        "data": ["daily bars", "mean reversion score"],
    },
    "risk_parity_flat": {
        "version": "cash-v1.0",
        "thesis": "当数据、回撤或策略质量不过关时，现金就是策略。",
        "parameters": {"max_allowed_drawdown_pct": 24, "min_strategy_score": 28, "target_notional": 0},
        "data": ["risk gates", "source health", "strategy ranking"],
    },
}


def build_strategy_lab(
    context: StrategyContext,
    ranking: list[StrategyScore],
    broker: PaperBroker,
    active_signal: StrategySignal,
    data_anomalies: list[str],
    ledger_summary: dict,
) -> StrategyLabResponse:
    score_by_id = {score.strategy_id.removesuffix("_options"): score for score in ranking}
    rank_by_id = {score.strategy_id.removesuffix("_options"): index + 1 for index, score in enumerate(ranking)}
    active_id = active_signal.strategy_id.removesuffix("_options")
    entries = [
        _build_entry(
            strategy=strategy,
            rank=rank_by_id.get(strategy.strategy_id, len(BUILT_IN_STRATEGIES)),
            score=score_by_id.get(strategy.strategy_id),
            context=context,
            broker=broker,
            active_id=active_id,
            data_anomalies=data_anomalies,
            ledger_summary=ledger_summary,
        )
        for strategy in BUILT_IN_STRATEGIES
    ]
    entries.sort(key=lambda entry: (entry.status != "active", entry.rank))
    return StrategyLabResponse(
        generated_at=datetime.now(UTC),
        active_strategy_id=active_id,
        entries=entries,
        research_notes=[
            "实验室分为 forward ledger 和历史窗口回测：forward 是真钱前唯一可采信的上线证据，历史回测只用于筛掉明显不适配的策略。",
            "策略活下来不能只看总分；必须解释数据质量、市场环境、风险门槛和最近真实模拟表现。",
            "如果某策略在高波动、熊市或震荡环境里样本太少，实验室会把它标记为需要更多样本，而不是直接相信分数。",
        ],
    )


def _build_entry(
    strategy: Strategy,
    rank: int,
    score: StrategyScore | None,
    context: StrategyContext,
    broker: PaperBroker,
    active_id: str,
    data_anomalies: list[str],
    ledger_summary: dict,
) -> StrategyLabEntry:
    metadata = STRATEGY_METADATA[strategy.strategy_id]
    environments = _environment_performance(strategy, context)
    backtest = _backtest_summary(environments)
    forward = _forward_performance(strategy.strategy_id, broker.trades, float(ledger_summary.get("completed_forward_weeks", 0.0)))
    score_value = score.score if score else 0.0
    status = _status(strategy.strategy_id, active_id, score, forward, backtest, data_anomalies)
    return StrategyLabEntry(
        strategy_id=strategy.strategy_id,
        name=strategy.name,
        rank=rank,
        status=status,
        score=score_value,
        parameter_version=StrategyParameterVersion(
            version_id=metadata["version"],
            description=f"{strategy.name} 参数版本，随 forward 表现和风控复盘迭代。",
            parameters=metadata["parameters"],
        ),
        thesis=metadata["thesis"],
        live_reason=_live_reason(strategy.strategy_id, active_id, score, forward, backtest),
        survival_reason=_survival_reason(score, forward, backtest),
        elimination_reason=_elimination_reason(score, forward, backtest, data_anomalies),
        risk_notes=_risk_notes(score, backtest, data_anomalies),
        data_requirements=metadata["data"],
        forward=forward,
        backtest=backtest,
        environments=environments,
    )


def _environment_performance(strategy: Strategy, context: StrategyContext) -> list[StrategyEnvironmentPerformance]:
    buckets: dict[str, list[tuple[float, float, bool]]] = defaultdict(list)
    for start in range(0, 150, 10):
        window_history: dict[str, list[Candle]] = {}
        for symbol, candles in context.history.items():
            if len(candles) < start + 31:
                continue
            window = candles[-(start + 31) : -start if start else None]
            if len(window) >= 31:
                window_history[symbol] = window
        if not window_history:
            continue
        window_context = StrategyContext(history=window_history, heat=context.heat, cash=context.cash, equity=context.equity)
        signal = strategy.generate(window_context)
        score = strategy.score(window_context)
        market_env = _classify_environment(window_history)
        simulated_return = score.weekly_return_pct if signal.action == SignalAction.BUY else 0.0
        if strategy.strategy_id == "risk_parity_flat":
            simulated_return = 0.0
        buckets[market_env].append((simulated_return, score.max_drawdown_pct, simulated_return > 0))

    if not buckets:
        return [
            StrategyEnvironmentPerformance(environment="unknown", return_pct=0, max_drawdown_pct=0, hit_rate=0, sample_size=0, verdict="样本不足，不能上线。")
        ]

    return [
        StrategyEnvironmentPerformance(
            environment=environment,
            return_pct=round(sum(item[0] for item in rows), 2),
            max_drawdown_pct=round(max(item[1] for item in rows), 2),
            hit_rate=round(sum(1 for item in rows if item[2]) / len(rows), 2),
            sample_size=len(rows),
            verdict=_environment_verdict(sum(item[0] for item in rows), max(item[1] for item in rows), len(rows)),
        )
        for environment, rows in sorted(buckets.items())
    ]


def _backtest_summary(environments: list[StrategyEnvironmentPerformance]) -> StrategyBacktestSummary:
    total_return = sum(env.return_pct for env in environments)
    max_drawdown = max((env.max_drawdown_pct for env in environments), default=0.0)
    sample_size = sum(env.sample_size for env in environments)
    hit_rate = (
        sum(env.hit_rate * env.sample_size for env in environments) / sample_size
        if sample_size
        else 0.0
    )
    best = max(environments, key=lambda env: env.return_pct, default=None)
    worst = min(environments, key=lambda env: env.return_pct, default=None)
    return StrategyBacktestSummary(
        total_return_pct=round(total_return, 2),
        max_drawdown_pct=round(max_drawdown, 2),
        hit_rate=round(hit_rate, 2),
        sample_size=sample_size,
        best_environment=best.environment if best else "unknown",
        worst_environment=worst.environment if worst else "unknown",
    )


def _forward_performance(strategy_id: str, trades: list[Trade], forward_weeks: float) -> StrategyForwardPerformance:
    related = [trade for trade in trades if trade.strategy_id.removesuffix("_options") == strategy_id]
    buys: dict[str, list[float]] = defaultdict(list)
    closed = 0
    wins = 0
    realized = 0.0
    for trade in related:
        if trade.side == SignalAction.BUY:
            buys[trade.symbol].append(trade.notional + trade.fee)
        elif trade.side == SignalAction.SELL and buys[trade.symbol]:
            entry_cost = buys[trade.symbol].pop(0)
            pnl = trade.notional - trade.fee - entry_cost
            realized += pnl
            closed += 1
            wins += 1 if pnl > 0 else 0
    last_trade_at = max((trade.timestamp for trade in related), default=None)
    return StrategyForwardPerformance(
        trades=len(related),
        closed_round_trips=closed,
        realized_pnl=round(realized, 2),
        win_rate=round(wins / closed, 2) if closed else 0.0,
        last_trade_at=last_trade_at,
        forward_weeks=round(forward_weeks, 2),
        verdict=_forward_verdict(len(related), closed, realized, wins / closed if closed else 0.0, forward_weeks),
    )


def _classify_environment(history: dict[str, list[Candle]]) -> str:
    returns: list[float] = []
    vols: list[float] = []
    drawdowns: list[float] = []
    for candles in history.values():
        closes = [candle.close for candle in candles[-21:] if candle.close > 0]
        if len(closes) < 6:
            continue
        daily = [(closes[idx] / closes[idx - 1] - 1) for idx in range(1, len(closes))]
        returns.append(closes[-1] / closes[0] - 1)
        vols.append(mean(abs(item) for item in daily))
        peak = closes[0]
        drawdown = 0.0
        for close in closes:
            peak = max(peak, close)
            drawdown = min(drawdown, close / peak - 1)
        drawdowns.append(drawdown)
    if not returns:
        return "unknown"
    total_return = mean(returns)
    volatility = mean(vols)
    drawdown = mean(drawdowns)
    if drawdown <= -0.18:
        return "flash_crash"
    if volatility >= 0.035:
        return "high_volatility"
    if total_return >= 0.06:
        return "bull_trend"
    if total_return <= -0.06:
        return "bear_trend"
    return "range_bound"


def _environment_verdict(return_pct: float, drawdown_pct: float, sample_size: int) -> str:
    if sample_size < 2:
        return "样本太少，只能观察。"
    if return_pct > 0 and drawdown_pct <= 18:
        return "环境适配，可以继续保留。"
    if drawdown_pct > 24:
        return "回撤过大，不能直接上线。"
    return "表现一般，需要 forward 继续证明。"


def _status(
    strategy_id: str,
    active_id: str,
    score: StrategyScore | None,
    forward: StrategyForwardPerformance,
    backtest: StrategyBacktestSummary,
    data_anomalies: list[str],
) -> str:
    if strategy_id == active_id:
        return "active"
    if data_anomalies and any("selected_option_quality" in anomaly or "market_freshness" in anomaly for anomaly in data_anomalies):
        return "data_watch"
    if score and (score.score < 28 or score.max_drawdown_pct > 24):
        return "rejected"
    if forward.trades == 0 and backtest.sample_size < 6:
        return "needs_samples"
    return "bench"


def _live_reason(strategy_id: str, active_id: str, score: StrategyScore | None, forward: StrategyForwardPerformance, backtest: StrategyBacktestSummary) -> str:
    if strategy_id == active_id:
        return "上线原因：当前排名最高或风险门槛后仍是最可执行策略。"
    if score and score.score >= 45 and backtest.max_drawdown_pct <= 20:
        return "候选原因：分数和历史环境表现足够进入观察队列，但还没超过当前策略。"
    if forward.trades > 0:
        return "候选原因：已经有 forward 交易样本，需要继续累积真实模拟结果。"
    return "未上线：目前没有足够证据超过当前策略。"


def _survival_reason(score: StrategyScore | None, forward: StrategyForwardPerformance, backtest: StrategyBacktestSummary) -> str:
    reasons = []
    if score and score.reliability_score >= 0.65:
        reasons.append("可靠性评分仍可接受")
    if backtest.hit_rate >= 0.45:
        reasons.append("历史窗口命中率没有失真")
    if forward.trades == 0:
        reasons.append("forward 样本不足，暂不淘汰")
    elif forward.realized_pnl >= 0:
        reasons.append("forward 已实现盈亏没有恶化")
    return "；".join(reasons) or "只能留作研究观察，暂时不能加仓。"


def _elimination_reason(score: StrategyScore | None, forward: StrategyForwardPerformance, backtest: StrategyBacktestSummary, data_anomalies: list[str]) -> str:
    if data_anomalies:
        return "淘汰/降级原因：当前存在数据异常，任何策略都不能靠坏数据上线。"
    if score and score.max_drawdown_pct > 24:
        return "淘汰原因：近期最大回撤超过策略切换阈值。"
    if score and score.score < 28:
        return "淘汰原因：综合分低于现金防御阈值。"
    if backtest.max_drawdown_pct > 30:
        return "淘汰原因：历史窗口回撤太深。"
    if forward.closed_round_trips >= 3 and forward.realized_pnl < 0:
        return "淘汰原因：forward 已实现交易连续证明失败。"
    return "暂不淘汰：没有触发硬性下线条件。"


def _risk_notes(score: StrategyScore | None, backtest: StrategyBacktestSummary, data_anomalies: list[str]) -> list[str]:
    notes: list[str] = []
    if score and score.sample_size < 10:
        notes.append("近期样本偏少，不能只看分数。")
    if backtest.max_drawdown_pct > 20:
        notes.append("历史环境里出现过较深回撤，需要仓位折扣。")
    if data_anomalies:
        notes.append("当前数据源异常，策略必须降级或空仓。")
    if not notes:
        notes.append("当前没有硬风险红旗，但仍必须经过 forward ledger 验证。")
    return notes


def _forward_verdict(trades: int, closed: int, realized: float, win_rate: float, forward_weeks: float) -> str:
    if forward_weeks < 1:
        return "forward 时间太短，不能下结论。"
    if trades == 0:
        return "还没有真实 forward 开仓样本。"
    if closed == 0:
        return "已有入场但尚未闭环，等待退出结果。"
    if realized > 0 and win_rate >= 0.5:
        return "forward 初步有效，但仍需至少 4 周。"
    return "forward 表现偏弱，需要降权或继续观察。"
