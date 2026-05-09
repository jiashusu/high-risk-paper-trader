"use client";

import { useMemo, useState } from "react";
import { BadgeDollarSign, Binoculars, BrainCircuit, CheckCircle2, KeyRound, Lock, Rocket, ShieldCheck, SlidersHorizontal, Sparkles, UserRound } from "lucide-react";
import { UserConfigStatus, UserConfigUpdate, formatUsd, saveUserConfig } from "@/lib/api";
import { useLanguage } from "@/lib/i18n";

type Persona = "beginner" | "player" | "expert";
type RiskLevel = "conservative" | "balanced" | "aggressive";

type WizardState = {
  persona: Persona;
  riskLevel: RiskLevel;
  initialCash: string;
  allowOptions: boolean;
  watchOnly: boolean;
  maxPositionPct: string;
  maxDailyLossPct: string;
  maxWeeklyLossPct: string;
  maxSlippagePct: string;
  forwardWeeks: string;
  massiveKey: string;
  alpacaKey: string;
  alpacaSecret: string;
  benzingaKey: string;
  fmpKey: string;
  translateKey: string;
  geminiKey: string;
};

const personaDefaults: Record<Persona, Pick<WizardState, "riskLevel" | "allowOptions" | "watchOnly" | "maxPositionPct" | "maxDailyLossPct" | "maxWeeklyLossPct" | "maxSlippagePct" | "forwardWeeks">> = {
  beginner: {
    riskLevel: "conservative",
    allowOptions: false,
    watchOnly: true,
    maxPositionPct: "20",
    maxDailyLossPct: "5",
    maxWeeklyLossPct: "10",
    maxSlippagePct: "5",
    forwardWeeks: "8",
  },
  player: {
    riskLevel: "balanced",
    allowOptions: true,
    watchOnly: false,
    maxPositionPct: "40",
    maxDailyLossPct: "10",
    maxWeeklyLossPct: "20",
    maxSlippagePct: "8",
    forwardWeeks: "6",
  },
  expert: {
    riskLevel: "aggressive",
    allowOptions: true,
    watchOnly: false,
    maxPositionPct: "82",
    maxDailyLossPct: "20",
    maxWeeklyLossPct: "35",
    maxSlippagePct: "15",
    forwardWeeks: "4",
  },
};

export function OnboardingWizard({ config, onComplete, compact = false }: { config: UserConfigStatus; onComplete?: (config: UserConfigStatus) => void; compact?: boolean }) {
  const { language } = useLanguage();
  const copy = getCopy(language);
  const initial = useMemo(() => buildInitialState(config), [config]);
  const [state, setState] = useState<WizardState>(initial);
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const steps = [copy.steps.identity, copy.steps.money, copy.steps.data, copy.steps.confirm];
  const isExpert = state.persona === "expert";

  function choosePersona(persona: Persona) {
    const preset = personaDefaults[persona];
    setState((current) => ({
      ...current,
      persona,
      riskLevel: preset.riskLevel,
      allowOptions: preset.allowOptions,
      watchOnly: preset.watchOnly,
      maxPositionPct: preset.maxPositionPct,
      maxDailyLossPct: preset.maxDailyLossPct,
      maxWeeklyLossPct: preset.maxWeeklyLossPct,
      maxSlippagePct: preset.maxSlippagePct,
      forwardWeeks: preset.forwardWeeks,
    }));
  }

  function chooseRisk(riskLevel: RiskLevel) {
    const preset = Object.values(personaDefaults).find((item) => item.riskLevel === riskLevel) ?? personaDefaults.beginner;
    setState((current) => ({
      ...current,
      riskLevel,
      maxPositionPct: current.persona === "expert" ? preset.maxPositionPct : current.maxPositionPct,
      maxDailyLossPct: current.persona === "expert" ? preset.maxDailyLossPct : current.maxDailyLossPct,
      maxWeeklyLossPct: current.persona === "expert" ? preset.maxWeeklyLossPct : current.maxWeeklyLossPct,
      maxSlippagePct: current.persona === "expert" ? preset.maxSlippagePct : current.maxSlippagePct,
      forwardWeeks: current.persona === "expert" ? preset.forwardWeeks : current.forwardWeeks,
    }));
  }

  async function submit() {
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const update: UserConfigUpdate = {
        onboarding_completed: true,
        player_persona: state.persona,
        risk_level: state.riskLevel,
        paper_initial_cash: Number(state.initialCash || 500),
        allow_options: state.allowOptions,
        watch_only_mode: state.watchOnly,
        reset_ledger: true,
      };
      if (isExpert) {
        update.max_position_pct = Number(state.maxPositionPct);
        update.max_daily_loss_pct = Number(state.maxDailyLossPct);
        update.max_weekly_loss_pct = Number(state.maxWeeklyLossPct);
        update.max_order_slippage_pct = Number(state.maxSlippagePct);
        update.live_min_forward_weeks = Number(state.forwardWeeks);
      }
      if (state.massiveKey.trim()) update.massive_api_key = state.massiveKey.trim();
      if (state.alpacaKey.trim()) update.alpaca_paper_api_key = state.alpacaKey.trim();
      if (state.alpacaSecret.trim()) update.alpaca_paper_secret_key = state.alpacaSecret.trim();
      if (state.benzingaKey.trim()) update.benzinga_api_key = state.benzingaKey.trim();
      if (state.fmpKey.trim()) update.fmp_api_key = state.fmpKey.trim();
      if (state.translateKey.trim()) update.google_translate_api_key = state.translateKey.trim();
      if (state.geminiKey.trim()) update.gemini_api_key = state.geminiKey.trim();
      const nextConfig = await saveUserConfig(update);
      setSaved(true);
      onComplete?.(nextConfig);
    } catch (err) {
      setError(err instanceof Error ? err.message : copy.saveFailed);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={`onboarding-shell ${compact ? "compact" : ""}`}>
      <div className="onboarding-hero">
        <div>
          <p className="eyebrow">{copy.eyebrow}</p>
          <h1>{copy.title}</h1>
          <p className="hero-subcopy">{copy.subtitle}</p>
        </div>
        <div className="onboarding-summary">
          <span><UserRound size={15} /> {copy.persona[state.persona].title}</span>
          <span><BadgeDollarSign size={15} /> {formatUsd(Number(state.initialCash || 0))}</span>
          <span><ShieldCheck size={15} /> {copy.risk[state.riskLevel].title}</span>
        </div>
      </div>

      <div className="wizard-progress" aria-label={copy.progress}>
        {steps.map((label, index) => (
          <button className={index === step ? "active" : index < step ? "done" : ""} type="button" key={label} onClick={() => setStep(index)}>
            <span>{index + 1}</span>
            {label}
          </button>
        ))}
      </div>

      {step === 0 ? (
        <div className="wizard-panel">
          <div className="wizard-card-grid">
            {(Object.keys(copy.persona) as Persona[]).map((persona) => (
              <button className={state.persona === persona ? "choice-card active" : "choice-card"} type="button" key={persona} onClick={() => choosePersona(persona)}>
                {persona === "beginner" ? <Binoculars size={24} /> : persona === "player" ? <Rocket size={24} /> : <BrainCircuit size={24} />}
                <strong>{copy.persona[persona].title}</strong>
                <span>{copy.persona[persona].body}</span>
              </button>
            ))}
          </div>
          <div className="wizard-note">
            <Lock size={17} />
            <span>{copy.identityNote}</span>
          </div>
        </div>
      ) : null}

      {step === 1 ? (
        <div className="wizard-panel">
          <div className="onboarding-two-col">
            <label className="config-field hero-field">
              <span>{copy.initialCash}</span>
              <input value={state.initialCash} inputMode="decimal" onChange={(event) => setState({ ...state, initialCash: event.target.value })} />
            </label>
            <div className="toggle-stack">
              <Toggle label={copy.allowOptions} detail={copy.allowOptionsDetail} checked={state.allowOptions} onChange={(allowOptions) => setState({ ...state, allowOptions })} />
              <Toggle label={copy.watchOnly} detail={copy.watchOnlyDetail} checked={state.watchOnly} onChange={(watchOnly) => setState({ ...state, watchOnly })} />
            </div>
          </div>

          <div className="risk-grid">
            {(Object.keys(copy.risk) as RiskLevel[]).map((riskLevel) => (
              <button className={state.riskLevel === riskLevel ? "risk-choice active" : "risk-choice"} type="button" key={riskLevel} onClick={() => chooseRisk(riskLevel)}>
                <strong>{copy.risk[riskLevel].title}</strong>
                <span>{copy.risk[riskLevel].body}</span>
              </button>
            ))}
          </div>

          {isExpert ? (
            <div className="advanced-grid">
              <Field label={copy.maxPosition} value={state.maxPositionPct} onChange={(maxPositionPct) => setState({ ...state, maxPositionPct })} />
              <Field label={copy.dailyFuse} value={state.maxDailyLossPct} onChange={(maxDailyLossPct) => setState({ ...state, maxDailyLossPct })} />
              <Field label={copy.weeklyFuse} value={state.maxWeeklyLossPct} onChange={(maxWeeklyLossPct) => setState({ ...state, maxWeeklyLossPct })} />
              <Field label={copy.slippage} value={state.maxSlippagePct} onChange={(maxSlippagePct) => setState({ ...state, maxSlippagePct })} />
              <Field label={copy.forwardWeeks} value={state.forwardWeeks} onChange={(forwardWeeks) => setState({ ...state, forwardWeeks })} />
            </div>
          ) : (
            <div className="wizard-note">
              <SlidersHorizontal size={17} />
              <span>{copy.advancedLocked}</span>
            </div>
          )}
        </div>
      ) : null}

      {step === 2 ? (
        <div className="wizard-panel">
          <div className="api-check-grid">
            {config.api_keys.map((key) => (
              <div className={key.configured ? "api-check configured" : "api-check"} key={key.name}>
                <KeyRound size={17} />
                <div>
                  <strong>{key.label}</strong>
                  <span>{key.configured ? copy.configured : copy.missing} · {key.required_for}</span>
                </div>
              </div>
            ))}
          </div>
          <p className="muted">{copy.keyHint}</p>
          <div className="advanced-grid">
            <Field label="Massive / Polygon" value={state.massiveKey} secret onChange={(massiveKey) => setState({ ...state, massiveKey })} />
            <Field label="Alpaca Paper Key" value={state.alpacaKey} secret onChange={(alpacaKey) => setState({ ...state, alpacaKey })} />
            <Field label="Alpaca Paper Secret" value={state.alpacaSecret} secret onChange={(alpacaSecret) => setState({ ...state, alpacaSecret })} />
            <Field label="Benzinga" value={state.benzingaKey} secret onChange={(benzingaKey) => setState({ ...state, benzingaKey })} />
            <Field label="FMP" value={state.fmpKey} secret onChange={(fmpKey) => setState({ ...state, fmpKey })} />
            <Field label="Google Translate" value={state.translateKey} secret onChange={(translateKey) => setState({ ...state, translateKey })} />
            <Field label="Gemini" value={state.geminiKey} secret onChange={(geminiKey) => setState({ ...state, geminiKey })} />
          </div>
        </div>
      ) : null}

      {step === 3 ? (
        <div className="wizard-panel">
          <div className="confirm-grid">
            <SummaryItem label={copy.identity} value={copy.persona[state.persona].title} />
            <SummaryItem label={copy.initialCash} value={formatUsd(Number(state.initialCash || 0))} />
            <SummaryItem label={copy.riskLabel} value={copy.risk[state.riskLevel].title} />
            <SummaryItem label={copy.allowOptions} value={state.allowOptions ? copy.yes : copy.no} />
            <SummaryItem label={copy.watchOnly} value={state.watchOnly ? copy.yes : copy.no} />
            <SummaryItem label={copy.resetLedger} value={copy.yes} />
          </div>
          <div className="wizard-note strong">
            <Sparkles size={18} />
            <span>{state.watchOnly ? copy.watchOnlyConfirm : copy.tradeConfirm}</span>
          </div>
          {error ? <p className="error-note">{error}</p> : null}
          {saved ? <p className="success-note"><CheckCircle2 size={16} /> {copy.saved}</p> : null}
        </div>
      ) : null}

      <div className="wizard-actions">
        <button className="primary-button" type="button" disabled={step === 0 || busy} onClick={() => setStep(Math.max(0, step - 1))}>{copy.back}</button>
        {step < steps.length - 1 ? (
          <button className="primary-button hot-button" type="button" onClick={() => setStep(Math.min(steps.length - 1, step + 1))}>{copy.next}</button>
        ) : (
          <button className="primary-button hot-button" type="button" disabled={busy} onClick={() => void submit()}>
            {busy ? copy.saving : copy.finish}
          </button>
        )}
      </div>
    </section>
  );
}

function buildInitialState(config: UserConfigStatus): WizardState {
  return {
    persona: config.player_persona,
    riskLevel: config.risk_level,
    initialCash: String(config.paper_initial_cash || 500),
    allowOptions: config.allow_options,
    watchOnly: config.watch_only_mode,
    maxPositionPct: String(config.max_position_pct),
    maxDailyLossPct: String(config.max_daily_loss_pct),
    maxWeeklyLossPct: String(config.max_weekly_loss_pct),
    maxSlippagePct: String(config.max_order_slippage_pct),
    forwardWeeks: String(config.live_min_forward_weeks),
    massiveKey: "",
    alpacaKey: "",
    alpacaSecret: "",
    benzingaKey: "",
    fmpKey: "",
    translateKey: "",
    geminiKey: "",
  };
}

function Field({ label, value, onChange, secret }: { label: string; value: string; onChange: (value: string) => void; secret?: boolean }) {
  return (
    <label className="config-field">
      <span>{label}</span>
      <input value={value} type={secret ? "password" : "text"} placeholder={secret ? "留空则不修改" : ""} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function Toggle({ label, detail, checked, onChange }: { label: string; detail: string; checked: boolean; onChange: (checked: boolean) => void }) {
  return (
    <button className={checked ? "toggle-card active" : "toggle-card"} type="button" onClick={() => onChange(!checked)}>
      <span>{label}</span>
      <strong>{checked ? "ON" : "OFF"}</strong>
      <small>{detail}</small>
    </button>
  );
}

function SummaryItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="summary-item">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function getCopy(language: "en" | "zh") {
  if (language === "en") {
    return {
      eyebrow: "First-start onboarding",
      title: "Set up your paper trading cockpit",
      subtitle: "Pick a player profile first. Beginner mode keeps the system conservative; expert mode opens the sharp controls.",
      progress: "Onboarding progress",
      steps: { identity: "Identity", money: "Risk", data: "API", confirm: "Confirm" },
      persona: {
        beginner: { title: "Beginner", body: "Plain language, watch-only by default, no options until you understand the ledger." },
        player: { title: "Player", body: "Paper trading can open entries, options allowed, moderate fuses." },
        expert: { title: "Expert", body: "Advanced parameters unlocked. You own the risk knobs." },
      },
      risk: {
        conservative: { title: "Conservative", body: "Smaller positions, tighter daily and weekly fuses." },
        balanced: { title: "Balanced", body: "Medium position cap and enough room for volatile names." },
        aggressive: { title: "Aggressive", body: "High-risk paper mode. Still no live auto-trading." },
      },
      identityNote: "Your profile changes what the app is allowed to do, not just what it displays.",
      initialCash: "Initial paper cash",
      allowOptions: "Allow options",
      allowOptionsDetail: "Only long call/put or defined-risk ideas.",
      watchOnly: "Watch-only mode",
      watchOnlyDetail: "No new paper entries; marks and reports still update.",
      advancedLocked: "Advanced risk parameters stay locked unless you choose Expert.",
      maxPosition: "Max position %",
      dailyFuse: "Daily loss fuse %",
      weeklyFuse: "Weekly loss fuse %",
      slippage: "Max slippage %",
      forwardWeeks: "Required forward weeks",
      keyHint: "Leave a key blank to keep the existing local value. Secrets are never returned to the browser.",
      configured: "configured",
      missing: "missing",
      identity: "Identity",
      riskLabel: "Risk",
      resetLedger: "Reset ledger",
      yes: "Yes",
      no: "No",
      watchOnlyConfirm: "Good first run: observe the system before allowing it to open paper positions.",
      tradeConfirm: "The paper engine may open forward ledger positions, but live money remains locked.",
      back: "Back",
      next: "Next",
      finish: "Finish setup",
      saving: "Saving",
      saved: "Setup saved. The new forward ledger starts from this profile.",
      saveFailed: "Setup failed",
    };
  }
  return {
    eyebrow: "首次启动向导",
    title: "先把你的模拟交易驾驶舱设好",
    subtitle: "先选你是什么类型的玩家。小白模式更保守；专家模式才开放高级参数。",
    progress: "入场进度",
    steps: { identity: "身份", money: "资金风控", data: "API", confirm: "确认" },
    persona: {
      beginner: { title: "小白", body: "默认只看不交易，不碰期权，用更直白的方式先理解账本。" },
      player: { title: "普通玩家", body: "允许模拟开仓，可启用期权，风控中等。" },
      expert: { title: "专家", body: "开放高级参数，你可以自己调仓位、熔断和滑点。" },
    },
    risk: {
      conservative: { title: "保守", body: "仓位小，单日/单周熔断更紧，优先活下来。" },
      balanced: { title: "平衡", body: "中等仓位，给波动资产留空间，但不过度满仓。" },
      aggressive: { title: "激进", body: "高风险模拟盘。仍然不能自动下真钱。" },
    },
    identityNote: "这个身份会改变系统真实允许做什么，不只是换个界面文字。",
    initialCash: "模拟初始资金",
    allowOptions: "允许期权",
    allowOptionsDetail: "只允许买 call/put 或有限风险策略。",
    watchOnly: "只看不交易",
    watchOnlyDetail: "不会开新仓；只更新行情、持仓标记和报告。",
    advancedLocked: "不是专家模式时，高级风控参数会锁住，系统使用对应默认值。",
    maxPosition: "最大仓位 %",
    dailyFuse: "单日亏损熔断 %",
    weeklyFuse: "单周亏损熔断 %",
    slippage: "最大滑点 %",
    forwardWeeks: "实盘前最少 forward 周数",
    keyHint: "密钥留空表示保留当前本地值。后端不会把密钥明文返回给浏览器。",
    configured: "已配置",
    missing: "缺少",
    identity: "身份",
    riskLabel: "风险",
    resetLedger: "重置账本",
    yes: "是",
    no: "否",
    watchOnlyConfirm: "很适合第一次跑：先观察系统，不允许它开模拟新仓。",
    tradeConfirm: "模拟引擎可以开 forward ledger 仓位，但真钱模式仍然锁死。",
    back: "上一步",
    next: "下一步",
    finish: "完成设置",
    saving: "保存中",
    saved: "设置已保存。新的 forward 模拟账本会按这套身份和资金开始。",
    saveFailed: "设置失败",
  };
}
