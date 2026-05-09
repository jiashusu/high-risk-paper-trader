from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from .models import Candle, EquityPoint, OptionContractCandidate, PortfolioSnapshot, Position, SignalAction, StrategySignal, Trade


OPTION_FEE_PER_CONTRACT = 0.65


class PaperBroker:
    def __init__(self, initial_cash: float = 500.0) -> None:
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.positions: dict[str, Position] = {}
        self.trades: list[Trade] = []
        self.equity_curve: list[EquityPoint] = []

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
        fill_price, slippage_per_contract = realistic_option_fill_price(candle, contract, side=SignalAction.BUY)
        per_contract_cost = fill_price * contract.multiplier + OPTION_FEE_PER_CONTRACT
        contracts = int(max_notional // per_contract_cost)
        if signal.contract_quantity is not None:
            contracts = min(contracts, signal.contract_quantity)
        if contracts < 1:
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
            liquidity_score=contract.liquidity_score,
            slippage_tier=contract.slippage_tier,
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
            liquidity_score=contract.liquidity_score,
            slippage_tier=contract.slippage_tier,
            chain_rank=contract.chain_rank,
            chain_candidates=contract.chain_candidates,
            theta_daily=contract.theta_daily,
            dte_risk=contract.dte_risk,
            earnings_risk=contract.earnings_risk,
            iv_crush_risk=contract.iv_crush_risk,
            expected_iv_crush_pct=contract.expected_iv_crush_pct,
        )
        self.trades.append(trade)
        return trade

    def close_option(self, candle: Candle, signal: StrategySignal, contract: OptionContractCandidate, exit_condition: str) -> Trade | None:
        position = self.positions.pop(contract.ticker, None)
        if not position:
            return None
        fill_price, slippage_per_contract = realistic_option_fill_price(candle, contract, side=SignalAction.SELL)
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
            liquidity_score=contract.liquidity_score,
            slippage_tier=contract.slippage_tier,
            chain_rank=contract.chain_rank,
            chain_candidates=contract.chain_candidates,
            theta_daily=contract.theta_daily,
            dte_risk=contract.dte_risk,
            earnings_risk=contract.earnings_risk,
            iv_crush_risk=contract.iv_crush_risk,
            expected_iv_crush_pct=contract.expected_iv_crush_pct,
        )
        self.trades.append(trade)
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
    reference_seed = contract.mid if candle.source == "massive_options_snapshot" else candle.open
    reference = modeled_option_mid(contract, reference_seed, days_held=0)
    spread_pct = contract.spread_pct or contract.historical_spread_pct or 0.0
    if spread_pct <= 0:
        liquidity = min(1.0, (contract.volume / 5000) * 0.7 + (contract.open_interest / 20000) * 0.3)
        spread_pct = max(2.5, (0.18 - liquidity * 0.13) * 100)
    if contract.historical_spread_pct:
        spread_pct = max(spread_pct, contract.historical_spread_pct)
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
    adjustment = half_spread + volatility_buffer + tier_buffer
    fill_price = reference + adjustment if side == SignalAction.BUY else reference - adjustment
    slippage_per_contract = abs(fill_price - reference)
    return max(0.01, fill_price), slippage_per_contract
