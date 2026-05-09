"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import type { ReactNode } from "react";
import {
  BarChart3,
  BookOpenCheck,
  ExternalLink,
  FileText,
  Gauge,
  HelpCircle,
  KeyRound,
  PlayCircle,
  Rocket,
  Settings,
  ShieldAlert,
  Sparkles,
  TerminalSquare,
} from "lucide-react";
import { createPlayer, saveUserConfig, setActivePlayerId, simulateWeek } from "@/lib/api";
import { useLanguage } from "@/lib/i18n";

export function WelcomeClient() {
  const { language } = useLanguage();
  const router = useRouter();
  const copy = getWelcomeCopy(language);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function startDemo() {
    setBusy(true);
    setMessage(null);
    try {
      const player = await createPlayer(copy.demoPlayerName, 500, "demo-player");
      setActivePlayerId(player.player_id);
      await saveUserConfig({
        onboarding_completed: true,
        player_persona: "player",
        risk_level: "balanced",
        paper_initial_cash: 500,
        allow_options: true,
        watch_only_mode: false,
        max_position_pct: 40,
        max_daily_loss_pct: 10,
        max_weekly_loss_pct: 20,
        max_order_slippage_pct: 8,
        live_min_forward_weeks: 6,
        reset_ledger: true,
      });
      await simulateWeek();
      router.push("/");
      router.refresh();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : copy.demoFailed);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="welcome-page">
      <section className="welcome-hero">
        <div className="welcome-hero-copy">
          <p className="eyebrow">{copy.eyebrow}</p>
          <h1>{copy.title}</h1>
          <p className="hero-subcopy">{copy.subtitle}</p>
          <div className="hero-tape">
            {copy.heroBadges.map((badge) => <span key={badge}>{badge}</span>)}
          </div>
          <div className="welcome-actions">
            <button className="primary-button hot-button" type="button" onClick={() => void startDemo()} disabled={busy}>
              <PlayCircle size={17} />
              {busy ? copy.demoStarting : copy.startDemo}
            </button>
            <Link className="primary-button" href="/setup">
              <Settings size={17} />
              {copy.configure}
            </Link>
            <Link className="primary-button welcome-secondary-button" href="/">
              <BarChart3 size={17} />
              {copy.enterDashboard}
            </Link>
          </div>
          {message ? <p className="error-note">{message}</p> : null}
        </div>
        <div className="welcome-demo-card">
          <div className="panel-kicker">{copy.sampleAccount}</div>
          <strong>{copy.demoPlayerName}</strong>
          <span>{copy.demoCash}</span>
          <span>{copy.demoMode}</span>
          <small>{copy.demoNote}</small>
        </div>
      </section>

      <section className="welcome-grid">
        <InfoCard icon={<ShieldAlert size={19} />} title={copy.disclaimerTitle} items={copy.disclaimers} tone="danger" />
        <InfoCard icon={<Rocket size={19} />} title={copy.playTitle} items={copy.playSteps} />
        <InfoCard icon={<TerminalSquare size={19} />} title={copy.startTitle} items={copy.startSteps} />
      </section>

      <section className="panel section welcome-flow-panel">
        <div className="section-head compact">
          <h2><Sparkles size={18} /> {copy.flowTitle}</h2>
          <span className="badge badge-active">{copy.phase}</span>
        </div>
        <div className="welcome-flow">
          {copy.flow.map((step, index) => (
            <div className="welcome-flow-step" key={step.title}>
              <span>{index + 1}</span>
              <strong>{step.title}</strong>
              <p>{step.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="panel section">
        <div className="section-head compact">
          <h2><KeyRound size={18} /> {copy.apiTitle}</h2>
          <Link className="text-link" href="/setup">{copy.openSetup}</Link>
        </div>
        <div className="api-guide-grid">
          {copy.apis.map((api) => (
            <article className="api-guide-card" key={api.name}>
              <div className="row">
                <strong>{api.name}</strong>
                <a href={api.href} target="_blank" rel="noreferrer" aria-label={`${api.name} ${copy.openExternal}`}>
                  <ExternalLink size={15} />
                </a>
              </div>
              <p>{api.why}</p>
              <small>{api.how}</small>
            </article>
          ))}
        </div>
      </section>

      <section className="welcome-grid two">
        <div className="panel section">
          <h2><Gauge size={18} /> {copy.riskTitle}</h2>
          <ul className="welcome-check-list danger">
            {copy.risks.map((risk) => <li key={risk}>{risk}</li>)}
          </ul>
        </div>
        <div className="panel section">
          <h2><HelpCircle size={18} /> {copy.faqTitle}</h2>
          <div className="faq-list">
            {copy.faq.map((item) => (
              <details key={item.q}>
                <summary>{item.q}</summary>
                <p>{item.a}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      <section className="panel section welcome-route-panel">
        <div className="section-head compact">
          <h2><BookOpenCheck size={18} /> {copy.routeTitle}</h2>
          <span className="badge">{copy.routeHint}</span>
        </div>
        <div className="route-card-grid">
          {copy.routes.map((route) => (
            <Link className="route-card" href={route.href} key={route.href}>
              {route.icon}
              <strong>{route.title}</strong>
              <span>{route.body}</span>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}

function InfoCard({ icon, title, items, tone }: { icon: ReactNode; title: string; items: string[]; tone?: "danger" }) {
  return (
    <article className={tone === "danger" ? "panel section welcome-info-card danger" : "panel section welcome-info-card"}>
      <h2>{icon} {title}</h2>
      <ul className="welcome-check-list">
        {items.map((item) => <li key={item}>{item}</li>)}
      </ul>
    </article>
  );
}

function getWelcomeCopy(language: "en" | "zh") {
  if (language === "en") {
    return {
      eyebrow: "External player start here",
      title: "High-Risk Paper Trader",
      subtitle: "A paper-only trading cockpit for learning, forward testing, and weekly review before any real-money decision.",
      heroBadges: ["Paper only", "$500 default", "Options realism", "Manual live gate"],
      startDemo: "Start Demo Mode",
      demoStarting: "Creating demo",
      configure: "Configure APIs",
      enterDashboard: "Enter Cockpit",
      sampleAccount: "Sample account",
      demoPlayerName: "Demo Player",
      demoCash: "$500 paper ledger",
      demoMode: "Synthetic data demo, no live orders",
      demoNote: "Creates an isolated workspace so the owner ledger stays untouched.",
      demoFailed: "Demo setup failed.",
      disclaimerTitle: "Disclaimer",
      disclaimers: [
        "This app is not financial advice and does not guarantee profit.",
        "Phase 1 never sends real broker orders.",
        "Options can lose 100% of premium and paper fills can still differ from reality.",
        "Real trading requires your explicit Phase 2 or Phase 3 approval.",
      ],
      playTitle: "How to play",
      playSteps: [
        "Create or select a player workspace.",
        "Pick beginner, player, or expert mode in Setup.",
        "Add API keys for better data, or use demo mode first.",
        "Run forward ticks, read risk, review the journal, and wait for weekly reports.",
      ],
      startTitle: "Local startup",
      startSteps: [
        "Double-click Trading Control.command.",
        "Choose Start, then Open Dashboard.",
        "Use Status when ports 3000 or 8010 look busy.",
        "Use Stop before closing your laptop or switching projects.",
      ],
      flowTitle: "What the system actually does",
      phase: "Phase 1",
      flow: [
        { title: "Data check", body: "Market, options, news, and earnings sources are scored before a signal matters." },
        { title: "Strategy contest", body: "Strategies survive by forward results, backtest context, reliability, and clear reasons." },
        { title: "Risk gate", body: "Position size, slippage, stop risk, weekly fuse, and data delay can block a trade." },
        { title: "Ledger and review", body: "Every accepted paper idea becomes a ledger event, journal item, and weekly review input." },
      ],
      apiTitle: "API key guide",
      openSetup: "Paste keys in Setup",
      openExternal: "external link",
      apis: [
        { name: "Massive / Polygon", href: "https://massive.com/dashboard/keys", why: "Main market data and options-chain realism.", how: "Create a key, make sure options permissions are enabled, then paste it as Massive / Polygon." },
        { name: "Alpaca Paper", href: "https://app.alpaca.markets/paper/dashboard/overview", why: "Paper broker readiness and future order-draft compatibility.", how: "Use paper keys only. Never paste live trading keys into Phase 1." },
        { name: "Benzinga", href: "https://www.benzinga.com/apis/licensing/user/api-keys", why: "News catalysts and market-moving headlines.", how: "Copy the API token and paste it into the Benzinga field." },
        { name: "FMP", href: "https://site.financialmodelingprep.com/developer/docs", why: "Earnings calendar, fundamentals, and event checks.", how: "Create a developer key and paste it into FMP." },
        { name: "Google Translate", href: "https://console.cloud.google.com/apis/library/translate.googleapis.com", why: "Chinese translation for dynamic strategy and source text.", how: "Enable Cloud Translation API, create an API key, paste it into Setup." },
        { name: "Gemini", href: "https://aistudio.google.com/app/api-keys", why: "AI tribunal analysis for attack trader, risk officer, and skeptic roles.", how: "Create a key in AI Studio and paste it into Gemini." },
      ],
      riskTitle: "Risk warnings",
      risks: [
        "Do not treat historical backtests as permission to trade real money.",
        "Do not bypass the weekly fuse after a losing streak.",
        "Do not use naked option selling or martingale sizing.",
        "Do not trade real money until the order-draft stage, max loss limits, and API separation are tested.",
      ],
      faqTitle: "FAQ",
      faq: [
        { q: "Can I use it without API keys?", a: "Yes, demo mode works with deterministic fallback data. It is useful for learning the interface, not for real readiness." },
        { q: "Can it trade real money now?", a: "No. Live submission is intentionally locked in Phase 1." },
        { q: "Why create separate players?", a: "Each player has an isolated workspace, config, ledger, and reports, so external users do not share your account." },
        { q: "What should I check weekly?", a: "Forward PnL, max drawdown, strategy hit rate, data anomalies, risk breaches, and whether the system should continue or stand down." },
      ],
      routeTitle: "Where to go next",
      routeHint: "self-guided",
      routes: [
        { href: "/", icon: <BarChart3 size={19} />, title: "Dashboard", body: "Equity, order draft, AI verdict, positions, and source health." },
        { href: "/setup", icon: <Settings size={19} />, title: "Setup", body: "Player profile, API keys, initial cash, risk limits." },
        { href: "/risk", icon: <Gauge size={19} />, title: "Risk Cockpit", body: "Plain-language answer to: can this wipe me out?" },
        { href: "/journal", icon: <FileText size={19} />, title: "Journal", body: "Trade reasons, planned risk, actual result, and correction loop." },
      ],
    };
  }

  return {
    eyebrow: "外部玩家从这里开始",
    title: "High-Risk Paper Trader",
    subtitle: "这是一个先模拟、再复盘、最后才考虑真钱的高风险交易训练系统。它帮你看机会，也专门拦住你乱来。",
    heroBadges: ["仅模拟", "$500 默认账户", "期权真实度", "真钱门槛锁死"],
    startDemo: "开启演示模式",
    demoStarting: "正在创建演示",
    configure: "配置 API",
    enterDashboard: "进入交易台",
    sampleAccount: "示例账号",
    demoPlayerName: "演示玩家",
    demoCash: "$500 模拟账本",
    demoMode: "演示数据，不会下真钱单",
    demoNote: "会创建独立工作区，不会动你的 Owner 账本。",
    demoFailed: "演示模式创建失败。",
    disclaimerTitle: "免责声明",
    disclaimers: [
      "本项目不是投资建议，也不保证赚钱。",
      "第一阶段永远不会发送真实券商订单。",
      "期权可能亏掉 100% 权利金；模拟成交也可能和真实成交不同。",
      "真钱交易必须由你明确进入 Phase 2 或 Phase 3 后才允许继续开发。",
    ],
    playTitle: "玩法介绍",
    playSteps: [
      "先创建或选择一个玩家工作区。",
      "在设置里选择小白、普通玩家或专家模式。",
      "有 API 就填 API；没有就先用演示模式熟悉流程。",
      "推进 forward tick，看风险页、交易日记和每周复盘，不靠感觉硬上。",
    ],
    startTitle: "启动说明",
    startSteps: [
      "双击 Trading Control.command。",
      "选择 Start，然后选择 Open Dashboard。",
      "如果 3000 或 8010 端口占用，先看 Status。",
      "不用时选择 Stop，避免电脑里 localhost 越开越多。",
    ],
    flowTitle: "系统到底在做什么",
    phase: "第一阶段",
    flow: [
      { title: "先查数据真不真", body: "行情、期权链、新闻、财报来源先过可信度检查，假数据不应该驱动交易。" },
      { title: "策略互相竞争", body: "策略不是只看分数，还要看 forward 表现、回测环境、可靠性和活下来的理由。" },
      { title: "风控先拦一遍", body: "仓位、滑点、止损风险、周度熔断、数据延迟都可能直接挡掉一笔交易。" },
      { title: "写入账本和复盘", body: "每个通过的模拟想法都会进入 ledger、交易日记和周报，方便长期纠错。" },
    ],
    apiTitle: "API 获取教程",
    openSetup: "去设置里粘贴",
    openExternal: "外部链接",
    apis: [
      { name: "Massive / Polygon", href: "https://massive.com/dashboard/keys", why: "主行情和期权链真实度。", how: "创建 key，确认有 Options 权限，然后粘贴到 Massive / Polygon。" },
      { name: "Alpaca Paper", href: "https://app.alpaca.markets/paper/dashboard/overview", why: "纸面券商账户检查，以及未来订单草稿兼容。", how: "只用 Paper key。第一阶段不要粘贴 live trading key。" },
      { name: "Benzinga", href: "https://www.benzinga.com/apis/licensing/user/api-keys", why: "新闻催化和影响市场的标题。", how: "复制 API token，粘贴到 Benzinga。" },
      { name: "FMP", href: "https://site.financialmodelingprep.com/developer/docs", why: "财报日历、基本面和事件检查。", how: "创建 developer key，粘贴到 FMP。" },
      { name: "Google Translate", href: "https://console.cloud.google.com/apis/library/translate.googleapis.com", why: "把动态策略、数据源、新闻说明翻译成中文。", how: "启用 Cloud Translation API，创建 API key，粘贴到设置。" },
      { name: "Gemini", href: "https://aistudio.google.com/app/api-keys", why: "AI 三方审判：进攻交易员、风控官、怀疑论者。", how: "在 AI Studio 创建 key，粘贴到 Gemini。" },
    ],
    riskTitle: "风险提示",
    risks: [
      "历史回测不能当作真钱交易许可，必须看 forward paper ledger。",
      "连亏以后不能绕过周度熔断，更不能急着翻本。",
      "禁止裸卖期权、禁止马丁格尔加仓。",
      "真钱前必须测试订单草稿、最大亏损、API 权限隔离和异常熔断。",
    ],
    faqTitle: "常见问题",
    faq: [
      { q: "没有 API 能玩吗？", a: "可以。演示模式会用确定性 fallback 数据，适合学习界面和流程，但不能代表真实交易准备好了。" },
      { q: "现在能自动下真钱单吗？", a: "不能。第一阶段 live submission 是锁死的。" },
      { q: "为什么要分玩家？", a: "每个玩家有独立 workspace、配置、账本和报告，外部玩家不会共用你的 Owner 账户。" },
      { q: "每周到底看什么？", a: "看 forward PnL、最大回撤、策略命中率、数据异常、风控是否触发，以及下周继续、空仓还是换策略。" },
    ],
    routeTitle: "下一步去哪",
    routeHint: "自己能走完",
    routes: [
      { href: "/", icon: <BarChart3 size={19} />, title: "仪表盘", body: "净值、订单草稿、AI 结论、持仓和数据源状态。" },
      { href: "/setup", icon: <Settings size={19} />, title: "设置", body: "玩家身份、API、初始资金、风险限制。" },
      { href: "/risk", icon: <Gauge size={19} />, title: "风险驾驶舱", body: "用大白话回答：现在会不会一下亏光。" },
      { href: "/journal", icon: <FileText size={19} />, title: "交易日记", body: "入场理由、计划风险、实际结果和下次修正。" },
    ],
  };
}
