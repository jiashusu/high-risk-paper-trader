"use client";

import { useEffect, useState } from "react";
import { Download, FileText, ShieldAlert, TimerReset } from "lucide-react";
import { WeeklyReport, fetchReport, formatPct, formatUsd, getActivePlayerId } from "@/lib/api";
import { cleanDynamicTranslation, translateDecision, useLanguage } from "@/lib/i18n";
import { useTranslatedTexts } from "@/lib/use-translated-texts";

export function ReportClient() {
  const { language, t } = useLanguage();
  const [report, setReport] = useState<WeeklyReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchReport().then(setReport).catch((err) => setError(err instanceof Error ? err.message : t.common.loadingReport));
  }, [t.common.loadingReport]);

  const translated = useTranslatedTexts(
    report ? [report.headline, report.markdown, ...(report.live_readiness?.blockers ?? []), ...report.data_anomalies] : [],
    language,
  );
  const z = (text: string | null | undefined) => cleanDynamicTranslation(text, translated(text), language);
  const copy = getReportCopy(language);

  if (error) return <div className="error">{t.common.apiUnavailable}: {error}</div>;
  if (!report) return <div className="loading">{t.common.loadingReport}</div>;

  const downloadHref = `${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000"}/api/report.md?player_id=${encodeURIComponent(getActivePlayerId())}`;
  const liveGate = report.live_readiness;

  return (
    <>
      <header className="trading-hero report-hero">
        <div className="hero-copy">
          <p className="eyebrow">{t.report.eyebrow} · {copy.forwardOnly}</p>
          <h1>{z(report.headline)}</h1>
          <p className="hero-subcopy">{copy.hero}</p>
          <div className="hero-tape">
            <span>{translateDecision(report.decision, language)}</span>
            <span>{report.trades.length} {copy.trades}</span>
            <span>{formatPct(report.forward_hit_rate * 100)} {copy.hitRate}</span>
            <span>{report.data_anomalies.length} {copy.dataAnomalies}</span>
          </div>
        </div>
        <a className="primary-button hot-button" href={downloadHref} target="_blank" rel="noreferrer">
          <Download size={17} />
          {t.common.markdown}
        </a>
      </header>

      <section className="desk-grid report-stats">
        <div className="panel capital-panel">
          <div className="panel-kicker">{t.dashboard.equity}</div>
          <div className={`mega-number ${report.portfolio.equity >= 500 ? "positive" : "negative"}`}>{formatUsd(report.portfolio.equity)}</div>
          <div className="execution-grid">
            <span>{t.report.weeklyReturn} <strong>{formatPct(report.portfolio.weekly_return_pct)}</strong></span>
            <span>{t.dashboard.maxDrawdown} <strong>{formatPct(-report.portfolio.max_drawdown_pct)}</strong></span>
          </div>
        </div>

        <div className="panel section">
          <h2><ShieldAlert size={18} /> Live Gate</h2>
          <div className="gate-meter">
            <div style={{ width: `${Math.min(100, ((liveGate?.completed_forward_weeks ?? 0) / Math.max(liveGate?.required_forward_weeks ?? 4, 1)) * 100)}%` }} />
          </div>
          <p className="muted">{copy.forwardWeeks(liveGate?.completed_forward_weeks ?? 0, liveGate?.required_forward_weeks ?? 4)}</p>
          <ul className="blocker-list">
            {(liveGate?.blockers.length ? liveGate.blockers.slice(0, 3) : [copy.liveDisabled]).map((blocker) => (
              <li key={blocker}>{z(blocker)}</li>
            ))}
          </ul>
        </div>

        <div className="panel section">
          <h2><TimerReset size={18} /> {copy.weeklyVerdict}</h2>
          <div className="ticket-symbol">{translateDecision(report.decision, language)}</div>
          <p className="muted">{copy.forwardPnl(formatUsd(report.forward_pnl))}</p>
        </div>
      </section>

      <section className="split-layout stack-gap">
        <div className="panel section">
          <h2>
            <FileText size={17} /> {t.report.reportMarkdown}
          </h2>
          <pre className="markdown">{z(report.markdown)}</pre>
        </div>
        <div className="panel section">
          <h2>{copy.checklist}</h2>
          <ul className="status-list">
            <li className="position-item">{t.report.gatePaper}</li>
            <li className="position-item">{t.report.gateFourReports}</li>
            <li className="position-item">{t.report.gateKeys}</li>
            {report.data_anomalies.length ? report.data_anomalies.map((anomaly) => (
              <li className="warning-item" key={anomaly}>{z(anomaly)}</li>
            )) : <li className="position-item">{copy.noAnomaly}</li>}
          </ul>
        </div>
      </section>
    </>
  );
}

function getReportCopy(language: "en" | "zh") {
  if (language === "en") {
    return {
      forwardOnly: "forward ledger only",
      hero: "This report is meant to answer one hard question: should the system keep trading paper, go flat, switch strategy, or prepare a manual live review.",
      trades: "trades",
      hitRate: "hit rate",
      dataAnomalies: "data anomalies",
      forwardWeeks: (done: number, required: number) => `${done}/${required} forward paper weeks completed.`,
      liveDisabled: "Live submission remains disabled until manual approval.",
      weeklyVerdict: "Weekly Verdict",
      forwardPnl: (pnl: string) => `Forward PnL ${pnl}. Historical replay is useful research, but the live gate only respects the paper ledger.`,
      checklist: "Trader Checklist",
      noAnomaly: "No reported data anomaly in this report.",
    };
  }
  return {
    forwardOnly: "只看 forward 模拟账本",
    hero: "这份周报只回答一个硬问题：继续模拟、空仓、切换策略，还是准备进入人工实盘复核。",
    trades: "笔交易",
    hitRate: "命中率",
    dataAnomalies: "个数据异常",
    forwardWeeks: (done: number, required: number) => `已完成 ${done}/${required} 周 forward 模拟。`,
    liveDisabled: "真钱提交仍然关闭，必须人工批准后才可能进入下一阶段。",
    weeklyVerdict: "本周结论",
    forwardPnl: (pnl: string) => `Forward 账本盈亏 ${pnl}。历史回放只能用于研究，真钱门槛只看真实 forward 模拟账本。`,
    checklist: "交易员检查清单",
    noAnomaly: "本周报告没有记录数据异常。",
  };
}
