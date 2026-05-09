import pytest

from trading_system.market_data import SyntheticMarketDataProvider
from trading_system.strategies import StrategyContext, rank_strategies, select_strategy


@pytest.mark.asyncio
async def test_strategy_ranking_selects_active_candidate() -> None:
    provider = SyntheticMarketDataProvider()
    history = await provider.get_history(["BTC-USD", "ETH-USD", "SOL-USD", "NVDA"], days=30)
    heat = {symbol: 0.75 for symbol in history}
    context = StrategyContext(history=history, heat=heat, cash=500, equity=500)
    scores = rank_strategies(context)
    selected = select_strategy(context)
    assert scores[0].status == "active"
    assert selected.strategy_id in {score.strategy_id for score in scores}

