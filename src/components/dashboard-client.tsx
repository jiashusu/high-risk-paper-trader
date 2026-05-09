"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  Activity,
  CandlestickChart,
  Database,
  FileClock,
  Gauge,
  Lock,
  RadioTower,
  RefreshCw,
  ShieldAlert,
  Target,
  TimerReset,
  WalletCards,
  Zap,
} from "lucide-react";
import { MarketChart } from "@/components/market-chart";
import { OnboardingWizard } from "@/components/onboarding-wizard";
import { TermExplain } from "@/components/term-explain";
import { AiAnalysisResponse, DashboardPayload, UserConfigStatus, fetchAiAnalysis, fetchDashboard, fetchUserConfig, formatPct, formatUsd, resetLedger, simulateWeek } from "@/lib/api";
import { cleanDynamicTranslation, translateWarning, useLanguage } from "@/lib/i18n";
import { useTranslatedTexts } from "@/lib/use-translated-texts";

export function DashboardClient() {
  const { language, t } = useLanguage();
  const [config, setConfig] = useState<UserConfigStatus | null>(null);
  const [data, setData] = useState<DashboardPayload | null>(null);
  const [ai, setAi] = useState<AiAnalysisResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [aiBusy, setAiBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setError(null);
      const nextConfig = await fetchUserConfig();
      setConfig(nextConfig);
      if (!nextConfig.onboarding_completed) {
        setData(null);
        return;
      }
      setData(await fetchDashboard());
    } catch (err) {
      setError(err instanceof Error ? err.message : t.common.loadingDashboard);
    }
  }, [t.common.loadingDashboard]);

  async function runSimulation() {
    setBusy(true);
    try {
      setError(null);
      setData(await simulateWeek());
    } catch (err) {
      setError(err instanceof Error ? err.message : t.common.runWeek);
    } finally {
      setBusy(false);
    }
  }

  async function startFreshLedger() {
    if (!window.confirm(language === "zh" ? "确定把本地模拟账本重置为新的 500 美元账户吗？" : "Reset the local paper ledger to a fresh $500 account?")) return;
    setBusy(true);
    try {
      setError(null);
      await resetLedger();
      setData(await fetchDashboard());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reset failed");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void load();
  }, [load]);

  const health = useMemo(() => {
    if (!data) return { ok: 0, total: 0, weak: 0 };
    const enabled = data.realism.source_statuses.filter((status) => status.enabled);
    const ok = enabled.filter((status) => status.healthy).length;
    return { ok, total: enabled.length, weak: enabled.length - ok };
  }, [data]);

  const dynamicTexts = useMemo(() => {
    if (!data) return [];
    return [
      data.current_strategy.name,
      data.current_strategy.explanation,
      data.realism.execution_model,
      data.realism.slippage_model,
      data.realism.fee_model,
      data.realism.account_source,
      ...(data.order_draft ? [data.order_draft.reason, ...data.order_draft.blocking_reasons] : []),
      ...(data.live_readiness ? [...data.live_readiness.blockers, ...data.live_readiness.criteria.flatMap((criterion) => [criterion.name, criterion.detail])] : []),
      ...data.candidate_strategies.flatMap((strategy) => [strategy.name, strategy.explanation]),
      ...data.trades.flatMap((trade) => [trade.reason, trade.instrument_type ?? ""]),
      ...data.realism.source_statuses.flatMap((status) => [status.name, status.detail]),
      ...data.warnings,
      ...(ai ? [ai.analysis, ai.final_verdict, ...ai.roles.flatMap((role) => [role.display_name, role.stance, role.thesis, ...role.objections, ...role.must_watch])] : []),
      "Forward-only ledger",
      "Historical replay cannot count as proof for live trading.",
      "Limit order draft",
      "Options risk modeled",
      "Multiplier, max loss, slippage, stop, target and expiry exit must stay visible.",
      "Source health traceable",
    ];
  }, [data]);
  const tr = useTranslatedTexts(dynamicTexts, language);
  const z = (text: string | null | undefined) => cleanDynamicTranslation(text, tr(text), language);
  const copy = getDashboardCopy(language);

  const loadAnalysis = useCallback(async () => {
    setAiBusy(true);
    try {
      setAi(await fetchAiAnalysis());
    } finally {
      setAiBusy(false);
    }
  }, []);

  useEffect(() => {
    if (data && !ai && !aiBusy) {
      void loadAnalysis();
    }
  }, [ai, aiBusy, data, loadAnalysis]);

  if (error) return <div className="error">{t.common.apiUnavailable}: {error}. API: 8010.</div>;
  if (config && !config.onboarding_completed) {
    return <OnboardingWizard config={config} onComplete={(nextConfig) => {
      setConfig(nextConfig);
      void load();
    }} />;
  }
  if (!data) return <div className="loading">{t.common.loadingDashboard}</div>;

  const portfolio = data.portfolio;
  const latestSymbol = data.candles.at(-1)?.symbol ?? "Universe";
  const primaryPosition = portfolio.positions[0];
  const draft = data.order_draft;
  const liveGate = data.live_readiness;
  const openRisk = draft?.max_loss ?? primaryPosition?.market_value ?? 0;
  const openRiskPct = portfolio.equity > 0 ? (openRisk / portfolio.equity) * 100 : 0;
  const daysToRiskExit = draft?.expiry_risk_exit_at
    ? Math.ceil((new Date(draft.expiry_risk_exit_at).getTime() - Date.now()) / 86_400_000)
    : primaryPosition?.expiration_date
      ? Math.ceil((new Date(primaryPosition.expiration_date).getTime() - Date.now()) / 86_400_000)
      : null;
  const topStrategies = data.candidate_strategies.slice(0, 5);
  const liveBlockers = liveGate?.blockers ?? [];
  const criticalSources = data.realism.source_statuses.filter((source) =>
    ["massive", "polygon", "benzinga", "fmp", "alpaca"].some((name) => source.name.toLowerCase().includes(name)),
  );
  const criticalHealthy = (criticalSources.length ? criticalSources : data.realism.source_statuses).every((source) => source.healthy);
  const auditChecks = [
    {
      label: "Forward-only ledger",
      ok: data.realism.execution_model.toLowerCase().includes("forward"),
      detail: "Historical replay cannot count as proof for live trading.",
    },
    {
      label: "Limit order draft",
      ok: draft?.order_type === "limit" && draft.live_submission_enabled === false,
      detail: draft ? `${draft.broker} ${draft.account_mode}; live send is locked.` : "No order draft yet.",
    },
    {
      label: "Options risk modeled",
      ok: Boolean(primaryPosition?.multiplier === 100 || draft?.instrument_type === "option"),
      detail: "Multiplier, max loss, slippage, stop, target and expiry exit must stay visible.",
    },
    {
      label: "Source health traceable",
      ok: criticalHealthy && data.realism.real_market_data_pct >= 95,
      detail: `${health.ok}/${health.total} enabled feeds healthy; critical feeds are ${criticalHealthy ? "clean" : "not clean"}.`,
    },
    {
      label: "真钱 gate locked",
      ok: liveGate ? !liveGate.ready_for_live : true,
      detail: liveGate ? `${liveGate.completed_forward_weeks}/${liveGate.required_forward_weeks} forward weeks completed.` : "Paper phase only.",
    },
  ];

  return (
    <>
      <section className="trading-hero">
        <div className="hero-copy">
          <p className="eyebrow">{t.dashboard.eyebrow} · Phase 1 locked</p>
          <h1>{copy.heroTitle}</h1>
          <p className="hero-subcopy">
            {copy.heroSubcopy(z(data.current_strategy.name))}
          </p>
          <div className="hero-tape" aria-label="desk tape">
            <span>{copy.paperMode}</span>
            <span>{health.ok}/{health.total} {copy.feedsOnline}</span>
            <span>{data.trades.length} {copy.ledgerTrades}</span>
            <span>{copy.nextReview} {new Date(data.next_review_at).toLocaleDateString()}</span>
          </div>
        </div>
        <div className="hero-actions trade-actions">
          <button className="icon-button" onClick={() => void load()} aria-label={t.common.refreshDashboard} title={t.common.refreshDashboard}>
            <RefreshCw size={18} />
          </button>
          <button className="primary-button hot-button" onClick={() => void runSimulation()} disabled={busy}>
            <Zap size={17} />
            {busy ? t.common.running : copy.forwardTick}
          </button>
          <button className="icon-button danger-button" onClick={() => void startFreshLedger()} disabled={busy} aria-label="Reset ledger" title="Reset ledger">
            <RefreshCw size={16} />
          </button>
        </div>
      </section>

      <section className="status-ribbon premium-ribbon" aria-label={t.dashboard.realism}>
        <StatusPill icon={<RadioTower size={16} />} label={t.dashboard.realMarketData} value={`${data.realism.real_market_data_pct.toFixed(1)}%`} tone={data.realism.real_market_data_pct >= 95 ? "positive" : "negative"} />
        <StatusPill icon={<ShieldAlert size={16} />} label={t.dashboard.realismScore} value={`${data.realism.score.toFixed(1)}/100`} tone={data.realism.score >= 85 ? "positive" : "warning"} />
        <StatusPill icon={<Database size={16} />} label={t.dashboard.sourceHealth} value={`${health.ok}/${health.total}`} tone={health.weak ? "warning" : "positive"} />
        <StatusPill icon={<Lock size={16} />} label={copy.liveMoney} value={liveGate?.ready_for_live ? copy.ready : copy.locked} tone={liveGate?.ready_for_live ? "warning" : "positive"} />
      </section>

      <section className="desk-grid" aria-label="trader command center">
        <div className="panel capital-panel">
          <div className="panel-kicker">{copy.netLiquidation}</div>
          <div className={`mega-number ${portfolio.equity >= 500 ? "positive" : "negative"}`}>{formatUsd(portfolio.equity)}</div>
          <div className="capital-bars">
            <RiskBar label={copy.cash} value={portfolio.cash} max={Math.max(portfolio.equity, 500)} display={formatUsd(portfolio.cash)} tone="positive" />
            <RiskBar label={<TermExplain term="risk_to_stop" label={copy.openRisk} context={{ percent: openRiskPct, accountEquity: portfolio.equity }} compact />} value={openRisk} max={Math.max(portfolio.equity, 1)} display={`${formatUsd(openRisk)} / ${openRiskPct.toFixed(0)}%`} tone={openRiskPct > 35 ? "warning" : "neutral"} />
            <RiskBar label={<TermExplain term="drawdown" label={copy.drawdown} context={{ percent: portfolio.max_drawdown_pct }} compact />} value={portfolio.max_drawdown_pct} max={50} display={formatPct(-portfolio.max_drawdown_pct)} tone={portfolio.max_drawdown_pct > 20 ? "negative" : "neutral"} />
          </div>
        </div>

        <div className="panel live-gate-panel">
          <div className="section-head compact">
            <div>
              <div className="panel-kicker">真钱前置门槛</div>
              <h2><ShieldAlert size={18} /> {copy.liveGate}</h2>
            </div>
            <span className={liveGate?.ready_for_live ? "badge badge-warning" : "badge badge-active"}>
              {liveGate?.ready_for_live ? copy.manualReview : copy.locked}
            </span>
          </div>
          <div className="gate-meter">
            <div style={{ width: `${Math.min(100, ((liveGate?.completed_forward_weeks ?? 0) / Math.max(liveGate?.required_forward_weeks ?? 4, 1)) * 100)}%` }} />
          </div>
          <p className="muted">
            {copy.forwardWeeks(liveGate?.completed_forward_weeks ?? 0, liveGate?.required_forward_weeks ?? 4)}
          </p>
          <ul className="blocker-list">
            {(liveBlockers.length ? liveBlockers.slice(0, 3) : [copy.liveStillDisabled]).map((blocker) => (
              <li key={blocker}>{z(blocker)}</li>
            ))}
          </ul>
        </div>

        <div className="panel ticket-panel">
          <div className="section-head compact">
            <div>
              <div className="panel-kicker">{copy.nextIdea}</div>
              <h2><FileClock size={18} /> {copy.orderDraft}</h2>
            </div>
            <span className={draft?.paper_trade_allowed ? "badge badge-active" : "badge badge-danger"}>
              {draft?.paper_trade_allowed ? copy.paperOk : copy.blocked}
            </span>
          </div>
          {draft ? (
            <>
              <div className="ticket-symbol">{draft.side.toUpperCase()} {draft.symbol}</div>
              <div className="ticket-grid">
                <span>{copy.limit} <strong>{formatUsd(draft.limit_price)}</strong></span>
                <span><TermExplain term="max_loss" label={copy.maxLoss} context={{ maxLoss: draft.max_loss, accountEquity: portfolio.equity }} /> <strong>{formatUsd(draft.max_loss)}</strong></span>
                <span><TermExplain term="slippage" label={copy.slipCap} context={{ percent: draft.max_slippage_pct }} /> <strong>{draft.max_slippage_pct.toFixed(2)}%</strong></span>
                <span><TermExplain term="dte" label={copy.riskExit} context={{ daysToRiskExit }} /> <strong>{draft.expiry_risk_exit_at ?? "n/a"}</strong></span>
              </div>
              <p className="muted clamp">{z(draft.reason)}</p>
            </>
          ) : (
            <div className="empty-state">{copy.noDraft}</div>
          )}
        </div>
      </section>

      <section className="panel ai-panel stack-gap">
        <div className="section-head compact">
          <div>
            <div className="panel-kicker">{copy.aiKicker}</div>
            <h2><Zap size={18} /> {copy.aiTitle}</h2>
          </div>
          {ai ? <span className={`badge ${actionBadge(ai.final_action)}`}>{actionLabel(ai.final_action, language)}</span> : null}
          <button className="icon-button" onClick={() => void loadAnalysis()} disabled={aiBusy} aria-label={copy.refreshAi} title={copy.refreshAi}>
            <RefreshCw size={16} />
          </button>
        </div>
        {ai ? (
          <div className="ai-tribunal">
            <div className="ai-verdict-card">
              <span>{copy.unifiedVerdict}</span>
              <strong>{z(ai.final_verdict || ai.analysis)}</strong>
              <p>{copy.aiCanObject}</p>
            </div>
            <div className="ai-role-grid">
              {ai.roles.map((role) => (
                <div className={`ai-role-card ${role.role}`} key={role.role}>
                  <div className="row">
                    <strong>{z(role.display_name)}</strong>
                    <span>{actionLabel(role.action, language)} · {(role.confidence * 100).toFixed(0)}%</span>
                  </div>
                  <p>{z(role.stance)}</p>
                  <small>{z(role.thesis)}</small>
                  <div className="ai-mini-list">
                    <b>{copy.objections}</b>
                    {role.objections.slice(0, 2).map((item) => <em key={item}>{z(item)}</em>)}
                  </div>
                  <div className="ai-mini-list">
                    <b>{copy.mustWatch}</b>
                    {role.must_watch.slice(0, 3).map((item) => <em key={item}>{z(item)}</em>)}
                  </div>
                </div>
              ))}
            </div>
            <div className="ai-analysis-text">{z(ai.analysis)}</div>
          </div>
        ) : (
          <div className="ai-analysis-text">{copy.aiLoading}</div>
        )}
        {ai?.warning ? <p className="muted">{copy.aiWarning}: {ai.warning}</p> : null}
      </section>

      <section className="cockpit-grid">
        <div className="panel chart-panel premium-chart">
          <div className="section-head">
            <div>
              <h2><CandlestickChart size={18} /> {latestSymbol} {t.dashboard.signalChart}</h2>
              <p className="muted">{t.dashboard.chartNote}</p>
            </div>
            <span className="badge badge-active">{data.current_strategy.name}</span>
          </div>
          <MarketChart candles={data.candles} trades={data.trades} />
        </div>

        <aside className="panel command-panel trader-rail">
          <h2><WalletCards size={18} /> {copy.positionGreeks}</h2>
          {primaryPosition ? (
            <div className="contract-card">
              <div className="row">
                <strong>{primaryPosition.symbol}</strong>
                <span className={primaryPosition.unrealized_pnl >= 0 ? "positive" : "negative"}>{formatUsd(primaryPosition.unrealized_pnl)}</span>
              </div>
              <p className="muted">{primaryPosition.underlying_symbol ?? primaryPosition.symbol} · {primaryPosition.instrument_type}</p>
              <div className="contract-grid">
                <span>{copy.value} <strong>{formatUsd(primaryPosition.market_value)}</strong></span>
                <span><TermExplain term="stop_loss" label={copy.stop} context={{ position: primaryPosition }} /> <strong>{formatUsd(primaryPosition.stop_loss)}</strong></span>
                <span><TermExplain term="take_profit" label={copy.target} context={{ position: primaryPosition }} /> <strong>{formatUsd(primaryPosition.take_profit)}</strong></span>
                <span><TermExplain term="delta" label="Delta" context={{ position: primaryPosition }} /> <strong>{primaryPosition.delta?.toFixed(2) ?? "n/a"}</strong></span>
                <span><TermExplain term="theta" label="Theta" context={{ position: primaryPosition }} /> <strong>{primaryPosition.theta?.toFixed(3) ?? "n/a"}</strong></span>
                <span><TermExplain term="iv" label="IV" context={{ position: primaryPosition }} /> <strong>{primaryPosition.implied_volatility ? `${(primaryPosition.implied_volatility * 100).toFixed(0)}%` : "n/a"}</strong></span>
                <span><TermExplain term="dte" label="DTE" context={{ position: primaryPosition, daysToRiskExit }} /> <strong>{daysToRiskExit ?? "n/a"}</strong></span>
                <span><TermExplain term="multiplier" label="Multiplier" context={{ position: primaryPosition }} /> <strong>{primaryPosition.multiplier ?? 1}</strong></span>
              </div>
            </div>
          ) : (
            <div className="empty-state">{copy.flatValid}</div>
          )}

          <h2><Target size={18} /> {copy.traderWants}</h2>
          <ul className="audit-list">
            {auditChecks.map((check) => (
              <li className={check.ok ? "audit-pass" : "audit-fail"} key={check.label}>
                <strong>{check.ok ? copy.pass : copy.fix} {z(check.label)}</strong>
                <span>{z(check.detail)}</span>
              </li>
            ))}
          </ul>
        </aside>
      </section>

      <section className="trader-review-grid stack-gap">
        <div className="panel section strategy-deck">
          <div className="section-head compact">
            <h2><Activity size={18} /> {copy.strategyQueue}</h2>
            <span className="badge">{topStrategies.length} {copy.ranked}</span>
          </div>
          <div className="mini-rank-list">
            {topStrategies.map((strategy, index) => (
              <div className="mini-rank" key={strategy.strategy_id}>
                <span className="rank-number">{index + 1}</span>
                <div>
                  <div className="row">
                    <strong>{z(strategy.name)}</strong>
                    <span className={strategy.status === "active" ? "badge badge-active" : "badge"}>{strategy.score}</span>
                  </div>
                  <div className="rank-track"><div style={{ width: `${Math.min(100, strategy.score)}%` }} /></div>
                  <p className="muted">{formatPct(strategy.weekly_return_pct)} {copy.weekly} · {(strategy.hit_rate * 100).toFixed(0)}% {copy.hit} · {(strategy.reliability_score * 100).toFixed(0)}% {copy.reliability}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <PanelList
          icon={<FileClock size={18} />}
          title={copy.forwardLedger}
          items={data.trades.length ? data.trades.slice(-5).reverse().map((trade) => ({
            key: trade.trade_id,
            title: `${trade.side.toUpperCase()} ${trade.symbol}`,
            meta: `${formatUsd(trade.notional)} · ${trade.instrument_type ?? "spot"} · ${new Date(trade.timestamp).toLocaleString()}`,
            body: z(trade.reason),
          })) : [{ key: "empty", title: t.dashboard.noTrades, meta: copy.waitingTick, body: copy.noDuplicate }]}
        />

        <PanelList
          icon={<ShieldAlert size={18} />}
          title={t.dashboard.riskIntegrations}
          items={[
            ...(liveGate ? liveGate.criteria.map((criterion) => ({
              key: criterion.name,
              title: `${criterion.passed ? copy.pass : copy.block} ${z(criterion.name)}`,
              meta: copy.liveGate,
              body: z(criterion.detail),
              tone: criterion.passed ? "normal" as const : "warning" as const,
            })) : []),
            ...data.warnings.map((warning) => ({
              key: warning,
              title: translateWarning(warning, language),
              meta: copy.riskGate,
              body: copy.paperUntilApproved,
              tone: "warning" as const,
            })),
          ]}
        />
      </section>

      <section className="three-column-grid stack-gap">
        <PanelList
          icon={<Database size={18} />}
          title={t.dashboard.sourceHealth}
          items={(criticalSources.length ? criticalSources : data.realism.source_statuses).map((status) => ({
            key: status.name,
            title: `${z(status.name)} · ${status.healthy ? copy.ok : copy.check}`,
            meta: status.symbols_requested ? `${copy.real} ${status.symbols_real}/${status.symbols_requested} · ${copy.fallback} ${status.symbols_fallback}` : copy.sourceCheck,
            body: z(status.detail),
            tone: status.healthy ? "normal" as const : "warning" as const,
          }))}
        />

        <div className="panel section">
          <h2><Gauge size={18} /> {copy.executionReality}</h2>
          <div className="execution-grid">
            <span>{copy.model} <strong>{z(data.realism.execution_model)}</strong></span>
            <span><TermExplain term="slippage" label={copy.slippage} /> <strong>{z(data.realism.slippage_model)}</strong></span>
            <span>{copy.fees} <strong>{z(data.realism.fee_model)}</strong></span>
            <span>{copy.account} <strong>{z(data.realism.account_source)}</strong></span>
          </div>
        </div>

        <div className="panel section">
          <h2><TimerReset size={18} /> {copy.nextActions}</h2>
          <ul className="status-list">
            <li className="position-item"><strong>{copy.actionOneTitle}</strong><p className="muted">{copy.actionOneBody}</p></li>
            <li className="position-item"><strong>{copy.actionTwoTitle}</strong><p className="muted">{copy.actionTwoBody}</p></li>
            <li className="warning-item"><strong>{copy.actionThreeTitle}</strong><p>{copy.actionThreeBody}</p></li>
          </ul>
        </div>
      </section>

      <section className="ledger-strip stack-gap">
        <div className="section-head">
          <h2><FileClock size={18} /> {copy.recentEvents}</h2>
          <span className="badge">{data.ledger_events.length} {copy.events}</span>
        </div>
        <div className="event-row">
          {data.ledger_events.slice(0, 6).map((event) => (
            <div className="event-chip" key={`${event.timestamp}-${event.kind}`}>
              <strong>{event.kind}</strong>
              <span>{new Date(event.timestamp).toLocaleString()}</span>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}

function StatusPill({ icon, label, value, tone }: { icon: ReactNode; label: string; value: string; tone: "positive" | "negative" | "warning" | "neutral" }) {
  return (
    <div className={`status-pill ${tone}`}>
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function RiskBar({ label, value, max, display, tone }: { label: ReactNode; value: number; max: number; display: string; tone: "positive" | "negative" | "warning" | "neutral" }) {
  const width = Math.max(2, Math.min(100, (Math.abs(value) / Math.max(max, 1)) * 100));
  return (
    <div className={`risk-bar ${tone}`}>
      <div className="row">
        <span>{label}</span>
        <strong>{display}</strong>
      </div>
      <div className="bar-track"><div style={{ width: `${width}%` }} /></div>
    </div>
  );
}

function actionLabel(action: string, language: "en" | "zh") {
  const zh: Record<string, string> = {
    continue: "继续",
    go_flat: "空仓",
    reduce_size: "降低仓位",
    switch_strategy: "换策略",
    observe_only: "仅观察",
  };
  const en: Record<string, string> = {
    continue: "Continue",
    go_flat: "Go flat",
    reduce_size: "Reduce size",
    switch_strategy: "Switch strategy",
    observe_only: "Observe only",
  };
  return (language === "zh" ? zh : en)[action] ?? (language === "zh" ? "仅观察" : "Observe only");
}

function actionBadge(action: string) {
  if (action === "continue") return "badge-active";
  if (action === "go_flat" || action === "switch_strategy") return "badge-danger";
  if (action === "reduce_size" || action === "observe_only") return "badge-warning";
  return "";
}

function PanelList({ icon, title, items }: { icon: ReactNode; title: string; items: Array<{ key: string; title: string; meta: string; body: string; tone?: "normal" | "warning" }> }) {
  return (
    <div className="panel section">
      <h2>{icon} {title}</h2>
      <ul className="status-list">
        {items.map((item) => (
          <li className={item.tone === "warning" ? "warning-item" : "position-item"} key={item.key}>
            <div className="row">
              <strong>{item.title}</strong>
              <span className="muted">{item.meta}</span>
            </div>
            <p className="muted">{item.body}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}

function getDashboardCopy(language: "en" | "zh") {
  if (language === "en") {
    return {
      heroTitle: "$500 High-Risk Paper Desk",
      heroSubcopy: (strategy: string) => `${strategy} is steering a real forward ledger. The system can draft orders, but it cannot send live money.`,
      paperMode: "phase 1 paper only",
      feedsOnline: "feeds online",
      ledgerTrades: "ledger trades",
      nextReview: "next review",
      forwardTick: "Forward Tick",
      liveMoney: "Live money",
      ready: "READY",
      locked: "LOCKED",
      netLiquidation: "Net liquidation",
      cash: "Cash",
      openRisk: "Open risk",
      drawdown: "Drawdown",
      liveGate: "Live Gate",
      manualReview: "Manual review",
      forwardWeeks: (done: number, required: number) => `${done}/${required} forward paper weeks. Historical backtest results do not count.`,
      liveStillDisabled: "No live blocker returned, but live submission remains disabled.",
      nextIdea: "Next executable idea",
      orderDraft: "Order Draft",
      paperOk: "Paper OK",
      blocked: "Blocked",
      limit: "Limit",
      maxLoss: "Max loss",
      slipCap: "Slip cap",
      riskExit: "Risk exit",
      noDraft: "No draft. The system should stay flat until signal and data quality are strong enough.",
      aiKicker: "Gemini review",
      aiTitle: "AI Paper-Trade Analysis",
      refreshAi: "Refresh AI analysis",
      aiLoading: "Generating AI analysis...",
      aiWarning: "AI warning",
      unifiedVerdict: "Unified verdict",
      aiCanObject: "The tribunal is allowed to disagree with the system and block the idea.",
      objections: "Objections",
      mustWatch: "Must watch",
      positionGreeks: "Position & Greeks",
      value: "Value",
      stop: "Stop",
      target: "Target",
      flatValid: "Flat is a valid position. No fresh entry unless a forward tick passes liquidity, spread, catalyst and risk checks.",
      traderWants: "Senior Trader Wants",
      pass: "PASS",
      fix: "FIX",
      block: "BLOCK",
      strategyQueue: "Strategy Queue",
      ranked: "ranked",
      weekly: "weekly",
      hit: "hit",
      reliability: "reliability",
      forwardLedger: "Forward Ledger",
      waitingTick: "Waiting for the next valid tick",
      noDuplicate: "The ledger will not duplicate same-day entries.",
      riskGate: "risk gate",
      paperUntilApproved: "Paper-only until the live gate is explicitly approved.",
      ok: "OK",
      check: "CHECK",
      real: "real",
      fallback: "fallback",
      sourceCheck: "source check",
      executionReality: "Execution Reality",
      model: "Model",
      slippage: "Slippage",
      fees: "Fees",
      account: "Account",
      nextActions: "Next Actions",
      actionOneTitle: "1. Forward tick only when watching",
      actionOneBody: "Entries are explicit via the tick button/API, so restarts do not secretly add trades.",
      actionTwoTitle: "2. Review blockers weekly",
      actionTwoBody: "Live money remains blocked until four real paper weeks and clean health checks.",
      actionThreeTitle: "3. Do not override low-liquidity options",
      actionThreeBody: "Wide spread, missing bid/ask or stale feed should mean flat, even if the story looks exciting.",
      recentEvents: "Recent System Events",
      events: "events",
    };
  }
  return {
    heroTitle: "$500 高风险模拟交易台",
    heroSubcopy: (strategy: string) => `当前由「${strategy}」驱动真实 forward 模拟账本。系统可以生成订单草稿，但不能发送真钱订单。`,
    paperMode: "第一阶段仅模拟",
    feedsOnline: "个数据源在线",
    ledgerTrades: "笔账本交易",
    nextReview: "下次复盘",
    forwardTick: "推进模拟",
    liveMoney: "真钱模式",
    ready: "待复核",
    locked: "已锁定",
    netLiquidation: "账户净值",
    cash: "现金",
    openRisk: "当前风险",
    drawdown: "回撤",
    liveGate: "实盘门槛",
    manualReview: "人工复核",
    forwardWeeks: (done: number, required: number) => `已完成 ${done}/${required} 周 forward 模拟。历史回放成绩不算实盘依据。`,
    liveStillDisabled: "没有新的实盘拦截原因，但真钱提交仍然关闭。",
    nextIdea: "下一笔可执行想法",
    orderDraft: "订单草稿",
    paperOk: "模拟可用",
    blocked: "已拦截",
    limit: "限价",
    maxLoss: "最大亏损",
    slipCap: "滑点上限",
    riskExit: "到期风控退出",
    noDraft: "暂无订单草稿。信号和数据质量不够强时，系统应该保持空仓。",
    aiKicker: "Gemini 复盘",
    aiTitle: "AI 模拟盘分析",
    refreshAi: "刷新 AI 分析",
    aiLoading: "正在生成 AI 分析...",
    aiWarning: "AI 提示",
    unifiedVerdict: "统一结论",
    aiCanObject: "三方审判允许反对系统，不是来替当前策略说好话。",
    objections: "反对点",
    mustWatch: "必须盯紧",
    positionGreeks: "持仓与希腊值",
    value: "市值",
    stop: "止损",
    target: "止盈目标",
    flatValid: "空仓也是有效仓位。只有 forward tick 同时通过流动性、价差、催化和风控检查，才允许新开模拟仓。",
    traderWants: "资深交易员检查项",
    pass: "通过",
    fix: "待修",
    block: "拦截",
    strategyQueue: "策略队列",
    ranked: "个已排名",
    weekly: "本周",
    hit: "命中",
    reliability: "可靠性",
    forwardLedger: "Forward 模拟账本",
    waitingTick: "等待下一次有效推进",
    noDuplicate: "同一天重复刷新不会重复开仓。",
    riskGate: "风控门槛",
    paperUntilApproved: "除非明确通过实盘门槛，否则只允许模拟。",
    ok: "正常",
    check: "检查",
    real: "真实",
    fallback: "备用",
    sourceCheck: "数据源检查",
    executionReality: "真实成交模型",
    model: "模型",
    slippage: "滑点",
    fees: "费用",
    account: "账户",
    nextActions: "下一步",
    actionOneTitle: "1. 只在你盯盘时推进模拟",
    actionOneBody: "开仓必须通过按钮/API 主动推进，重启或刷新页面不会偷偷加仓。",
    actionTwoTitle: "2. 每周看一次实盘拦截原因",
    actionTwoBody: "真钱模式至少需要四周真实 forward 模拟和干净的数据/风控记录。",
    actionThreeTitle: "3. 不要强行交易低流动性期权",
    actionThreeBody: "价差太宽、缺 bid/ask、行情过期时，即使故事很诱人也必须空仓。",
    recentEvents: "最近系统事件",
    events: "个事件",
  };
}
