import pytest

from trading_system.config import Settings
from trading_system.service import TradingResearchService


@pytest.mark.asyncio
async def test_dashboard_includes_realism_report(tmp_path) -> None:
    service = TradingResearchService(
        Settings(
            massive_api_key=None,
            alpaca_paper_api_key=None,
            alpaca_paper_secret_key=None,
            database_path=str(tmp_path / "paper.duckdb"),
        )
    )
    dashboard, _ = await service.run_cycle()

    assert dashboard.realism.data_points > 0
    assert dashboard.realism.real_market_data_pct == 0
    assert dashboard.realism.synthetic_symbols
    assert dashboard.realism.source_statuses
    assert "Forward ledger" in dashboard.realism.execution_model
    assert dashboard.ledger_events
