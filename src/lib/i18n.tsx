"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";

export type Language = "en" | "zh";

type Dictionary = {
  nav: {
    welcome: string;
    dashboard: string;
    strategies: string;
    data: string;
    risk: string;
    journal: string;
    report: string;
    setup: string;
    phase: string;
  };
  common: {
    loadingDashboard: string;
    loadingStrategies: string;
    loadingReport: string;
    apiUnavailable: string;
    refreshDashboard: string;
    running: string;
    runWeek: string;
    score: string;
    weekly: string;
    return: string;
    drawdown: string;
    hitRate: string;
    heat: string;
    reliability: string;
    markdown: string;
  };
  dashboard: {
    eyebrow: string;
    title: string;
    metricsLabel: string;
    equity: string;
    cash: string;
    weeklyReturn: string;
    paperOnly: string;
    maxDrawdown: string;
    drawdownNote: string;
    nextReview: string;
    signalChart: string;
    chartNote: string;
    currentStrategy: string;
    positions: string;
    noPositions: string;
    value: string;
    stop: string;
    target: string;
    tradeLog: string;
    noTrades: string;
    riskIntegrations: string;
    realism: string;
    realismScore: string;
    realMarketData: string;
    dataPoints: string;
    syntheticFallback: string;
    executionModel: string;
    sourceHealth: string;
  };
  strategies: {
    eyebrow: string;
    title: string;
    gated: string;
    candidates: string;
    switchRules: string;
    ruleBeat: string;
    ruleReliability: string;
    ruleDrawdown: string;
    rulePaper: string;
  };
  report: {
    eyebrow: string;
    decision: string;
    manualReview: string;
    equityStarted: string;
    weeklyReturn: string;
    paperSimulation: string;
    trades: string;
    reasonsLogged: string;
    reportMarkdown: string;
    liveGate: string;
    gatePaper: string;
    gateFourReports: string;
    gateKeys: string;
  };
};

const dictionaries: Record<Language, Dictionary> = {
  en: {
    nav: {
      welcome: "Welcome",
      dashboard: "Dashboard",
      strategies: "Strategies",
      data: "Data Trust",
      risk: "Risk",
      journal: "Journal",
      report: "Weekly Report",
      setup: "Setup",
      phase: "Phase 1 paper-only",
    },
    common: {
      loadingDashboard: "Loading paper trading dashboard...",
      loadingStrategies: "Loading strategy ranking...",
      loadingReport: "Loading weekly report...",
      apiUnavailable: "API unavailable",
      refreshDashboard: "Refresh dashboard",
      running: "Running",
      runWeek: "Forward tick",
      score: "score",
      weekly: "Weekly",
      return: "Return",
      drawdown: "Drawdown",
      hitRate: "Hit rate",
      heat: "Heat",
      reliability: "Reliability",
      markdown: "Markdown",
    },
    dashboard: {
      eyebrow: "Forward paper ledger",
      title: "$500 Options Control Room",
      metricsLabel: "Portfolio metrics",
      equity: "Equity",
      cash: "Cash",
      weeklyReturn: "Weekly return",
      paperOnly: "Ledger paper only",
      maxDrawdown: "Max drawdown",
      drawdownNote: "Weekly fuse watches this",
      nextReview: "Next review",
      signalChart: "Signal Chart",
      chartNote: "Underlying trend, forward ledger fills, exits, and strategy context.",
      currentStrategy: "Current Strategy",
      positions: "Positions",
      noPositions: "No open simulated positions.",
      value: "Value",
      stop: "Stop",
      target: "Target",
      tradeLog: "Trade Log",
      noTrades: "No forward ledger trades yet.",
      riskIntegrations: "Risk & Integrations",
      realism: "Realism Check",
      realismScore: "Realism score",
      realMarketData: "Real market data",
      dataPoints: "Data points",
      syntheticFallback: "Fallback symbols",
      executionModel: "Execution model",
      sourceHealth: "Source Health",
    },
    strategies: {
      eyebrow: "Strategy switchboard",
      title: "Ranking, Heat, Reliability",
      gated: "auto-switch gated",
      candidates: "Candidate Strategies",
      switchRules: "Switch Rules",
      ruleBeat: "A challenger must beat the active score by at least 8 points.",
      ruleReliability: "Reliability must be at least 65% before replacing the active strategy.",
      ruleDrawdown: "Severe drawdown forces the cash-defense strategy, even if another setup is popular.",
      rulePaper: "Phase 1 never sends real orders.",
    },
    report: {
      eyebrow: "Weekly review",
      decision: "Decision",
      manualReview: "Manual review before real trading",
      equityStarted: "Started at $500.00",
      weeklyReturn: "Weekly return",
      paperSimulation: "Paper simulation",
      trades: "Trades",
      reasonsLogged: "All with reasons logged",
      reportMarkdown: "Report Markdown",
      liveGate: "Live Gate",
      gatePaper: "No automatic live trading is enabled in Phase 1.",
      gateFourReports: "Four clean weekly reports are required before manual-live review.",
      gateKeys: "Real API keys must be separated by read-only, paper, and live trade permissions.",
    },
  },
  zh: {
    nav: {
      welcome: "欢迎",
      dashboard: "仪表盘",
      strategies: "策略",
      data: "数据可信度",
      risk: "风险驾驶舱",
      journal: "交易日记",
      report: "周报",
      setup: "设置",
      phase: "第一阶段：仅模拟",
    },
    common: {
      loadingDashboard: "正在加载模拟交易仪表盘...",
      loadingStrategies: "正在加载策略排名...",
      loadingReport: "正在加载周报...",
      apiUnavailable: "API 无法访问",
      refreshDashboard: "刷新仪表盘",
      running: "运行中",
      runWeek: "推进账本",
      score: "评分",
      weekly: "本周",
      return: "收益",
      drawdown: "回撤",
      hitRate: "命中率",
      heat: "热度",
      reliability: "可靠性",
      markdown: "Markdown",
    },
    dashboard: {
      eyebrow: "Forward 模拟账本",
      title: "$500 期权交易控制室",
      metricsLabel: "组合指标",
      equity: "净值",
      cash: "现金",
      weeklyReturn: "本周收益",
      paperOnly: "仅账本模拟",
      maxDrawdown: "最大回撤",
      drawdownNote: "周度熔断监控",
      nextReview: "下次复盘",
      signalChart: "信号图",
      chartNote: "底层趋势、forward 账本成交、退出和策略上下文。",
      currentStrategy: "当前策略",
      positions: "持仓",
      noPositions: "当前没有模拟持仓。",
      value: "市值",
      stop: "止损",
      target: "目标",
      tradeLog: "交易记录",
      noTrades: "还没有 forward 账本交易。",
      riskIntegrations: "风险与接口",
      realism: "真实性检查",
      realismScore: "真实性评分",
      realMarketData: "真实行情占比",
      dataPoints: "数据点",
      syntheticFallback: "Fallback 标的",
      executionModel: "成交模型",
      sourceHealth: "数据源健康",
    },
    strategies: {
      eyebrow: "策略切换台",
      title: "排名、热度、可靠性",
      gated: "自动切换受风控限制",
      candidates: "候选策略",
      switchRules: "切换规则",
      ruleBeat: "挑战策略必须比当前策略高至少 8 分。",
      ruleReliability: "可靠性至少达到 65% 才能替换当前策略。",
      ruleDrawdown: "严重回撤会强制进入现金防守策略，即使其他策略更热门。",
      rulePaper: "第一阶段永远不会发送真实订单。",
    },
    report: {
      eyebrow: "周度复盘",
      decision: "决策",
      manualReview: "真实交易前必须人工确认",
      equityStarted: "初始资金 $500.00",
      weeklyReturn: "本周收益",
      paperSimulation: "模拟交易",
      trades: "交易数",
      reasonsLogged: "每笔交易都记录理由",
      reportMarkdown: "周报 Markdown",
      liveGate: "实盘门槛",
      gatePaper: "第一阶段未启用任何自动实盘交易。",
      gateFourReports: "进入手动实盘评估前，需要四份干净的周报。",
      gateKeys: "真实 API key 必须区分只读、模拟和实盘交易权限。",
    },
  },
};

type LanguageContextValue = {
  language: Language;
  setLanguage: (language: Language) => void;
  t: Dictionary;
};

const LanguageContext = createContext<LanguageContextValue | null>(null);

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [language, setLanguageState] = useState<Language>("zh");

  useEffect(() => {
    const saved = window.localStorage.getItem("paper-trader-language");
    if (saved === "en" || saved === "zh") {
      setLanguageState(saved);
    }
  }, []);

  const setLanguage = (nextLanguage: Language) => {
    setLanguageState(nextLanguage);
    window.localStorage.setItem("paper-trader-language", nextLanguage);
  };

  const value = useMemo(
    () => ({
      language,
      setLanguage,
      t: dictionaries[language],
    }),
    [language],
  );

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage() {
  const context = useContext(LanguageContext);
  if (!context) {
    throw new Error("useLanguage must be used inside LanguageProvider");
  }
  return context;
}

export function translateDecision(decision: string, language: Language) {
  if (language === "en") return decision.replaceAll("_", " ");
  const decisions: Record<string, string> = {
    continue: "继续模拟",
    switch_strategy: "切换策略",
    go_flat: "转为空仓",
    ready_for_manual_live: "可进入手动实盘评估",
  };
  return decisions[decision] ?? decision;
}

export function translateWarning(warning: string, language: Language) {
  if (language === "en") return warning;
  const warnings: Record<string, string> = {
    "Real trading is disabled: Phase 1 is paper-only.": "真实交易已禁用：第一阶段仅进行模拟交易。",
    "MASSIVE_API_KEY is missing; using deterministic synthetic market data.": "缺少 MASSIVE_API_KEY：正在使用确定性模拟行情。",
    "News/fundamental APIs are missing; using synthetic heat scores.": "缺少新闻/基本面 API：正在使用模拟热度评分。",
    "Alpaca paper credentials are not configured yet.": "尚未配置 Alpaca 模拟交易凭证。",
    "Data quality gate blocked trading signals: real market data must be at least 95%.": "数据质量闸门已拦截交易信号：真实行情占比必须至少达到 95%。",
    "Options snapshot data is not authorized; do not use live options chain strategies yet.": "期权快照数据尚未授权：暂时不要使用实时期权链策略。",
    "Options chain is connected, but no liquid candidate passed the safety filters.": "期权链已连接，但没有合约通过流动性和风险筛选。",
  };
  if (warning.startsWith("Market data is")) {
    return warning
      .replace("Market data is", "真实行情占比")
      .replace("real; fallback symbols:", "；fallback 标的：")
      .replace("none", "无");
  }
  return warnings[warning] ?? warning;
}

export function cleanDynamicTranslation(source: string | null | undefined, translated: string, language: Language) {
  if (language === "en" || !source) return translated;
  const exact: Record<string, string> = {
    "Momentum Breakout Options Overlay": "动量突破期权叠加",
    "Momentum Breakout": "动量突破",
    "Trend Following": "趋势跟随",
    "Relative Strength Rotation": "相对强弱轮动",
    "Event Catalyst Momentum": "事件催化动量",
    "Risk Parity / Cash Defense": "风险平价 / 现金防守",
    "Volatility Contraction Breakout": "低波动收缩突破",
    "Volatility Expansion": "波动率扩张",
    "Mean Reversion Snapback": "均值回归反弹",
    massive: "Massive 行情",
    benzinga_news: "Benzinga 新闻",
    fmp_earnings: "FMP 财报",
    alpaca_paper: "Alpaca 模拟账户",
    options_snapshot: "期权快照",
    options_opportunity_scan: "期权机会扫描",
    "4_week_forward_ledger": "4 周 forward 模拟账本",
    order_draft_only: "仅订单草稿",
    critical_data_sources: "关键数据源",
    no_data_anomalies: "无数据异常",
    forward_drawdown: "forward 最大回撤",
    daily_loss_fuse: "单日亏损熔断",
    weekly_loss_fuse: "单周亏损熔断",
    "真钱 gate locked": "真钱模式已锁定",
    "live gate": "实盘门槛",
    "risk gate": "风控门槛",
    "source check": "数据源检查",
    "Alpaca paper account read-only check": "Alpaca 模拟账户只读检查",
    "Local simulator only": "仅本地模拟器",
    "No live blocker returned, but live submission remains disabled.": "没有新的实盘拦截原因，但真钱提交仍然关闭。",
  };
  if (exact[source]) return exact[source];
  if (/^\d+(\.\d+)?\/\d+ forward paper weeks complete\.$/.test(source)) {
    return `已完成 ${source.replace(" forward paper weeks complete.", "")} 周 forward 模拟。`;
  }
  if (/^\d+(\.\d+)?\/\d+ forward weeks completed\.$/.test(source)) {
    return `已完成 ${source.replace(" forward weeks completed.", "")} 周 forward 模拟。`;
  }
  if (source.includes("enabled feeds healthy; critical feeds are clean")) {
    return source.replace("enabled feeds healthy; critical feeds are clean.", "个启用数据源健康；关键数据源正常。");
  }
  if (source.startsWith("Forward ledger mode:")) {
    return "Forward 账本模式：信号使用上一阶段市场数据，成交使用当前模拟 tick，重复刷新不会重复开同一天的仓。";
  }
  if (source.startsWith("Spot fills use range/liquidity impact.")) {
    return "现货按价格区间和流动性估算滑点；期权按 bid/ask 价差、波动率缓冲、成交量和未平仓量估算成交。";
  }
  if (source.startsWith("US equities/ETFs:")) {
    return "美股/ETF 按 0 佣金估算；加密按 25 bps taker 费用估算；期权按每张 $0.65 保守估算。";
  }
  if (source.startsWith("Account status=ACTIVE")) {
    return "账户状态=ACTIVE，购买力=200000，组合价值=100000。";
  }
  if (source.startsWith("FMP earnings calendar reachable")) {
    return translated.replace("fmp_收入", "FMP 财报").replace("收入", "财报");
  }
  return translated
    .replaceAll("论文", "模拟")
    .replaceAll("纸质", "模拟")
    .replaceAll("羊驼", "Alpaca")
    .replaceAll("大量的", "Massive")
    .replaceAll("支票", "检查");
}
