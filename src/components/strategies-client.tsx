"use client";

import { useEffect, useMemo, useState } from "react";
import { Activity, BadgeCheck, Beaker, FileClock, FlaskConical, ShieldAlert, SlidersHorizontal, TrendingUp } from "lucide-react";
import { DashboardPayload, StrategyLabEntry, StrategyLabResponse, fetchDashboard, fetchStrategyLab, formatPct, formatUsd } from "@/lib/api";
import { cleanDynamicTranslation, useLanguage } from "@/lib/i18n";
import { useTranslatedTexts } from "@/lib/use-translated-texts";

export function StrategiesClient() {
  const { language, t } = useLanguage();
  const [data, setData] = useState<DashboardPayload | null>(null);
  const [lab, setLab] = useState<StrategyLabResponse | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([fetchDashboard(), fetchStrategyLab()])
      .then(([dashboardPayload, labPayload]) => {
        setData(dashboardPayload);
        setLab(labPayload);
        setSelectedId(labPayload.active_strategy_id || labPayload.entries[0]?.strategy_id || null);
      })
      .catch((err) => setError(err instanceof Error ? err.message : t.common.loadingStrategies));
  }, [t.common.loadingStrategies]);

  const selected = useMemo(() => lab?.entries.find((entry) => entry.strategy_id === selectedId) ?? lab?.entries[0] ?? null, [lab, selectedId]);
  const activeStrategy = useMemo(() => data?.candidate_strategies.find((strategy) => strategy.status === "active") ?? data?.current_strategy, [data]);
  const dynamicTexts = useMemo(() => {
    if (!lab) return [];
    return lab.entries.flatMap((entry) => [
      entry.name,
      entry.thesis,
      entry.live_reason,
      entry.survival_reason,
      entry.elimination_reason,
      entry.forward.verdict,
      entry.parameter_version.description,
      ...entry.risk_notes,
      ...entry.data_requirements,
      ...entry.environments.flatMap((env) => [env.environment, env.verdict]),
    ]);
  }, [lab]);
  const tr = useTranslatedTexts(dynamicTexts, language);
  const z = (text: string | null | undefined) => {
    if (language === "zh" && text && /[\u3400-\u9fff]/.test(text)) return text;
    return cleanDynamicTranslation(text, tr(text), language);
  };
  const copy = getStrategiesCopy(language);

  if (error) return <div className="error">{t.common.apiUnavailable}: {error}</div>;
  if (!data || !lab || !activeStrategy || !selected) return <div className="loading">{t.common.loadingStrategies}</div>;

  return (
    <>
      <header className="trading-hero strategy-hero">
        <div className="hero-copy">
          <p className="eyebrow">{copy.eyebrow} · {copy.rankBy}</p>
          <h1>{copy.title}</h1>
          <p className="hero-subcopy">{copy.hero}</p>
          <div className="hero-tape">
            <span>{copy.active}: {z(activeStrategy.name)}</span>
            <span>{lab.entries.length} {copy.candidates}</span>
            <span>{copy.forwardOnly}</span>
            <span>{data.live_readiness?.ready_for_live ? copy.liveGateReview : copy.paperLocked}</span>
          </div>
        </div>
        <span className="badge badge-active">
          <FlaskConical size={14} /> {copy.labBadge}
        </span>
      </header>

      <section className="lab-overview-grid">
        <div className="panel section active-strategy-panel">
          <div className="section-head compact">
            <div>
              <div className="panel-kicker">{copy.currentPlaybook}</div>
              <h2><BadgeCheck size={18} /> {z(activeStrategy.name)}</h2>
            </div>
            <span className="badge badge-active">{t.common.score} {activeStrategy.score}</span>
          </div>
          <p className="muted">{z(selected.live_reason)}</p>
          <div className="execution-grid">
            <span>{copy.forwardPnl} <strong>{formatUsd(selected.forward.realized_pnl)}</strong></span>
            <span>{copy.backtestReturn} <strong>{formatPct(selected.backtest.total_return_pct)}</strong></span>
            <span>{copy.bestEnv} <strong>{envLabel(selected.backtest.best_environment, language)}</strong></span>
            <span>{copy.version} <strong>{selected.parameter_version.version_id}</strong></span>
          </div>
        </div>

        <div className="panel section">
          <h2><ShieldAlert size={18} /> {copy.researchNotes}</h2>
          <ul className="status-list">
            {lab.research_notes.map((note) => (
              <li className="position-item" key={note}>{z(note)}</li>
            ))}
          </ul>
        </div>
      </section>

      <section className="lab-layout stack-gap">
        <aside className="panel section lab-list">
          <div className="section-head compact">
            <h2><Beaker size={18} /> {copy.strategyShelf}</h2>
            <span className="badge">{lab.entries.length}</span>
          </div>
          {lab.entries.map((entry) => (
            <button className={entry.strategy_id === selected.strategy_id ? "lab-strategy-card active" : "lab-strategy-card"} type="button" key={entry.strategy_id} onClick={() => setSelectedId(entry.strategy_id)}>
              <span className="rank-number">{entry.rank}</span>
              <div>
                <strong>{z(entry.name)}</strong>
                <small>{statusLabel(entry.status, language)} · {entry.parameter_version.version_id}</small>
              </div>
              <b>{entry.score.toFixed(1)}</b>
            </button>
          ))}
        </aside>

        <div className="panel section lab-detail">
          <div className="section-head compact">
            <div>
              <div className="panel-kicker">{statusLabel(selected.status, language)}</div>
              <h2><Activity size={18} /> {z(selected.name)}</h2>
            </div>
            <span className="badge badge-active">#{selected.rank}</span>
          </div>

          <p className="lab-thesis">{z(selected.thesis)}</p>

          <div className="lab-metric-grid">
            <Metric label={copy.forwardTrades} value={`${selected.forward.trades}`} detail={z(selected.forward.verdict)} />
            <Metric label={copy.closedTrips} value={`${selected.forward.closed_round_trips}`} detail={`${copy.winRate} ${(selected.forward.win_rate * 100).toFixed(0)}%`} />
            <Metric label={copy.backtest} value={formatPct(selected.backtest.total_return_pct)} detail={`${copy.samples} ${selected.backtest.sample_size}`} />
            <Metric label={copy.maxDrawdown} value={formatPct(-selected.backtest.max_drawdown_pct)} detail={`${copy.worstEnv} ${envLabel(selected.backtest.worst_environment, language)}`} />
          </div>

          <section className="lab-reason-grid">
            <ReasonCard title={copy.liveReason} body={z(selected.live_reason)} />
            <ReasonCard title={copy.survivalReason} body={z(selected.survival_reason)} />
            <ReasonCard title={copy.eliminationReason} body={z(selected.elimination_reason)} warning />
          </section>

          <section className="lab-section">
            <h2><TrendingUp size={18} /> {copy.environmentPerformance}</h2>
            <div className="environment-grid">
              {selected.environments.map((env) => (
                <div className="environment-card" key={env.environment}>
                  <div className="row">
                    <strong>{envLabel(env.environment, language)}</strong>
                    <span className={env.return_pct >= 0 ? "positive" : "negative"}>{formatPct(env.return_pct)}</span>
                  </div>
                  <div className="contract-grid">
                    <span>{copy.drawdown} <strong>{formatPct(-env.max_drawdown_pct)}</strong></span>
                    <span>{copy.hit} <strong>{(env.hit_rate * 100).toFixed(0)}%</strong></span>
                    <span>{copy.samples} <strong>{env.sample_size}</strong></span>
                  </div>
                  <p className="muted">{z(env.verdict)}</p>
                </div>
              ))}
            </div>
          </section>

          <section className="split-layout stack-gap">
            <div className="panel-inner">
              <h2><SlidersHorizontal size={18} /> {copy.parameters}</h2>
              <p className="muted">{z(selected.parameter_version.description)}</p>
              <div className="parameter-grid">
                {Object.entries(selected.parameter_version.parameters).map(([key, value]) => (
                  <span key={key}>{key}<strong>{String(value)}</strong></span>
                ))}
              </div>
            </div>
            <div className="panel-inner">
              <h2><FileClock size={18} /> {copy.dataAndRisk}</h2>
              <ul className="status-list">
                {selected.data_requirements.map((item) => <li className="position-item" key={item}>{dataLabel(item, language)}</li>)}
                {selected.risk_notes.map((item) => <li className="warning-item" key={item}>{z(item)}</li>)}
              </ul>
            </div>
          </section>
        </div>
      </section>
    </>
  );
}

function Metric({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="lab-metric">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}

function ReasonCard({ title, body, warning }: { title: string; body: string; warning?: boolean }) {
  return (
    <div className={warning ? "reason-card warning-item" : "reason-card position-item"}>
      <strong>{title}</strong>
      <p>{body}</p>
    </div>
  );
}

function statusLabel(status: string, language: "en" | "zh") {
  const zh: Record<string, string> = {
    active: "当前上线",
    bench: "候选观察",
    rejected: "已淘汰",
    data_watch: "数据观察",
    needs_samples: "样本不足",
  };
  const en: Record<string, string> = {
    active: "active",
    bench: "bench",
    rejected: "rejected",
    data_watch: "data watch",
    needs_samples: "needs samples",
  };
  return (language === "zh" ? zh : en)[status] ?? status;
}

function envLabel(environment: string, language: "en" | "zh") {
  const zh: Record<string, string> = {
    bull_trend: "牛市趋势",
    bear_trend: "熊市趋势",
    high_volatility: "高波动",
    flash_crash: "闪崩",
    range_bound: "震荡",
    unknown: "未知",
  };
  const en: Record<string, string> = {
    bull_trend: "Bull trend",
    bear_trend: "Bear trend",
    high_volatility: "High volatility",
    flash_crash: "Flash crash",
    range_bound: "Range bound",
    unknown: "Unknown",
  };
  return (language === "zh" ? zh : en)[environment] ?? environment;
}

function dataLabel(item: string, language: "en" | "zh") {
  const zh: Record<string, string> = {
    "daily bars": "日线 K 线",
    "news heat": "新闻热度",
    "liquidity score": "流动性评分",
    "daily high/low/close": "日线高低收",
    "range expansion": "波动区间扩张",
    "moving averages": "均线结构",
    "relative strength ranking": "相对强弱排名",
    "range breakout": "区间突破",
    "volatility contraction": "波动率收缩",
    "earnings calendar": "财报日历",
    "mean reversion score": "均值回归评分",
    "risk gates": "风控门槛",
    "source health": "数据源健康",
    "strategy ranking": "策略排名",
  };
  return language === "zh" ? (zh[item] ?? item) : item;
}

function getStrategiesCopy(language: "en" | "zh") {
  if (language === "en") {
    return {
      eyebrow: "Strategy laboratory",
      title: "Strategy Research Lab",
      rankBy: "ranked by survival evidence",
      hero: "A strategy cannot live on score alone. This lab shows forward proof, historical windows, market environments, parameter versions, and the exact reason it survives or gets cut.",
      active: "active",
      candidates: "strategies",
      forwardOnly: "forward proof first",
      liveGateReview: "live gate review",
      paperLocked: "paper locked",
      labBadge: "research mode",
      currentPlaybook: "Current playbook",
      researchNotes: "Research rules",
      strategyShelf: "Strategy shelf",
      forwardPnl: "Forward PnL",
      backtestReturn: "Backtest return",
      bestEnv: "Best environment",
      version: "Version",
      forwardTrades: "Forward trades",
      closedTrips: "Closed trips",
      winRate: "win rate",
      backtest: "Backtest",
      samples: "samples",
      maxDrawdown: "Max DD",
      worstEnv: "worst",
      liveReason: "Why online",
      survivalReason: "Why it survives",
      eliminationReason: "Cut reason",
      environmentPerformance: "Market environment performance",
      drawdown: "DD",
      hit: "Hit",
      parameters: "Parameter version",
      dataAndRisk: "Data + risk requirements",
    };
  }
  return {
    eyebrow: "策略实验室",
    title: "策略研究实验室",
    rankBy: "按生存证据排名",
    hero: "策略不能只靠分数活着。这里看 forward 证明、历史窗口、市场环境、参数版本，以及它为什么上线、为什么留下、为什么被淘汰。",
    active: "当前策略",
    candidates: "个策略",
    forwardOnly: "先看 forward 证据",
    liveGateReview: "实盘门槛待复核",
    paperLocked: "仅模拟已锁定",
    labBadge: "研究模式",
    currentPlaybook: "当前打法",
    researchNotes: "研究规则",
    strategyShelf: "策略货架",
    forwardPnl: "Forward 盈亏",
    backtestReturn: "回测收益",
    bestEnv: "最佳环境",
    version: "参数版本",
    forwardTrades: "Forward 交易",
    closedTrips: "闭环交易",
    winRate: "胜率",
    backtest: "历史回测",
    samples: "样本",
    maxDrawdown: "最大回撤",
    worstEnv: "最差环境",
    liveReason: "为什么上线",
    survivalReason: "为什么还活着",
    eliminationReason: "淘汰原因",
    environmentPerformance: "不同市场环境表现",
    drawdown: "回撤",
    hit: "命中",
    parameters: "参数版本",
    dataAndRisk: "数据和风险要求",
  };
}
