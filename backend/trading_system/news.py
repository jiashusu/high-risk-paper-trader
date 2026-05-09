from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx

from .config import Settings
from .models import DataSourceStatus


class NewsProvider:
    def __init__(self) -> None:
        self.statuses: list[DataSourceStatus] = []

    async def sentiment_heat(self, symbols: list[str]) -> dict[str, float]:
        raise NotImplementedError


class SyntheticNewsProvider(NewsProvider):
    def __init__(self) -> None:
        super().__init__()

    async def sentiment_heat(self, symbols: list[str]) -> dict[str, float]:
        heat: dict[str, float] = {}
        for symbol in symbols:
            if symbol in {"BTC-USD", "SOL-USD", "NVDA"}:
                heat[symbol] = 0.82
            elif symbol in {"TQQQ", "ETH-USD"}:
                heat[symbol] = 0.72
            else:
                heat[symbol] = 0.52
        self.statuses = [
            DataSourceStatus(
                name="synthetic_news",
                enabled=True,
                healthy=True,
                detail="Synthetic heat scores are active; not suitable for real catalyst trading.",
                symbols_requested=len(symbols),
                symbols_real=0,
                symbols_fallback=len(symbols),
            )
        ]
        return heat


class FinnhubNewsProvider(NewsProvider):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings

    async def sentiment_heat(self, symbols: list[str]) -> dict[str, float]:
        if not self.settings.finnhub_api_key:
            return await SyntheticNewsProvider().sentiment_heat(symbols)

        scores: dict[str, float] = {}
        real = 0
        async with httpx.AsyncClient(timeout=12) as client:
            for symbol in symbols:
                if "-USD" in symbol:
                    scores[symbol] = 0.6
                    continue
                response = await client.get(
                    "https://finnhub.io/api/v1/news-sentiment",
                    params={"symbol": symbol, "token": self.settings.finnhub_api_key},
                )
                if response.status_code >= 400:
                    scores[symbol] = 0.5
                    continue
                data = response.json()
                buzz = data.get("buzz", {}).get("buzz", 0.5)
                sentiment = data.get("companyNewsScore", 0.5)
                scores[symbol] = max(0, min(1, (buzz + sentiment) / 2))
                real += 1
        self.statuses = [
            DataSourceStatus(
                name="finnhub_sentiment",
                enabled=True,
                healthy=real > 0,
                detail=f"Finnhub sentiment loaded for {real}/{len([s for s in symbols if '-USD' not in s])} equity symbols.",
                symbols_requested=len(symbols),
                symbols_real=real,
                symbols_fallback=len(symbols) - real,
            )
        ]
        return scores


class CatalystProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def statuses(self, symbols: list[str]) -> list[DataSourceStatus]:
        statuses = []
        statuses.append(await self._benzinga_status(symbols))
        statuses.append(await self._fmp_status(symbols))
        return statuses

    async def _benzinga_status(self, symbols: list[str]) -> DataSourceStatus:
        if not self.settings.benzinga_api_key:
            return DataSourceStatus(name="benzinga_news", enabled=False, healthy=False, detail="Benzinga API key is not configured.")

        equity_symbols = [symbol for symbol in symbols if "-USD" not in symbol]
        async with httpx.AsyncClient(timeout=12, headers={"accept": "application/json"}) as client:
            try:
                response = await client.get(
                    "https://api.benzinga.com/api/v2/news",
                    params={"token": self.settings.benzinga_api_key, "tickers": ",".join(equity_symbols), "pagesize": 20},
                )
                response.raise_for_status()
                items = response.json()
                count = len(items) if isinstance(items, list) else 0
                return DataSourceStatus(
                    name="benzinga_news",
                    enabled=True,
                    healthy=True,
                    detail=f"Benzinga key accepted; {count} recent catalyst items returned for the watchlist.",
                    symbols_requested=len(equity_symbols),
                    symbols_real=count,
                    symbols_fallback=0,
                )
            except (httpx.HTTPError, ValueError, TypeError) as exc:
                return DataSourceStatus(
                    name="benzinga_news",
                    enabled=True,
                    healthy=False,
                    detail=f"Benzinga check failed: {exc.__class__.__name__}.",
                    symbols_requested=len(equity_symbols),
                )

    async def _fmp_status(self, symbols: list[str]) -> DataSourceStatus:
        if not self.settings.fmp_api_key:
            return DataSourceStatus(name="fmp_earnings", enabled=False, healthy=False, detail="FMP API key is not configured.")

        today = datetime.now(UTC).date()
        end = today + timedelta(days=45)
        watchlist = {symbol for symbol in symbols if "-USD" not in symbol}
        async with httpx.AsyncClient(timeout=12) as client:
            try:
                response = await client.get(
                    "https://financialmodelingprep.com/stable/earnings-calendar",
                    params={"from": str(today), "to": str(end), "apikey": self.settings.fmp_api_key},
                )
                response.raise_for_status()
                items = response.json()
                matching = [item for item in items if item.get("symbol") in watchlist] if isinstance(items, list) else []
                return DataSourceStatus(
                    name="fmp_earnings",
                    enabled=True,
                    healthy=True,
                    detail=f"FMP earnings calendar reachable; {len(matching)} watchlist earnings events in the next 45 days.",
                    symbols_requested=len(watchlist),
                    symbols_real=len(matching),
                    symbols_fallback=0,
                )
            except (httpx.HTTPError, ValueError, TypeError) as exc:
                return DataSourceStatus(
                    name="fmp_earnings",
                    enabled=True,
                    healthy=False,
                    detail=f"FMP earnings check failed: {exc.__class__.__name__}.",
                    symbols_requested=len(watchlist),
                )


def get_news_provider(settings: Settings) -> NewsProvider:
    if settings.finnhub_api_key:
        return FinnhubNewsProvider(settings)
    return SyntheticNewsProvider()


def source_stamp() -> str:
    return f"generated:{datetime.now(UTC).isoformat()}"
