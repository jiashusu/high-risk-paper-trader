export type SignalAction = "buy" | "sell" | "hold" | "flat";

export type Candle = {
  symbol: string;
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  source: string;
  synthetic: boolean;
};

export type DataSourceStatus = {
  name: string;
  enabled: boolean;
  healthy: boolean;
  detail: string;
  symbols_requested: number;
  symbols_real: number;
  symbols_fallback: number;
  latest_timestamp?: string | null;
};

export type GateCriterion = {
  name: string;
  passed: boolean;
  detail: string;
};

export type LiveReadinessGate = {
  ready_for_live: boolean;
  required_forward_weeks: number;
  completed_forward_weeks: number;
  can_create_order_draft: boolean;
  blockers: string[];
  criteria: GateCriterion[];
};

export type BrokerOrderDraft = {
  draft_id: string;
  created_at: string;
  broker: string;
  account_mode: string;
  live_submission_enabled: boolean;
  symbol: string;
  underlying_symbol?: string | null;
  instrument_type: string;
  side: SignalAction;
  quantity: number;
  order_type: string;
  limit_price: number;
  estimated_notional: number;
  estimated_fee: number;
  max_loss: number;
  max_slippage_pct: number;
  position_cap_pct: number;
  time_in_force: string;
  expiry_risk_exit_at?: string | null;
  strategy_id: string;
  reason: string;
  checks: GateCriterion[];
  blocking_reasons: string[];
  paper_trade_allowed: boolean;
};

export type Trade = {
  trade_id: string;
  timestamp: string;
  symbol: string;
  side: SignalAction;
  quantity: number;
  price: number;
  notional: number;
  fee: number;
  slippage: number;
  strategy_id: string;
  reason: string;
  exit_condition?: string | null;
  instrument_type?: string;
  underlying_symbol?: string | null;
  multiplier?: number;
  expiration_date?: string | null;
  strike?: number | null;
  option_type?: string | null;
  delta?: number | null;
  theta?: number | null;
  implied_volatility?: number | null;
};

export type Position = {
  symbol: string;
  quantity: number;
  avg_entry_price: number;
  market_price: number;
  market_value: number;
  unrealized_pnl: number;
  stop_loss: number;
  take_profit: number;
  instrument_type?: string;
  underlying_symbol?: string | null;
  multiplier?: number;
  expiration_date?: string | null;
  strike?: number | null;
  option_type?: string | null;
  delta?: number | null;
  theta?: number | null;
  implied_volatility?: number | null;
};

export type PortfolioSnapshot = {
  timestamp: string;
  cash: number;
  equity: number;
  weekly_return_pct: number;
  max_drawdown_pct: number;
  positions: Position[];
};

export type EquityPoint = {
  timestamp: string;
  equity: number;
};

export type StrategyScore = {
  strategy_id: string;
  name: string;
  score: number;
  weekly_return_pct: number;
  max_drawdown_pct: number;
  hit_rate: number;
  sample_size: number;
  heat_score: number;
  reliability_score: number;
  explanation: string;
  status: string;
};

export type StrategyEnvironmentPerformance = {
  environment: string;
  return_pct: number;
  max_drawdown_pct: number;
  hit_rate: number;
  sample_size: number;
  verdict: string;
};

export type StrategyBacktestSummary = {
  total_return_pct: number;
  max_drawdown_pct: number;
  hit_rate: number;
  sample_size: number;
  best_environment: string;
  worst_environment: string;
};

export type StrategyForwardPerformance = {
  trades: number;
  closed_round_trips: number;
  realized_pnl: number;
  win_rate: number;
  last_trade_at?: string | null;
  forward_weeks: number;
  verdict: string;
};

export type StrategyParameterVersion = {
  version_id: string;
  description: string;
  parameters: Record<string, string | number | boolean>;
};

export type StrategyLabEntry = {
  strategy_id: string;
  name: string;
  rank: number;
  status: string;
  score: number;
  parameter_version: StrategyParameterVersion;
  thesis: string;
  live_reason: string;
  survival_reason: string;
  elimination_reason: string;
  risk_notes: string[];
  data_requirements: string[];
  forward: StrategyForwardPerformance;
  backtest: StrategyBacktestSummary;
  environments: StrategyEnvironmentPerformance[];
};

export type StrategyLabResponse = {
  generated_at: string;
  active_strategy_id: string;
  entries: StrategyLabEntry[];
  research_notes: string[];
};

export type RealismReport = {
  score: number;
  real_market_data_pct: number;
  data_points: number;
  synthetic_symbols: string[];
  execution_model: string;
  slippage_model: string;
  fee_model: string;
  account_source: string;
  source_statuses: DataSourceStatus[];
};

export type DataTimestampCheck = {
  label: string;
  symbol?: string | null;
  source: string;
  latest_timestamp?: string | null;
  age_minutes?: number | null;
  healthy: boolean;
  detail: string;
};

export type PriceDeviationCheck = {
  symbol: string;
  primary_source: string;
  comparison_source: string;
  primary_price?: number | null;
  comparison_price?: number | null;
  diff_pct?: number | null;
  healthy: boolean;
  detail: string;
};

export type DecisionDataInput = {
  category: string;
  label: string;
  source: string;
  value: string;
  impact: string;
};

export type DataCredibilityResponse = {
  generated_at: string;
  score: number;
  verdict: "tradable" | "watch" | "blocked" | string;
  plain_language_summary: string;
  market_timestamps: DataTimestampCheck[];
  price_deviations: PriceDeviationCheck[];
  news_sources: DataSourceStatus[];
  earnings_sources: DataSourceStatus[];
  options_chain_sources: DataSourceStatus[];
  source_statuses: DataSourceStatus[];
  decision_inputs: DecisionDataInput[];
  warnings: string[];
};

export type RiskStatus = "safe" | "watch" | "danger";

export type RiskCockpitMetric = {
  label: string;
  value: number;
  display_value: string;
  status: RiskStatus;
  plain_language: string;
};

export type RiskExposureItem = {
  symbol: string;
  instrument_type: string;
  market_value: number;
  position_pct: number;
  max_loss_to_stop: number;
  max_loss_pct: number;
  plain_language: string;
};

export type RiskMapItem = {
  area: string;
  severity: RiskStatus;
  title: string;
  plain_language: string;
  action: string;
};

export type RiskCockpitResponse = {
  generated_at: string;
  equity: number;
  cash: number;
  total_position_value: number;
  position_exposure_pct: number;
  max_single_trade_loss: number;
  open_risk_amount: number;
  open_risk_pct: number;
  remaining_daily_loss_amount: number;
  remaining_weekly_loss_amount: number;
  consecutive_losses: number;
  daily_loss_pct: number;
  weekly_loss_pct: number;
  max_daily_loss_pct: number;
  max_weekly_loss_pct: number;
  weekly_fuse_status: RiskStatus;
  danger_level: RiskStatus;
  plain_language_summary: string;
  metrics: RiskCockpitMetric[];
  exposures: RiskExposureItem[];
  risk_map: RiskMapItem[];
  warnings: string[];
};

export type TradeJournalStats = {
  total_entries: number;
  closed_entries: number;
  open_entries: number;
  wins: number;
  losses: number;
  plan_follow_rate: number;
  most_common_error_tags: string[];
};

export type TradeJournalEntry = {
  journal_id: string;
  entry_trade_id: string;
  exit_trade_id?: string | null;
  symbol: string;
  instrument_type: string;
  side: SignalAction;
  status: "open" | "closed";
  entry_at: string;
  exit_at?: string | null;
  quantity: number;
  entry_price: number;
  exit_price?: number | null;
  entry_notional: number;
  exit_notional?: number | null;
  realized_pnl?: number | null;
  realized_pnl_pct?: number | null;
  planned_risk: string;
  entry_reason: string;
  exit_condition: string;
  actual_result: string;
  followed_plan: boolean;
  plan_compliance_notes: string;
  error_tags: string[];
  next_fix: string;
  pre_entry_snapshot_svg: string;
  pre_entry_snapshot_note: string;
};

export type TradeJournalResponse = {
  generated_at: string;
  summary: string;
  stats: TradeJournalStats;
  entries: TradeJournalEntry[];
};

export type DashboardPayload = {
  portfolio: PortfolioSnapshot;
  equity_curve: EquityPoint[];
  candles: Candle[];
  trades: Trade[];
  current_strategy: StrategyScore;
  candidate_strategies: StrategyScore[];
  next_review_at: string;
  mode: string;
  warnings: string[];
  realism: RealismReport;
  ledger_events: Array<{ timestamp: string; kind: string; payload: Record<string, unknown> }>;
  order_draft?: BrokerOrderDraft | null;
  live_readiness?: LiveReadinessGate | null;
};

export type WeeklyReport = {
  generated_at: string;
  period_start: string;
  period_end: string;
  decision: "continue" | "switch_strategy" | "go_flat" | "ready_for_manual_live";
  headline: string;
  markdown: string;
  portfolio: PortfolioSnapshot;
  current_strategy: StrategyScore;
  candidate_strategies: StrategyScore[];
  trades: Trade[];
  forward_pnl: number;
  forward_hit_rate: number;
  data_anomalies: string[];
  live_readiness?: LiveReadinessGate | null;
};

export type TranslationResponse = {
  translations: string[];
  provider: string;
  enabled: boolean;
  warning?: string | null;
};

export type AiAnalysisResponse = {
  enabled: boolean;
  generated_at: string;
  model: string;
  analysis: string;
  final_action: "continue" | "go_flat" | "reduce_size" | "switch_strategy" | "observe_only";
  final_verdict: string;
  roles: Array<{
    role: "attack_trader" | "risk_officer" | "skeptic";
    display_name: string;
    stance: string;
    action: "continue" | "go_flat" | "reduce_size" | "switch_strategy" | "observe_only";
    confidence: number;
    thesis: string;
    objections: string[];
    must_watch: string[];
  }>;
  can_override_system: boolean;
  warning?: string | null;
};

export type ApiKeyStatus = {
  name: string;
  label: string;
  configured: boolean;
  required_for: string;
};

export type PlayerWorkspace = {
  player_id: string;
  display_name: string;
  workspace_path: string;
  config_path: string;
  ledger_path: string;
  report_path: string;
  created_at: string;
  updated_at: string;
  onboarding_completed: boolean;
  initial_cash: number;
};

export type PlayersResponse = {
  active_player_id: string;
  players: PlayerWorkspace[];
};

export type UserConfigStatus = {
  player_id: string;
  display_name: string;
  workspace_path: string;
  ledger_path: string;
  report_path: string;
  onboarding_completed: boolean;
  player_persona: "beginner" | "player" | "expert";
  risk_level: "conservative" | "balanced" | "aggressive";
  allow_options: boolean;
  watch_only_mode: boolean;
  advanced_unlocked: boolean;
  paper_initial_cash: number;
  max_single_trade_loss_pct: number;
  max_daily_loss_pct: number;
  max_weekly_loss_pct: number;
  max_position_pct: number;
  max_order_slippage_pct: number;
  live_min_forward_weeks: number;
  gemini_model: string;
  api_keys: ApiKeyStatus[];
  external_ready: boolean;
  blockers: string[];
};

export type UserConfigUpdate = Partial<{
  onboarding_completed: boolean;
  player_persona: "beginner" | "player" | "expert";
  risk_level: "conservative" | "balanced" | "aggressive";
  allow_options: boolean;
  watch_only_mode: boolean;
  paper_initial_cash: number;
  max_single_trade_loss_pct: number;
  max_daily_loss_pct: number;
  max_weekly_loss_pct: number;
  max_position_pct: number;
  max_order_slippage_pct: number;
  live_min_forward_weeks: number;
  alpaca_paper_api_key: string;
  alpaca_paper_secret_key: string;
  massive_api_key: string;
  benzinga_api_key: string;
  fmp_api_key: string;
  google_translate_api_key: string;
  gemini_api_key: string;
  gemini_model: string;
  reset_ledger: boolean;
}>;

export type ExpertAuditResponse = {
  generated_at: string;
  verdict: string;
  can_share_with_external_players: boolean;
  items: Array<{ area: string; status: string; severity: string; finding: string; recommendation: string }>;
  next_hardening_steps: string[];
};

const PLAYER_STORAGE_KEY = "high-risk-paper-trader-player";

function apiBase() {
  if (process.env.NEXT_PUBLIC_API_BASE_URL !== undefined) return process.env.NEXT_PUBLIC_API_BASE_URL;
  if (typeof window !== "undefined" && ["localhost", "127.0.0.1"].includes(window.location.hostname)) {
    return "http://127.0.0.1:8010";
  }
  return "";
}

export function getActivePlayerId() {
  if (typeof window === "undefined") return "owner";
  return window.localStorage.getItem(PLAYER_STORAGE_KEY) || "owner";
}

export function setActivePlayerId(playerId: string) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(PLAYER_STORAGE_KEY, playerId);
  window.dispatchEvent(new CustomEvent("paper-trader-player-change", { detail: playerId }));
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const playerId = getActivePlayerId();
  const response = await fetch(`${apiBase()}${path}`, {
    ...init,
    cache: "no-store",
    headers: { "Content-Type": "application/json", "X-Player-Id": playerId, ...(init?.headers ?? {}) },
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export function fetchDashboard() {
  return apiFetch<DashboardPayload>("/api/dashboard");
}

export function simulateWeek() {
  return apiFetch<DashboardPayload>("/api/ledger/tick", { method: "POST" });
}

export function resetLedger() {
  return apiFetch<{ status: string; mode: string; player_id: string }>("/api/ledger/reset", { method: "POST" });
}

export function fetchReport() {
  return apiFetch<WeeklyReport>("/api/report");
}

export function fetchStrategyLab() {
  return apiFetch<StrategyLabResponse>("/api/strategy-lab");
}

export function fetchDataCredibility() {
  return apiFetch<DataCredibilityResponse>("/api/data-credibility");
}

export function fetchRiskCockpit() {
  return apiFetch<RiskCockpitResponse>("/api/risk-cockpit");
}

export function fetchTradeJournal() {
  return apiFetch<TradeJournalResponse>("/api/trade-journal");
}

export function translateTexts(texts: string[], target = "zh-CN", source = "en") {
  return apiFetch<TranslationResponse>("/api/translate", {
    method: "POST",
    body: JSON.stringify({ texts, target, source }),
  });
}

export function fetchAiAnalysis() {
  return apiFetch<AiAnalysisResponse>("/api/ai-analysis");
}

export function fetchUserConfig() {
  return apiFetch<UserConfigStatus>("/api/user-config");
}

export function saveUserConfig(update: UserConfigUpdate) {
  return apiFetch<UserConfigStatus>("/api/user-config", { method: "POST", body: JSON.stringify(update) });
}

export function fetchExpertAudit() {
  return apiFetch<ExpertAuditResponse>("/api/expert-audit");
}

export function fetchPlayers() {
  return apiFetch<PlayersResponse>(`/api/players?player_id=${encodeURIComponent(getActivePlayerId())}`);
}

export function createPlayer(display_name: string, initial_cash = 500, player_id?: string) {
  return apiFetch<PlayerWorkspace>("/api/players", {
    method: "POST",
    body: JSON.stringify({ display_name, initial_cash, player_id }),
  });
}

export function formatUsd(value: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(value);
}

export function formatPct(value: number) {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}
