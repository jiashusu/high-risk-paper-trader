"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { AlertTriangle, Flame, Gauge, Landmark, RefreshCw, ShieldAlert, ShieldCheck, TrendingDown, WalletCards } from "lucide-react";
import { TermExplain } from "@/components/term-explain";
import { fetchRiskCockpit, formatUsd, RiskCockpitResponse, RiskMapItem, RiskStatus } from "@/lib/api";
import { cleanDynamicTranslation, useLanguage } from "@/lib/i18n";
import { useTranslatedTexts } from "@/lib/use-translated-texts";

export function RiskCockpitClient() {
  const { language, t } = useLanguage();
  const [data, setData] = useState<RiskCockpitResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    try {
      setError(null);
      setData(await fetchRiskCockpit());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load risk cockpit.");
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const dynamicTexts = useMemo(() => {
    if (!data) return [];
    return [
      data.plain_language_summary,
      ...data.warnings,
      ...data.metrics.flatMap((metric) => [metric.label, metric.plain_language]),
      ...data.exposures.flatMap((item) => [item.symbol, item.instrument_type, item.plain_language]),
      ...data.risk_map.flatMap((item) => [item.area, item.title, item.plain_language, item.action]),
    ];
  }, [data]);
  const tr = useTranslatedTexts(dynamicTexts, language);
  const z = (text: string | null | undefined) => cleanDynamicTranslation(text, tr(text), language);
  const copy = getRiskCopy(language);

  if (error) return <div className="error">{t.common.apiUnavailable}: {error}. API: 8010.</div>;
  if (!data) return <div className="loading">{copy.loading}</div>;

  const dangerTone = data.danger_level === "danger" ? "negative" : data.danger_level === "watch" ? "warning" : "positive";
  const fuseUsedPct = data.max_weekly_loss_pct > 0 ? Math.min(100, (data.weekly_loss_pct / data.max_weekly_loss_pct) * 100) : 0;
  const cashPct = data.equity > 0 ? (data.cash / data.equity) * 100 : 0;

  return (
    <>
      <section className={`trading-hero risk-hero ${data.danger_level}`}>
        <div className="hero-copy">
          <p className="eyebrow">{copy.eyebrow}</p>
          <h1>{copy.title}</h1>
          <p className="hero-subcopy">{language === "zh" ? data.plain_language_summary : z(data.plain_language_summary)}</p>
          <div className="hero-tape" aria-label="risk cockpit tape">
            <span>{copy.danger}: {copy.status[data.danger_level]}</span>
            <span>{copy.exposure}: {data.position_exposure_pct.toFixed(1)}%</span>
            <span>{copy.openRisk}: {data.open_risk_pct.toFixed(1)}%</span>
            <span>{copy.weeklyFuse}: {data.weekly_loss_pct.toFixed(1)} / {data.max_weekly_loss_pct.toFixed(1)}%</span>
          </div>
        </div>
        <div className="hero-actions trade-actions">
          <button className="icon-button" onClick={() => void load()} disabled={busy} aria-label={copy.refresh} title={copy.refresh}>
            <RefreshCw size={18} />
          </button>
        </div>
      </section>

      <section className="status-ribbon premium-ribbon">
        <RiskPill icon={<Gauge size={16} />} label={copy.accountRisk} value={copy.status[data.danger_level]} tone={dangerTone} />
        <RiskPill icon={<WalletCards size={16} />} label={<TermExplain term="max_loss" label={copy.maxSingleLoss} context={{ maxLoss: data.max_single_trade_loss, accountEquity: data.equity }} compact />} value={formatUsd(data.max_single_trade_loss)} tone={tone(data.max_single_trade_loss / Math.max(data.equity, 1) * 100, 20, 50)} />
        <RiskPill icon={<ShieldAlert size={16} />} label={<TermExplain term="weekly_fuse" label={copy.remainingWeek} context={{ percent: fuseUsedPct }} compact />} value={formatUsd(data.remaining_weekly_loss_amount)} tone={data.weekly_fuse_status === "safe" ? "positive" : data.weekly_fuse_status === "watch" ? "warning" : "negative"} />
        <RiskPill icon={<TrendingDown size={16} />} label={copy.lossStreak} value={String(data.consecutive_losses)} tone={data.consecutive_losses >= 3 ? "negative" : data.consecutive_losses >= 2 ? "warning" : "positive"} />
      </section>

      <section className="risk-command-grid">
        <div className="panel risk-speedometer-panel">
          <div className="panel-kicker">{copy.canLose}</div>
          <div className={`mega-number ${dangerTone}`}>{formatUsd(data.remaining_weekly_loss_amount)}</div>
          <p className="muted">{copy.canLoseHelp}</p>
          <div className="capital-bars">
            <RiskMeter label={<TermExplain term="position_exposure" label={copy.positionExposure} context={{ percent: data.position_exposure_pct }} compact />} value={data.position_exposure_pct} max={100} display={`${data.position_exposure_pct.toFixed(1)}%`} status={data.position_exposure_pct >= 82 ? "danger" : data.position_exposure_pct >= 45 ? "watch" : "safe"} />
            <RiskMeter label={<TermExplain term="risk_to_stop" label={copy.lossToStop} context={{ percent: data.open_risk_pct, accountEquity: data.equity }} compact />} value={data.open_risk_pct} max={100} display={`${data.open_risk_pct.toFixed(1)}%`} status={data.open_risk_pct >= 50 ? "danger" : data.open_risk_pct >= 18 ? "watch" : "safe"} />
            <RiskMeter label={<TermExplain term="weekly_fuse" label={copy.weeklyFuseUsed} context={{ percent: fuseUsedPct }} compact />} value={fuseUsedPct} max={100} display={`${fuseUsedPct.toFixed(0)}%`} status={data.weekly_fuse_status} />
            <RiskMeter label={<TermExplain term="cash_buffer" label={copy.cashBuffer} context={{ percent: cashPct }} compact />} value={cashPct} max={100} display={`${cashPct.toFixed(0)}%`} status={cashPct < 15 ? "danger" : cashPct < 35 ? "watch" : "safe"} reverse />
          </div>
        </div>

        <div className="panel section risk-metric-panel">
          <div className="section-head compact">
            <h2><Landmark size={18} /> {copy.coreNumbers}</h2>
            <span className="badge">{data.metrics.length}</span>
          </div>
          <div className="risk-metric-grid">
            {data.metrics.map((metric) => (
              <div className={`risk-metric-card ${metric.status}`} key={metric.label}>
                <span>{metricCopy(metric.label, language).label}</span>
                <strong>{metric.display_value}</strong>
                <p>{metricCopy(metric.label, language).plain}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="risk-layout stack-gap">
        <div className="panel section">
          <div className="section-head compact">
            <h2><Flame size={18} /> {copy.riskMap}</h2>
            <span className={`badge ${data.danger_level === "danger" ? "badge-danger" : data.danger_level === "watch" ? "badge-warning" : "badge-active"}`}>
              {copy.status[data.danger_level]}
            </span>
          </div>
          <div className="risk-map-grid">
            {data.risk_map.map((item) => (
              <RiskMapCard item={item} data={data} copy={copy} key={item.area} />
            ))}
          </div>
        </div>

        <aside className="panel section">
          <h2><AlertTriangle size={18} /> {copy.whereDanger}</h2>
          <ul className="risk-warning-list">
            {(data.warnings.length ? data.warnings : [copy.noDanger]).slice(0, 8).map((warning) => (
              <li key={warning}>{z(warning)}</li>
            ))}
          </ul>
        </aside>
      </section>

      <section className="panel section stack-gap">
        <div className="section-head compact">
          <h2><WalletCards size={18} /> {copy.exposures}</h2>
          <span className="badge">{data.exposures.length}</span>
        </div>
        {data.exposures.length ? (
          <div className="risk-exposure-grid">
            {data.exposures.map((item) => (
              <div className="risk-exposure-card" key={item.symbol}>
                <div className="row">
                  <strong>{item.symbol}</strong>
                  <span>{item.instrument_type}</span>
                </div>
                <div className="ticket-grid">
                  <span>{copy.value}<strong>{formatUsd(item.market_value)}</strong></span>
                  <span><TermExplain term="position_exposure" label={copy.accountPct} context={{ percent: item.position_pct }} /><strong>{item.position_pct.toFixed(1)}%</strong></span>
                  <span><TermExplain term="risk_to_stop" label={copy.stopRisk} context={{ percent: item.max_loss_pct }} /><strong>{formatUsd(item.max_loss_to_stop)}</strong></span>
                  <span>{copy.stopRiskPct}<strong>{item.max_loss_pct.toFixed(1)}%</strong></span>
                </div>
                <p className="muted">{language === "zh" ? exposurePlain(item) : z(item.plain_language)}</p>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty-state">
            <ShieldCheck size={20} />
            {copy.noPosition}
          </div>
        )}
      </section>
    </>
  );
}

function RiskPill({ icon, label, value, tone }: { icon: ReactNode; label: ReactNode; value: string; tone: "positive" | "warning" | "negative" }) {
  return (
    <div className={`status-pill ${tone}`}>
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function RiskMeter({ label, value, max, display, status, reverse = false }: { label: ReactNode; value: number; max: number; display: string; status: RiskStatus; reverse?: boolean }) {
  const width = Math.min(100, Math.max(0, (value / Math.max(max, 1)) * 100));
  const cls = reverse ? (status === "safe" ? "safe" : status) : status;
  return (
    <div className={`risk-bar ${cls}`}>
      <div className="row">
        <span>{label}</span>
        <strong>{display}</strong>
      </div>
      <div className="bar-track">
        <div style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

function RiskMapCard({ item, data, copy }: { item: RiskMapItem; data: RiskCockpitResponse; copy: ReturnType<typeof getRiskCopy> }) {
  const text = riskMapCopy(item, data, copy.language);
  return (
    <div className={`risk-map-card ${item.severity}`}>
      <div className="row">
        <strong>{text.title}</strong>
        <span>{copy.status[item.severity]}</span>
      </div>
      <p>{text.plain}</p>
      <small>{text.action}</small>
    </div>
  );
}

function tone(value: number, watch: number, danger: number): "positive" | "warning" | "negative" {
  if (value >= danger) return "negative";
  if (value >= watch) return "warning";
  return "positive";
}

function getRiskCopy(language: "en" | "zh") {
  if (language === "zh") {
    return {
      language,
      loading: "正在加载风险驾驶舱...",
      eyebrow: "会不会一下亏光",
      title: "风险驾驶舱",
      refresh: "刷新风险驾驶舱",
      danger: "危险等级",
      exposure: "仓位暴露",
      openRisk: "止损前风险",
      weeklyFuse: "周度熔断",
      accountRisk: "账户风险",
      maxSingleLoss: "最大单笔亏损",
      remainingWeek: "本周还能亏",
      lossStreak: "连续亏损",
      canLose: "本周剩余可亏金额",
      canLoseHelp: "这不是建议亏掉的钱，而是触发周度熔断前还剩多少缓冲。",
      positionExposure: "当前仓位占比",
      lossToStop: "止损前风险暴露",
      weeklyFuseUsed: "周度熔断已用",
      cashBuffer: "现金缓冲",
      coreNumbers: "核心风险数字",
      riskMap: "风险地图",
      whereDanger: "现在危险在哪里",
      noDanger: "当前没有明显红灯。继续保持小仓位、真数据和止损。",
      exposures: "当前持仓风险暴露",
      value: "市值",
      accountPct: "账户占比",
      stopRisk: "止损风险",
      stopRiskPct: "止损占比",
      noPosition: "当前没有持仓，所以没有开放仓位风险。",
      status: { safe: "安全", watch: "盯紧", danger: "危险" } as Record<RiskStatus, string>,
    };
  }
  return {
    language,
    loading: "Loading risk cockpit...",
    eyebrow: "Can I get wiped out?",
    title: "Risk Cockpit",
    refresh: "Refresh risk cockpit",
    danger: "Danger",
    exposure: "Exposure",
    openRisk: "Risk to stop",
    weeklyFuse: "Weekly fuse",
    accountRisk: "Account risk",
    maxSingleLoss: "Max single loss",
    remainingWeek: "Week loss room",
    lossStreak: "Loss streak",
    canLose: "Remaining weekly loss room",
    canLoseHelp: "This is not money to spend. It is the buffer before the weekly fuse should stop risk.",
    positionExposure: "Current position exposure",
    lossToStop: "Risk before stops",
    weeklyFuseUsed: "Weekly fuse used",
    cashBuffer: "Cash buffer",
    coreNumbers: "Core Risk Numbers",
    riskMap: "Risk Map",
    whereDanger: "Where danger is now",
    noDanger: "No obvious red light right now. Keep size small, data real, and stops active.",
    exposures: "Open Position Risk",
    value: "Value",
    accountPct: "Account %",
    stopRisk: "Stop risk",
    stopRiskPct: "Stop %",
    noPosition: "No open position, so there is no open position risk.",
    status: { safe: "Safe", watch: "Watch", danger: "Danger" } as Record<RiskStatus, string>,
  };
}

function metricCopy(label: string, language: "en" | "zh") {
  const en: Record<string, { label: string; plain: string }> = {
    "Max single-trade loss": { label: "Max single-trade loss", plain: "The largest modeled hit if the current draft or biggest position goes wrong." },
    "Current position exposure": { label: "Current position exposure", plain: "How much of the account is currently at risk in open positions." },
    "Remaining daily loss room": { label: "Remaining daily loss room", plain: "Buffer left before the daily fuse should block new risk." },
    "Remaining weekly loss room": { label: "Remaining weekly loss room", plain: "Buffer left before the weekly fuse should force cash mode." },
    "Consecutive losses": { label: "Consecutive losses", plain: "A losing streak means reduce size or pause, not press harder." },
  };
  const zh: Record<string, { label: string; plain: string }> = {
    "Max single-trade loss": { label: "最大单笔亏损", plain: "当前订单草稿或最大持仓出问题时，系统估算的一次最大打击。" },
    "Current position exposure": { label: "当前仓位占比", plain: "账户里有多少资金正在冒险，比例越高，单笔判断错的伤害越大。" },
    "Remaining daily loss room": { label: "今天还能亏多少", plain: "触发日内熔断前还剩多少缓冲。它不是目标，是警戒线。" },
    "Remaining weekly loss room": { label: "本周还能亏多少", plain: "触发周度熔断前还剩多少缓冲。接近 0 就应该停止开新仓。" },
    "Consecutive losses": { label: "连续亏损次数", plain: "连亏不是加仓理由。连亏越多，越应该缩小仓位或暂停。" },
  };
  if (language === "zh") return zh[label] ?? { label, plain: "" };
  return en[label] ?? { label, plain: "" };
}

function riskMapCopy(item: RiskMapItem, data: RiskCockpitResponse, language: "en" | "zh") {
  if (language !== "zh") return { title: item.title, plain: item.plain_language, action: item.action };
  const map: Record<string, { title: string; plain: string; action: string }> = {
    position_size: {
      title: "仓位大小",
      plain: data.exposures.length ? `现在 ${data.position_exposure_pct.toFixed(1)}% 的账户在持仓里。仓位越大，一个错误判断越容易伤到账户。` : "现在没有持仓，所以没有开放仓位风险。",
      action: "接近仓位上限时，先减仓或空仓，不要硬上。",
    },
    stop_loss: {
      title: "止损前风险",
      plain: `如果持仓打到止损，当前模型估算会亏掉账户的 ${data.open_risk_pct.toFixed(1)}%。注意：跳空时止损不一定按理想价成交。`,
      action: "每一笔都必须有止损；财报、事件、低流动性时要更保守。",
    },
    weekly_fuse: {
      title: "周度熔断",
      plain: `本周已亏 ${data.weekly_loss_pct.toFixed(1)}%，周度熔断线是 ${data.max_weekly_loss_pct.toFixed(1)}%。`,
      action: "变黄或变红时，不再开新仓，让系统进入防守。",
    },
    losing_streak: {
      title: "连续亏损",
      plain: `最近连续亏损 ${data.consecutive_losses} 次。小账户最怕亏了以后急着翻本。`,
      action: "连亏 2 次减仓，连亏 3 次暂停，等下一次复盘。",
    },
    options_expiry: {
      title: "期权到期风险",
      plain: data.exposures.some((item) => item.instrument_type === "option") ? "有期权持仓时，越接近到期，theta、价差和流动性都会更狠。" : "当前没有期权持仓。",
      action: "不要把弱势期权拖进到期风险窗口。",
    },
    data_risk: {
      title: "数据风险",
      plain: "如果行情或期权链不真实，所有风险数字都会变得不可靠。",
      action: "真实行情低于 95% 时，不要相信入场信号。",
    },
    single_trade_loss: {
      title: "单笔打击",
      plain: `当前最大单笔打击约为 ${formatUsd(data.max_single_trade_loss)}，占账户 ${(data.max_single_trade_loss / Math.max(data.equity, 1) * 100).toFixed(1)}%。`,
      action: "单笔亏损必须低于上限，必要时换更小的合约。",
    },
  };
  return map[item.area] ?? { title: item.title, plain: item.plain_language, action: item.action };
}

function exposurePlain(item: { instrument_type: string; max_loss_to_stop: number }) {
  if (item.instrument_type === "option") {
    return `这笔期权到止损大约会亏 ${formatUsd(item.max_loss_to_stop)}，但极端情况下可能损失全部权利金。`;
  }
  return `如果价格打到止损，这笔持仓估算会亏 ${formatUsd(item.max_loss_to_stop)}。`;
}
