from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from .models import Candle, SignalAction, StrategyScore, StrategySignal


@dataclass(frozen=True)
class StrategyContext:
    history: dict[str, list[Candle]]
    heat: dict[str, float]
    cash: float
    equity: float


class Strategy:
    strategy_id: str
    name: str
    base_heat: float
    reliability: float

    def generate(self, context: StrategyContext) -> StrategySignal:
        raise NotImplementedError

    def score(self, context: StrategyContext) -> StrategyScore:
        symbol, weekly_return, drawdown, hit_rate, sample_size = self._best_symbol_metrics(context)
        score = (
            weekly_return * 1.7
            - drawdown * 1.2
            + hit_rate * 16
            + self.base_heat * 14
            + self.reliability * 18
            + context.heat.get(symbol, 0.5) * 12
        )
        return StrategyScore(
            strategy_id=self.strategy_id,
            name=self.name,
            score=round(score, 2),
            weekly_return_pct=round(weekly_return, 2),
            max_drawdown_pct=round(drawdown, 2),
            hit_rate=round(hit_rate, 2),
            sample_size=sample_size,
            heat_score=round((self.base_heat + context.heat.get(symbol, 0.5)) / 2, 2),
            reliability_score=self.reliability,
            explanation=self._explanation(symbol),
            status="candidate",
        )

    def _best_symbol_metrics(self, context: StrategyContext) -> tuple[str, float, float, float, int]:
        best_symbol = "BTC-USD"
        best_return = -999.0
        best_drawdown = 0.0
        best_hit_rate = 0.0
        best_sample = 0
        for symbol, candles in context.history.items():
            if len(candles) < 15:
                continue
            closes = [c.close for c in candles]
            weekly_return = (closes[-1] / closes[-6] - 1) * 100
            rolling_peak = closes[-15]
            drawdown = 0.0
            wins = 0
            for idx in range(-14, 0):
                rolling_peak = max(rolling_peak, closes[idx])
                drawdown = min(drawdown, (closes[idx] / rolling_peak - 1) * 100)
                wins += 1 if closes[idx] > closes[idx - 1] else 0
            adjusted = weekly_return + context.heat.get(symbol, 0.5) * 4
            if adjusted > best_return:
                best_symbol = symbol
                best_return = weekly_return
                best_drawdown = abs(drawdown)
                best_hit_rate = wins / 14
                best_sample = 14
        return best_symbol, best_return, best_drawdown, best_hit_rate, best_sample

    def _explanation(self, symbol: str) -> str:
        return f"{symbol} has the strongest fit for {self.name} under the current weekly ranking."


class MomentumBreakoutStrategy(Strategy):
    strategy_id = "momentum_breakout"
    name = "Momentum Breakout"
    base_heat = 0.88
    reliability = 0.7

    def generate(self, context: StrategyContext) -> StrategySignal:
        symbol, weekly_return, drawdown, hit_rate, _ = self._best_symbol_metrics(context)
        confidence = max(0.35, min(0.92, 0.48 + weekly_return / 35 + context.heat.get(symbol, 0.5) / 4))
        target_notional = context.equity * min(0.78, 0.38 + confidence / 2)
        action = SignalAction.BUY if weekly_return > 0 and hit_rate >= 0.45 else SignalAction.HOLD
        return StrategySignal(
            strategy_id=self.strategy_id,
            strategy_name=self.name,
            symbol=symbol,
            action=action,
            confidence=round(confidence, 2),
            target_notional=round(target_notional, 2),
            stop_loss_pct=0.16,
            take_profit_pct=0.55,
            invalidation=f"Weekly momentum turns negative or drawdown exceeds {max(12, round(drawdown + 4, 1))}%.",
            reason=f"{symbol} is leading the universe on 5-day momentum with sufficient heat and liquidity.",
            data_sources=["market:daily-bars", "news:heat-score"],
            generated_at=datetime.now(UTC),
        )


class VolatilityExpansionStrategy(Strategy):
    strategy_id = "volatility_expansion"
    name = "Volatility Expansion"
    base_heat = 0.76
    reliability = 0.64

    def generate(self, context: StrategyContext) -> StrategySignal:
        selected = "BTC-USD"
        selected_range = -1.0
        for symbol, candles in context.history.items():
            if len(candles) < 10:
                continue
            recent = candles[-5:]
            avg_range = sum((c.high - c.low) / c.close for c in recent) / len(recent)
            if avg_range > selected_range:
                selected = symbol
                selected_range = avg_range
        confidence = max(0.4, min(0.86, selected_range * 6 + context.heat.get(selected, 0.5) / 3))
        return StrategySignal(
            strategy_id=self.strategy_id,
            strategy_name=self.name,
            symbol=selected,
            action=SignalAction.BUY if confidence > 0.55 else SignalAction.HOLD,
            confidence=round(confidence, 2),
            target_notional=round(context.equity * min(0.65, 0.25 + confidence / 2), 2),
            stop_loss_pct=0.18,
            take_profit_pct=0.7,
            invalidation="Range expansion fails and closes back below the prior 5-day median.",
            reason=f"{selected} has the widest recent range expansion, suitable for a convex weekly bet.",
            data_sources=["market:daily-bars", "volatility:range"],
            generated_at=datetime.now(UTC),
        )


class TrendFollowingStrategy(Strategy):
    strategy_id = "trend_following"
    name = "Trend Following"
    base_heat = 0.72
    reliability = 0.78

    def generate(self, context: StrategyContext) -> StrategySignal:
        selected = "SPY"
        selected_slope = -999.0
        for symbol, candles in context.history.items():
            if len(candles) < 70:
                continue
            closes = [c.close for c in candles]
            ma20 = sum(closes[-20:]) / 20
            ma50 = sum(closes[-50:]) / 50
            slope = (ma20 / ma50 - 1) * 100 + context.heat.get(symbol, 0.5) * 2
            if slope > selected_slope:
                selected = symbol
                selected_slope = slope
        confidence = max(0.35, min(0.86, 0.48 + selected_slope / 20))
        return StrategySignal(
            strategy_id=self.strategy_id,
            strategy_name=self.name,
            symbol=selected,
            action=SignalAction.BUY if selected_slope > 0.8 else SignalAction.HOLD,
            confidence=round(confidence, 2),
            target_notional=round(context.equity * min(0.62, 0.28 + confidence / 3), 2),
            stop_loss_pct=0.14,
            take_profit_pct=0.42,
            invalidation="20-day trend falls back below the 50-day trend filter.",
            reason=f"{selected} has the cleanest 20/50 trend alignment in the universe.",
            data_sources=["market:daily-bars", "trend:ma20-ma50"],
            generated_at=datetime.now(UTC),
        )


class RelativeStrengthRotationStrategy(Strategy):
    strategy_id = "relative_strength_rotation"
    name = "Relative Strength Rotation"
    base_heat = 0.8
    reliability = 0.7

    def generate(self, context: StrategyContext) -> StrategySignal:
        selected = "QQQ"
        selected_strength = -999.0
        for symbol, candles in context.history.items():
            if len(candles) < 35:
                continue
            closes = [c.close for c in candles]
            strength = (closes[-1] / closes[-21] - 1) * 100 + (closes[-1] / closes[-6] - 1) * 45
            strength += context.heat.get(symbol, 0.5) * 5
            if strength > selected_strength:
                selected = symbol
                selected_strength = strength
        confidence = max(0.38, min(0.9, 0.42 + selected_strength / 55))
        return StrategySignal(
            strategy_id=self.strategy_id,
            strategy_name=self.name,
            symbol=selected,
            action=SignalAction.BUY if selected_strength > 4 else SignalAction.HOLD,
            confidence=round(confidence, 2),
            target_notional=round(context.equity * min(0.72, 0.32 + confidence / 2.6), 2),
            stop_loss_pct=0.17,
            take_profit_pct=0.58,
            invalidation="Relative strength rank drops below the top third of the universe.",
            reason=f"{selected} is leading on combined 1-month and 1-week relative strength.",
            data_sources=["market:daily-bars", "ranking:relative-strength"],
            generated_at=datetime.now(UTC),
        )


class VolatilityContractionBreakoutStrategy(Strategy):
    strategy_id = "volatility_contraction_breakout"
    name = "Volatility Contraction Breakout"
    base_heat = 0.74
    reliability = 0.66

    def generate(self, context: StrategyContext) -> StrategySignal:
        selected = "NVDA"
        selected_score = -999.0
        for symbol, candles in context.history.items():
            if len(candles) < 30:
                continue
            recent = candles[-5:]
            prior = candles[-20:-5]
            recent_range = sum((c.high - c.low) / c.close for c in recent) / len(recent)
            prior_range = sum((c.high - c.low) / c.close for c in prior) / len(prior)
            breakout = candles[-1].close / max(c.high for c in prior) - 1
            score = (prior_range / max(recent_range, 0.001)) + breakout * 40 + context.heat.get(symbol, 0.5) * 2
            if score > selected_score:
                selected = symbol
                selected_score = score
        confidence = max(0.34, min(0.88, 0.38 + selected_score / 18))
        return StrategySignal(
            strategy_id=self.strategy_id,
            strategy_name=self.name,
            symbol=selected,
            action=SignalAction.BUY if selected_score > 2.5 else SignalAction.HOLD,
            confidence=round(confidence, 2),
            target_notional=round(context.equity * min(0.58, 0.25 + confidence / 3), 2),
            stop_loss_pct=0.2,
            take_profit_pct=0.75,
            invalidation="Breakout fails and closes back inside the contraction range.",
            reason=f"{selected} shows volatility contraction with a breakout attempt.",
            data_sources=["market:daily-bars", "volatility:contraction", "breakout:range"],
            generated_at=datetime.now(UTC),
        )


class EventCatalystMomentumStrategy(Strategy):
    strategy_id = "event_catalyst_momentum"
    name = "Event Catalyst Momentum"
    base_heat = 0.84
    reliability = 0.62

    def generate(self, context: StrategyContext) -> StrategySignal:
        symbol, weekly_return, drawdown, _, _ = self._best_symbol_metrics(context)
        heat = context.heat.get(symbol, 0.5)
        confidence = max(0.32, min(0.9, heat * 0.72 + weekly_return / 45))
        return StrategySignal(
            strategy_id=self.strategy_id,
            strategy_name=self.name,
            symbol=symbol,
            action=SignalAction.BUY if heat >= 0.68 and weekly_return > -2 else SignalAction.HOLD,
            confidence=round(confidence, 2),
            target_notional=round(context.equity * min(0.55, 0.18 + confidence / 3), 2),
            stop_loss_pct=0.22,
            take_profit_pct=0.9,
            invalidation=f"Catalyst heat fades or drawdown exceeds {max(14, round(drawdown + 6, 1))}%.",
            reason=f"{symbol} combines high catalyst heat with non-negative weekly momentum.",
            data_sources=["news:heat-score", "market:daily-bars", "events:earnings-calendar"],
            generated_at=datetime.now(UTC),
        )


class MeanReversionSnapbackStrategy(Strategy):
    strategy_id = "mean_reversion_snapback"
    name = "Mean Reversion Snapback"
    base_heat = 0.55
    reliability = 0.58

    def generate(self, context: StrategyContext) -> StrategySignal:
        selected = "QQQ"
        selected_score = -999.0
        for symbol, candles in context.history.items():
            if len(candles) < 60:
                continue
            closes = [c.close for c in candles]
            ma50 = sum(closes[-50:]) / 50
            five_day = (closes[-1] / closes[-6] - 1) * 100
            trend_ok = closes[-1] > ma50
            score = (-five_day if five_day < 0 else -999) + (2 if trend_ok else -4) + context.heat.get(symbol, 0.5)
            if score > selected_score:
                selected = symbol
                selected_score = score
        confidence = max(0.28, min(0.72, 0.35 + selected_score / 16))
        return StrategySignal(
            strategy_id=self.strategy_id,
            strategy_name=self.name,
            symbol=selected,
            action=SignalAction.BUY if selected_score > 3 else SignalAction.HOLD,
            confidence=round(confidence, 2),
            target_notional=round(context.equity * min(0.38, 0.15 + confidence / 4), 2),
            stop_loss_pct=0.12,
            take_profit_pct=0.28,
            invalidation="Snapback fails within the next paper tick or breaks the 50-day trend.",
            reason=f"{selected} is oversold inside a still-positive medium-term trend.",
            data_sources=["market:daily-bars", "mean-reversion:5-day-drop"],
            generated_at=datetime.now(UTC),
        )


class RiskParityFlatStrategy(Strategy):
    strategy_id = "risk_parity_flat"
    name = "Risk Parity / Cash Defense"
    base_heat = 0.45
    reliability = 0.92

    def generate(self, context: StrategyContext) -> StrategySignal:
        return StrategySignal(
            strategy_id=self.strategy_id,
            strategy_name=self.name,
            symbol="USD",
            action=SignalAction.FLAT,
            confidence=0.8,
            target_notional=0,
            stop_loss_pct=0.01,
            take_profit_pct=0.02,
            invalidation="Re-enter only after a candidate strategy clears reliability and drawdown thresholds.",
            reason="Capital preservation wins when drawdown or data quality violates the weekly risk gate.",
            data_sources=["risk:drawdown", "strategy:ranking"],
            generated_at=datetime.now(UTC),
        )


BUILT_IN_STRATEGIES: list[Strategy] = [
    MomentumBreakoutStrategy(),
    VolatilityExpansionStrategy(),
    TrendFollowingStrategy(),
    RelativeStrengthRotationStrategy(),
    VolatilityContractionBreakoutStrategy(),
    EventCatalystMomentumStrategy(),
    MeanReversionSnapbackStrategy(),
    RiskParityFlatStrategy(),
]


def rank_strategies(context: StrategyContext) -> list[StrategyScore]:
    scores = [strategy.score(context) for strategy in BUILT_IN_STRATEGIES]
    scores.sort(key=lambda item: item.score, reverse=True)
    if scores:
        scores[0].status = "active"
    return scores


def select_strategy(context: StrategyContext) -> Strategy:
    scores = rank_strategies(context)
    if scores and (scores[0].max_drawdown_pct > 24 or scores[0].score < 28):
        return RiskParityFlatStrategy()
    active_id = scores[0].strategy_id if scores else "risk_parity_flat"
    return next((strategy for strategy in BUILT_IN_STRATEGIES if strategy.strategy_id == active_id), RiskParityFlatStrategy())
