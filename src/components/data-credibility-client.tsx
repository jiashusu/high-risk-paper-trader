"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  AlertTriangle,
  BadgeCheck,
  Clock3,
  DatabaseZap,
  FileWarning,
  LineChart,
  Newspaper,
  Radar,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { DataCredibilityResponse, DataSourceStatus, fetchDataCredibility } from "@/lib/api";
import { cleanDynamicTranslation, useLanguage } from "@/lib/i18n";
import { useTranslatedTexts } from "@/lib/use-translated-texts";

export function DataCredibilityClient() {
  const { language, t } = useLanguage();
  const [data, setData] = useState<DataCredibilityResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    try {
      setError(null);
      setData(await fetchDataCredibility());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data credibility.");
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
      ...data.market_timestamps.flatMap((item) => [item.label, item.source, item.detail]),
      ...data.price_deviations.flatMap((item) => [item.symbol, item.primary_source, item.comparison_source, item.detail]),
      ...data.news_sources.flatMap((item) => [item.name, item.detail]),
      ...data.earnings_sources.flatMap((item) => [item.name, item.detail]),
      ...data.options_chain_sources.flatMap((item) => [item.name, item.detail]),
      ...data.decision_inputs.flatMap((item) => [item.category, item.label, item.source, item.value, item.impact]),
      ...data.source_statuses.flatMap((item) => [item.name, item.detail]),
    ];
  }, [data]);
  const tr = useTranslatedTexts(dynamicTexts, language);
  const z = (text: string | null | undefined) => cleanDynamicTranslation(text, tr(text), language);
  const copy = getCopy(language);

  if (error) return <div className="error">{t.common.apiUnavailable}: {error}. API: 8010.</div>;
  if (!data) return <div className="loading">{copy.loading}</div>;

  const enabledSources = data.source_statuses.filter((source) => source.enabled);
  const healthySources = enabledSources.filter((source) => source.healthy);
  const staleCount = data.market_timestamps.filter((item) => !item.healthy).length;
  const badDeviationCount = data.price_deviations.filter((item) => !item.healthy).length;
  const verdictTone = data.verdict === "tradable" ? "positive" : data.verdict === "watch" ? "warning" : "negative";

  return (
    <>
      <section className="trading-hero data-hero">
        <div className="hero-copy">
          <p className="eyebrow">{copy.eyebrow}</p>
          <h1>{copy.title}</h1>
          <p className="hero-subcopy">{z(data.plain_language_summary)}</p>
          <div className="hero-tape" aria-label="data credibility tape">
            <span>{copy.score}: {data.score.toFixed(1)}/100</span>
            <span>{copy.verdict}: {copy.verdicts[data.verdict] ?? data.verdict}</span>
            <span>{healthySources.length}/{enabledSources.length} {copy.sourcesOk}</span>
            <span>{copy.generated} {new Date(data.generated_at).toLocaleString()}</span>
          </div>
        </div>
        <div className="hero-actions trade-actions">
          <button className="icon-button" onClick={() => void load()} disabled={busy} aria-label={copy.refresh} title={copy.refresh}>
            <RefreshCw size={18} />
          </button>
        </div>
      </section>

      <section className="status-ribbon premium-ribbon">
        <DataPill icon={<ShieldCheck size={16} />} label={copy.dataScore} value={`${data.score.toFixed(1)}/100`} tone={verdictTone} />
        <DataPill icon={<DatabaseZap size={16} />} label={copy.sourceHealth} value={`${healthySources.length}/${enabledSources.length}`} tone={healthySources.length === enabledSources.length ? "positive" : "warning"} />
        <DataPill icon={<Clock3 size={16} />} label={copy.timestampRisk} value={String(staleCount)} tone={staleCount ? "negative" : "positive"} />
        <DataPill icon={<LineChart size={16} />} label={copy.priceDeviation} value={String(badDeviationCount)} tone={badDeviationCount ? "negative" : "positive"} />
      </section>

      <section className="data-command-grid">
        <div className="panel section data-timeline-panel">
          <div className="section-head compact">
            <h2><Clock3 size={18} /> {copy.timestamps}</h2>
            <span className="badge">{data.market_timestamps.length}</span>
          </div>
          <div className="data-table">
            <div className="data-table-head">
              <span>{copy.item}</span>
              <span>{copy.source}</span>
              <span>{copy.latest}</span>
              <span>{copy.delay}</span>
              <span>{copy.status}</span>
            </div>
            {data.market_timestamps.map((item, index) => (
              <div className="data-row" key={`${item.label}-${item.symbol ?? item.source}-${index}`}>
                <span>
                  <strong>{z(item.symbol ?? item.label)}</strong>
                  <small>{z(item.label)}</small>
                </span>
                <span>{z(item.source)}</span>
                <span>{item.latest_timestamp ? new Date(item.latest_timestamp).toLocaleString() : "n/a"}</span>
                <span>{formatAge(item.age_minutes, language)}</span>
                <span className={item.healthy ? "positive" : "negative"}>{item.healthy ? copy.ok : copy.review}</span>
              </div>
            ))}
          </div>
        </div>

        <aside className="panel section">
          <h2><Radar size={18} /> {copy.crossCheck}</h2>
          <div className="cred-card-list">
            {data.price_deviations.length ? data.price_deviations.map((item) => (
              <div className={item.healthy ? "cred-card good" : "cred-card bad"} key={`${item.symbol}-${item.primary_source}`}>
                <div className="row">
                  <strong>{item.symbol}</strong>
                  <span>{item.diff_pct == null ? "n/a" : `${item.diff_pct.toFixed(2)}%`}</span>
                </div>
                <p>{item.primary_source} {formatPrice(item.primary_price)} · {item.comparison_source} {formatPrice(item.comparison_price)}</p>
                <small>{z(item.detail)}</small>
              </div>
            )) : <div className="empty-state">{copy.noCrossCheck}</div>}
          </div>
        </aside>
      </section>

      <section className="data-sources-grid stack-gap">
        <SourcePanel title={copy.news} icon={<Newspaper size={18} />} sources={data.news_sources} z={z} empty={copy.noNews} />
        <SourcePanel title={copy.earnings} icon={<FileWarning size={18} />} sources={data.earnings_sources} z={z} empty={copy.noEarnings} />
        <SourcePanel title={copy.optionsChain} icon={<BadgeCheck size={18} />} sources={data.options_chain_sources} z={z} empty={copy.noOptions} />
      </section>

      <section className="panel section stack-gap">
        <div className="section-head compact">
          <h2><DatabaseZap size={18} /> {copy.decisionInputs}</h2>
          <span className="badge">{data.decision_inputs.length}</span>
        </div>
        <div className="decision-input-grid">
          {data.decision_inputs.map((item, index) => (
            <div className="decision-input-card" key={`${item.category}-${item.label}-${index}`}>
              <span className="badge">{z(item.category)}</span>
              <h3>{z(item.label)}</h3>
              <strong>{z(item.value)}</strong>
              <p>{z(item.impact)}</p>
              <small>{copy.from}: {z(item.source)}</small>
            </div>
          ))}
        </div>
      </section>

      <section className="panel section stack-gap">
        <div className="section-head compact">
          <h2><AlertTriangle size={18} /> {copy.allSources}</h2>
          <span className="badge">{enabledSources.length}</span>
        </div>
        <div className="source-health-grid">
          {data.source_statuses.map((source) => (
            <SourceHealthCard source={source} key={source.name} z={z} copy={copy} />
          ))}
        </div>
      </section>
    </>
  );
}

function DataPill({ icon, label, value, tone }: { icon: ReactNode; label: string; value: string; tone: "positive" | "warning" | "negative" }) {
  return (
    <div className={`status-pill ${tone}`}>
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function SourcePanel({ title, icon, sources, z, empty }: { title: string; icon: ReactNode; sources: DataSourceStatus[]; z: (text: string | null | undefined) => string; empty: string }) {
  return (
    <div className="panel section">
      <h2>{icon} {title}</h2>
      <div className="cred-card-list">
        {sources.length ? sources.map((source) => (
          <div className={source.healthy ? "cred-card good" : source.enabled ? "cred-card bad" : "cred-card muted-card"} key={source.name}>
            <div className="row">
              <strong>{z(source.name)}</strong>
              <span>{source.enabled ? (source.healthy ? "OK" : "Review") : "Off"}</span>
            </div>
            <p>{z(source.detail)}</p>
            <small>{source.symbols_real}/{source.symbols_requested} real · fallback {source.symbols_fallback}</small>
          </div>
        )) : <div className="empty-state">{empty}</div>}
      </div>
    </div>
  );
}

function SourceHealthCard({ source, z, copy }: { source: DataSourceStatus; z: (text: string | null | undefined) => string; copy: ReturnType<typeof getCopy> }) {
  const tone = !source.enabled ? "muted-card" : source.healthy ? "good" : "bad";
  return (
    <div className={`cred-card ${tone}`}>
      <div className="row">
        <strong>{z(source.name)}</strong>
        <span>{!source.enabled ? copy.off : source.healthy ? copy.ok : copy.review}</span>
      </div>
      <p>{z(source.detail)}</p>
      <small>{copy.real}: {source.symbols_real} · {copy.fallback}: {source.symbols_fallback}</small>
    </div>
  );
}

function formatAge(minutes: number | null | undefined, language: "en" | "zh") {
  if (minutes == null) return "n/a";
  if (minutes < 90) return language === "zh" ? `${minutes.toFixed(0)} 分钟` : `${minutes.toFixed(0)} min`;
  const hours = minutes / 60;
  if (hours < 48) return language === "zh" ? `${hours.toFixed(1)} 小时` : `${hours.toFixed(1)} hr`;
  const days = hours / 24;
  return language === "zh" ? `${days.toFixed(1)} 天` : `${days.toFixed(1)} d`;
}

function formatPrice(value: number | null | undefined) {
  if (value == null) return "n/a";
  return `$${value.toFixed(value > 100 ? 2 : 4)}`;
}

function getCopy(language: "en" | "zh") {
  if (language === "zh") {
    return {
      loading: "正在加载数据可信度中心...",
      eyebrow: "数据真不真",
      title: "数据可信度中心",
      score: "评分",
      verdict: "结论",
      verdicts: { tradable: "可用于模拟决策", watch: "谨慎观察", blocked: "不可信，先别交易" } as Record<string, string>,
      sourcesOk: "数据源正常",
      generated: "生成于",
      refresh: "刷新数据可信度",
      dataScore: "可信度评分",
      sourceHealth: "来源健康",
      timestampRisk: "时间戳问题",
      priceDeviation: "价格偏差问题",
      timestamps: "行情时间戳与延迟",
      item: "项目",
      source: "来源",
      latest: "最新时间",
      delay: "延迟",
      status: "状态",
      ok: "正常",
      review: "需要检查",
      crossCheck: "跨源价格偏差",
      noCrossCheck: "还没有可用的跨源价格对比。",
      news: "新闻 / 情绪来源",
      earnings: "财报 / 事件来源",
      optionsChain: "期权链实时性",
      noNews: "没有启用新闻来源。",
      noEarnings: "没有启用财报来源。",
      noOptions: "没有启用期权链来源。",
      decisionInputs: "本次决策实际用了什么数据",
      from: "来源",
      allSources: "全部数据源明细",
      off: "关闭",
      real: "真实",
      fallback: "备用",
    };
  }
  return {
    loading: "Loading data credibility center...",
    eyebrow: "Data truth check",
    title: "Data Credibility Center",
    score: "Score",
    verdict: "Verdict",
    verdicts: { tradable: "paper-tradable", watch: "watch carefully", blocked: "blocked" } as Record<string, string>,
    sourcesOk: "sources healthy",
    generated: "Generated",
    refresh: "Refresh data credibility",
    dataScore: "Credibility score",
    sourceHealth: "Source health",
    timestampRisk: "Timestamp issues",
    priceDeviation: "Price deviation issues",
    timestamps: "Market Timestamps & Delay",
    item: "Item",
    source: "Source",
    latest: "Latest",
    delay: "Delay",
    status: "Status",
    ok: "OK",
    review: "Review",
    crossCheck: "Cross-Source Price Deviation",
    noCrossCheck: "No structured cross-source price comparison yet.",
    news: "News / Sentiment Sources",
    earnings: "Earnings / Event Sources",
    optionsChain: "Options Chain Freshness",
    noNews: "No news source enabled.",
    noEarnings: "No earnings source enabled.",
    noOptions: "No options chain source enabled.",
    decisionInputs: "Data Used By This Decision",
    from: "From",
    allSources: "All Source Details",
    off: "Off",
    real: "Real",
    fallback: "Fallback",
  };
}
