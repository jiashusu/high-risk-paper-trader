"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, KeyRound, RefreshCw, Save, ShieldAlert, UserRoundCog } from "lucide-react";
import { OnboardingWizard } from "@/components/onboarding-wizard";
import { ExpertAuditResponse, UserConfigStatus, fetchExpertAudit, fetchUserConfig, formatUsd, saveUserConfig } from "@/lib/api";
import { useLanguage } from "@/lib/i18n";

type FormState = {
  paper_initial_cash: string;
  max_position_pct: string;
  max_order_slippage_pct: string;
  max_daily_loss_pct: string;
  max_weekly_loss_pct: string;
  live_min_forward_weeks: string;
  massive_api_key: string;
  alpaca_paper_api_key: string;
  alpaca_paper_secret_key: string;
  benzinga_api_key: string;
  fmp_api_key: string;
  google_translate_api_key: string;
  gemini_api_key: string;
  gemini_model: string;
};

const emptyForm: FormState = {
  paper_initial_cash: "",
  max_position_pct: "",
  max_order_slippage_pct: "",
  max_daily_loss_pct: "",
  max_weekly_loss_pct: "",
  live_min_forward_weeks: "",
  massive_api_key: "",
  alpaca_paper_api_key: "",
  alpaca_paper_secret_key: "",
  benzinga_api_key: "",
  fmp_api_key: "",
  google_translate_api_key: "",
  gemini_api_key: "",
  gemini_model: "",
};

export function SetupClient() {
  const { language, t } = useLanguage();
  const copy = getSetupCopy(language);
  const [config, setConfig] = useState<UserConfigStatus | null>(null);
  const [audit, setAudit] = useState<ExpertAuditResponse | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [busy, setBusy] = useState(false);
  const [showWizard, setShowWizard] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setError(null);
    const [configPayload, auditPayload] = await Promise.all([fetchUserConfig(), fetchExpertAudit()]);
    setConfig(configPayload);
    setAudit(auditPayload);
    setShowWizard(!configPayload.onboarding_completed);
    setForm((current) => ({
      ...current,
      paper_initial_cash: String(configPayload.paper_initial_cash),
      max_position_pct: String(configPayload.max_position_pct),
      max_order_slippage_pct: String(configPayload.max_order_slippage_pct),
      max_daily_loss_pct: String(configPayload.max_daily_loss_pct),
      max_weekly_loss_pct: String(configPayload.max_weekly_loss_pct),
      live_min_forward_weeks: String(configPayload.live_min_forward_weeks),
      gemini_model: configPayload.gemini_model,
    }));
  }

  useEffect(() => {
    load().catch((err) => setError(err instanceof Error ? err.message : t.common.apiUnavailable));
  }, [t.common.apiUnavailable]);

  async function submit() {
    setBusy(true);
    setMessage(null);
    setError(null);
    try {
      const update: Record<string, string | number | boolean> = { reset_ledger: true };
      for (const [key, value] of Object.entries(form)) {
        const trimmed = value.trim();
        if (!trimmed) continue;
        if (key.includes("pct") || key.includes("cash") || key.includes("weeks")) {
          update[key] = Number(trimmed);
        } else {
          update[key] = trimmed;
        }
      }
      const nextConfig = await saveUserConfig(update);
      setConfig(nextConfig);
      setForm((current) => ({
        ...emptyForm,
        paper_initial_cash: String(nextConfig.paper_initial_cash),
        max_position_pct: String(nextConfig.max_position_pct),
        max_order_slippage_pct: String(nextConfig.max_order_slippage_pct),
        max_daily_loss_pct: String(nextConfig.max_daily_loss_pct),
        max_weekly_loss_pct: String(nextConfig.max_weekly_loss_pct),
        live_min_forward_weeks: String(nextConfig.live_min_forward_weeks),
        gemini_model: current.gemini_model || nextConfig.gemini_model,
      }));
      setAudit(await fetchExpertAudit());
      setMessage(copy.saved);
    } catch (err) {
      setError(err instanceof Error ? err.message : copy.saveFailed);
    } finally {
      setBusy(false);
    }
  }

  if (error) return <div className="error">{t.common.apiUnavailable}: {error}</div>;
  if (!config || !audit) return <div className="loading">{copy.loading}</div>;

  return (
    <>
      <header className="trading-hero strategy-hero">
        <div className="hero-copy">
          <p className="eyebrow">{copy.eyebrow}</p>
          <h1>{copy.title}</h1>
          <p className="hero-subcopy">{copy.hero}</p>
          <div className="hero-tape">
            <span>{copy.initialCash}: {formatUsd(config.paper_initial_cash)}</span>
            <span>{copy.player}: {config.display_name}</span>
            <span>{config.external_ready ? copy.ready : copy.notReady}</span>
            <span>{config.api_keys.filter((key) => key.configured).length}/{config.api_keys.length} API</span>
          </div>
        </div>
        <button className="primary-button hot-button" type="button" onClick={() => void load()}>
          <RefreshCw size={17} />
          {copy.refresh}
        </button>
      </header>

      {showWizard ? (
        <OnboardingWizard
          config={config}
          onComplete={(nextConfig) => {
            setConfig(nextConfig);
            setShowWizard(false);
            void load();
          }}
        />
      ) : (
        <section className="panel section onboarding-mini">
          <div>
            <p className="eyebrow">{copy.currentProfile}</p>
            <h2><UserRoundCog size={18} /> {copy.profileLine(config.player_persona, config.risk_level)}</h2>
            <p className="muted">{config.watch_only_mode ? copy.watchOnlyOn : copy.watchOnlyOff} · {config.allow_options ? copy.optionsOn : copy.optionsOff}</p>
          </div>
          <button className="primary-button" type="button" onClick={() => setShowWizard(true)}>
            {copy.reopenWizard}
          </button>
        </section>
      )}

      <section className="setup-grid">
        <div className="panel section setup-form">
          <div className="section-head compact">
            <h2><UserRoundCog size={18} /> {copy.localConfig}</h2>
            <button className="primary-button" type="button" onClick={() => void submit()} disabled={busy}>
              <Save size={16} />
              {busy ? copy.saving : copy.save}
            </button>
          </div>
          {message ? <p className="success-note">{message}</p> : null}
          <div className="form-grid">
            <Field label={copy.initialCash} value={form.paper_initial_cash} onChange={(value) => setForm({ ...form, paper_initial_cash: value })} />
            <Field label={copy.maxPosition} value={form.max_position_pct} onChange={(value) => setForm({ ...form, max_position_pct: value })} />
            <Field label={copy.slippageCap} value={form.max_order_slippage_pct} onChange={(value) => setForm({ ...form, max_order_slippage_pct: value })} />
            <Field label={copy.dailyFuse} value={form.max_daily_loss_pct} onChange={(value) => setForm({ ...form, max_daily_loss_pct: value })} />
            <Field label={copy.weeklyFuse} value={form.max_weekly_loss_pct} onChange={(value) => setForm({ ...form, max_weekly_loss_pct: value })} />
            <Field label={copy.forwardWeeks} value={form.live_min_forward_weeks} onChange={(value) => setForm({ ...form, live_min_forward_weeks: value })} />
          </div>

          <h2><KeyRound size={18} /> {copy.apiKeys}</h2>
          <p className="muted">{copy.keyHint}</p>
          <div className="form-grid">
            <Field label="Massive / Polygon" value={form.massive_api_key} secret onChange={(value) => setForm({ ...form, massive_api_key: value })} />
            <Field label="Alpaca Paper Key" value={form.alpaca_paper_api_key} secret onChange={(value) => setForm({ ...form, alpaca_paper_api_key: value })} />
            <Field label="Alpaca Paper Secret" value={form.alpaca_paper_secret_key} secret onChange={(value) => setForm({ ...form, alpaca_paper_secret_key: value })} />
            <Field label="Benzinga" value={form.benzinga_api_key} secret onChange={(value) => setForm({ ...form, benzinga_api_key: value })} />
            <Field label="FMP" value={form.fmp_api_key} secret onChange={(value) => setForm({ ...form, fmp_api_key: value })} />
            <Field label="Google Translate" value={form.google_translate_api_key} secret onChange={(value) => setForm({ ...form, google_translate_api_key: value })} />
            <Field label="Gemini" value={form.gemini_api_key} secret onChange={(value) => setForm({ ...form, gemini_api_key: value })} />
            <Field label="Gemini Model" value={form.gemini_model} onChange={(value) => setForm({ ...form, gemini_model: value })} />
          </div>
        </div>

        <aside className="panel section">
          <h2><CheckCircle2 size={18} /> {copy.apiStatus}</h2>
          <ul className="status-list">
            {config.api_keys.map((key) => (
              <li className={key.configured ? "position-item" : "warning-item"} key={key.name}>
                <div className="row">
                  <strong>{key.label}</strong>
                  <span>{key.configured ? copy.configured : copy.missing}</span>
                </div>
                <p className="muted">{key.required_for}</p>
              </li>
            ))}
          </ul>
          {config.blockers.length ? (
            <>
              <h2><ShieldAlert size={18} /> {copy.blockers}</h2>
              <ul className="status-list">
                {config.blockers.map((blocker) => <li className="warning-item" key={blocker}>{blocker}</li>)}
              </ul>
            </>
          ) : null}
        </aside>
      </section>

      <section className="panel section stack-gap">
        <div className="section-head compact">
          <h2><ShieldAlert size={18} /> {copy.expertAudit}</h2>
          <span className={audit.can_share_with_external_players ? "badge badge-active" : "badge badge-warning"}>{audit.can_share_with_external_players ? copy.shareable : copy.needsWork}</span>
        </div>
        <p className="muted">{audit.verdict}</p>
        <div className="audit-grid">
          {audit.items.map((item) => (
            <div className={item.status === "PASS" ? "audit-pass" : item.status === "WATCH" ? "warning-item" : "audit-fail"} key={`${item.area}-${item.finding}`}>
              <div className="row">
                <strong>{item.area}</strong>
                <span className="badge">{item.status}</span>
              </div>
              <p>{item.finding}</p>
              <p className="muted">{item.recommendation}</p>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}

function Field({ label, value, onChange, secret }: { label: string; value: string; onChange: (value: string) => void; secret?: boolean }) {
  return (
    <label className="config-field">
      <span>{label}</span>
      <input value={value} type={secret ? "password" : "text"} placeholder={secret ? "留空则不修改" : ""} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function getSetupCopy(language: "en" | "zh") {
  if (language === "en") {
    return {
      loading: "Loading setup...",
      eyebrow: "External player setup",
      title: "Local Config & Expert Audit",
      hero: "Each player should bring their own API keys and choose their own paper starting cash. Secrets are written only to the local backend .env file.",
      initialCash: "Initial cash",
      player: "Player",
      ready: "external ready",
      notReady: "needs setup",
      refresh: "Refresh",
      localConfig: "Local player config",
      save: "Save & reset ledger",
      saving: "Saving",
      saved: "Saved. Runtime config reloaded and the forward ledger was reset.",
      saveFailed: "Save failed",
      maxPosition: "Max position %",
      slippageCap: "Max slippage %",
      dailyFuse: "Daily loss fuse %",
      weeklyFuse: "Weekly loss fuse %",
      forwardWeeks: "Required forward weeks",
      apiKeys: "Player API keys",
      keyHint: "Leave a key blank to keep the existing local value. Keys are never returned to the browser.",
      apiStatus: "API status",
      configured: "configured",
      missing: "missing",
      blockers: "Setup blockers",
      expertAudit: "Expert audit",
      shareable: "Shareable",
      needsWork: "Needs work",
      currentProfile: "Current player profile",
      profileLine: (persona: string, risk: string) => `${persona} · ${risk}`,
      watchOnlyOn: "watch-only on",
      watchOnlyOff: "paper entries allowed",
      optionsOn: "options enabled",
      optionsOff: "options disabled",
      reopenWizard: "Run onboarding again",
    };
  }
  return {
    loading: "正在加载设置...",
    eyebrow: "外部玩家配置",
    title: "本地配置与专家审查",
    hero: "每个玩家应该输入自己的 API key，并设置自己的模拟初始金额。密钥只写入本地后端 .env 文件，不返回给浏览器。",
    initialCash: "初始资金",
    player: "玩家",
    ready: "可给外部玩家试用",
    notReady: "还需要配置",
    refresh: "刷新",
    localConfig: "本地玩家配置",
    save: "保存并重置账本",
    saving: "保存中",
    saved: "已保存。运行配置已热重载，forward 模拟账本已按新配置重置。",
    saveFailed: "保存失败",
    maxPosition: "最大仓位 %",
    slippageCap: "最大滑点 %",
    dailyFuse: "单日亏损熔断 %",
    weeklyFuse: "单周亏损熔断 %",
    forwardWeeks: "要求 forward 周数",
    apiKeys: "玩家自己的 API key",
    keyHint: "密钥留空表示不修改现有本地值。后端不会把密钥明文返回给浏览器。",
    apiStatus: "API 状态",
    configured: "已配置",
    missing: "缺少",
    blockers: "配置阻塞项",
    expertAudit: "专家审查",
    shareable: "可分享",
    needsWork: "需完善",
    currentProfile: "当前玩家身份",
    profileLine: (persona: string, risk: string) => {
      const personas: Record<string, string> = { beginner: "小白", player: "普通玩家", expert: "专家" };
      const risks: Record<string, string> = { conservative: "保守", balanced: "平衡", aggressive: "激进" };
      return `${personas[persona] ?? persona} · ${risks[risk] ?? risk}`;
    },
    watchOnlyOn: "只看不交易开启",
    watchOnlyOff: "允许模拟开仓",
    optionsOn: "期权已启用",
    optionsOff: "期权已关闭",
    reopenWizard: "重新运行入场向导",
  };
}
