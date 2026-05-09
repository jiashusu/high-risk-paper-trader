"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { BookOpenCheck, CheckCircle2, RefreshCw, Tag, Target, XCircle } from "lucide-react";
import { TermExplain } from "@/components/term-explain";
import { fetchTradeJournal, formatPct, formatUsd, TradeJournalEntry, TradeJournalResponse } from "@/lib/api";
import { cleanDynamicTranslation, useLanguage } from "@/lib/i18n";
import { useTranslatedTexts } from "@/lib/use-translated-texts";

export function TradeJournalClient() {
  const { language, t } = useLanguage();
  const [journal, setJournal] = useState<TradeJournalResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    try {
      setError(null);
      setJournal(await fetchTradeJournal());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load trade journal.");
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const dynamicTexts = useMemo(() => {
    if (!journal) return [];
    return [
      journal.summary,
      ...journal.stats.most_common_error_tags,
      ...journal.entries.flatMap((entry) => [
        entry.symbol,
        entry.planned_risk,
        entry.entry_reason,
        entry.exit_condition,
        entry.actual_result,
        entry.plan_compliance_notes,
        entry.next_fix,
        entry.pre_entry_snapshot_note,
        ...entry.error_tags,
      ]),
    ];
  }, [journal]);
  const tr = useTranslatedTexts(dynamicTexts, language);
  const z = (text: string | null | undefined) => cleanDynamicTranslation(text, tr(text), language);
  const copy = getJournalCopy(language);

  if (error) return <div className="error">{t.common.apiUnavailable}: {error}. API: 8010.</div>;
  if (!journal) return <div className="loading">{copy.loading}</div>;

  return (
    <>
      <section className="trading-hero journal-hero">
        <div className="hero-copy">
          <p className="eyebrow">{copy.eyebrow}</p>
          <h1>{copy.title}</h1>
          <p className="hero-subcopy">{z(journal.summary)}</p>
          <div className="hero-tape">
            <span>{journal.stats.total_entries} {copy.entries}</span>
            <span>{journal.stats.closed_entries} {copy.closed}</span>
            <span>{formatPct(journal.stats.plan_follow_rate * 100)} <TermExplain term="plan_follow_rate" label={copy.planRate} context={{ percent: journal.stats.plan_follow_rate * 100 }} compact /></span>
            <span>{journal.stats.most_common_error_tags[0] ?? copy.noMainError}</span>
          </div>
        </div>
        <button className="icon-button" onClick={() => void load()} disabled={busy} aria-label={copy.refresh} title={copy.refresh}>
          <RefreshCw size={18} />
        </button>
      </section>

      <section className="status-ribbon premium-ribbon">
        <JournalPill label={copy.totalEntries} value={String(journal.stats.total_entries)} tone="positive" />
        <JournalPill label={copy.winLoss} value={`${journal.stats.wins}/${journal.stats.losses}`} tone={journal.stats.losses > journal.stats.wins ? "warning" : "positive"} />
        <JournalPill label={copy.openTrades} value={String(journal.stats.open_entries)} tone={journal.stats.open_entries ? "warning" : "positive"} />
        <JournalPill label={<TermExplain term="plan_follow_rate" label={copy.planFollow} context={{ percent: journal.stats.plan_follow_rate * 100 }} compact />} value={`${(journal.stats.plan_follow_rate * 100).toFixed(0)}%`} tone={journal.stats.plan_follow_rate >= 0.8 ? "positive" : "warning"} />
      </section>

      <section className="panel section">
        <div className="section-head compact">
          <h2><Tag size={18} /> {copy.errorTags}</h2>
          <span className="badge">{journal.stats.most_common_error_tags.length}</span>
        </div>
        <div className="tag-cloud">
          {(journal.stats.most_common_error_tags.length ? journal.stats.most_common_error_tags : [copy.noMainError]).map((tag) => (
            <span key={tag}>{z(tag)}</span>
          ))}
        </div>
      </section>

      <section className="journal-list stack-gap">
        {journal.entries.length ? journal.entries.map((entry) => (
          <TradeJournalCard entry={entry} z={z} copy={copy} key={entry.journal_id} />
        )) : (
          <div className="panel section empty-journal">
            <BookOpenCheck size={26} />
            <h2>{copy.emptyTitle}</h2>
            <p className="muted">{copy.emptyBody}</p>
          </div>
        )}
      </section>
    </>
  );
}

function JournalPill({ label, value, tone }: { label: ReactNode; value: string; tone: "positive" | "warning" | "negative" }) {
  return (
    <div className={`status-pill ${tone}`}>
      <BookOpenCheck size={16} />
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function TradeJournalCard({ entry, z, copy }: { entry: TradeJournalEntry; z: (text: string | null | undefined) => string; copy: ReturnType<typeof getJournalCopy> }) {
  const svgSrc = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(entry.pre_entry_snapshot_svg)}`;
  const pnlTone = (entry.realized_pnl ?? 0) > 0 ? "positive" : (entry.realized_pnl ?? 0) < 0 ? "negative" : "muted";
  return (
    <article className="panel journal-card">
      <div className="journal-card-head">
        <div>
          <div className="panel-kicker">{entry.status === "closed" ? copy.closedTrade : copy.openTrade}</div>
          <h2>{entry.symbol} · {entry.instrument_type}</h2>
        </div>
        <span className={entry.followed_plan ? "badge badge-active" : "badge badge-danger"}>
          {entry.followed_plan ? copy.followed : copy.brokePlan}
        </span>
      </div>
      <div className="journal-card-grid">
        <div className="journal-snapshot">
          <img src={svgSrc} alt={`${entry.symbol} pre-entry chart snapshot`} />
          <p>{z(entry.pre_entry_snapshot_note)}</p>
        </div>
        <div className="journal-detail-grid">
          <InfoBox title={copy.entryReason} body={z(entry.entry_reason)} />
          <InfoBox title={<TermExplain term="stop_loss" label={copy.exitCondition} />} body={z(entry.exit_condition)} />
          <InfoBox title={<TermExplain term="planned_risk" label={copy.plannedRisk} />} body={z(entry.planned_risk)} />
          <InfoBox title={<TermExplain term="actual_result" label={copy.actualResult} />} body={z(entry.actual_result)} accent={pnlTone} />
          <InfoBox title={copy.planCheck} body={z(entry.plan_compliance_notes)} icon={entry.followed_plan ? <CheckCircle2 size={16} /> : <XCircle size={16} />} />
          <InfoBox title={copy.nextFix} body={z(entry.next_fix)} icon={<Target size={16} />} />
        </div>
      </div>
      <div className="journal-footer">
        <div className="ticket-grid">
          <span>{copy.entry}<strong>{formatUsd(entry.entry_price)} · {new Date(entry.entry_at).toLocaleString()}</strong></span>
          <span>{copy.exit}<strong>{entry.exit_price == null ? "n/a" : `${formatUsd(entry.exit_price)} · ${entry.exit_at ? new Date(entry.exit_at).toLocaleString() : ""}`}</strong></span>
          <span>{copy.pnl}<strong className={pnlTone}>{entry.realized_pnl == null ? "open" : `${formatUsd(entry.realized_pnl)} / ${entry.realized_pnl_pct?.toFixed(2)}%`}</strong></span>
          <span>{copy.quantity}<strong>{entry.quantity}</strong></span>
        </div>
        <div className="journal-tags">
          {entry.error_tags.map((tag) => <span key={tag}>{z(tag)}</span>)}
        </div>
      </div>
    </article>
  );
}

function InfoBox({ title, body, accent, icon }: { title: ReactNode; body: string; accent?: string; icon?: ReactNode }) {
  return (
    <div className="journal-info-box">
      <strong>{icon}{title}</strong>
      <p className={accent ?? ""}>{body}</p>
    </div>
  );
}

function getJournalCopy(language: "en" | "zh") {
  if (language === "zh") {
    return {
      loading: "正在加载交易日记...",
      eyebrow: "长期纠错能力",
      title: "交易日志与复盘系统",
      refresh: "刷新交易日记",
      entries: "笔入场",
      closed: "笔已平仓",
      planRate: "计划遵守率",
      noMainError: "暂无主要错误",
      totalEntries: "总入场",
      winLoss: "胜/负",
      openTrades: "未平仓",
      planFollow: "遵守计划",
      errorTags: "错误标签排行榜",
      emptyTitle: "还没有交易可复盘",
      emptyBody: "等 forward ledger 产生真实模拟入场后，这里会自动生成入场前图、理由、结果和错误标签。",
      closedTrade: "已完成复盘",
      openTrade: "进行中",
      followed: "遵守计划",
      brokePlan: "计划问题",
      entryReason: "入场理由",
      exitCondition: "退出条件",
      plannedRisk: "计划风险",
      actualResult: "实际结果",
      planCheck: "是否遵守计划",
      nextFix: "下次修正",
      entry: "入场",
      exit: "退出",
      pnl: "结果",
      quantity: "数量",
    };
  }
  return {
    loading: "Loading trade journal...",
    eyebrow: "Long-term correction loop",
    title: "Trade Journal & Review",
    refresh: "Refresh trade journal",
    entries: "entries",
    closed: "closed",
    planRate: "plan follow rate",
    noMainError: "No main error yet",
    totalEntries: "Total entries",
    winLoss: "Win/loss",
    openTrades: "Open trades",
    planFollow: "Plan follow",
    errorTags: "Error Tag Leaderboard",
    emptyTitle: "No trades to review yet",
    emptyBody: "Once the forward ledger creates real paper entries, this page will generate pre-entry charts, reasons, results, and error tags.",
    closedTrade: "Closed review",
    openTrade: "Open trade",
    followed: "Followed plan",
    brokePlan: "Plan issue",
    entryReason: "Entry reason",
    exitCondition: "Exit condition",
    plannedRisk: "Planned risk",
    actualResult: "Actual result",
    planCheck: "Plan compliance",
    nextFix: "Next correction",
    entry: "Entry",
    exit: "Exit",
    pnl: "Result",
    quantity: "Quantity",
  };
}
