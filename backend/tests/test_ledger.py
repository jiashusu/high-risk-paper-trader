from datetime import UTC, datetime

from trading_system.ledger import ForwardLedger
from trading_system.models import SignalAction, Trade


def test_forward_ledger_persists_cash_and_deduplicates_trades(tmp_path) -> None:
    ledger = ForwardLedger(str(tmp_path / "ledger.duckdb"), initial_cash=500)
    broker = ledger.load_broker()
    broker.cash = 420
    trade = Trade(
        trade_id="trade-1",
        timestamp=datetime(2026, 5, 9, tzinfo=UTC),
        symbol="O:TQQQ260522C00080000",
        side=SignalAction.BUY,
        quantity=1,
        price=2.5,
        notional=250,
        fee=0.65,
        slippage=3.2,
        strategy_id="test",
        reason="test",
        instrument_type="option",
        underlying_symbol="TQQQ",
        multiplier=100,
    )
    broker.trades.append(trade)
    broker.mark_to_market({}, timestamp=trade.timestamp)

    ledger.save_broker(broker, trade.timestamp)
    ledger.save_broker(broker, trade.timestamp)
    reloaded = ledger.load_broker()

    assert reloaded.cash == 420
    assert len(reloaded.trades) == 1
    assert reloaded.trades[0].instrument_type == "option"
