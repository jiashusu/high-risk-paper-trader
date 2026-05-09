from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import re
from zoneinfo import ZoneInfo

import httpx

from .alpaca import AlpacaPaperClient
from .config import Settings
from .ledger import ForwardLedger
from .live_gate import build_live_readiness, build_order_draft
from .market_data import get_market_data_provider
from .models import BrokerOrderDraft, Candle, DashboardPayload, DataCredibilityResponse, DataSourceStatus, DataTimestampCheck, DecisionDataInput, LiveReadinessGate, OptionContractCandidate, PriceDeviationCheck, RealismReport, RiskCockpitMetric, RiskCockpitResponse, RiskExposureItem, RiskMapItem, SignalAction, StrategySignal, Trade, TradeJournalEntry, TradeJournalResponse, TradeJournalStats, WeeklyReport
from .news import CatalystProvider, get_news_provider
from .options_data import OptionsDataProbe
from .reporting import build_weekly_report
from .risk import RiskManager
from .simulator import PaperBroker, modeled_option_mid
from .strategy_lab import build_strategy_lab
from .strategies import RiskParityFlatStrategy, StrategyContext, rank_strategies, select_strategy
from .universe import DEFAULT_UNIVERSE


def _svg_escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


class TradingResearchService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.market_data = get_market_data_provider(settings)
        self.news = get_news_provider(settings)
        self.catalysts = CatalystProvider(settings)
        self.options = OptionsDataProbe(settings)
        self.alpaca = AlpacaPaperClient(settings)
        self.risk = RiskManager(
            weekly_loss_limit_pct=settings.max_weekly_loss_pct,
            single_position_cap_pct=settings.max_position_pct,
        )
        self.ledger = ForwardLedger(settings.database_path, settings.paper_initial_cash)
        self._last_dashboard: DashboardPayload | None = None
        self._last_report: WeeklyReport | None = None
        self._last_strategy_lab = None

    async def run_cycle(self, allow_entry: bool = True) -> tuple[DashboardPayload, WeeklyReport]:
        symbols = [asset.symbol for asset in DEFAULT_UNIVERSE if asset.enabled]
        now = datetime.now(UTC)
        broker = self.ledger.load_broker()
        history = await self.market_data.get_history(symbols, days=180)
        heat = await self.news.sentiment_heat(symbols)
        data_quality_ok = self._market_real_data_pct(history) >= 95
        current_equity = self._current_equity(broker)
        context = StrategyContext(history=history, heat=heat, cash=broker.cash, equity=current_equity)
        selected = select_strategy(context) if data_quality_ok else RiskParityFlatStrategy()
        raw_signal = selected.generate(context)
        liquidity = next((asset.liquidity_score for asset in DEFAULT_UNIVERSE if asset.symbol == raw_signal.symbol), 1.0)
        adjusted_signal, warnings = self.risk.apply(raw_signal, current_equity, self._weekly_return_pct(broker), list(broker.positions.values()), liquidity)
        option_contract: OptionContractCandidate | None = None
        option_signal: StrategySignal | None = None
        option_statuses: list[DataSourceStatus] = []
        if self.settings.allow_options:
            option_underlyings = ["NVDA", "TSLA", "QQQ", "TQQQ", "SPY"]
            max_option_premium = max(0.01, min(broker.cash, current_equity * self.settings.max_position_pct / 100) / 100)
            options_scan = await self.options.scan_opportunities(option_underlyings, max_premium=max_option_premium)
            option_contract = self._select_option_contract(adjusted_signal, options_scan.candidates)
            option_signal = self._build_option_signal(adjusted_signal, option_contract, current_equity) if option_contract else None
            option_statuses = [
                *await self.options.statuses("NVDA"),
                self.options.status_from_scan(options_scan),
                self._selected_option_status(option_contract),
            ]
        else:
            option_statuses = [
                DataSourceStatus(
                    name="options_mode",
                    enabled=False,
                    healthy=True,
                    detail="Options are disabled by the first-start onboarding profile.",
                )
            ]
        if option_contract and option_signal:
            adjusted_signal = option_signal
        ranking = rank_strategies(context)
        for score in ranking:
            score.status = "candidate"
        base_strategy_id = adjusted_signal.strategy_id.removesuffix("_options")
        current_score = next((score for score in ranking if score.strategy_id == base_strategy_id), ranking[0])
        if adjusted_signal.instrument_type == "option":
            current_score = current_score.model_copy(
                update={
                    "strategy_id": adjusted_signal.strategy_id,
                    "name": adjusted_signal.strategy_name,
                    "explanation": adjusted_signal.reason,
                }
            )
        current_score.status = "active"
        chart_symbol = adjusted_signal.symbol if adjusted_signal.symbol in history else "BTC-USD"
        if adjusted_signal.instrument_type == "option" and adjusted_signal.underlying_symbol:
            chart_symbol = adjusted_signal.underlying_symbol
        account_status = await self.alpaca.account_status()
        source_statuses = [
            *self.news.statuses,
            *await self.catalysts.statuses(symbols),
            *option_statuses,
            await self._intraday_status(history),
            self._market_freshness_status(history),
            await self._price_cross_check_status(history),
        ]
        realism = self._build_realism_report(history, account_status, source_statuses)
        data_anomalies = self._data_anomalies(realism)
        ledger_summary = self.ledger.summary()
        order_draft = build_order_draft(
            self.settings,
            adjusted_signal,
            option_contract,
            ledger_summary,
            realism.source_statuses,
            data_anomalies,
        )
        broker = await self._forward_tick(
            broker,
            history,
            adjusted_signal,
            option_signal,
            option_contract,
            now,
            data_quality_ok and (order_draft.paper_trade_allowed if option_contract and order_draft else True),
            allow_entry and not self.settings.watch_only_mode and self.settings.onboarding_completed,
        )
        ledger_summary = self.ledger.summary()
        live_readiness = build_live_readiness(self.settings, ledger_summary, realism.source_statuses, data_anomalies)
        report = build_weekly_report(
            broker,
            current_score,
            ranking,
            live_readiness=live_readiness,
            data_anomalies=data_anomalies,
            forward_hit_rate=self._forward_hit_rate(broker),
        )
        strategy_lab = build_strategy_lab(context, ranking, broker, adjusted_signal, data_anomalies, ledger_summary)
        self._save_report(report)
        self.ledger.record_event(
            "source_snapshot",
            {
                "real_market_data_pct": realism.real_market_data_pct,
                "statuses": [status.model_dump(mode="json") for status in realism.source_statuses],
            },
            now,
        )
        dashboard = DashboardPayload(
            portfolio=report.portfolio,
            equity_curve=broker.equity_curve,
            candles=history.get(chart_symbol, [])[-90:],
            trades=broker.trades,
            current_strategy=current_score,
            candidate_strategies=ranking,
            next_review_at=self.next_review_at(),
            mode="phase_1_paper_only",
            warnings=warnings + self._integration_warnings(realism),
            realism=realism,
            ledger_events=self.ledger.latest_events(limit=12),
            order_draft=order_draft,
            live_readiness=live_readiness,
        )
        self._last_dashboard = dashboard
        self._last_report = report
        self._last_strategy_lab = strategy_lab
        return dashboard, report

    async def dashboard(self) -> DashboardPayload:
        if not self._last_dashboard:
            await self.run_cycle(allow_entry=False)
        assert self._last_dashboard is not None
        return self._last_dashboard

    async def report(self) -> WeeklyReport:
        if not self._last_report:
            await self.run_cycle(allow_entry=False)
        assert self._last_report is not None
        return self._last_report

    async def strategy_lab(self):
        if not self._last_strategy_lab:
            await self.run_cycle(allow_entry=False)
        assert self._last_strategy_lab is not None
        return self._last_strategy_lab

    async def data_credibility(self) -> DataCredibilityResponse:
        dashboard = await self.dashboard()
        now = datetime.now(UTC)
        statuses = dashboard.realism.source_statuses
        market_timestamps = self._market_timestamp_checks(dashboard.candles, statuses, now)
        price_deviations = self._price_deviation_checks(statuses)
        news_sources = [status for status in statuses if any(token in status.name for token in ("news", "sentiment", "benzinga", "finnhub"))]
        earnings_sources = [status for status in statuses if any(token in status.name for token in ("earnings", "fmp"))]
        options_sources = [status for status in statuses if any(token in status.name for token in ("options", "selected_option"))]
        decision_inputs = self._decision_inputs(dashboard)
        warnings = [
            warning
            for warning in [
                *dashboard.warnings,
                *(f"Unhealthy source: {status.name} - {status.detail}" for status in statuses if status.enabled and not status.healthy),
            ]
            if warning
        ]
        enabled = [status for status in statuses if status.enabled]
        source_health_pct = sum(1 for status in enabled if status.healthy) / max(1, len(enabled)) * 100
        fresh_pct = sum(1 for check in market_timestamps if check.healthy) / max(1, len(market_timestamps)) * 100
        deviation_pct = sum(1 for check in price_deviations if check.healthy) / max(1, len(price_deviations)) * 100 if price_deviations else 75
        score = round(min(100, dashboard.realism.real_market_data_pct * 0.40 + source_health_pct * 0.25 + fresh_pct * 0.20 + deviation_pct * 0.15), 1)
        verdict = "tradable" if score >= 85 and not warnings else "watch" if score >= 70 else "blocked"
        summary = self._credibility_summary(score, verdict, warnings, market_timestamps, price_deviations)
        return DataCredibilityResponse(
            generated_at=now,
            score=score,
            verdict=verdict,
            plain_language_summary=summary,
            market_timestamps=market_timestamps,
            price_deviations=price_deviations,
            news_sources=news_sources,
            earnings_sources=earnings_sources,
            options_chain_sources=options_sources,
            source_statuses=statuses,
            decision_inputs=decision_inputs,
            warnings=warnings,
        )

    async def risk_cockpit(self) -> RiskCockpitResponse:
        dashboard = await self.dashboard()
        ledger_summary = self.ledger.summary()
        portfolio = dashboard.portfolio
        equity = max(portfolio.equity, 0.01)
        total_position_value = sum(position.market_value for position in portfolio.positions)
        position_exposure_pct = total_position_value / equity * 100
        exposures = [self._risk_exposure_item(position, equity) for position in portfolio.positions]
        open_risk_amount = sum(item.max_loss_to_stop for item in exposures)
        open_risk_pct = open_risk_amount / equity * 100
        draft_loss = dashboard.order_draft.max_loss if dashboard.order_draft else 0.0
        max_single_trade_loss = max([draft_loss, *(item.max_loss_to_stop for item in exposures), 0.0])
        daily_loss_pct = float(ledger_summary.get("daily_loss_pct", 0.0))
        weekly_loss_pct = float(ledger_summary.get("weekly_loss_pct", 0.0))
        daily_loss_limit = equity * self.settings.max_daily_loss_pct / 100
        weekly_loss_limit = equity * self.settings.max_weekly_loss_pct / 100
        current_daily_loss = equity * daily_loss_pct / 100
        current_weekly_loss = equity * weekly_loss_pct / 100
        remaining_daily = max(0.0, daily_loss_limit - current_daily_loss)
        remaining_weekly = max(0.0, weekly_loss_limit - current_weekly_loss)
        consecutive_losses = self._consecutive_losses(dashboard.trades)
        weekly_fuse_status = self._risk_status(weekly_loss_pct, self.settings.max_weekly_loss_pct * 0.55, self.settings.max_weekly_loss_pct * 0.85)
        risk_map = self._risk_map(
            dashboard,
            position_exposure_pct,
            open_risk_pct,
            max_single_trade_loss / equity * 100,
            consecutive_losses,
            weekly_loss_pct,
        )
        danger_level = self._overall_danger(risk_map)
        metrics = [
            RiskCockpitMetric(
                label="Max single-trade loss",
                value=round(max_single_trade_loss, 2),
                display_value=f"${max_single_trade_loss:.2f}",
                status=self._risk_status(max_single_trade_loss / equity * 100, 20, self.settings.max_single_trade_loss_pct),
                plain_language="If the current draft or biggest open position goes wrong, this is the largest modeled hit.",
            ),
            RiskCockpitMetric(
                label="Current position exposure",
                value=round(position_exposure_pct, 2),
                display_value=f"{position_exposure_pct:.1f}%",
                status=self._risk_status(position_exposure_pct, 45, self.settings.max_position_pct),
                plain_language="How much of your account is currently tied up in open positions.",
            ),
            RiskCockpitMetric(
                label="Remaining daily loss room",
                value=round(remaining_daily, 2),
                display_value=f"${remaining_daily:.2f}",
                status="danger" if remaining_daily <= daily_loss_limit * 0.15 else "watch" if remaining_daily <= daily_loss_limit * 0.4 else "safe",
                plain_language="How much more the account can lose today before the daily fuse should stop new risk.",
            ),
            RiskCockpitMetric(
                label="Remaining weekly loss room",
                value=round(remaining_weekly, 2),
                display_value=f"${remaining_weekly:.2f}",
                status="danger" if remaining_weekly <= weekly_loss_limit * 0.15 else "watch" if remaining_weekly <= weekly_loss_limit * 0.4 else "safe",
                plain_language="How much more the account can lose this week before the weekly fuse should force cash mode.",
            ),
            RiskCockpitMetric(
                label="Consecutive losses",
                value=consecutive_losses,
                display_value=str(consecutive_losses),
                status="danger" if consecutive_losses >= 3 else "watch" if consecutive_losses >= 2 else "safe",
                plain_language="A losing streak is a warning to reduce size, not press harder.",
            ),
        ]
        warnings = [item.plain_language for item in risk_map if item.severity in {"watch", "danger"}]
        return RiskCockpitResponse(
            generated_at=datetime.now(UTC),
            equity=round(portfolio.equity, 2),
            cash=round(portfolio.cash, 2),
            total_position_value=round(total_position_value, 2),
            position_exposure_pct=round(position_exposure_pct, 2),
            max_single_trade_loss=round(max_single_trade_loss, 2),
            open_risk_amount=round(open_risk_amount, 2),
            open_risk_pct=round(open_risk_pct, 2),
            remaining_daily_loss_amount=round(remaining_daily, 2),
            remaining_weekly_loss_amount=round(remaining_weekly, 2),
            consecutive_losses=consecutive_losses,
            daily_loss_pct=round(daily_loss_pct, 2),
            weekly_loss_pct=round(weekly_loss_pct, 2),
            max_daily_loss_pct=self.settings.max_daily_loss_pct,
            max_weekly_loss_pct=self.settings.max_weekly_loss_pct,
            weekly_fuse_status=weekly_fuse_status,
            danger_level=danger_level,
            plain_language_summary=self._risk_summary(danger_level, position_exposure_pct, open_risk_pct, remaining_weekly, weekly_loss_limit, consecutive_losses),
            metrics=metrics,
            exposures=exposures,
            risk_map=risk_map,
            warnings=warnings,
        )

    async def trade_journal(self) -> TradeJournalResponse:
        dashboard = await self.dashboard()
        entries = self._build_trade_journal_entries(dashboard)
        closed = [entry for entry in entries if entry.status == "closed"]
        wins = [entry for entry in closed if (entry.realized_pnl or 0) > 0]
        losses = [entry for entry in closed if (entry.realized_pnl or 0) < 0]
        followed = [entry for entry in entries if entry.followed_plan]
        tag_counts: dict[str, int] = {}
        for entry in entries:
            for tag in entry.error_tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        common_tags = [tag for tag, _ in sorted(tag_counts.items(), key=lambda item: item[1], reverse=True)[:5]]
        plan_rate = len(followed) / len(entries) if entries else 0.0
        summary = self._journal_summary(entries, plan_rate, common_tags)
        return TradeJournalResponse(
            generated_at=datetime.now(UTC),
            summary=summary,
            stats=TradeJournalStats(
                total_entries=len(entries),
                closed_entries=len(closed),
                open_entries=len(entries) - len(closed),
                wins=len(wins),
                losses=len(losses),
                plan_follow_rate=round(plan_rate, 3),
                most_common_error_tags=common_tags,
            ),
            entries=entries,
        )

    def reset_ledger(self) -> None:
        self.ledger.reset()
        self._last_dashboard = None
        self._last_report = None
        self._last_strategy_lab = None

    def _market_timestamp_checks(self, candles: list[Candle], statuses: list[DataSourceStatus], now: datetime) -> list[DataTimestampCheck]:
        checks: list[DataTimestampCheck] = []
        by_symbol: dict[str, Candle] = {}
        for candle in candles:
            current = by_symbol.get(candle.symbol)
            if not current or candle.timestamp > current.timestamp:
                by_symbol[candle.symbol] = candle
        for symbol, candle in sorted(by_symbol.items()):
            age_minutes = max(0.0, (now - candle.timestamp).total_seconds() / 60)
            checks.append(
                DataTimestampCheck(
                    label="Current chart bar",
                    symbol=symbol,
                    source=candle.source,
                    latest_timestamp=candle.timestamp,
                    age_minutes=round(age_minutes, 1),
                    healthy=not candle.synthetic and age_minutes <= self.settings.max_market_data_age_days * 1440,
                    detail="Latest candle used by the visible decision chart.",
                )
            )
        for status in statuses:
            if status.latest_timestamp:
                age_minutes = max(0.0, (now - status.latest_timestamp).total_seconds() / 60)
                checks.append(
                    DataTimestampCheck(
                        label=status.name,
                        source=status.name,
                        latest_timestamp=status.latest_timestamp,
                        age_minutes=round(age_minutes, 1),
                        healthy=status.healthy and age_minutes <= self.settings.max_market_data_age_days * 1440,
                        detail=status.detail,
                    )
                )
        return checks

    def _price_deviation_checks(self, statuses: list[DataSourceStatus]) -> list[PriceDeviationCheck]:
        checks: list[PriceDeviationCheck] = []
        for status in statuses:
            if status.name != "price_cross_check":
                continue
            match = re.search(r"([A-Z.]+) Massive=([0-9.]+), FMP=([0-9.]+), diff=([0-9.]+)%", status.detail)
            if match:
                symbol, massive, fmp, diff = match.groups()
                diff_pct = float(diff)
                checks.append(
                    PriceDeviationCheck(
                        symbol=symbol,
                        primary_source="Massive/Polygon",
                        comparison_source="FMP",
                        primary_price=float(massive),
                        comparison_price=float(fmp),
                        diff_pct=diff_pct,
                        healthy=status.healthy and diff_pct <= 3.0,
                        detail=status.detail,
                    )
                )
            else:
                checks.append(
                    PriceDeviationCheck(
                        symbol="watchlist",
                        primary_source="Massive/Polygon",
                        comparison_source="FMP",
                        healthy=status.healthy,
                        detail=status.detail,
                    )
                )
        return checks

    def _decision_inputs(self, dashboard: DashboardPayload) -> list[DecisionDataInput]:
        inputs = [
            DecisionDataInput(category="strategy", label="Active strategy", source="strategy engine", value=dashboard.current_strategy.name, impact=dashboard.current_strategy.explanation),
            DecisionDataInput(category="execution", label="Execution model", source="simulator", value=dashboard.realism.execution_model, impact="Determines whether the signal can be counted as forward paper evidence."),
            DecisionDataInput(category="execution", label="Slippage model", source="simulator", value=dashboard.realism.slippage_model, impact="Changes fill price and paper PnL."),
            DecisionDataInput(category="risk", label="Live readiness", source="live gate", value="ready" if dashboard.live_readiness and dashboard.live_readiness.ready_for_live else "locked", impact="Blocks real-money mode until forward evidence and data checks are clean."),
        ]
        if dashboard.order_draft:
            draft = dashboard.order_draft
            inputs.extend(
                [
                    DecisionDataInput(category="order", label="Draft symbol", source=draft.broker, value=f"{draft.side.value.upper()} {draft.symbol}", impact=draft.reason),
                    DecisionDataInput(category="order", label="Limit price", source=draft.broker, value=f"${draft.limit_price:.4f}", impact=f"Max loss ${draft.max_loss:.2f}; slippage cap {draft.max_slippage_pct:.2f}%."),
                ]
            )
            inputs.extend(
                DecisionDataInput(category="gate", label=check.name, source="order draft gate", value="pass" if check.passed else "fail", impact=check.detail)
                for check in draft.checks[:8]
            )
        latest_trade = dashboard.trades[-1] if dashboard.trades else None
        if latest_trade:
            inputs.append(
                DecisionDataInput(category="ledger", label="Latest trade", source="forward ledger", value=f"{latest_trade.side.value.upper()} {latest_trade.symbol}", impact=latest_trade.reason)
            )
        return inputs

    def _credibility_summary(
        self,
        score: float,
        verdict: str,
        warnings: list[str],
        market_timestamps: list[DataTimestampCheck],
        price_deviations: list[PriceDeviationCheck],
    ) -> str:
        stale = [check for check in market_timestamps if not check.healthy]
        bad_deviation = [check for check in price_deviations if not check.healthy]
        if verdict == "tradable":
            return f"Data is strong enough for paper decisions: score {score:.1f}/100, timestamps are fresh, and cross-source prices are within tolerance."
        if verdict == "watch" and not stale and not bad_deviation:
            return f"Data is mostly strong but still has {len(warnings)} warning(s): score {score:.1f}/100. Use it for paper research, but review the warnings before trusting the signal."
        if stale or bad_deviation:
            return f"Data needs caution: score {score:.1f}/100. {len(stale)} timestamp check(s) and {len(bad_deviation)} price cross-check(s) need review before trusting the signal."
        return f"Data is not clean enough yet: score {score:.1f}/100 with {len(warnings)} warning(s). Treat this cycle as research, not a trade signal."

    def _risk_exposure_item(self, position, equity: float) -> RiskExposureItem:
        market_value = max(0.0, position.market_value)
        if position.instrument_type == "option":
            loss_to_stop = max(0.0, (position.market_price - position.stop_loss) * position.quantity * position.multiplier)
            max_loss = min(market_value, loss_to_stop if loss_to_stop > 0 else market_value)
        else:
            max_loss = max(0.0, (position.market_price - position.stop_loss) * position.quantity * position.multiplier)
        position_pct = market_value / equity * 100
        loss_pct = max_loss / equity * 100
        if max_loss <= 0:
            plain = "This position has no modeled stop risk right now, but it still needs live mark checks."
        elif position.instrument_type == "option":
            plain = f"This option can lose about ${max_loss:.2f} to its stop, and a gap can still damage the full premium."
        else:
            plain = f"If price hits the stop, this position is modeled to lose about ${max_loss:.2f}."
        return RiskExposureItem(
            symbol=position.symbol,
            instrument_type=position.instrument_type,
            market_value=round(market_value, 2),
            position_pct=round(position_pct, 2),
            max_loss_to_stop=round(max_loss, 2),
            max_loss_pct=round(loss_pct, 2),
            plain_language=plain,
        )

    def _consecutive_losses(self, trades: list[Trade]) -> int:
        entries: dict[str, list[float]] = {}
        closed_results: list[float] = []
        for trade in sorted(trades, key=lambda item: item.timestamp):
            if trade.side == SignalAction.BUY:
                entries.setdefault(trade.symbol, []).append(trade.notional + trade.fee)
            elif trade.side == SignalAction.SELL and entries.get(trade.symbol):
                entry_cost = entries[trade.symbol].pop(0)
                closed_results.append(trade.notional - trade.fee - entry_cost)
        streak = 0
        for result in reversed(closed_results):
            if result < 0:
                streak += 1
            else:
                break
        return streak

    def _risk_status(self, value: float, watch_threshold: float, danger_threshold: float) -> str:
        if value >= danger_threshold:
            return "danger"
        if value >= watch_threshold:
            return "watch"
        return "safe"

    def _risk_map(
        self,
        dashboard: DashboardPayload,
        position_exposure_pct: float,
        open_risk_pct: float,
        single_trade_loss_pct: float,
        consecutive_losses: int,
        weekly_loss_pct: float,
    ) -> list[RiskMapItem]:
        positions = dashboard.portfolio.positions
        option_positions = [position for position in positions if position.instrument_type == "option"]
        map_items = [
            RiskMapItem(
                area="position_size",
                severity=self._risk_status(position_exposure_pct, 45, self.settings.max_position_pct),
                title="Position size",
                plain_language=(
                    f"{position_exposure_pct:.1f}% of the account is in positions. A large position can make one bad idea dominate the whole account."
                    if positions
                    else "No open position right now. The safest risk is no active risk."
                ),
                action="Reduce size or stay flat if this rises near the position cap.",
            ),
            RiskMapItem(
                area="stop_loss",
                severity=self._risk_status(open_risk_pct, 18, self.settings.max_single_trade_loss_pct),
                title="Loss to stop",
                plain_language=f"Open positions are modeled to risk {open_risk_pct:.1f}% of equity before stops. Stops are estimates, not guarantees.",
                action="Keep every position tied to a stop and avoid gap-prone names near events.",
            ),
            RiskMapItem(
                area="weekly_fuse",
                severity=self._risk_status(weekly_loss_pct, self.settings.max_weekly_loss_pct * 0.55, self.settings.max_weekly_loss_pct * 0.85),
                title="Weekly fuse",
                plain_language=f"Weekly loss is {weekly_loss_pct:.1f}% versus a {self.settings.max_weekly_loss_pct:.1f}% fuse.",
                action="If this turns yellow or red, stop opening new risk and let the system go flat.",
            ),
            RiskMapItem(
                area="losing_streak",
                severity="danger" if consecutive_losses >= 3 else "watch" if consecutive_losses >= 2 else "safe",
                title="Losing streak",
                plain_language=f"The latest closed-trade losing streak is {consecutive_losses}. Chasing after losses is how small accounts disappear.",
                action="After 2 losses, cut size. After 3, pause entries until the next review.",
            ),
            RiskMapItem(
                area="options_expiry",
                severity="danger" if any((position.dte_risk in {"expiration_risk", "expired"}) for position in option_positions) else "watch" if option_positions else "safe",
                title="Options expiry risk",
                plain_language=(
                    "At least one option is close to the danger window where theta and bid/ask can punish the account fast."
                    if option_positions
                    else "No open options position right now."
                ),
                action="Exit before expiration risk and avoid holding weak options into event windows.",
            ),
            RiskMapItem(
                area="data_risk",
                severity="danger" if dashboard.realism.real_market_data_pct < 80 else "watch" if dashboard.realism.real_market_data_pct < 95 else "safe",
                title="Data risk",
                plain_language=f"{dashboard.realism.real_market_data_pct:.1f}% of market data is real. Bad data means the risk numbers may lie.",
                action="Do not trust entries when real data drops below 95%.",
            ),
            RiskMapItem(
                area="single_trade_loss",
                severity=self._risk_status(single_trade_loss_pct, 25, self.settings.max_single_trade_loss_pct),
                title="Single trade hit",
                plain_language=f"The biggest modeled single hit is {single_trade_loss_pct:.1f}% of equity.",
                action="Keep max loss below the configured cap and prefer smaller contracts when possible.",
            ),
        ]
        return map_items

    def _overall_danger(self, risk_map: list[RiskMapItem]) -> str:
        if any(item.severity == "danger" for item in risk_map):
            return "danger"
        if any(item.severity == "watch" for item in risk_map):
            return "watch"
        return "safe"

    def _risk_summary(self, danger_level: str, exposure_pct: float, open_risk_pct: float, remaining_weekly: float, weekly_limit: float, consecutive_losses: int) -> str:
        if danger_level == "danger":
            return f"现在最危险的是仓位或熔断已经接近红线。当前暴露 {exposure_pct:.1f}%，止损前风险 {open_risk_pct:.1f}%，本周剩余可亏 ${remaining_weekly:.2f}。先保命，不要加仓。"
        if danger_level == "watch":
            return f"现在还没到爆仓式危险，但需要盯紧。当前暴露 {exposure_pct:.1f}%，止损前风险 {open_risk_pct:.1f}%，本周剩余可亏 ${remaining_weekly:.2f}，连亏 {consecutive_losses} 次。"
        return f"当前风险比较干净。仓位暴露 {exposure_pct:.1f}%，止损前风险 {open_risk_pct:.1f}%，本周熔断空间还剩 ${remaining_weekly:.2f}/${weekly_limit:.2f}。"

    def _build_trade_journal_entries(self, dashboard: DashboardPayload) -> list[TradeJournalEntry]:
        open_entries: dict[str, list[Trade]] = {}
        closed_pairs: list[tuple[Trade, Trade | None]] = []
        for trade in sorted(dashboard.trades, key=lambda item: item.timestamp):
            if trade.side == SignalAction.BUY:
                open_entries.setdefault(trade.symbol, []).append(trade)
            elif trade.side == SignalAction.SELL and open_entries.get(trade.symbol):
                entry = open_entries[trade.symbol].pop(0)
                closed_pairs.append((entry, trade))
        for remaining in open_entries.values():
            for entry in remaining:
                closed_pairs.append((entry, None))
        return [self._trade_journal_entry(entry, exit_trade, dashboard) for entry, exit_trade in closed_pairs]

    def _trade_journal_entry(self, entry: Trade, exit_trade: Trade | None, dashboard: DashboardPayload) -> TradeJournalEntry:
        planned_risk = self._planned_risk(entry)
        result = self._actual_trade_result(entry, exit_trade)
        followed_plan, plan_notes = self._plan_compliance(entry, exit_trade)
        error_tags = self._journal_error_tags(entry, exit_trade, dashboard, followed_plan)
        return TradeJournalEntry(
            journal_id=f"journal-{entry.trade_id}",
            entry_trade_id=entry.trade_id,
            exit_trade_id=exit_trade.trade_id if exit_trade else None,
            symbol=entry.symbol,
            instrument_type=entry.instrument_type,
            side=entry.side,
            status="closed" if exit_trade else "open",
            entry_at=entry.timestamp,
            exit_at=exit_trade.timestamp if exit_trade else None,
            quantity=entry.quantity,
            entry_price=entry.price,
            exit_price=exit_trade.price if exit_trade else None,
            entry_notional=entry.notional,
            exit_notional=exit_trade.notional if exit_trade else None,
            realized_pnl=result["pnl"],
            realized_pnl_pct=result["pnl_pct"],
            planned_risk=planned_risk,
            entry_reason=entry.reason,
            exit_condition=entry.exit_condition or "No explicit exit condition was recorded at entry.",
            actual_result=result["text"],
            followed_plan=followed_plan,
            plan_compliance_notes=plan_notes,
            error_tags=error_tags,
            next_fix=self._next_fix(error_tags, exit_trade),
            pre_entry_snapshot_svg=self._trade_snapshot_svg(entry, dashboard.candles),
            pre_entry_snapshot_note=self._snapshot_note(entry, dashboard.candles),
        )

    def _planned_risk(self, trade: Trade) -> str:
        parts = [
            f"Entry notional ${trade.notional:.2f}",
            f"fee ${trade.fee:.2f}",
            f"slippage ${trade.slippage:.2f}",
        ]
        if trade.instrument_type == "option":
            parts.append("defined-risk long option; worst case can be full premium plus fee")
            if trade.expiration_date:
                parts.append(f"expiry {trade.expiration_date.isoformat()}")
            if trade.theta is not None:
                parts.append(f"theta {trade.theta:.3f}")
        return "; ".join(parts)

    def _actual_trade_result(self, entry: Trade, exit_trade: Trade | None) -> dict[str, float | str | None]:
        if not exit_trade:
            return {"pnl": None, "pnl_pct": None, "text": "Position is still open; result is not final yet."}
        pnl = exit_trade.notional - exit_trade.fee - entry.notional - entry.fee
        pnl_pct = pnl / max(entry.notional + entry.fee, 0.01) * 100
        verdict = "盈利" if pnl > 0 else "亏损" if pnl < 0 else "持平"
        return {"pnl": round(pnl, 2), "pnl_pct": round(pnl_pct, 2), "text": f"Closed with {verdict}: ${pnl:.2f} ({pnl_pct:.2f}%)."}

    def _plan_compliance(self, entry: Trade, exit_trade: Trade | None) -> tuple[bool, str]:
        if not entry.exit_condition:
            return False, "Entry did not record a clear exit condition."
        if not exit_trade:
            return True, "Plan is still active; no exit has happened yet."
        if exit_trade.exit_condition or "Exit" in exit_trade.reason:
            return True, "Exit was linked to a recorded rule or system exit reason."
        return False, "Exit happened without a clear recorded rule."

    def _journal_error_tags(self, entry: Trade, exit_trade: Trade | None, dashboard: DashboardPayload, followed_plan: bool) -> list[str]:
        tags: list[str] = []
        equity = max(dashboard.portfolio.equity, self.settings.paper_initial_cash, 1)
        if not followed_plan:
            tags.append("plan_not_followed")
        if not entry.exit_condition:
            tags.append("missing_exit_condition")
        if entry.notional / equity * 100 > self.settings.max_position_pct:
            tags.append("oversized")
        if entry.slippage / max(entry.notional, 0.01) * 100 > self.settings.max_order_slippage_pct:
            tags.append("slippage_too_high")
        if dashboard.realism.real_market_data_pct < 95:
            tags.append("data_quality")
        if exit_trade:
            pnl = exit_trade.notional - exit_trade.fee - entry.notional - entry.fee
            if pnl < 0:
                tags.append("loss")
        else:
            tags.append("still_open")
        if entry.instrument_type == "option":
            if entry.dte_risk in {"accelerating", "expiration_risk", "expired"}:
                tags.append("dte_risk")
            if entry.iv_crush_risk in {"medium", "high"}:
                tags.append("iv_crush_risk")
            if entry.slippage_tier in {"wide", "avoid"}:
                tags.append("wide_option_spread")
        if not tags:
            tags.append("good_process")
        return tags

    def _next_fix(self, tags: list[str], exit_trade: Trade | None) -> str:
        if "missing_exit_condition" in tags:
            return "Next time, do not allow the entry unless stop, target, invalidation, and time exit are written before entry."
        if "oversized" in tags:
            return "Reduce contract count or skip the trade; one idea should not dominate the account."
        if "slippage_too_high" in tags or "wide_option_spread" in tags:
            return "Use a stricter limit price and skip contracts with wide bid/ask spread."
        if "data_quality" in tags:
            return "Do not trade when real data is below 95% or source checks are unhealthy."
        if "loss" in tags:
            return "Review whether the entry reason was still valid at exit; if not, tighten the invalidation rule."
        if "still_open" in tags:
            return "Keep watching stop, target, liquidity, and time-based exit until this trade closes."
        if exit_trade:
            return "Keep the same rule, but verify the win came from process, not luck or stale data."
        return "No correction needed yet; keep collecting forward evidence."

    def _snapshot_note(self, trade: Trade, candles: list[Candle]) -> str:
        matching = self._snapshot_candles(trade, candles)
        if not matching:
            return "No matching chart candles were available; snapshot records the trade ticket only."
        first, last = matching[0], matching[-1]
        direction = "up" if last.close >= first.close else "down"
        return f"Pre-entry chart snapshot from {first.timestamp.date().isoformat()} to {last.timestamp.date().isoformat()}; price moved {direction} from {first.close:.2f} to {last.close:.2f}."

    def _snapshot_candles(self, trade: Trade, candles: list[Candle]) -> list[Candle]:
        candidates = [
            candle
            for candle in candles
            if candle.symbol in {trade.symbol, trade.underlying_symbol or trade.symbol}
            and candle.timestamp <= trade.timestamp
        ]
        if not candidates:
            candidates = [candle for candle in candles if candle.timestamp <= trade.timestamp]
        if not candidates:
            candidates = candles[:30]
        return candidates[-30:]

    def _trade_snapshot_svg(self, trade: Trade, candles: list[Candle]) -> str:
        series = self._snapshot_candles(trade, candles)
        width = 640
        height = 260
        pad = 28
        if not series:
            return (
                f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' viewBox='0 0 {width} {height}'>"
                "<rect width='100%' height='100%' fill='#080d10'/>"
                f"<text x='{pad}' y='{pad + 12}' fill='#e8f1ee' font-family='Arial' font-size='16'>No chart snapshot available</text>"
                f"<text x='{pad}' y='{pad + 38}' fill='#9aa8aa' font-family='Arial' font-size='13'>{trade.symbol} entry ${trade.price:.2f}</text>"
                "</svg>"
            )
        closes = [candle.close for candle in series]
        low = min(closes)
        high = max(closes)
        span = max(high - low, 0.01)
        step = (width - pad * 2) / max(len(series) - 1, 1)
        points = []
        for idx, candle in enumerate(series):
            x = pad + idx * step
            y = height - pad - ((candle.close - low) / span) * (height - pad * 2)
            points.append(f"{x:.1f},{y:.1f}")
        entry_y = height - pad - ((trade.price - low) / span) * (height - pad * 2)
        entry_y = max(pad, min(height - pad, entry_y))
        title = f"{trade.symbol} pre-entry snapshot"
        subtitle = f"{trade.timestamp.date().isoformat()} entry ${trade.price:.2f} · {trade.strategy_id}"
        return (
            f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' viewBox='0 0 {width} {height}'>"
            "<rect width='100%' height='100%' rx='10' fill='#080d10'/>"
            "<path d='M28 42 H612 M28 104 H612 M28 166 H612 M28 228 H612' stroke='#1d2a31' stroke-width='1'/>"
            f"<polyline points='{' '.join(points)}' fill='none' stroke='#36e39b' stroke-width='3' stroke-linecap='round' stroke-linejoin='round'/>"
            f"<line x1='{pad}' x2='{width - pad}' y1='{entry_y:.1f}' y2='{entry_y:.1f}' stroke='#f4c766' stroke-dasharray='6 6' stroke-width='1.5'/>"
            f"<circle cx='{width - pad}' cy='{entry_y:.1f}' r='5' fill='#f4c766'/>"
            f"<text x='{pad}' y='24' fill='#e8f1ee' font-family='Arial' font-size='16' font-weight='700'>{_svg_escape(title)}</text>"
            f"<text x='{pad}' y='246' fill='#9aa8aa' font-family='Arial' font-size='13'>{_svg_escape(subtitle)}</text>"
            f"<text x='{width - 180}' y='24' fill='#6ee7f9' font-family='Arial' font-size='12'>PRE-ENTRY</text>"
            "</svg>"
        )

    def _journal_summary(self, entries: list[TradeJournalEntry], plan_rate: float, tags: list[str]) -> str:
        if not entries:
            return "还没有交易日记。先不要急，等 forward ledger 产生真实模拟交易后再复盘。"
        if plan_rate < 0.75:
            return f"交易日记显示纪律问题：计划遵守率 {plan_rate * 100:.0f}%。先修流程，再谈提高收益。"
        if tags and tags[0] not in {"good_process", "still_open"}:
            return f"当前最常见问题是 {tags[0]}。下一步应优先减少重复错误。"
        return f"交易日记目前较干净：{len(entries)} 笔入场，计划遵守率 {plan_rate * 100:.0f}%。继续积累样本。"

    def _save_report(self, report: WeeklyReport) -> None:
        report_dir = Path(self.settings.report_dir)
        report_dir.mkdir(parents=True, exist_ok=True)
        dated = report_dir / f"weekly-{report.generated_at.date().isoformat()}.md"
        latest = report_dir / "weekly-latest.md"
        dated.write_text(report.markdown, encoding="utf-8")
        latest.write_text(report.markdown, encoding="utf-8")

    def next_review_at(self) -> datetime:
        weekdays = {"MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4, "SAT": 5, "SUN": 6}
        tz = ZoneInfo(self.settings.local_timezone)
        now = datetime.now(tz)
        target = now.replace(hour=self.settings.review_hour_local, minute=0, second=0, microsecond=0)
        days_ahead = (weekdays[self.settings.review_weekday] - now.weekday()) % 7
        if days_ahead == 0 and target <= now:
            days_ahead = 7
        return (target + timedelta(days=days_ahead)).astimezone(UTC)

    def _integration_warnings(self, realism: RealismReport) -> list[str]:
        warnings = ["Real trading is disabled: Phase 1 is paper-only."]
        if not self.settings.onboarding_completed:
            warnings.append("First-start onboarding is not complete; the desk is locked to setup mode.")
        if self.settings.watch_only_mode:
            warnings.append("Watch-only mode is enabled: forward ticks will update marks but will not open new paper entries.")
        if not self.settings.allow_options:
            warnings.append("Options are disabled by onboarding profile; the system will not scan or buy option contracts.")
        if realism.real_market_data_pct < 95:
            warnings.append("Data quality gate blocked trading signals: real market data must be at least 95%.")
        if realism.real_market_data_pct < 100:
            warnings.append(f"Market data is {realism.real_market_data_pct:.0f}% real; fallback symbols: {', '.join(realism.synthetic_symbols) or 'none'}.")
        if not self.settings.finnhub_api_key and not self.settings.fmp_api_key:
            warnings.append("News/fundamental APIs are missing; using synthetic heat scores.")
        if not self.settings.alpaca_paper_api_key:
            warnings.append("Alpaca paper credentials are not configured yet.")
        if any(status.name == "options_snapshot" and status.enabled and not status.healthy for status in realism.source_statuses):
            warnings.append("Options snapshot data is not authorized; do not use live options chain strategies yet.")
        if any(status.name == "options_opportunity_scan" and status.enabled and not status.healthy for status in realism.source_statuses):
            warnings.append("Options chain is connected, but no liquid candidate passed the safety filters.")
        return warnings

    def _build_realism_report(
        self,
        history: dict[str, list[Candle]],
        account_status: DataSourceStatus,
        extra_statuses: list[DataSourceStatus] | None = None,
    ) -> RealismReport:
        candles = [candle for candles in history.values() for candle in candles]
        total_points = len(candles)
        real_points = sum(1 for candle in candles if not candle.synthetic)
        real_market_pct = (real_points / total_points * 100) if total_points else 0.0
        synthetic_symbols = sorted(symbol for symbol, candles in history.items() if any(candle.synthetic for candle in candles))
        source_statuses = [*self.market_data.statuses, *(extra_statuses or []), account_status]
        enabled_statuses = [status for status in source_statuses if status.enabled]
        source_health = sum(1 for status in enabled_statuses if status.healthy) / max(1, len(enabled_statuses))
        score = min(100.0, real_market_pct * 0.65 + source_health * 25 + (10 if account_status.healthy else 0))
        return RealismReport(
            score=round(score, 1),
            real_market_data_pct=round(real_market_pct, 1),
            data_points=total_points,
            synthetic_symbols=synthetic_symbols,
            execution_model="Forward ledger mode: signals use prior market data, fills use the current paper tick, and repeated refreshes do not duplicate same-day entries.",
            slippage_model="Spot fills use range/liquidity impact. Option fills use limit-order simulation with bid/ask, historical spread path, missed fills, liquidity gaps, theta decay, DTE risk, and event IV crush.",
            fee_model="US equities/ETFs: $0 commission model; crypto: 25 bps taker-style fee estimate; options: $0.65/contract conservative fee estimate.",
            account_source="Alpaca paper account read-only check" if account_status.healthy else "Local simulator only",
            source_statuses=source_statuses,
        )

    async def _forward_tick(
        self,
        broker: PaperBroker,
        history: dict[str, list[Candle]],
        adjusted_signal: StrategySignal,
        option_signal: StrategySignal | None,
        option_contract: OptionContractCandidate | None,
        timestamp: datetime,
        data_quality_ok: bool,
        allow_entry: bool,
    ) -> PaperBroker:
        await self._update_open_positions(broker, history, timestamp)
        self._flush_execution_events(broker)
        attempted_today = self._entry_attempted_today(broker, timestamp)

        if allow_entry and data_quality_ok and not broker.positions and not attempted_today:
            if option_contract and option_signal and option_signal.target_notional >= option_contract.ask * option_contract.multiplier + 0.65:
                trade = broker.buy_option(option_signal, self._option_mark_candle(option_contract, timestamp), option_contract)
                self._flush_execution_events(broker)
                if trade:
                    self.ledger.record_event(
                        "signal",
                        {
                            "strategy_id": option_signal.strategy_id,
                            "symbol": option_signal.symbol,
                            "action": option_signal.action.value,
                            "reason": option_signal.reason,
                            "contract": option_contract.model_dump(mode="json"),
                        },
                        timestamp,
                    )
            elif adjusted_signal.action == SignalAction.BUY and adjusted_signal.symbol in history and history[adjusted_signal.symbol]:
                candle = history[adjusted_signal.symbol][-1].model_copy(update={"timestamp": timestamp})
                broker.execute(adjusted_signal, candle)
                self.ledger.record_event(
                    "signal",
                    {
                        "strategy_id": adjusted_signal.strategy_id,
                        "symbol": adjusted_signal.symbol,
                        "action": adjusted_signal.action.value,
                        "reason": adjusted_signal.reason,
                    },
                    timestamp,
                )

        marks = await self._position_marks(broker, history, timestamp)
        broker.mark_to_market(marks, timestamp=timestamp)
        self._flush_execution_events(broker)
        self.ledger.save_broker(broker, timestamp)
        return broker

    def _entry_attempted_today(self, broker: PaperBroker, timestamp: datetime) -> bool:
        if any(trade.timestamp.date() == timestamp.date() for trade in broker.trades):
            return True
        for event in self.ledger.latest_events(limit=80):
            if event.get("kind") not in {"signal", "option_order_missed", "option_limit_fill"}:
                continue
            try:
                event_time = datetime.fromisoformat(str(event.get("timestamp")).replace("Z", "+00:00"))
            except ValueError:
                continue
            if event_time.date() == timestamp.date():
                return True
        return False

    async def _update_open_positions(self, broker: PaperBroker, history: dict[str, list[Candle]], timestamp: datetime) -> None:
        for position in list(broker.positions.values()):
            if position.instrument_type == "option" and position.underlying_symbol:
                contract = await self.options.contract_snapshot(position.underlying_symbol, position.symbol)
                if not contract:
                    contract = self._contract_from_position(position, timestamp)
                bid = contract.bid
                exit_reason = None
                if bid <= position.stop_loss:
                    exit_reason = "Forward ledger option stop loss touched by current bid."
                elif bid >= position.take_profit:
                    exit_reason = "Forward ledger option take profit touched by current bid."
                elif contract.dte <= 2 or contract.dte_risk in {"expiration_risk", "expired"}:
                    exit_reason = "Forward ledger exited before expiration risk window."
                elif contract.slippage_tier == "avoid":
                    exit_reason = "Forward ledger exited because option liquidity/slippage deteriorated."
                if exit_reason:
                    broker.close_option(self._option_mark_candle(contract, timestamp), self._exit_signal(position, timestamp), contract, exit_reason)
                    self._flush_execution_events(broker)
            elif position.symbol in history and history[position.symbol]:
                candle = history[position.symbol][-1].model_copy(update={"timestamp": timestamp})
                broker.enforce_stops({position.symbol: candle}, self._exit_signal(position, timestamp))

    async def _position_marks(self, broker: PaperBroker, history: dict[str, list[Candle]], timestamp: datetime) -> dict[str, Candle]:
        marks: dict[str, Candle] = {}
        for position in broker.positions.values():
            if position.instrument_type == "option" and position.underlying_symbol:
                contract = await self.options.contract_snapshot(position.underlying_symbol, position.symbol)
                if not contract:
                    contract = self._contract_from_position(position, timestamp)
                marks[position.symbol] = self._option_mark_candle(contract, timestamp)
            elif position.symbol in history and history[position.symbol]:
                marks[position.symbol] = history[position.symbol][-1].model_copy(update={"timestamp": timestamp})
        return marks

    def _option_mark_candle(self, contract: OptionContractCandidate, timestamp: datetime) -> Candle:
        modeled_mid = modeled_option_mid(contract, contract.mid, days_held=1)
        spread_pct = contract.spread_pct or contract.historical_spread_pct or 6.0
        if contract.historical_spread_pct:
            spread_pct = max(spread_pct, contract.historical_spread_pct)
        half_spread = modeled_mid * spread_pct / 200
        bid = max(0.01, modeled_mid - half_spread)
        ask = max(bid + 0.01, modeled_mid + half_spread)
        return Candle(
            symbol=contract.ticker,
            timestamp=timestamp,
            open=modeled_mid,
            high=max(ask, modeled_mid, bid),
            low=max(0.01, min(bid, modeled_mid, ask)),
            close=bid,
            volume=contract.volume,
            source="massive_options_snapshot",
            synthetic=False,
        )

    def _flush_execution_events(self, broker: PaperBroker) -> None:
        for event in broker.drain_execution_events():
            self.ledger.record_event(event["kind"], event["payload"], event.get("timestamp"))

    def _contract_from_position(self, position, timestamp: datetime) -> OptionContractCandidate:
        dte = max(0, (position.expiration_date - timestamp.date()).days) if position.expiration_date else 0
        premium = max(0.01, position.market_price)
        return OptionContractCandidate(
            ticker=position.symbol,
            underlying=position.underlying_symbol or position.symbol,
            contract_type=position.option_type or "call",
            expiration_date=position.expiration_date or timestamp.date(),
            strike=position.strike or 0,
            premium=premium,
            bid=max(0.01, premium * 0.97),
            ask=max(0.02, premium * 1.03),
            mid=premium,
            delta=position.delta or 0.0,
            theta=position.theta,
            implied_volatility=position.implied_volatility or 0.0,
            volume=0,
            open_interest=0,
            dte=dte,
            score=0,
            spread_pct=position.spread_pct or 6.0,
            historical_spread_pct=position.historical_spread_pct,
            spread_history_pct=position.spread_history_pct,
            liquidity_score=position.liquidity_score or 0.2,
            slippage_tier=position.slippage_tier,
            chain_rank=position.chain_rank or 0,
            chain_candidates=position.chain_candidates or 0,
            theta_daily=position.theta_daily or position.theta or 0.0,
            dte_risk=position.dte_risk or ("expiration_risk" if dte <= 2 else "accelerating" if dte <= 7 else "normal"),
            earnings_risk=position.earnings_risk or "unknown",
            iv_crush_risk=position.iv_crush_risk or "unknown",
            expected_iv_crush_pct=position.expected_iv_crush_pct or 0.0,
        )

    def _exit_signal(self, position, timestamp: datetime) -> StrategySignal:
        return StrategySignal(
            strategy_id="forward_ledger_exit",
            strategy_name="Forward Ledger Exit",
            symbol=position.symbol,
            action=SignalAction.SELL,
            confidence=1,
            target_notional=0,
            stop_loss_pct=0.01,
            take_profit_pct=0.01,
            invalidation="Forward ledger exit rule triggered.",
            reason="Forward ledger exit rule triggered.",
            data_sources=["ledger", "risk"],
            generated_at=timestamp,
            instrument_type=position.instrument_type,
            underlying_symbol=position.underlying_symbol,
            multiplier=position.multiplier,
        )

    def _current_equity(self, broker: PaperBroker) -> float:
        return broker.cash + sum(position.market_value for position in broker.positions.values())

    def _weekly_return_pct(self, broker: PaperBroker) -> float:
        equity = self._current_equity(broker)
        return ((equity / broker.initial_cash) - 1) * 100 if broker.initial_cash else 0

    def _select_option_contract(self, signal: StrategySignal, candidates: list[OptionContractCandidate]) -> OptionContractCandidate | None:
        if signal.action != SignalAction.BUY:
            return None
        if signal.symbol not in {"NVDA", "TSLA", "QQQ", "TQQQ", "SPY"}:
            return None
        direction = "call"
        matching = [candidate for candidate in candidates if candidate.underlying == signal.symbol and candidate.contract_type == direction]
        if not matching:
            matching = [candidate for candidate in candidates if candidate.contract_type == direction]
        return matching[0] if matching else None

    def _build_option_signal(self, signal: StrategySignal, contract: OptionContractCandidate, current_equity: float) -> StrategySignal:
        max_contracts = int((current_equity * self.settings.max_position_pct / 100) // (contract.ask * contract.multiplier + 0.65))
        target_notional = max_contracts * (contract.ask * contract.multiplier + 0.65) if max_contracts else 0
        return signal.model_copy(
            update={
                "strategy_id": f"{signal.strategy_id}_options",
                "strategy_name": f"{signal.strategy_name} Options Overlay",
                "symbol": contract.ticker,
                "target_notional": round(min(signal.target_notional, target_notional), 2),
                "stop_loss_pct": 0.45,
                "take_profit_pct": 1.1,
                "invalidation": (
                    f"Exit if premium loses 45%, gains 110%, liquidity/slippage deteriorates, IV crush risk spikes, DTE reaches risk window, or {contract.underlying} momentum fails."
                ),
                "reason": (
                    f"{signal.reason} Executed through {contract.ticker} "
                    f"{contract.expiration_date} {contract.contract_type.upper()} {contract.strike:g}; "
                    f"delta={contract.delta:.2f}, theta={contract.theta or 0:.2f}, IV={contract.implied_volatility:.2f}, "
                    f"spread={contract.spread_pct:.1f}%, histSpread={contract.historical_spread_pct or 0:.1f}%, "
                    f"tier={contract.slippage_tier}, liquidity={contract.liquidity_score:.2f}, "
                    f"DTE={contract.dte}/{contract.dte_risk}, earnings={contract.earnings_risk}, "
                    f"ivCrush={contract.iv_crush_risk}({contract.expected_iv_crush_pct:.1f}%), "
                    f"chainRank={contract.chain_rank}/{contract.chain_candidates}, volume={contract.volume}, OI={contract.open_interest}."
                ),
                "data_sources": [*signal.data_sources, "options:snapshot", "options:historical-aggs", "options:greeks"],
                "instrument_type": "option",
                "underlying_symbol": contract.underlying,
                "multiplier": contract.multiplier,
                "option_contract": contract,
                "contract_quantity": max_contracts,
            }
        )

    def _market_real_data_pct(self, history: dict[str, list[Candle]]) -> float:
        candles = [candle for candles in history.values() for candle in candles]
        if not candles:
            return 0.0
        real_points = sum(1 for candle in candles if not candle.synthetic)
        return real_points / len(candles) * 100

    def _market_freshness_status(self, history: dict[str, list[Candle]]) -> DataSourceStatus:
        latest = [candles[-1].timestamp for candles in history.values() if candles and not candles[-1].synthetic]
        if not latest:
            return DataSourceStatus(name="market_freshness", enabled=True, healthy=False, detail="No real market timestamps available.")
        newest = max(latest)
        age_days = (datetime.now(UTC) - newest).days
        return DataSourceStatus(
            name="market_freshness",
            enabled=True,
            healthy=age_days <= self.settings.max_market_data_age_days,
            detail=f"Newest real market bar is {age_days} day(s) old at {newest.isoformat()} with limit {self.settings.max_market_data_age_days} day(s).",
            symbols_requested=len(history),
            symbols_real=len(latest),
            symbols_fallback=len(history) - len(latest),
            latest_timestamp=newest,
        )

    async def _price_cross_check_status(self, history: dict[str, list[Candle]]) -> DataSourceStatus:
        if not self.settings.fmp_api_key:
            return DataSourceStatus(name="price_cross_check", enabled=False, healthy=False, detail="FMP key is not configured for cross-source price checks.")

        symbols = [symbol for symbol in ("NVDA", "TQQQ", "QQQ", "SPY") if history.get(symbol)]
        if not symbols:
            return DataSourceStatus(name="price_cross_check", enabled=True, healthy=False, detail="No equity symbols available for cross-source price check.")

        checked = 0
        passed = 0
        worst_detail = ""
        async with httpx.AsyncClient(timeout=12) as client:
            for symbol in symbols:
                massive_close = history[symbol][-1].close
                try:
                    response = await client.get(
                        "https://financialmodelingprep.com/stable/quote",
                        params={"symbol": symbol, "apikey": self.settings.fmp_api_key},
                    )
                    response.raise_for_status()
                    rows = response.json()
                    price = float(rows[0]["price"]) if isinstance(rows, list) and rows else 0.0
                except (httpx.HTTPError, KeyError, TypeError, ValueError):
                    continue
                if price <= 0:
                    continue
                checked += 1
                diff_pct = abs(price / massive_close - 1) * 100
                if diff_pct <= 3.0:
                    passed += 1
                if not worst_detail or diff_pct > float(worst_detail.split("diff=")[-1].split("%")[0]):
                    worst_detail = f"{symbol} Massive={massive_close:.2f}, FMP={price:.2f}, diff={diff_pct:.2f}%"

        return DataSourceStatus(
            name="price_cross_check",
            enabled=True,
            healthy=checked > 0 and passed == checked,
            detail=f"Cross-source price check passed {passed}/{checked}. Worst: {worst_detail or 'none'}.",
            symbols_requested=len(symbols),
            symbols_real=passed,
            symbols_fallback=len(symbols) - passed,
        )

    def _data_anomalies(self, realism: RealismReport) -> list[str]:
        anomalies = []
        if realism.real_market_data_pct < 95:
            anomalies.append(f"Real market data below 95%: {realism.real_market_data_pct:.1f}%.")
        for status in realism.source_statuses:
            if status.enabled and status.name in {"massive", "options_snapshot", "market_freshness", "selected_option_quality", "price_cross_check"} and not status.healthy:
                anomalies.append(f"{status.name}: {status.detail}")
        return anomalies

    def _forward_hit_rate(self, broker: PaperBroker) -> float:
        buys: dict[str, list[float]] = {}
        closed = 0
        wins = 0
        for trade in broker.trades:
            if trade.side == SignalAction.BUY:
                buys.setdefault(trade.symbol, []).append(trade.notional + trade.fee)
            elif trade.side == SignalAction.SELL and buys.get(trade.symbol):
                entry = buys[trade.symbol].pop(0)
                closed += 1
                if trade.notional - trade.fee > entry:
                    wins += 1
        return wins / closed if closed else 0.0

    def _selected_option_status(self, contract: OptionContractCandidate | None) -> DataSourceStatus:
        if not contract:
            return DataSourceStatus(name="selected_option_quality", enabled=True, healthy=False, detail="No option contract selected for the current signal.")
        spread_pct = contract.spread_pct or (contract.ask - contract.bid) / max(contract.mid, 0.01) * 100
        historical_spread = contract.historical_spread_pct or spread_pct
        healthy = (
            spread_pct <= self.settings.max_order_slippage_pct
            and historical_spread <= max(self.settings.max_order_slippage_pct, 18)
            and contract.volume >= 20
            and contract.open_interest >= 100
            and contract.liquidity_score >= 0.25
            and contract.slippage_tier in {"tight", "normal", "wide"}
            and contract.dte_risk in {"normal", "accelerating"}
            and contract.iv_crush_risk != "high"
        )
        return DataSourceStatus(
            name="selected_option_quality",
            enabled=True,
            healthy=healthy,
            detail=(
                f"{contract.ticker} bid={contract.bid:.2f}, ask={contract.ask:.2f}, spread={spread_pct:.1f}%, "
                f"histSpread={historical_spread:.1f}%, tier={contract.slippage_tier}, liquidity={contract.liquidity_score:.2f}, "
                f"rank={contract.chain_rank}/{contract.chain_candidates}, delta={contract.delta:.2f}, thetaDaily={contract.theta_daily:.2f}, "
                f"IV={contract.implied_volatility:.2f}, ivCrush={contract.iv_crush_risk}({contract.expected_iv_crush_pct:.1f}%), "
                f"earnings={contract.earnings_risk}, DTE={contract.dte}/{contract.dte_risk}, volume={contract.volume}, OI={contract.open_interest}."
            ),
            symbols_requested=1,
            symbols_real=1,
        )

    async def _intraday_status(self, history: dict[str, list[Candle]]) -> DataSourceStatus:
        if not self.settings.massive_api_key:
            return DataSourceStatus(name="intraday_1min", enabled=False, healthy=False, detail="Massive API key is not configured.")

        checks = {"NVDA": "NVDA", "BTC-USD": "X:BTCUSD"}
        real = 0
        async with httpx.AsyncClient(timeout=15) as client:
            for display_symbol, ticker in checks.items():
                real_candles = [candle for candle in history.get(display_symbol, []) if not candle.synthetic]
                if not real_candles:
                    continue
                end = real_candles[-1].timestamp.date()
                start = end - timedelta(days=3)
                try:
                    response = await client.get(
                        f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/minute/{start}/{end}",
                        params={"adjusted": "true", "sort": "desc", "limit": 1, "apiKey": self.settings.massive_api_key},
                    )
                    response.raise_for_status()
                    if response.json().get("results"):
                        real += 1
                except (httpx.HTTPError, ValueError, TypeError):
                    continue

        return DataSourceStatus(
            name="intraday_1min",
            enabled=True,
            healthy=real == len(checks),
            detail=f"Massive 1-minute aggregates reachable for {real}/{len(checks)} spot checks.",
            symbols_requested=len(checks),
            symbols_real=real,
            symbols_fallback=len(checks) - real,
        )
