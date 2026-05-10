from datetime import date, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class AssetClass(str, Enum):
    CRYPTO = "crypto"
    EQUITY = "equity"
    ETF = "etf"


class SignalAction(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    FLAT = "flat"


class ReviewDecision(str, Enum):
    CONTINUE = "continue"
    SWITCH_STRATEGY = "switch_strategy"
    GO_FLAT = "go_flat"
    READY_FOR_MANUAL_LIVE = "ready_for_manual_live"


class Asset(BaseModel):
    symbol: str
    display_name: str
    asset_class: AssetClass
    min_notional: float = 1.0
    liquidity_score: float = Field(ge=0, le=1)
    enabled: bool = True


class Candle(BaseModel):
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str = "unknown"
    synthetic: bool = False


class DataSourceStatus(BaseModel):
    name: str
    enabled: bool
    healthy: bool
    detail: str
    symbols_requested: int = 0
    symbols_real: int = 0
    symbols_fallback: int = 0
    latest_timestamp: datetime | None = None


class GateCriterion(BaseModel):
    name: str
    passed: bool
    detail: str


class LiveReadinessGate(BaseModel):
    ready_for_live: bool
    required_forward_weeks: int
    completed_forward_weeks: float
    can_create_order_draft: bool
    blockers: list[str]
    criteria: list[GateCriterion]


class BrokerOrderDraft(BaseModel):
    draft_id: str
    created_at: datetime
    broker: str
    account_mode: str
    live_submission_enabled: bool = False
    symbol: str
    underlying_symbol: str | None = None
    instrument_type: str
    side: SignalAction
    quantity: float
    order_type: str = "limit"
    limit_price: float
    estimated_notional: float
    estimated_fee: float
    max_loss: float
    max_slippage_pct: float
    position_cap_pct: float
    time_in_force: str
    expiry_risk_exit_at: date | None = None
    strategy_id: str
    reason: str
    checks: list[GateCriterion]
    blocking_reasons: list[str]
    paper_trade_allowed: bool


class RealismReport(BaseModel):
    score: float = Field(ge=0, le=100)
    real_market_data_pct: float = Field(ge=0, le=100)
    data_points: int
    synthetic_symbols: list[str]
    execution_model: str
    slippage_model: str
    fee_model: str
    account_source: str
    source_statuses: list[DataSourceStatus]


class DataTimestampCheck(BaseModel):
    label: str
    symbol: str | None = None
    source: str
    latest_timestamp: datetime | None = None
    age_minutes: float | None = None
    healthy: bool
    detail: str


class PriceDeviationCheck(BaseModel):
    symbol: str
    primary_source: str
    comparison_source: str
    primary_price: float | None = None
    comparison_price: float | None = None
    diff_pct: float | None = None
    healthy: bool
    detail: str


class DecisionDataInput(BaseModel):
    category: str
    label: str
    source: str
    value: str
    impact: str


class DataCredibilityResponse(BaseModel):
    generated_at: datetime
    score: float = Field(ge=0, le=100)
    verdict: str
    plain_language_summary: str
    market_timestamps: list[DataTimestampCheck]
    price_deviations: list[PriceDeviationCheck]
    news_sources: list[DataSourceStatus]
    earnings_sources: list[DataSourceStatus]
    options_chain_sources: list[DataSourceStatus]
    source_statuses: list[DataSourceStatus]
    decision_inputs: list[DecisionDataInput]
    warnings: list[str]


class RiskCockpitMetric(BaseModel):
    label: str
    value: float
    display_value: str
    status: Literal["safe", "watch", "danger"]
    plain_language: str


class RiskExposureItem(BaseModel):
    symbol: str
    instrument_type: str
    market_value: float
    position_pct: float
    max_loss_to_stop: float
    max_loss_pct: float
    plain_language: str


class RiskMapItem(BaseModel):
    area: str
    severity: Literal["safe", "watch", "danger"]
    title: str
    plain_language: str
    action: str


class RiskCockpitResponse(BaseModel):
    generated_at: datetime
    equity: float
    cash: float
    total_position_value: float
    position_exposure_pct: float
    max_single_trade_loss: float
    open_risk_amount: float
    open_risk_pct: float
    remaining_daily_loss_amount: float
    remaining_weekly_loss_amount: float
    consecutive_losses: int
    daily_loss_pct: float
    weekly_loss_pct: float
    max_daily_loss_pct: float
    max_weekly_loss_pct: float
    weekly_fuse_status: Literal["safe", "watch", "danger"]
    danger_level: Literal["safe", "watch", "danger"]
    plain_language_summary: str
    metrics: list[RiskCockpitMetric]
    exposures: list[RiskExposureItem]
    risk_map: list[RiskMapItem]
    warnings: list[str]


class TradeJournalStats(BaseModel):
    total_entries: int
    closed_entries: int
    open_entries: int
    wins: int
    losses: int
    plan_follow_rate: float
    most_common_error_tags: list[str]


class TradeJournalEntry(BaseModel):
    journal_id: str
    entry_trade_id: str
    exit_trade_id: str | None = None
    symbol: str
    instrument_type: str
    side: SignalAction
    status: Literal["open", "closed"]
    entry_at: datetime
    exit_at: datetime | None = None
    quantity: float
    entry_price: float
    exit_price: float | None = None
    entry_notional: float
    exit_notional: float | None = None
    realized_pnl: float | None = None
    realized_pnl_pct: float | None = None
    planned_risk: str
    entry_reason: str
    exit_condition: str
    actual_result: str
    followed_plan: bool
    plan_compliance_notes: str
    error_tags: list[str]
    next_fix: str
    pre_entry_snapshot_svg: str
    pre_entry_snapshot_note: str


class TradeJournalResponse(BaseModel):
    generated_at: datetime
    summary: str
    stats: TradeJournalStats
    entries: list[TradeJournalEntry]


class StrategySignal(BaseModel):
    strategy_id: str
    strategy_name: str
    symbol: str
    action: SignalAction
    confidence: float = Field(ge=0, le=1)
    target_notional: float = Field(ge=0)
    stop_loss_pct: float = Field(gt=0, le=0.5)
    take_profit_pct: float = Field(gt=0, le=3)
    invalidation: str
    reason: str
    data_sources: list[str]
    generated_at: datetime
    instrument_type: str = "spot"
    underlying_symbol: str | None = None
    multiplier: float = 1.0
    option_contract: "OptionContractCandidate | None" = None
    contract_quantity: int | None = None


class OptionContractCandidate(BaseModel):
    ticker: str
    underlying: str
    contract_type: str
    expiration_date: date
    strike: float
    multiplier: float = 100.0
    premium: float
    bid: float
    ask: float
    mid: float
    delta: float
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    implied_volatility: float
    volume: int
    open_interest: int
    dte: int
    score: float
    spread_pct: float = 0.0
    historical_spread_pct: float | None = None
    spread_history_pct: list[float] = Field(default_factory=list)
    quote_timestamp: datetime | None = None
    quote_age_seconds: float | None = None
    last_trade_price: float | None = None
    last_trade_size: int | None = None
    last_trade_timestamp: datetime | None = None
    microstructure_score: float = Field(default=0.0, ge=0, le=1)
    liquidity_score: float = Field(default=0.0, ge=0, le=1)
    slippage_tier: Literal["tight", "normal", "wide", "avoid", "unknown"] = "unknown"
    chain_rank: int = 0
    chain_candidates: int = 0
    moneyness_pct: float | None = None
    theta_daily: float = 0.0
    dte_risk: Literal["normal", "accelerating", "expiration_risk", "expired"] = "normal"
    earnings_risk: Literal["none", "earnings_before_expiration", "earnings_within_7d", "unknown"] = "unknown"
    iv_crush_risk: Literal["low", "medium", "high", "unknown"] = "unknown"
    expected_iv_crush_pct: float = 0.0


class Position(BaseModel):
    symbol: str
    quantity: float
    avg_entry_price: float
    market_price: float
    market_value: float
    unrealized_pnl: float
    stop_loss: float
    take_profit: float
    instrument_type: str = "spot"
    underlying_symbol: str | None = None
    multiplier: float = 1.0
    expiration_date: date | None = None
    strike: float | None = None
    option_type: str | None = None
    delta: float | None = None
    theta: float | None = None
    implied_volatility: float | None = None
    spread_pct: float | None = None
    historical_spread_pct: float | None = None
    spread_history_pct: list[float] = Field(default_factory=list)
    quote_timestamp: datetime | None = None
    quote_age_seconds: float | None = None
    last_trade_price: float | None = None
    last_trade_size: int | None = None
    last_trade_timestamp: datetime | None = None
    microstructure_score: float | None = None
    liquidity_score: float | None = None
    slippage_tier: Literal["tight", "normal", "wide", "avoid", "unknown"] = "unknown"
    entry_bid: float | None = None
    entry_ask: float | None = None
    entry_mid: float | None = None
    entry_limit_price: float | None = None
    entry_fill_probability: float | None = None
    entry_liquidity_gap: bool | None = None
    entry_queue_position_pct: float | None = None
    chain_rank: int | None = None
    chain_candidates: int | None = None
    theta_daily: float | None = None
    dte_risk: Literal["normal", "accelerating", "expiration_risk", "expired"] | None = None
    earnings_risk: Literal["none", "earnings_before_expiration", "earnings_within_7d", "unknown"] | None = None
    iv_crush_risk: Literal["low", "medium", "high", "unknown"] | None = None
    expected_iv_crush_pct: float | None = None


class Trade(BaseModel):
    trade_id: str
    timestamp: datetime
    symbol: str
    side: SignalAction
    quantity: float
    price: float
    notional: float
    fee: float
    slippage: float
    strategy_id: str
    reason: str
    exit_condition: str | None = None
    instrument_type: str = "spot"
    underlying_symbol: str | None = None
    multiplier: float = 1.0
    expiration_date: date | None = None
    strike: float | None = None
    option_type: str | None = None
    delta: float | None = None
    theta: float | None = None
    implied_volatility: float | None = None
    spread_pct: float | None = None
    historical_spread_pct: float | None = None
    spread_history_pct: list[float] = Field(default_factory=list)
    quote_timestamp: datetime | None = None
    quote_age_seconds: float | None = None
    last_trade_price: float | None = None
    last_trade_size: int | None = None
    last_trade_timestamp: datetime | None = None
    microstructure_score: float | None = None
    liquidity_score: float | None = None
    slippage_tier: Literal["tight", "normal", "wide", "avoid", "unknown"] = "unknown"
    bid: float | None = None
    ask: float | None = None
    mid_price: float | None = None
    limit_price: float | None = None
    fill_probability: float | None = None
    liquidity_gap: bool | None = None
    queue_position_pct: float | None = None
    chain_rank: int | None = None
    chain_candidates: int | None = None
    theta_daily: float | None = None
    dte_risk: Literal["normal", "accelerating", "expiration_risk", "expired"] | None = None
    earnings_risk: Literal["none", "earnings_before_expiration", "earnings_within_7d", "unknown"] | None = None
    iv_crush_risk: Literal["low", "medium", "high", "unknown"] | None = None
    expected_iv_crush_pct: float | None = None


class EquityPoint(BaseModel):
    timestamp: datetime
    equity: float


class PortfolioSnapshot(BaseModel):
    timestamp: datetime
    cash: float
    equity: float
    weekly_return_pct: float
    max_drawdown_pct: float
    positions: list[Position]


class StrategyScore(BaseModel):
    strategy_id: str
    name: str
    score: float
    weekly_return_pct: float
    max_drawdown_pct: float
    hit_rate: float
    sample_size: int
    heat_score: float
    reliability_score: float
    explanation: str
    status: str


class StrategyParameterVersion(BaseModel):
    version_id: str
    description: str
    parameters: dict[str, str | float | int | bool]


class StrategyEnvironmentPerformance(BaseModel):
    environment: str
    return_pct: float
    max_drawdown_pct: float
    hit_rate: float
    sample_size: int
    verdict: str


class StrategyBacktestSummary(BaseModel):
    total_return_pct: float
    max_drawdown_pct: float
    hit_rate: float
    sample_size: int
    best_environment: str
    worst_environment: str


class StrategyWalkForwardWindow(BaseModel):
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    train_return_pct: float
    test_return_pct: float
    train_environment: str
    test_environment: str
    passed: bool
    ending_equity: float
    max_drawdown_pct: float
    trades: int
    missed_fills: int


class StrategyWalkForwardSummary(BaseModel):
    windows: int
    pass_rate: float
    train_return_pct: float
    out_of_sample_return_pct: float
    efficiency_ratio: float
    verdict: str
    recent_windows: list[StrategyWalkForwardWindow]


class StrategyVersionComparison(BaseModel):
    current_version: str
    previous_version: str
    current_score: float
    previous_score: float
    delta: float
    verdict: str


class StrategyForwardPerformance(BaseModel):
    trades: int
    closed_round_trips: int
    realized_pnl: float
    win_rate: float
    last_trade_at: datetime | None = None
    forward_weeks: float
    verdict: str


class StrategyLabEntry(BaseModel):
    strategy_id: str
    name: str
    rank: int
    status: str
    score: float
    parameter_version: StrategyParameterVersion
    thesis: str
    live_reason: str
    survival_reason: str
    elimination_reason: str
    risk_notes: list[str]
    data_requirements: list[str]
    forward: StrategyForwardPerformance
    backtest: StrategyBacktestSummary
    environments: list[StrategyEnvironmentPerformance]
    walk_forward: StrategyWalkForwardSummary
    version_comparison: StrategyVersionComparison
    regime_tags: list[str]


class StrategyLabResponse(BaseModel):
    generated_at: datetime
    active_strategy_id: str
    entries: list[StrategyLabEntry]
    research_notes: list[str]


class WeeklyReport(BaseModel):
    generated_at: datetime
    period_start: datetime
    period_end: datetime
    decision: ReviewDecision
    headline: str
    markdown: str
    portfolio: PortfolioSnapshot
    current_strategy: StrategyScore
    candidate_strategies: list[StrategyScore]
    trades: list[Trade]
    forward_pnl: float = 0.0
    forward_hit_rate: float = 0.0
    data_anomalies: list[str] = []
    live_readiness: LiveReadinessGate | None = None


class TranslationRequest(BaseModel):
    texts: list[str] = Field(default_factory=list, max_length=128)
    target: str = "zh-CN"
    source: str | None = None


class TranslationResponse(BaseModel):
    translations: list[str]
    provider: str
    enabled: bool
    warning: str | None = None


class AiRoleAnalysis(BaseModel):
    role: Literal["attack_trader", "risk_officer", "skeptic"]
    display_name: str
    stance: str
    action: Literal["continue", "go_flat", "reduce_size", "switch_strategy", "observe_only"]
    confidence: float = Field(ge=0, le=1)
    thesis: str
    objections: list[str]
    must_watch: list[str]


class AiAnalysisResponse(BaseModel):
    enabled: bool
    generated_at: datetime
    model: str
    analysis: str
    final_action: Literal["continue", "go_flat", "reduce_size", "switch_strategy", "observe_only"] = "observe_only"
    final_verdict: str = ""
    roles: list[AiRoleAnalysis] = []
    can_override_system: bool = True
    warning: str | None = None


class ApiKeyStatus(BaseModel):
    name: str
    label: str
    configured: bool
    required_for: str


class PlayerWorkspace(BaseModel):
    player_id: str
    display_name: str
    workspace_path: str
    config_path: str
    ledger_path: str
    report_path: str
    created_at: datetime
    updated_at: datetime
    onboarding_completed: bool = False
    initial_cash: float = 500.0


class PlayerCreateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    player_id: str | None = Field(default=None, min_length=1, max_length=48)
    initial_cash: float = Field(default=500.0, ge=1, le=1_000_000)


class PlayersResponse(BaseModel):
    active_player_id: str
    players: list[PlayerWorkspace]


class UserConfigStatus(BaseModel):
    player_id: str
    display_name: str
    workspace_path: str
    ledger_path: str
    report_path: str
    onboarding_completed: bool
    player_persona: Literal["beginner", "player", "expert"]
    risk_level: Literal["conservative", "balanced", "aggressive"]
    allow_options: bool
    watch_only_mode: bool
    advanced_unlocked: bool
    paper_initial_cash: float
    max_single_trade_loss_pct: float
    max_daily_loss_pct: float
    max_weekly_loss_pct: float
    max_position_pct: float
    max_order_slippage_pct: float
    live_min_forward_weeks: int
    gemini_model: str
    api_keys: list[ApiKeyStatus]
    external_ready: bool
    blockers: list[str]


class UserConfigUpdate(BaseModel):
    onboarding_completed: bool | None = None
    player_persona: Literal["beginner", "player", "expert"] | None = None
    risk_level: Literal["conservative", "balanced", "aggressive"] | None = None
    allow_options: bool | None = None
    watch_only_mode: bool | None = None
    paper_initial_cash: float | None = Field(default=None, ge=1, le=1_000_000)
    max_single_trade_loss_pct: float | None = Field(default=None, ge=1, le=100)
    max_daily_loss_pct: float | None = Field(default=None, ge=1, le=100)
    max_weekly_loss_pct: float | None = Field(default=None, ge=1, le=100)
    max_position_pct: float | None = Field(default=None, ge=1, le=100)
    max_order_slippage_pct: float | None = Field(default=None, ge=0.1, le=50)
    live_min_forward_weeks: int | None = Field(default=None, ge=1, le=52)
    alpaca_paper_api_key: str | None = None
    alpaca_paper_secret_key: str | None = None
    massive_api_key: str | None = None
    benzinga_api_key: str | None = None
    fmp_api_key: str | None = None
    google_translate_api_key: str | None = None
    gemini_api_key: str | None = None
    gemini_model: str | None = None
    reset_ledger: bool = True


class ExpertAuditItem(BaseModel):
    area: str
    status: str
    severity: str
    finding: str
    recommendation: str


class ExpertAuditResponse(BaseModel):
    generated_at: datetime
    verdict: str
    can_share_with_external_players: bool
    items: list[ExpertAuditItem]
    next_hardening_steps: list[str]


class DashboardPayload(BaseModel):
    portfolio: PortfolioSnapshot
    equity_curve: list[EquityPoint]
    candles: list[Candle]
    trades: list[Trade]
    current_strategy: StrategyScore
    candidate_strategies: list[StrategyScore]
    next_review_at: datetime
    mode: str
    warnings: list[str]
    realism: RealismReport
    ledger_events: list[dict] = []
    order_draft: BrokerOrderDraft | None = None
    live_readiness: LiveReadinessGate | None = None
