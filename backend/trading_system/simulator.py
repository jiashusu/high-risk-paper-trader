from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
import hashlib
from uuid import uuid4

from .models import Candle, EquityPoint, OptionContractCandidate, PortfolioSnapshot, Position, SignalAction, StrategySignal, Trade


OPTION_FEE_PER_CONTRACT = 0.65


@dataclass(frozen=True)
class OptionFillDecision:
    filled: bool
    fill_price: float
    slippage_per_contract: float
    limit_price: float
    bid: float
    ask: float
    mid_price: float
    spread_pct: float
    historical_spread_pct: float | None
    fill_probability: float
    liquidity_gap: bool
    missed_reason: str | None = None


class PaperBroker:
    def __init__(self, initial_cash: float = 500.0) -> None:
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.positions: dict[str, Position] = {}
        self.trades: list[Trade] = []
        self.equity_curve: list[EquityPoint] = []
        self.execution_events: list[dict] = []

    def drain_execution_events(self) -> list[dict]:
        events = self.execution_events
        self.execution_events = []
        return events

    def mark_to_market(self, latest: dict[str, Candle], timestamp: datetime | None = None) -> PortfolioSnapshot:
        positions: list[Position] = []
        equity = self.cash
        for symbol, position in list(self.positions.items()):
            price = latest.get(symbol).close if symbol in latest else position.market_price
            market_value = position.quantity * price * position.multiplier
            updated = position.model_copy(
                update={
                    "market_price": price,
                    "market_value": market_value,
                    "unrealized_pnl": market_value - position.quantity * position.avg_entry_price * position.multiplier,
                }
            )
            self.positions[symbol] = updated
            positions.append(updated)
            equity += market_value

        now = timestamp or datetime.now(UTC)
        self.equity_curve.append(EquityPoint(timestamp=now, equity=round(equity, 2)))
        weekly_return = ((equity / self.initial_cash) - 1) * 100
        max_drawdown = self._max_drawdown_pct()
        return PortfolioSnapshot(
            timestamp=now,
            cash=round(self.cash, 2),
            equity=round(equity, 2),
            weekly_return_pct=round(weekly_return, 2),
            max_drawdown_pct=round(max_drawdown, 2),
            positions=positions,
        )

    def execute(self, signal: StrategySignal, candle: Candle) -> Trade | None:
        if signal.action in {SignalAction.HOLD, SignalAction.FLAT}:
            if signal.action == SignalAction.FLAT:
                return self.close_all(candle, signal)
            return None
        if signal.action == SignalAction.BUY:
            return self.buy(signal, candle)
        if signal.action == SignalAction.SELL:
            return self.close_all(candle, signal)
        return None

    def buy(self, signal: StrategySignal, candle: Candle) -> Trade | None:
        notional = min(signal.target_notional, self.cash)
        if notional < 1:
            return None
        fill_price, slippage = realistic_fill_price(candle, notional, side=SignalAction.BUY)
        fee = notional * fee_rate_for_symbol(signal.symbol)
        quantity = max(0, (notional - fee) / fill_price)
        self.cash -= notional
        existing = self.positions.get(signal.symbol)
        if existing:
            total_qty = existing.quantity + quantity
            avg_price = ((existing.avg_entry_price * existing.quantity) + (fill_price * quantity)) / total_qty
        else:
            total_qty = quantity
            avg_price = fill_price
        self.positions[signal.symbol] = Position(
            symbol=signal.symbol,
            quantity=total_qty,
            avg_entry_price=avg_price,
            market_price=candle.close,
            market_value=total_qty * candle.close,
            unrealized_pnl=total_qty * (candle.close - avg_price),
            stop_loss=avg_price * (1 - signal.stop_loss_pct),
            take_profit=avg_price * (1 + signal.take_profit_pct),
        )
        trade = Trade(
            trade_id=str(uuid4()),
            timestamp=candle.timestamp,
            symbol=signal.symbol,
            side=SignalAction.BUY,
            quantity=round(quantity, 8),
            price=round(fill_price, 4),
            notional=round(notional, 2),
            fee=round(fee, 4),
            slippage=round(slippage, 4),
            strategy_id=signal.strategy_id,
            reason=signal.reason,
            exit_condition=signal.invalidation,
        )
        self.trades.append(trade)
        return trade

    def close_all(self, candle: Candle, signal: StrategySignal) -> Trade | None:
        position = self.positions.pop(candle.symbol, None)
        if not position:
            return None
        gross_reference = position.quantity * candle.open
        fill_price, slippage = realistic_fill_price(candle, gross_reference, side=SignalAction.SELL)
        gross = position.quantity * fill_price
        fee = gross * fee_rate_for_symbol(candle.symbol)
        self.cash += gross - fee
        trade = Trade(
            trade_id=str(uuid4()),
            timestamp=candle.timestamp,
            symbol=candle.symbol,
            side=SignalAction.SELL,
            quantity=round(position.quantity, 8),
            price=round(fill_price, 4),
            notional=round(gross, 2),
            fee=round(fee, 4),
            slippage=round(slippage, 4),
            strategy_id=signal.strategy_id,
            reason=f"Exit: {signal.invalidation}",
            exit_condition=signal.invalidation,
        )
        self.trades.append(trade)
        return trade

    def enforce_stops(self, candles: dict[str, Candle], signal: StrategySignal) -> None:
        for symbol, position in list(self.positions.items()):
            candle = candles.get(symbol)
            if not candle:
                continue
            stop_touched = candle.low <= position.stop_loss
            target_touched = candle.high >= position.take_profit
            if stop_touched or target_touched:
                trigger = position.stop_loss if stop_touched else position.take_profit
                execution_candle = candle.model_copy(update={"open": trigger, "close": trigger})
                exit_signal = signal.model_copy(
                    update={
                        "symbol": symbol,
                        "action": SignalAction.SELL,
                        "invalidation": "Stop loss or take profit touched by intraday high/low.",
                    }
                )
                self.close_all(execution_candle, exit_signal)

    def buy_option(self, signal: StrategySignal, candle: Candle, contract: OptionContractCandidate) -> Trade | None:
        max_notional = min(signal.target_notional, self.cash)
        decision = simulate_option_limit_fill(candle, contract, side=SignalAction.BUY, allow_missed=True)
        if not decision.filled:
            self._record_option_execution_event("option_order_missed", decision, signal, contract, candle)
            return None
        fill_price = decision.fill_price
        slippage_per_contract = decision.slippage_per_contract
        per_contract_cost = fill_price * contract.multiplier + OPTION_FEE_PER_CONTRACT
        contracts = int(max_notional // per_contract_cost)
        if signal.contract_quantity is not None:
            contracts = min(contracts, signal.contract_quantity)
        if contracts < 1:
            self._record_option_execution_event("option_order_missed", decision, signal, contract, candle, "Insufficient cash for one option contract after limit-fill estimate.")
            return None

        gross = contracts * fill_price * contract.multiplier
        fee = contracts * OPTION_FEE_PER_CONTRACT
        total_cost = gross + fee
        self.cash -= total_cost
        self.positions[contract.ticker] = Position(
            symbol=contract.ticker,
            quantity=contracts,
            avg_entry_price=fill_price,
            market_price=candle.close,
            market_value=contracts * candle.close * contract.multiplier,
            unrealized_pnl=contracts * (candle.close - fill_price) * contract.multiplier,
            stop_loss=fill_price * (1 - signal.stop_loss_pct),
            take_profit=fill_price * (1 + signal.take_profit_pct),
            instrument_type="option",
            underlying_symbol=contract.underlying,
            multiplier=contract.multiplier,
            expiration_date=contract.expiration_date,
            strike=contract.strike,
            option_type=contract.contract_type,
            delta=contract.delta,
            theta=contract.theta,
            implied_volatility=contract.implied_volatility,
            spread_pct=contract.spread_pct,
            historical_spread_pct=contract.historical_spread_pct,
            spread_history_pct=contract.spread_history_pct,
            liquidity_score=contract.liquidity_score,
            slippage_tier=contract.slippage_tier,
            entry_bid=decision.bid,
            entry_ask=decision.ask,
            entry_mid=decision.mid_price,
            entry_limit_price=decision.limit_price,
            entry_fill_probability=decision.fill_probability,
            entry_liquidity_gap=decision.liquidity_gap,
            chain_rank=contract.chain_rank,
            chain_candidates=contract.chain_candidates,
            theta_daily=contract.theta_daily,
            dte_risk=contract.dte_risk,
            earnings_risk=contract.earnings_risk,
            iv_crush_risk=contract.iv_crush_risk,
            expected_iv_crush_pct=contract.expected_iv_crush_pct,
        )
        trade = Trade(
            trade_id=str(uuid4()),
            timestamp=candle.timestamp,
            symbol=contract.ticker,
            side=SignalAction.BUY,
            quantity=contracts,
            price=round(fill_price, 4),
            notional=round(gross, 2),
            fee=round(fee, 4),
            slippage=round(slippage_per_contract * contracts * contract.multiplier, 4),
            strategy_id=signal.strategy_id,
            reason=signal.reason,
            exit_condition=signal.invalidation,
            instrument_type="option",
            underlying_symbol=contract.underlying,
            multiplier=contract.multiplier,
            expiration_date=contract.expiration_date,
            strike=contract.strike,
            option_type=contract.contract_type,
            delta=contract.delta,
            theta=contract.theta,
            implied_volatility=contract.implied_volatility,
            spread_pct=contract.spread_pct,
            historical_spread_pct=contract.historical_spread_pct,
            spread_history_pct=contract.spread_history_pct,
            liquidity_score=contract.liquidity_score,
            slippage_tier=contract.slippage_tier,
            bid=round(decision.bid, 4),
            ask=round(decision.ask, 4),
            mid_price=round(decision.mid_price, 4),
            limit_price=round(decision.limit_price, 4),
            fill_probability=round(decision.fill_probability, 4),
            liquidity_gap=decision.liquidity_gap,
            chain_rank=contract.chain_rank,
            chain_candidates=contract.chain_candidates,
            theta_daily=contract.theta_daily,
            dte_risk=contract.dte_risk,
            earnings_risk=contract.earnings_risk,
            iv_crush_risk=contract.iv_crush_risk,
            expected_iv_crush_pct=contract.expected_iv_crush_pct,
        )
        self.trades.append(trade)
        self._record_option_execution_event("option_limit_fill", decision, signal, contract, candle)
        return trade

    def close_option(self, candle: Candle, signal: StrategySignal, contract: OptionContractCandidate, exit_condition: str) -> Trade | None:
        position = self.positions.get(contract.ticker)
        if not position:
            return None
        decision = simulate_option_limit_fill(candle, contract, side=SignalAction.SELL, allow_missed=True)
        if not decision.filled:
            self._record_option_execution_event("option_exit_missed", decision, signal, contract, candle, exit_condition)
            return None
        self.positions.pop(contract.ticker, None)
        fill_price = decision.fill_price
        slippage_per_contract = decision.slippage_per_contract
        gross = position.quantity * fill_price * contract.multiplier
        fee = position.quantity * OPTION_FEE_PER_CONTRACT
        self.cash += gross - fee
        trade = Trade(
            trade_id=str(uuid4()),
            timestamp=candle.timestamp,
            symbol=contract.ticker,
            side=SignalAction.SELL,
            quantity=round(position.quantity, 8),
            price=round(fill_price, 4),
            notional=round(gross, 2),
            fee=round(fee, 4),
            slippage=round(slippage_per_contract * position.quantity * contract.multiplier, 4),
            strategy_id=signal.strategy_id,
            reason=f"Exit option: {exit_condition}",
            exit_condition=exit_condition,
            instrument_type="option",
            underlying_symbol=contract.underlying,
            multiplier=contract.multiplier,
            expiration_date=contract.expiration_date,
            strike=contract.strike,
            option_type=contract.contract_type,
            delta=contract.delta,
            theta=contract.theta,
            implied_volatility=contract.implied_volatility,
            spread_pct=contract.spread_pct,
            historical_spread_pct=contract.historical_spread_pct,
            spread_history_pct=contract.spread_history_pct,
            liquidity_score=contract.liquidity_score,
            slippage_tier=contract.slippage_tier,
            bid=round(decision.bid, 4),
            ask=round(decision.ask, 4),
            mid_price=round(decision.mid_price, 4),
            limit_price=round(decision.limit_price, 4),
            fill_probability=round(decision.fill_probability, 4),
            liquidity_gap=decision.liquidity_gap,
            chain_rank=contract.chain_rank,
            chain_candidates=contract.chain_candidates,
            theta_daily=contract.theta_daily,
            dte_risk=contract.dte_risk,
            earnings_risk=contract.earnings_risk,
            iv_crush_risk=contract.iv_crush_risk,
            expected_iv_crush_pct=contract.expected_iv_crush_pct,
        )
        self.trades.append(trade)
        self._record_option_execution_event("option_limit_exit", decision, signal, contract, candle, exit_condition)
        return trade

    def enforce_option_stops(self, candle: Candle, signal: StrategySignal, contract: OptionContractCandidate) -> None:
        position = self.positions.get(contract.ticker)
        if not position:
            return
        stop_touched = candle.low <= position.stop_loss
        target_touched = candle.high >= position.take_profit
        expiration_risk = contract.dte <= 2
        if stop_touched or target_touched or expiration_risk:
            trigger = position.stop_loss if stop_touched else position.take_profit if target_touched else candle.open
            execution_candle = candle.model_copy(update={"open": max(0.01, trigger), "close": max(0.01, trigger)})
            reason = (
                "Option stop loss touched by intraday low."
                if stop_touched
                else "Option take profit touched by intraday high."
                if target_touched
                else "Option exited before expiration risk window."
            )
            self.close_option(execution_candle, signal, contract, reason)

    def _max_drawdown_pct(self) -> float:
        peak = self.initial_cash
        max_drawdown = 0.0
        for point in self.equity_curve:
            peak = max(peak, point.equity)
            if peak:
                max_drawdown = min(max_drawdown, (point.equity / peak - 1) * 100)
        return abs(max_drawdown)

    def _record_option_execution_event(
        self,
        kind: str,
        decision: OptionFillDecision,
        signal: StrategySignal,
        contract: OptionContractCandidate,
        candle: Candle,
        note: str | None = None,
    ) -> None:
        payload = asdict(decision)
        payload.update(
            {
                "symbol": contract.ticker,
                "underlying": contract.underlying,
                "strategy_id": signal.strategy_id,
                "side": signal.action.value,
                "timestamp": candle.timestamp.isoformat(),
                "note": note,
                "volume": contract.volume,
                "open_interest": contract.open_interest,
                "spread_history_pct": contract.spread_history_pct[-10:],
                "slippage_tier": contract.slippage_tier,
            }
        )
        self.execution_events.append({"kind": kind, "timestamp": candle.timestamp, "payload": payload})


def replay_week(initial_cash: float, history: dict[str, list[Candle]], signal: StrategySignal) -> PaperBroker:
    broker = PaperBroker(initial_cash=initial_cash)
    days = min(len(series) for series in history.values())
    start = max(0, days - 7)
    for idx in range(start, days):
        latest = {symbol: candles[idx] for symbol, candles in history.items() if idx < len(candles)}
        if idx == start + 1 and signal.symbol in latest:
            broker.execute(signal, latest[signal.symbol])
        broker.enforce_stops(latest, signal)
        broker.mark_to_market(latest, timestamp=next(iter(latest.values())).timestamp if latest else datetime.now(UTC) + timedelta(days=idx))
    return broker


def replay_options_week(
    initial_cash: float,
    option_history: list[Candle],
    signal: StrategySignal,
    contract: OptionContractCandidate,
) -> PaperBroker:
    broker = PaperBroker(initial_cash=initial_cash)
    if len(option_history) < 3:
        broker.mark_to_market({}, timestamp=datetime.now(UTC))
        return broker

    days = len(option_history)
    start = max(0, days - 7)
    for idx in range(start, days):
        candle = option_carry_adjusted_candle(option_history[idx], contract, days_held=max(0, idx - start))
        latest = {contract.ticker: candle}
        if idx == start + 1 and signal.action == SignalAction.BUY:
            broker.buy_option(signal, candle, contract)
        broker.enforce_option_stops(candle, signal, contract)
        broker.mark_to_market(latest, timestamp=candle.timestamp)
    return broker


def fee_rate_for_symbol(symbol: str) -> float:
    if "-USD" in symbol:
        return 0.0025
    return 0.0


def realistic_fill_price(candle: Candle, notional: float, side: SignalAction) -> tuple[float, float]:
    intraday_range_pct = max(0.0005, (candle.high - candle.low) / max(candle.close, 0.01))
    dollar_volume = max(candle.volume * candle.close, 1)
    participation = min(0.01, notional / dollar_volume)
    spread_bps = 8 if "-USD" in candle.symbol else 2
    volatility_bps = min(75, intraday_range_pct * 10_000 * 0.08)
    impact_bps = min(25, participation * 10_000)
    total_bps = spread_bps / 2 + volatility_bps + impact_bps
    reference_price = candle.open
    adjustment = reference_price * total_bps / 10_000
    fill_price = reference_price + adjustment if side == SignalAction.BUY else reference_price - adjustment
    slippage = abs(fill_price - reference_price) * (notional / max(reference_price, 0.01))
    return max(0.01, fill_price), slippage


def modeled_option_mid(contract: OptionContractCandidate, reference_price: float | None = None, days_held: int = 0) -> float:
    reference = max(0.01, reference_price if reference_price is not None else contract.mid or contract.premium)
    held = max(0, days_held)
    theta = abs(contract.theta_daily or contract.theta or 0.0)
    theta_decay = min(reference * 0.70, theta * held)
    dte_penalty_pct = {
        "normal": 0.0,
        "accelerating": 0.012,
        "expiration_risk": 0.075,
        "expired": 1.0,
    }.get(contract.dte_risk, 0.02)
    dte_decay = reference * dte_penalty_pct * held
    crush_fraction = 0.0
    if contract.iv_crush_risk == "high":
        crush_fraction = min(1.0, held / 3)
    elif contract.iv_crush_risk == "medium":
        crush_fraction = min(1.0, held / 5)
    elif contract.iv_crush_risk == "low" and contract.expected_iv_crush_pct > 0:
        crush_fraction = min(1.0, held / 7)
    crush_decay = reference * (contract.expected_iv_crush_pct / 100) * crush_fraction
    return max(0.01, reference - theta_decay - dte_decay - crush_decay)


def option_carry_adjusted_candle(candle: Candle, contract: OptionContractCandidate, days_held: int = 0) -> Candle:
    modeled_close = modeled_option_mid(contract, candle.close, days_held)
    scale = modeled_close / max(candle.close, 0.01)
    return candle.model_copy(
        update={
            "open": max(0.01, candle.open * scale),
            "high": max(0.01, candle.high * scale),
            "low": max(0.01, candle.low * scale),
            "close": modeled_close,
        }
    )


def realistic_option_fill_price(candle: Candle, contract: OptionContractCandidate, side: SignalAction) -> tuple[float, float]:
    decision = simulate_option_limit_fill(candle, contract, side=side, allow_missed=False)
    return decision.fill_price, decision.slippage_per_contract


def simulate_option_limit_fill(
    candle: Candle,
    contract: OptionContractCandidate,
    side: SignalAction,
    allow_missed: bool = True,
) -> OptionFillDecision:
    bid, ask, mid, spread_pct = option_execution_quote(candle, contract)
    spread_width = max(0.01, ask - bid)
    aggression = {
        "tight": 0.34,
        "normal": 0.48,
        "wide": 0.64,
        "avoid": 0.78,
        "unknown": 0.58,
    }.get(contract.slippage_tier, 0.58)
    if side == SignalAction.BUY:
        limit_price = min(ask, mid + spread_width * aggression)
        touched = candle.low <= limit_price or candle.source == "massive_options_snapshot"
        fill_price = min(ask, limit_price)
    else:
        limit_price = max(bid, mid - spread_width * aggression)
        touched = candle.high >= limit_price or candle.source == "massive_options_snapshot"
        fill_price = max(bid, limit_price)

    probability = option_fill_probability(contract, spread_pct)
    liquidity_gap = option_liquidity_gap(contract, spread_pct)
    deterministic_threshold = _deterministic_fill_threshold(contract.ticker, candle.timestamp, side)
    severe_gap = liquidity_gap and (
        spread_pct >= 55
        or (contract.historical_spread_pct or 0) >= 45
        or contract.liquidity_score < 0.18
        or (contract.volume <= 0 and contract.open_interest < 50)
    )
    missed_reason = None
    if not touched:
        missed_reason = "Limit price was not touched by the option bar range."
    elif severe_gap:
        missed_reason = "Liquidity gap: spread, volume/open interest, or liquidity score made a realistic fill unsafe."
    elif allow_missed and probability < 0.95 and deterministic_threshold > probability:
        missed_reason = f"Limit order queued but did not receive a fill; modeled fill probability {probability:.0%}."

    filled = missed_reason is None or not allow_missed
    slippage_per_contract = abs(fill_price - mid)
    return OptionFillDecision(
        filled=filled,
        fill_price=max(0.01, fill_price),
        slippage_per_contract=round(slippage_per_contract, 4),
        limit_price=round(limit_price, 4),
        bid=round(bid, 4),
        ask=round(ask, 4),
        mid_price=round(mid, 4),
        spread_pct=round(spread_pct, 2),
        historical_spread_pct=contract.historical_spread_pct,
        fill_probability=round(probability, 4),
        liquidity_gap=liquidity_gap,
        missed_reason=missed_reason,
    )


def option_execution_quote(candle: Candle, contract: OptionContractCandidate) -> tuple[float, float, float, float]:
    raw_mid = (contract.bid + contract.ask) / 2 if contract.ask > contract.bid > 0 else contract.mid or contract.premium
    reference_seed = raw_mid if candle.source == "massive_options_snapshot" else candle.open
    reference = modeled_option_mid(contract, reference_seed, days_held=0)
    spread_pct = contract.spread_pct or contract.historical_spread_pct or 0.0
    if spread_pct <= 0:
        liquidity = min(1.0, (contract.volume / 5000) * 0.7 + (contract.open_interest / 20000) * 0.3)
        spread_pct = max(2.5, (0.18 - liquidity * 0.13) * 100)
    if contract.historical_spread_pct:
        spread_pct = max(spread_pct, contract.historical_spread_pct)
    if contract.spread_history_pct:
        recent_worst = sorted(contract.spread_history_pct[-10:])[-1]
        spread_pct = max(spread_pct, recent_worst * 0.75)
    range_pct = max(0.01, (candle.high - candle.low) / max(candle.close, 0.01))
    tier_impact_pct = {
        "tight": 0.0025,
        "normal": 0.0075,
        "wide": 0.018,
        "avoid": 0.04,
        "unknown": 0.015,
    }.get(contract.slippage_tier, 0.015)
    half_spread = reference * spread_pct / 200
    volatility_buffer = reference * min(0.08, range_pct * 0.08)
    tier_buffer = reference * tier_impact_pct
    adjusted_half_spread = half_spread + volatility_buffer + tier_buffer
    bid = max(0.01, reference - adjusted_half_spread)
    ask = max(bid + 0.01, reference + adjusted_half_spread)
    mid = (bid + ask) / 2
    effective_spread_pct = (ask - bid) / max(mid, 0.01) * 100
    return bid, ask, mid, effective_spread_pct


def option_fill_probability(contract: OptionContractCandidate, spread_pct: float) -> float:
    volume_score = min(1.0, max(0, contract.volume) / 1500)
    oi_score = min(1.0, max(0, contract.open_interest) / 6000)
    spread_score = max(0.0, 1 - max(0.0, spread_pct - 3) / 45)
    tier_cap = {"tight": 0.97, "normal": 0.82, "wide": 0.58, "avoid": 0.22, "unknown": 0.45}.get(contract.slippage_tier, 0.45)
    probability = 0.12 + contract.liquidity_score * 0.40 + volume_score * 0.18 + oi_score * 0.12 + spread_score * 0.18
    return max(0.03, min(tier_cap, probability))


def option_liquidity_gap(contract: OptionContractCandidate, spread_pct: float) -> bool:
    return (
        spread_pct >= 24
        or (contract.historical_spread_pct or 0) >= 22
        or contract.liquidity_score < 0.30
        or contract.slippage_tier == "avoid"
        or contract.volume < 10
        or contract.open_interest < 75
    )


def _deterministic_fill_threshold(symbol: str, timestamp: datetime, side: SignalAction) -> float:
    seed = f"{symbol}|{timestamp.isoformat()}|{side.value}".encode()
    digest = hashlib.sha256(seed).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF
