from __future__ import annotations

import asyncio
import json
import math
import os
import random
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx

from .config import Settings
from .models import Candle, DataSourceStatus


class MarketDataProvider:
    def __init__(self) -> None:
        self.statuses: list[DataSourceStatus] = []

    async def get_history(self, symbols: list[str], days: int = 45) -> dict[str, list[Candle]]:
        raise NotImplementedError


class SyntheticMarketDataProvider(MarketDataProvider):
    """Deterministic synthetic market data for zero-key local development."""

    def __init__(self, seed: int = 42) -> None:
        super().__init__()
        self.seed = seed

    async def get_history(self, symbols: list[str], days: int = 45) -> dict[str, list[Candle]]:
        end = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
        start = end - timedelta(days=days)
        history = {symbol: self._series(symbol, start, days) for symbol in symbols}
        self.statuses = [
            DataSourceStatus(
                name="synthetic",
                enabled=True,
                healthy=True,
                detail="Deterministic fallback data; not suitable as a real trading data source.",
                symbols_requested=len(symbols),
                symbols_real=0,
                symbols_fallback=len(symbols),
                latest_timestamp=end,
            )
        ]
        return history

    def _series(self, symbol: str, start: datetime, days: int) -> list[Candle]:
        rng = random.Random(f"{self.seed}:{symbol}")
        base_price = {
            "BTC-USD": 64000,
            "ETH-USD": 3200,
            "SOL-USD": 150,
            "NVDA": 920,
            "TSLA": 210,
            "QQQ": 450,
            "TQQQ": 62,
            "SPY": 520,
        }.get(symbol, 100)
        volatility = 0.035 if "-USD" in symbol else 0.022
        if symbol == "TQQQ":
            volatility = 0.045

        candles: list[Candle] = []
        price = float(base_price)
        for day in range(days):
            timestamp = start + timedelta(days=day)
            cycle = math.sin(day / 4.2) * volatility * 0.9
            event_shock = 0.0
            if day in {days - 11, days - 4} and symbol in {"SOL-USD", "NVDA", "TQQQ"}:
                event_shock = volatility * 3.2
            if day == days - 8 and symbol in {"BTC-USD", "ETH-USD", "TSLA"}:
                event_shock = -volatility * 2.6
            drift = 0.0025 if symbol in {"BTC-USD", "SOL-USD", "NVDA", "TQQQ"} else 0.0007
            daily_return = drift + cycle + event_shock + rng.gauss(0, volatility)
            open_price = price
            close = max(0.1, open_price * (1 + daily_return))
            high = max(open_price, close) * (1 + abs(rng.gauss(volatility, volatility / 2)))
            low = min(open_price, close) * (1 - abs(rng.gauss(volatility, volatility / 2)))
            volume = rng.uniform(2_000_000, 20_000_000) * (1 + abs(daily_return) * 8)
            candles.append(
                Candle(
                    symbol=symbol,
                    timestamp=timestamp,
                    open=round(open_price, 4),
                    high=round(high, 4),
                    low=round(max(0.1, low), 4),
                    close=round(close, 4),
                    volume=round(volume, 2),
                    source="synthetic",
                    synthetic=True,
                )
            )
            price = close
        return candles


class MassiveMarketDataProvider(MarketDataProvider):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        self.cache_dir = Path(os.getenv("PAPER_TRADER_MARKET_CACHE_DIR") or ("/tmp/high-risk-paper-trader/cache/market" if os.getenv("VERCEL") else "data/cache/market"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    async def get_history(self, symbols: list[str], days: int = 45) -> dict[str, list[Candle]]:
        if not self.settings.massive_api_key:
            return await SyntheticMarketDataProvider().get_history(symbols, days)

        fallback_provider = SyntheticMarketDataProvider()
        fallback = await fallback_provider.get_history(symbols, days)
        end = datetime.now(UTC).date()
        start = end - timedelta(days=days)
        output: dict[str, list[Candle]] = {}
        real_symbols = 0
        fallback_symbols: list[str] = []
        latest_timestamp: datetime | None = None
        async with httpx.AsyncClient(timeout=20) as client:
            for symbol in symbols:
                ticker = f"X:{symbol.replace('-', '')}" if "-USD" in symbol else symbol
                try:
                    rows = await self._fetch_aggregate_rows(client, ticker, start, end, days)
                    if rows:
                        self._write_cache(ticker, rows)
                    else:
                        rows = self._read_cache(ticker, days)
                    output[symbol] = [
                        Candle(
                            symbol=symbol,
                            timestamp=datetime.fromtimestamp(row["t"] / 1000, UTC),
                            open=row["o"],
                            high=row["h"],
                            low=row["l"],
                            close=row["c"],
                            volume=row.get("v", 0),
                            source=row.get("source", "massive"),
                            synthetic=False,
                        )
                        for row in rows
                    ]
                    if output[symbol]:
                        real_symbols += 1
                        latest_timestamp = max(latest_timestamp or output[symbol][-1].timestamp, output[symbol][-1].timestamp)
                    else:
                        output[symbol] = fallback[symbol]
                        fallback_symbols.append(symbol)
                except (httpx.HTTPError, KeyError, TypeError, ValueError):
                    cached_rows = self._read_cache(ticker, days)
                    if cached_rows:
                        output[symbol] = [
                            Candle(
                                symbol=symbol,
                                timestamp=datetime.fromtimestamp(row["t"] / 1000, UTC),
                                open=row["o"],
                                high=row["h"],
                                low=row["l"],
                                close=row["c"],
                                volume=row.get("v", 0),
                                source="massive_cache",
                                synthetic=False,
                            )
                            for row in cached_rows
                        ]
                        real_symbols += 1
                        latest_timestamp = max(latest_timestamp or output[symbol][-1].timestamp, output[symbol][-1].timestamp)
                    else:
                        output[symbol] = fallback[symbol]
                        fallback_symbols.append(symbol)
                await asyncio.sleep(0.15)
        self.statuses = [
            DataSourceStatus(
                name="massive",
                enabled=True,
                healthy=real_symbols > 0,
                detail=(
                    f"Real daily aggregate bars loaded for {real_symbols}/{len(symbols)} symbols. Cached real bars are used during provider rate limits."
                    if real_symbols
                    else "Massive/Polygon returned no usable bars; using synthetic fallback."
                ),
                symbols_requested=len(symbols),
                symbols_real=real_symbols,
                symbols_fallback=len(fallback_symbols),
                latest_timestamp=latest_timestamp,
            )
        ]
        return output

    async def _fetch_aggregate_rows(
        self,
        client: httpx.AsyncClient,
        ticker: str,
        preferred_start: date,
        preferred_end: date,
        days: int,
    ) -> list[dict]:
        for offset_days in (0, 365, 730):
            end = preferred_end - timedelta(days=offset_days)
            start = preferred_start - timedelta(days=offset_days)
            url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}"
            response = await client.get(
                url,
                params={"adjusted": "true", "sort": "asc", "limit": max(days, 5000), "apiKey": self.settings.massive_api_key},
            )
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", "1"))
                await asyncio.sleep(min(3, max(1, retry_after)))
                response = await client.get(
                    url,
                    params={"adjusted": "true", "sort": "asc", "limit": max(days, 5000), "apiKey": self.settings.massive_api_key},
                )
            response.raise_for_status()
            rows = response.json().get("results", [])
            if rows:
                return rows
        return []

    def _cache_path(self, ticker: str) -> Path:
        safe = ticker.replace(":", "_").replace("/", "_")
        return self.cache_dir / f"{safe}.json"

    def _write_cache(self, ticker: str, rows: list[dict]) -> None:
        payload = [{**row, "source": "massive_cache"} for row in rows]
        self._cache_path(ticker).write_text(json.dumps(payload), encoding="utf-8")

    def _read_cache(self, ticker: str, days: int) -> list[dict]:
        path = self._cache_path(ticker)
        if not path.exists():
            return []
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(rows, list):
            return []
        return rows[-days:]


def get_market_data_provider(settings: Settings) -> MarketDataProvider:
    if settings.massive_api_key:
        return MassiveMarketDataProvider(settings)
    return SyntheticMarketDataProvider()
