from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import duckdb

from .models import EquityPoint, PortfolioSnapshot, Position, Trade
from .simulator import PaperBroker


class ForwardLedger:
    def __init__(self, database_path: str, initial_cash: float) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.initial_cash = initial_cash
        self._ensure_schema()

    def load_broker(self) -> PaperBroker:
        self._ensure_started()
        with self._connect() as con:
            cash = con.execute("SELECT cash FROM ledger_state WHERE id = 1").fetchone()[0]
            position_rows = con.execute("SELECT payload FROM ledger_positions ORDER BY symbol").fetchall()
            trade_rows = con.execute("SELECT payload FROM ledger_trades ORDER BY timestamp, trade_id").fetchall()
            equity_rows = con.execute("SELECT payload FROM ledger_equity ORDER BY timestamp").fetchall()

        broker = PaperBroker(initial_cash=self.initial_cash)
        broker.cash = float(cash)
        broker.positions = {
            position.symbol: position
            for position in (Position.model_validate(json.loads(row[0])) for row in position_rows)
        }
        broker.trades = [Trade.model_validate(json.loads(row[0])) for row in trade_rows]
        broker.equity_curve = [EquityPoint.model_validate(json.loads(row[0])) for row in equity_rows]
        return broker

    def save_broker(self, broker: PaperBroker, timestamp: datetime) -> None:
        self._ensure_started()
        with self._connect() as con:
            con.execute("UPDATE ledger_state SET cash = ?, updated_at = ?, last_tick_at = ? WHERE id = 1", [broker.cash, timestamp, timestamp])
            con.execute("DELETE FROM ledger_positions")
            for position in broker.positions.values():
                con.execute(
                    "INSERT INTO ledger_positions VALUES (?, ?, ?)",
                    [position.symbol, _model_json(position), timestamp],
                )
            for trade in broker.trades:
                con.execute("DELETE FROM ledger_trades WHERE trade_id = ?", [trade.trade_id])
                con.execute(
                    "INSERT INTO ledger_trades VALUES (?, ?, ?, ?, ?)",
                    [trade.trade_id, trade.timestamp, trade.symbol, trade.side.value, _model_json(trade)],
                )
            if broker.equity_curve:
                point = broker.equity_curve[-1]
                con.execute(
                    "INSERT INTO ledger_equity VALUES (?, ?, ?)",
                    [point.timestamp, point.equity, _model_json(point)],
                )

    def reset(self) -> None:
        now = datetime.now(UTC)
        with self._connect() as con:
            con.execute("DELETE FROM ledger_positions")
            con.execute("DELETE FROM ledger_trades")
            con.execute("DELETE FROM ledger_equity")
            con.execute("DELETE FROM ledger_events")
            con.execute("DELETE FROM ledger_state WHERE id = 1")
            con.execute(
                "INSERT INTO ledger_state VALUES (1, ?, ?, ?, ?, NULL)",
                [self.initial_cash, self.initial_cash, now, now],
            )
            con.execute(
                "INSERT INTO ledger_events VALUES (?, ?, ?, ?)",
                [str(uuid4()), now, "ledger_reset", json.dumps({"initial_cash": self.initial_cash})],
            )

    def record_event(self, kind: str, payload: dict, timestamp: datetime | None = None) -> None:
        self._ensure_started()
        now = timestamp or datetime.now(UTC)
        with self._connect() as con:
            con.execute(
                "INSERT INTO ledger_events VALUES (?, ?, ?, ?)",
                [str(uuid4()), now, kind, json.dumps(payload, default=str)],
            )

    def latest_events(self, limit: int = 20) -> list[dict]:
        self._ensure_started()
        with self._connect() as con:
            rows = con.execute(
                "SELECT timestamp, kind, payload FROM ledger_events ORDER BY timestamp DESC LIMIT ?",
                [limit],
            ).fetchall()
        return [{"timestamp": str(row[0]), "kind": row[1], "payload": json.loads(row[2])} for row in rows]

    def summary(self) -> dict:
        self._ensure_started()
        with self._connect() as con:
            state = con.execute("SELECT initial_cash, cash, started_at, updated_at, last_tick_at FROM ledger_state WHERE id = 1").fetchone()
            trade_count = con.execute("SELECT COUNT(*) FROM ledger_trades").fetchone()[0]
            equity_rows = con.execute("SELECT timestamp, equity FROM ledger_equity ORDER BY timestamp").fetchall()
        started_at = _as_utc(state[2])
        now = datetime.now(UTC)
        forward_days = max(0.0, (now - started_at).total_seconds() / 86400)
        latest_equity = float(equity_rows[-1][1]) if equity_rows else float(state[1])
        day_equities = [float(row[1]) for row in equity_rows if _as_utc(row[0]).date() == now.date()]
        max_drawdown = _max_drawdown([float(row[1]) for row in equity_rows], float(state[0]))
        daily_loss_pct = _period_loss_pct(day_equities)
        weekly_loss_pct = _period_loss_pct([float(row[1]) for row in equity_rows if (now - _as_utc(row[0])).days <= 7])
        return {
            "initial_cash": float(state[0]),
            "cash": float(state[1]),
            "started_at": started_at,
            "updated_at": _as_utc(state[3]),
            "last_tick_at": _as_utc(state[4]) if state[4] else None,
            "forward_days": forward_days,
            "completed_forward_weeks": forward_days / 7,
            "trade_count": int(trade_count),
            "latest_equity": latest_equity,
            "forward_pnl": latest_equity - float(state[0]),
            "max_drawdown_pct": max_drawdown,
            "daily_loss_pct": daily_loss_pct,
            "weekly_loss_pct": weekly_loss_pct,
        }

    def traded_today(self, timestamp: datetime) -> bool:
        broker = self.load_broker()
        local_day = timestamp.date()
        return any(trade.timestamp.date() == local_day for trade in broker.trades)

    def portfolio_snapshot(self, broker: PaperBroker, timestamp: datetime) -> PortfolioSnapshot:
        latest = {symbol: position_to_candle_stub(position, timestamp) for symbol, position in broker.positions.items()}
        return broker.mark_to_market(latest, timestamp=timestamp)

    def _connect(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self.database_path))

    def _ensure_schema(self) -> None:
        with self._connect() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS ledger_state (
                    id INTEGER PRIMARY KEY,
                    initial_cash DOUBLE,
                    cash DOUBLE,
                    started_at TIMESTAMP,
                    updated_at TIMESTAMP,
                    last_tick_at TIMESTAMP
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS ledger_positions (
                    symbol VARCHAR PRIMARY KEY,
                    payload VARCHAR,
                    updated_at TIMESTAMP
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS ledger_trades (
                    trade_id VARCHAR PRIMARY KEY,
                    timestamp TIMESTAMP,
                    symbol VARCHAR,
                    side VARCHAR,
                    payload VARCHAR
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS ledger_equity (
                    timestamp TIMESTAMP,
                    equity DOUBLE,
                    payload VARCHAR
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS ledger_events (
                    event_id VARCHAR PRIMARY KEY,
                    timestamp TIMESTAMP,
                    kind VARCHAR,
                    payload VARCHAR
                )
                """
            )

    def _ensure_started(self) -> None:
        now = datetime.now(UTC)
        with self._connect() as con:
            exists = con.execute("SELECT COUNT(*) FROM ledger_state WHERE id = 1").fetchone()[0]
            if not exists:
                con.execute(
                    "INSERT INTO ledger_state VALUES (1, ?, ?, ?, ?, NULL)",
                    [self.initial_cash, self.initial_cash, now, now],
                )


def _model_json(model: object) -> str:
    return model.model_dump_json()  # type: ignore[attr-defined]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo:
        return value.astimezone(UTC)
    return value.replace(tzinfo=UTC)


def _max_drawdown(values: list[float], initial: float) -> float:
    peak = initial
    drawdown = 0.0
    for value in values:
        peak = max(peak, value)
        if peak:
            drawdown = min(drawdown, value / peak - 1)
    return abs(drawdown * 100)


def _period_loss_pct(values: list[float]) -> float:
    if len(values) < 2 or values[0] <= 0:
        return 0.0
    change = (values[-1] / values[0] - 1) * 100
    return abs(min(0.0, change))


def position_to_candle_stub(position: Position, timestamp: datetime):
    from .models import Candle

    return Candle(
        symbol=position.symbol,
        timestamp=timestamp,
        open=position.market_price,
        high=position.market_price,
        low=position.market_price,
        close=position.market_price,
        volume=0,
        source="ledger",
        synthetic=False,
    )
