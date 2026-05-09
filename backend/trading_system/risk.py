from .models import Position, SignalAction, StrategySignal


class RiskManager:
    def __init__(
        self,
        weekly_loss_limit_pct: float = 35.0,
        single_position_cap_pct: float = 82.0,
        min_liquidity_score: float = 0.7,
    ) -> None:
        self.weekly_loss_limit_pct = weekly_loss_limit_pct
        self.single_position_cap_pct = single_position_cap_pct
        self.min_liquidity_score = min_liquidity_score

    def apply(
        self,
        signal: StrategySignal,
        equity: float,
        weekly_return_pct: float,
        existing_positions: list[Position],
        liquidity_score: float,
    ) -> tuple[StrategySignal, list[str]]:
        warnings: list[str] = []
        adjusted = signal.model_copy(deep=True)

        if weekly_return_pct <= -self.weekly_loss_limit_pct:
            adjusted.action = SignalAction.FLAT
            adjusted.target_notional = 0
            adjusted.reason = f"Weekly loss limit breached; original signal blocked. {signal.reason}"
            warnings.append("Weekly loss fuse triggered: portfolio should move to cash.")

        if liquidity_score < self.min_liquidity_score and adjusted.action == SignalAction.BUY:
            adjusted.action = SignalAction.HOLD
            adjusted.target_notional = 0
            warnings.append(f"{signal.symbol} liquidity score is below the allowed threshold.")

        max_notional = equity * (self.single_position_cap_pct / 100)
        if adjusted.target_notional > max_notional:
            adjusted.target_notional = round(max_notional, 2)
            warnings.append("Single-position cap reduced target notional.")

        if existing_positions and adjusted.action == SignalAction.BUY:
            same_symbol = next((position for position in existing_positions if position.symbol == adjusted.symbol), None)
            if same_symbol and same_symbol.unrealized_pnl < 0:
                adjusted.action = SignalAction.HOLD
                adjusted.target_notional = 0
                warnings.append("Blocked martingale-style add: existing position is losing.")

        return adjusted, warnings

