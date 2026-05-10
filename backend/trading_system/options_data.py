from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from statistics import median

import httpx

from .config import Settings
from .models import Candle, DataSourceStatus, OptionContractCandidate


@dataclass(frozen=True)
class OptionsScanResult:
    underlyings: list[str]
    checked_contracts: int
    candidates: list[OptionContractCandidate]
    chain_summaries: dict[str, str] | None = None


class OptionsDataProbe:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def statuses(self, underlying: str = "NVDA") -> list[DataSourceStatus]:
        if not self.settings.massive_api_key:
            return [DataSourceStatus(name="options_data", enabled=False, healthy=False, detail="Massive API key is not configured.")]

        async with httpx.AsyncClient(timeout=15) as client:
            contracts_status, sample_contract = await self._contracts_status(client, underlying)
            snapshot_status = await self._snapshot_status(client, underlying)
            aggregates_status = await self._aggregates_status(client, sample_contract)
        return [contracts_status, snapshot_status, aggregates_status]

    async def opportunity_status(self, underlyings: list[str], max_premium: float | None = None) -> DataSourceStatus:
        scan = await self.scan_opportunities(underlyings, max_premium=max_premium)
        return self.status_from_scan(scan)

    async def scan_opportunities(self, underlyings: list[str], max_premium: float | None = None) -> OptionsScanResult:
        if not self.settings.massive_api_key:
            return OptionsScanResult(underlyings=underlyings, checked_contracts=0, candidates=[], chain_summaries={})

        candidates: list[OptionContractCandidate] = []
        summaries: dict[str, str] = {}
        checked = 0
        async with httpx.AsyncClient(timeout=20) as client:
            earnings = await self._earnings_dates(client, underlyings)
            for underlying in underlyings:
                rows = await self._snapshot_rows(client, underlying, limit=250)
                checked += len(rows)
                liquid = self._liquid_candidates(underlying, rows, max_premium=max_premium, earnings_date=earnings.get(underlying))
                liquid.sort(key=lambda item: item.score, reverse=True)
                summaries[underlying] = self._chain_summary(underlying, rows, liquid)
                candidates.extend(
                    candidate.model_copy(update={"chain_rank": idx + 1, "chain_candidates": len(liquid)})
                    for idx, candidate in enumerate(liquid)
                )

        candidates.sort(key=lambda item: item.score, reverse=True)
        top_with_history = []
        for candidate in candidates[:12]:
            spread_history = await self.historical_spread_history_pct(candidate)
            history_spread = round(median(spread_history), 2) if spread_history else None
            top_with_history.append(
                candidate.model_copy(
                    update={
                        "historical_spread_pct": history_spread,
                        "spread_history_pct": spread_history,
                    }
                )
            )
        candidates = [*top_with_history, *candidates[12:]]
        return OptionsScanResult(underlyings=underlyings, checked_contracts=checked, candidates=candidates, chain_summaries=summaries)

    def status_from_scan(self, scan: OptionsScanResult) -> DataSourceStatus:
        if not self.settings.massive_api_key:
            return DataSourceStatus(name="options_opportunity_scan", enabled=False, healthy=False, detail="Massive API key is not configured.")

        if not scan.candidates:
            return DataSourceStatus(
                name="options_opportunity_scan",
                enabled=True,
                healthy=False,
                detail=(
                    f"Scanned {scan.checked_contracts} option contracts but found no liquid 7-45 DTE candidates "
                    "with usable delta, volume, open interest, and premium filters."
                ),
                symbols_requested=len(scan.underlyings),
                symbols_fallback=len(scan.underlyings),
            )

        top = scan.candidates[:3]
        contracts = ", ".join(
            f"{item.ticker} rank={item.chain_rank}/{item.chain_candidates} spread={item.spread_pct:.1f}% tier={item.slippage_tier} theta={item.theta_daily:.2f} ivCrush={item.iv_crush_risk}"
            for item in top
        )
        chain_summary = " | ".join((scan.chain_summaries or {}).values())
        return DataSourceStatus(
            name="options_opportunity_scan",
            enabled=True,
            healthy=True,
            detail=f"Found {len(scan.candidates)} liquid option candidates across {len(scan.underlyings)} underlyings. Chain comparison: {chain_summary}. Top: {contracts}.",
            symbols_requested=len(scan.underlyings),
            symbols_real=len(scan.candidates),
            symbols_fallback=0,
        )

    async def historical_spread_pct(self, contract: OptionContractCandidate, days: int = 20) -> float | None:
        spreads = await self.historical_spread_history_pct(contract, days=days)
        return round(median(spreads), 2) if spreads else None

    async def historical_spread_history_pct(self, contract: OptionContractCandidate, days: int = 20) -> list[float]:
        candles = await self.historical_candles(contract, days=days)
        spreads = []
        for candle in candles[-days:]:
            _, bid, ask = option_quote_estimate(candle.close, int(candle.volume), contract.open_interest)
            spreads.append(round((ask - bid) / max(candle.close, 0.01) * 100, 2))
        return spreads

    async def historical_candles(self, contract: OptionContractCandidate, days: int = 45) -> list[Candle]:
        if not self.settings.massive_api_key:
            return []

        end = datetime.now(UTC).date()
        start = end - timedelta(days=days)
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                f"https://api.polygon.io/v2/aggs/ticker/{contract.ticker}/range/1/day/{start}/{end}",
                params={"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": self.settings.massive_api_key},
            )
            response.raise_for_status()
            rows = response.json().get("results", [])
        if not isinstance(rows, list):
            return []
        return [
            Candle(
                symbol=contract.ticker,
                timestamp=datetime.fromtimestamp(row["t"] / 1000, UTC),
                open=row["o"],
                high=row["h"],
                low=row["l"],
                close=row["c"],
                volume=row.get("v", 0),
                source="massive_options",
                synthetic=False,
            )
            for row in rows
        ]

    async def contract_snapshot(self, underlying: str, ticker: str) -> OptionContractCandidate | None:
        if not self.settings.massive_api_key:
            return None
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                response = await client.get(
                    f"https://api.polygon.io/v3/snapshot/options/{underlying}/{ticker}",
                    params={"apiKey": self.settings.massive_api_key},
                )
                response.raise_for_status()
                row = response.json().get("results")
                return self._candidate_from_row(underlying, row, max_premium=None, enforce_liquidity=False) if isinstance(row, dict) else None
            except (httpx.HTTPError, ValueError, TypeError):
                return None

    async def _contracts_status(self, client: httpx.AsyncClient, underlying: str) -> tuple[DataSourceStatus, str | None]:
        try:
            response = await client.get(
                "https://api.polygon.io/v3/reference/options/contracts",
                params={"underlying_ticker": underlying, "limit": 1, "apiKey": self.settings.massive_api_key},
            )
            response.raise_for_status()
            results = response.json().get("results", [])
            ticker = results[0].get("ticker") if results else None
            return (
                DataSourceStatus(
                    name="options_contracts",
                    enabled=True,
                    healthy=bool(ticker),
                    detail=f"Options reference contracts available for {underlying}." if ticker else "No option contracts returned.",
                    symbols_requested=1,
                    symbols_real=1 if ticker else 0,
                    symbols_fallback=0 if ticker else 1,
                ),
                ticker,
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            return (
                DataSourceStatus(
                    name="options_contracts",
                    enabled=True,
                    healthy=False,
                    detail=f"Options contracts check failed: {exc.__class__.__name__}.",
                    symbols_requested=1,
                    symbols_fallback=1,
                ),
                None,
            )

    async def _snapshot_status(self, client: httpx.AsyncClient, underlying: str) -> DataSourceStatus:
        try:
            response = await client.get(f"https://api.polygon.io/v3/snapshot/options/{underlying}", params={"limit": 10, "apiKey": self.settings.massive_api_key})
            if response.status_code in {401, 403}:
                message = response.json().get("message", "Not authorized for options snapshots.")
                return DataSourceStatus(
                    name="options_snapshot",
                    enabled=True,
                    healthy=False,
                    detail=f"Not authorized: {message}",
                    symbols_requested=1,
                    symbols_fallback=1,
                )
            response.raise_for_status()
            results = response.json().get("results", [])
            return DataSourceStatus(
                name="options_snapshot",
                enabled=True,
                healthy=bool(results),
                detail=f"Options chain snapshot available for {underlying}." if results else "Snapshot endpoint returned no chain rows.",
                symbols_requested=1,
                symbols_real=1 if results else 0,
                symbols_fallback=0 if results else 1,
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            return DataSourceStatus(
                name="options_snapshot",
                enabled=True,
                healthy=False,
                detail=f"Options snapshot check failed: {exc.__class__.__name__}.",
                symbols_requested=1,
                symbols_fallback=1,
            )

    async def _snapshot_rows(self, client: httpx.AsyncClient, underlying: str, limit: int) -> list[dict]:
        today = datetime.now(UTC).date()
        response = await client.get(
            f"https://api.polygon.io/v3/snapshot/options/{underlying}",
            params={
                "limit": limit,
                "expiration_date.gte": str(today + timedelta(days=7)),
                "expiration_date.lte": str(today + timedelta(days=45)),
                "apiKey": self.settings.massive_api_key,
            },
        )
        response.raise_for_status()
        rows = response.json().get("results", [])
        return rows if isinstance(rows, list) else []

    def _liquid_candidates(self, underlying: str, rows: list[dict], max_premium: float | None = None, earnings_date=None) -> list[OptionContractCandidate]:
        underlying_prices = [
            float(row.get("underlying_asset", {}).get("price"))
            for row in rows
            if isinstance(row.get("underlying_asset", {}).get("price"), int | float)
        ]
        underlying_price = median(underlying_prices) if underlying_prices else None
        candidates: list[OptionContractCandidate] = []
        for row in rows:
            candidate = self._candidate_from_row(underlying, row, max_premium=max_premium, enforce_liquidity=True, underlying_price=underlying_price, earnings_date=earnings_date)
            if candidate:
                candidates.append(candidate)
        return candidates

    def _candidate_from_row(
        self,
        underlying: str,
        row: dict,
        max_premium: float | None,
        enforce_liquidity: bool,
        underlying_price: float | None = None,
        earnings_date=None,
    ) -> OptionContractCandidate | None:
        details = row.get("details", {})
        day = row.get("day", {})
        greeks = row.get("greeks", {})
        last_quote = row.get("last_quote") or {}
        last_trade = row.get("last_trade") or {}
        try:
            ticker = details["ticker"]
            expiration = datetime.fromisoformat(details["expiration_date"]).date()
            strike = float(details["strike_price"])
            contract_type = details["contract_type"]
            volume = int(day.get("volume") or 0)
            open_interest = int(row.get("open_interest") or 0)
            last_trade_price = _float_or_none(last_trade.get("price"))
            premium = float(day.get("close") or day.get("vwap") or last_trade_price or 0)
            estimated_mid, estimated_bid, estimated_ask = option_quote_estimate(premium, volume, open_interest)
            quote_bid = _float_or_none(last_quote.get("bid") or last_quote.get("bid_price"))
            quote_ask = _float_or_none(last_quote.get("ask") or last_quote.get("ask_price"))
            if quote_bid and quote_ask and quote_ask > quote_bid:
                bid = quote_bid
                ask = quote_ask
                mid = (bid + ask) / 2
                premium = premium or mid
            else:
                mid, bid, ask = estimated_mid, estimated_bid, estimated_ask
            delta = abs(float(greeks.get("delta")))
            gamma = float(greeks["gamma"]) if greeks.get("gamma") is not None else None
            theta = float(greeks["theta"]) if greeks.get("theta") is not None else None
            vega = float(greeks["vega"]) if greeks.get("vega") is not None else None
            implied_volatility = float(row.get("implied_volatility") or 0)
        except (KeyError, TypeError, ValueError):
            return None

        quote_timestamp = _timestamp_from_any(
            last_quote.get("sip_timestamp")
            or last_quote.get("participant_timestamp")
            or last_quote.get("last_updated")
            or last_quote.get("timestamp")
        )
        last_trade_timestamp = _timestamp_from_any(
            last_trade.get("sip_timestamp")
            or last_trade.get("participant_timestamp")
            or last_trade.get("timestamp")
        )
        now = datetime.now(UTC)
        quote_age_seconds = max(0.0, (now - quote_timestamp).total_seconds()) if quote_timestamp else None
        last_trade_size = _int_or_none(last_trade.get("size"))
        dte = (expiration - datetime.now(UTC).date()).days
        spread_pct = (ask - bid) / max(mid, 0.01) * 100
        liquidity_score = option_liquidity_score(volume, open_interest, spread_pct)
        slippage_tier = option_slippage_tier(liquidity_score, spread_pct)
        microstructure_score = option_microstructure_score(
            liquidity_score=liquidity_score,
            spread_pct=spread_pct,
            quote_age_seconds=quote_age_seconds,
            last_trade_size=last_trade_size,
            volume=volume,
            open_interest=open_interest,
        )
        moneyness_pct = None
        if underlying_price:
            moneyness_pct = (strike / underlying_price - 1) * 100
            if contract_type == "put":
                moneyness_pct *= -1
        theta_daily = theta if theta is not None else -max(0.01, premium * 0.035 / max(dte, 1))
        dte_risk = option_dte_risk(dte)
        earnings_risk = option_earnings_risk(earnings_date, expiration)
        expected_iv_crush = option_expected_iv_crush(implied_volatility, earnings_risk, dte)
        iv_crush_risk = option_iv_crush_risk(expected_iv_crush)
        if enforce_liquidity:
            if not 7 <= dte <= 45:
                return None
            if volume < 20 or open_interest < 100:
                return None
            if not 0.25 <= delta <= 0.7:
                return None
            if not 0.15 <= implied_volatility <= 3.5:
                return None
            if not 0.25 <= premium <= 25:
                return None
            if slippage_tier == "avoid":
                return None
            if max_premium is not None and ask > max_premium:
                return None
            if underlying_price and contract_type == "call" and strike < underlying_price * 0.85:
                return None
            if underlying_price and contract_type == "put" and strike > underlying_price * 1.15:
                return None

        affordability_bonus = 8 if max_premium is not None and ask <= max_premium * 0.72 else 0
        spread_penalty = min(30, spread_pct * 1.2)
        dte_penalty = {"normal": 0, "accelerating": 4, "expiration_risk": 20, "expired": 99}[dte_risk]
        event_penalty = expected_iv_crush * 0.28
        score = volume * 0.28 + open_interest * 0.035 + (1 - abs(delta - 0.45)) * 25 + liquidity_score * 35 - dte * 0.06 + affordability_bonus - spread_penalty - dte_penalty - event_penalty
        return OptionContractCandidate(
            ticker=ticker,
            underlying=underlying,
            contract_type=contract_type,
            expiration_date=expiration,
            strike=strike,
            premium=round(premium, 4),
            bid=round(bid, 4),
            ask=round(ask, 4),
            mid=round(mid, 4),
            delta=round(delta, 4),
            gamma=gamma,
            theta=theta,
            vega=vega,
            implied_volatility=round(implied_volatility, 4),
            volume=volume,
            open_interest=open_interest,
            dte=dte,
            score=round(score, 4),
            spread_pct=round(spread_pct, 2),
            quote_timestamp=quote_timestamp,
            quote_age_seconds=round(quote_age_seconds, 2) if quote_age_seconds is not None else None,
            last_trade_price=round(last_trade_price, 4) if last_trade_price is not None else None,
            last_trade_size=last_trade_size,
            last_trade_timestamp=last_trade_timestamp,
            microstructure_score=round(microstructure_score, 3),
            liquidity_score=round(liquidity_score, 3),
            slippage_tier=slippage_tier,
            moneyness_pct=round(moneyness_pct, 2) if moneyness_pct is not None else None,
            theta_daily=round(theta_daily, 4),
            dte_risk=dte_risk,
            earnings_risk=earnings_risk,
            iv_crush_risk=iv_crush_risk,
            expected_iv_crush_pct=round(expected_iv_crush, 2),
        )

    async def _earnings_dates(self, client: httpx.AsyncClient, underlyings: list[str]) -> dict[str, date]:
        if not self.settings.fmp_api_key:
            return {}
        today = datetime.now(UTC).date()
        end = today + timedelta(days=60)
        try:
            response = await client.get(
                "https://financialmodelingprep.com/stable/earnings-calendar",
                params={"from": str(today), "to": str(end), "apikey": self.settings.fmp_api_key},
            )
            response.raise_for_status()
            rows = response.json()
        except (httpx.HTTPError, ValueError, TypeError):
            return {}
        wanted = set(underlyings)
        dates = {}
        if isinstance(rows, list):
            for row in rows:
                if row.get("symbol") in wanted and row.get("date"):
                    try:
                        dates[row["symbol"]] = datetime.fromisoformat(str(row["date"])[:10]).date()
                    except ValueError:
                        continue
        return dates

    def _chain_summary(self, underlying: str, rows: list[dict], liquid: list[OptionContractCandidate]) -> str:
        if not rows:
            return f"{underlying}: no chain rows"
        spreads = [item.spread_pct for item in liquid if item.spread_pct > 0]
        avg_spread = median(spreads) if spreads else 0
        tight = sum(1 for item in liquid if item.slippage_tier == "tight")
        return f"{underlying}: checked={len(rows)}, liquid={len(liquid)}, tight={tight}, medianSpread={avg_spread:.1f}%"

    async def _aggregates_status(self, client: httpx.AsyncClient, option_ticker: str | None) -> DataSourceStatus:
        if not option_ticker:
            return DataSourceStatus(name="options_aggs", enabled=True, healthy=False, detail="Skipped because no sample option contract was found.")

        end = datetime.now(UTC).date()
        start = end - timedelta(days=10)
        try:
            response = await client.get(
                f"https://api.polygon.io/v2/aggs/ticker/{option_ticker}/range/1/day/{start}/{end}",
                params={"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": self.settings.massive_api_key},
            )
            response.raise_for_status()
            results = response.json().get("results", [])
            return DataSourceStatus(
                name="options_aggs",
                enabled=True,
                healthy=bool(results),
                detail=f"Historical option aggregates available for sample contract {option_ticker}." if results else "No historical option aggregate rows returned.",
                symbols_requested=1,
                symbols_real=1 if results else 0,
                symbols_fallback=0 if results else 1,
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            return DataSourceStatus(
                name="options_aggs",
                enabled=True,
                healthy=False,
                detail=f"Options aggregates check failed: {exc.__class__.__name__}.",
                symbols_requested=1,
                symbols_fallback=1,
            )


def option_quote_estimate(premium: float, volume: int, open_interest: int) -> tuple[float, float, float]:
    liquidity = min(1.0, (volume / 5000) * 0.7 + (open_interest / 20000) * 0.3)
    spread_pct = max(0.025, 0.16 - liquidity * 0.12)
    half_spread = premium * spread_pct / 2
    bid = max(0.01, premium - half_spread)
    ask = max(bid + 0.01, premium + half_spread)
    return premium, bid, ask


def option_liquidity_score(volume: int, open_interest: int, spread_pct: float) -> float:
    volume_score = min(1.0, max(0, volume) / 5000)
    open_interest_score = min(1.0, max(0, open_interest) / 20000)
    spread_score = max(0.0, 1 - max(0.0, spread_pct - 2.5) / 22.5)
    return max(0.0, min(1.0, volume_score * 0.38 + open_interest_score * 0.32 + spread_score * 0.30))


def option_slippage_tier(liquidity_score: float, spread_pct: float) -> str:
    if spread_pct <= 5 and liquidity_score >= 0.70:
        return "tight"
    if spread_pct <= 10 and liquidity_score >= 0.45:
        return "normal"
    if spread_pct <= 18 and liquidity_score >= 0.25:
        return "wide"
    return "avoid"


def option_microstructure_score(
    liquidity_score: float,
    spread_pct: float,
    quote_age_seconds: float | None,
    last_trade_size: int | None,
    volume: int,
    open_interest: int,
) -> float:
    freshness = 0.45
    if quote_age_seconds is not None:
        freshness = max(0.0, min(1.0, 1 - quote_age_seconds / 900))
    trade_print = min(1.0, max(0, last_trade_size or 0) / 25)
    activity = min(1.0, max(0, volume) / 2000)
    oi_depth = min(1.0, max(0, open_interest) / 10000)
    spread_quality = max(0.0, 1 - max(0.0, spread_pct - 2.5) / 27.5)
    return max(0.0, min(1.0, freshness * 0.28 + trade_print * 0.18 + activity * 0.18 + oi_depth * 0.14 + spread_quality * 0.22 + liquidity_score * 0.18))


def option_dte_risk(dte: int) -> str:
    if dte <= 0:
        return "expired"
    if dte <= 2:
        return "expiration_risk"
    if dte <= 7:
        return "accelerating"
    return "normal"


def _float_or_none(value) -> float | None:
    try:
        if value is None:
            return None
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _int_or_none(value) -> int | None:
    try:
        if value is None:
            return None
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _timestamp_from_any(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
        except ValueError:
            return None
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return None
    if numeric > 10**17:
        return datetime.fromtimestamp(numeric / 1_000_000_000, UTC)
    if numeric > 10**14:
        return datetime.fromtimestamp(numeric / 1_000_000, UTC)
    if numeric > 10**11:
        return datetime.fromtimestamp(numeric / 1000, UTC)
    return datetime.fromtimestamp(numeric, UTC)


def option_earnings_risk(earnings_date: date | None, expiration: date) -> str:
    if not earnings_date:
        return "none"
    today = datetime.now(UTC).date()
    if today <= earnings_date <= expiration:
        if (earnings_date - today).days <= 7:
            return "earnings_within_7d"
        return "earnings_before_expiration"
    return "none"


def option_expected_iv_crush(implied_volatility: float, earnings_risk: str, dte: int) -> float:
    if earnings_risk == "none" or implied_volatility <= 0:
        return 0.0
    base = min(45.0, max(8.0, implied_volatility * 100 * 0.22))
    if earnings_risk == "earnings_within_7d":
        base *= 1.20
    if dte <= 10:
        base *= 1.10
    return round(min(55.0, base), 2)


def option_iv_crush_risk(expected_iv_crush_pct: float) -> str:
    if expected_iv_crush_pct >= 25:
        return "high"
    if expected_iv_crush_pct >= 12:
        return "medium"
    return "low"
