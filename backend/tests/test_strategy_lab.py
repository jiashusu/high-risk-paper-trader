from datetime import UTC, datetime, timedelta

from trading_system.models import Candle
from trading_system.simulator import PaperBroker
from trading_system.strategy_lab import build_strategy_lab
from trading_system.strategies import StrategyContext, rank_strategies, select_strategy


def test_strategy_lab_includes_walk_forward_and_version_comparison() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    history = {
        "NVDA": [
            Candle(
                symbol="NVDA",
                timestamp=start + timedelta(days=idx),
                open=100 + idx * 0.3,
                high=102 + idx * 0.3,
                low=99 + idx * 0.3,
                close=101 + idx * 0.35,
                volume=5_000_000,
                source="test",
            )
            for idx in range(140)
        ],
        "QQQ": [
            Candle(
                symbol="QQQ",
                timestamp=start + timedelta(days=idx),
                open=400 + idx * 0.2,
                high=403 + idx * 0.2,
                low=398 + idx * 0.2,
                close=401 + idx * 0.22,
                volume=20_000_000,
                source="test",
            )
            for idx in range(140)
        ],
    }
    context = StrategyContext(history=history, heat={"NVDA": 0.8, "QQQ": 0.6}, cash=500, equity=500)
    active_signal = select_strategy(context).generate(context)
    ranking = rank_strategies(context)

    lab = build_strategy_lab(context, ranking, PaperBroker(), active_signal, [], {"completed_forward_weeks": 0})
    first = lab.entries[0]

    assert first.walk_forward.windows >= 3
    assert first.walk_forward.recent_windows
    assert first.walk_forward.recent_windows[0].ending_equity > 0
    assert first.walk_forward.recent_windows[0].trades >= 0
    assert first.version_comparison.current_version
    assert first.version_comparison.previous_version
    assert first.version_comparison.current_score != first.version_comparison.previous_score or first.walk_forward.windows > 0
    assert first.regime_tags
