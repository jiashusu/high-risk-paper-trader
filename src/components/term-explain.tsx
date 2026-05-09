"use client";

import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import { HelpCircle } from "lucide-react";
import type { Position } from "@/lib/api";
import { formatUsd } from "@/lib/api";
import { useLanguage } from "@/lib/i18n";

export type TermKey =
  | "delta"
  | "theta"
  | "iv"
  | "dte"
  | "multiplier"
  | "max_loss"
  | "slippage"
  | "spread"
  | "drawdown"
  | "weekly_fuse"
  | "stop_loss"
  | "take_profit"
  | "position_exposure"
  | "risk_to_stop"
  | "cash_buffer"
  | "plan_follow_rate"
  | "planned_risk"
  | "actual_result";

type ExplainContext = {
  value?: number | string | null;
  position?: Pick<Position, "quantity" | "market_price" | "avg_entry_price" | "market_value" | "stop_loss" | "take_profit" | "multiplier" | "expiration_date" | "delta" | "theta" | "implied_volatility"> | null;
  accountEquity?: number | null;
  maxLoss?: number | null;
  daysToRiskExit?: number | null;
  percent?: number | null;
};

type Explanation = {
  title: string;
  body: string;
  current?: string;
  warning?: string;
};

export function TermExplain({ term, label, context, compact = false }: { term: TermKey; label: ReactNode; context?: ExplainContext; compact?: boolean }) {
  const { language } = useLanguage();
  const [open, setOpen] = useState(false);
  const explanation = useMemo(() => explain(term, context ?? {}, language), [term, context, language]);

  return (
    <span className={compact ? "term-explain compact" : "term-explain"}>
      <span className="term-label">{label}</span>
      <button
        type="button"
        className="term-explain-button"
        aria-label={language === "zh" ? `解释 ${plainLabel(label)}` : `Explain ${plainLabel(label)}`}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <HelpCircle size={13} />
      </button>
      {open ? (
        <span className="term-explain-panel" role="note">
          <strong>{explanation.title}</strong>
          <span>{explanation.body}</span>
          {explanation.current ? <em>{explanation.current}</em> : null}
          {explanation.warning ? <small>{explanation.warning}</small> : null}
        </span>
      ) : null}
    </span>
  );
}

function explain(term: TermKey, context: ExplainContext, language: "en" | "zh"): Explanation {
  if (language === "en") return explainEn(term, context);
  const p = context.position;
  const qty = absNumber(p?.quantity, 1);
  const multiplier = absNumber(p?.multiplier, 100);
  const equity = positiveNumber(context.accountEquity);

  switch (term) {
    case "delta": {
      const delta = finiteNumber(p?.delta ?? context.value);
      const dollarMove = delta == null ? null : Math.abs(delta * qty * multiplier);
      return {
        title: "Delta：底层价格动一下，期权大概跟着动多少",
        body: "Delta 可以粗略理解成期权对标的价格的敏感度。Call 通常是正数，Put 通常是负数。它不是保证值，行情快、临近到期、IV 变化时会变。",
        current: dollarMove == null
          ? "当前没有足够数据计算这笔持仓的 Delta 美元影响。"
          : `结合当前持仓：Delta ${delta?.toFixed(2)}，数量 ${qty}，乘数 ${multiplier}。标的每涨跌 1 美元，这笔期权理论上大约变化 ${formatUsd(dollarMove)}。`,
      };
    }
    case "theta": {
      const theta = finiteNumber(p?.theta ?? context.value);
      const dailyDecay = theta == null ? null : Math.abs(theta * qty * multiplier);
      return {
        title: "Theta：时间损耗",
        body: "Theta 是期权每天被时间吃掉的理论价值。买入期权时，Theta 多数时候对你不利；越接近到期，它越可能变得更狠。",
        current: dailyDecay == null
          ? "当前没有足够数据计算每日时间损耗。"
          : `结合当前持仓：Theta ${theta?.toFixed(3)}，数量 ${qty}，乘数 ${multiplier}。如果其他条件不变，这张/这些期权每天可能因为时间损耗亏约 ${formatUsd(dailyDecay)}。`,
        warning: "Theta 不是固定扣费。标的暴涨暴跌、IV 改变、买卖价差扩大时，真实盈亏会不同。",
      };
    }
    case "iv": {
      const iv = finiteNumber(p?.implied_volatility ?? context.value);
      return {
        title: "IV：市场给这张期权定价时假设的波动率",
        body: "IV 越高，期权通常越贵。财报、重大新闻前 IV 往往升高；事件结束后 IV 可能快速下降，这叫 IV crush。",
        current: iv == null ? "当前没有 IV 数据。" : `当前 IV 大约 ${(iv * 100).toFixed(1)}%。如果买在高 IV，方向猜对也可能被波动率回落吃掉一部分利润。`,
      };
    }
    case "dte": {
      const days = finiteNumber(context.daysToRiskExit ?? daysUntil(p?.expiration_date) ?? context.value);
      return {
        title: "DTE：距离到期还有几天",
        body: "DTE 越短，期权反应越刺激，但容错越低。小账户做短 DTE，最怕方向没错但时间不够。",
        current: days == null ? "当前没有到期日数据。" : `当前大约还剩 ${Math.max(0, Math.ceil(days))} 天。越接近 0，Theta、价差和流动性风险越需要盯紧。`,
      };
    }
    case "multiplier":
      return {
        title: "Multiplier：期权报价要乘多少",
        body: "美股期权通常 1 张合约控制 100 股，所以屏幕上看起来 2.00 美元的期权，真实权利金通常是 200 美元。",
        current: `当前乘数是 ${multiplier}。如果期权价格是 ${formatUsd(absNumber(p?.market_price, 0))}，1 张的名义价格约为 ${formatUsd(absNumber(p?.market_price, 0) * multiplier)}。`,
      };
    case "max_loss": {
      const loss = positiveNumber(context.maxLoss ?? context.value);
      const pct = loss != null && equity ? (loss / equity) * 100 : null;
      return {
        title: "最大亏损：这笔最坏可能打掉多少钱",
        body: "买入期权最坏通常是权利金归零；价差策略看定义风险。这个数字是开仓前必须先接受的亏损上限。",
        current: loss == null ? "当前没有最大亏损估算。" : `当前模型最大亏损约 ${formatUsd(loss)}${pct == null ? "" : `，约占账户 ${pct.toFixed(1)}%`}。`,
      };
    }
    case "slippage": {
      const pct = finiteNumber(context.percent ?? context.value);
      return {
        title: "滑点：你以为成交的价格和真实成交价格的差",
        body: "期权流动性差时，滑点会很痛。系统必须用限价单和最大滑点限制，不然小账户可能刚进场就亏一截。",
        current: pct == null ? "当前没有滑点上限。" : `当前滑点上限约 ${pct.toFixed(2)}%。超过这个范围，这笔单应该被拦住。`,
      };
    }
    case "spread":
      return {
        title: "Bid/Ask Spread：买价和卖价之间的坑",
        body: "Bid 是别人愿意买的价，Ask 是别人愿意卖的价。差距越大，你进出场成本越高，也越容易模拟失真。",
        current: context.value == null ? "当前没有价差数据。" : `当前价差参考：${String(context.value)}。价差太宽时，宁可空仓。`,
      };
    case "drawdown":
      return {
        title: "回撤：从最高点跌下来多少",
        body: "回撤不是单笔亏损，而是账户从最近高点往下掉的幅度。它用来判断系统是不是正在失控。",
        current: context.percent == null ? undefined : `当前回撤约 ${context.percent.toFixed(1)}%。小账户高回撤后，翻本难度会明显增加。`,
      };
    case "weekly_fuse":
      return {
        title: "周度熔断：本周亏到线就停手",
        body: "它不是预测工具，是刹车。到线后系统应该停止开新风险，避免连续错误把账户打穿。",
        current: context.percent == null ? undefined : `当前周度熔断已使用约 ${context.percent.toFixed(0)}%。越接近 100%，越应该进入防守。`,
      };
    case "stop_loss":
      return {
        title: "止损：错了以后在哪里认输",
        body: "止损是计划里的退出点，不是保证成交价。跳空、新闻、低流动性期权都可能让真实亏损比计划更差。",
        current: p?.stop_loss == null ? "当前没有止损价。" : `当前止损价是 ${formatUsd(p.stop_loss)}。如果打到这里，系统应优先保护本金，而不是赌反弹。`,
      };
    case "take_profit":
      return {
        title: "止盈目标：对了以后在哪里收钱",
        body: "止盈目标是防止盈利变回亏损的纪律线。高波动期权涨得快，也跌得快。",
        current: p?.take_profit == null ? "当前没有止盈目标。" : `当前止盈目标是 ${formatUsd(p.take_profit)}。接近目标时，要按计划减仓或退出。`,
      };
    case "position_exposure":
      return {
        title: "仓位暴露：账户里有多少正在冒险",
        body: "仓位暴露越高，单次判断错误对账户伤害越大。$500 账户尤其不能把大部分钱压在一张难成交的期权上。",
        current: context.percent == null ? undefined : `当前仓位暴露约 ${context.percent.toFixed(1)}%。超过系统上限时应减仓或不开新仓。`,
      };
    case "risk_to_stop":
      return {
        title: "止损前风险：打到止损会亏多少",
        body: "这是从当前价格到止损价之间的预计损失。它比“我觉得会涨”重要，因为它决定你错一次会伤多重。",
        current: context.percent == null ? undefined : `当前止损前风险约占账户 ${context.percent.toFixed(1)}%。如果跳空，真实结果可能更差。`,
      };
    case "cash_buffer":
      return {
        title: "现金缓冲：还没拿去冒险的钱",
        body: "现金不是浪费机会。激进系统里，现金是下一次高质量机会的子弹，也是防止一次亏光的垫子。",
        current: context.percent == null ? undefined : `当前现金缓冲约 ${context.percent.toFixed(0)}%。太低时，系统应该减少新仓。`,
      };
    case "plan_follow_rate":
      return {
        title: "计划遵守率：有没有按开仓前说好的做",
        body: "长期赚钱不只看某一笔赚没赚，更看有没有执行入场理由、止损、止盈和仓位纪律。",
        current: context.percent == null ? undefined : `当前计划遵守率约 ${context.percent.toFixed(0)}%。低于 80% 时，说明问题可能在人，而不是策略。`,
      };
    case "planned_risk":
      return {
        title: "计划风险：开仓前允许亏多少、为什么亏",
        body: "真正的交易日记必须先写清楚：这笔最多亏多少、什么情况证明我错了、到哪里必须退出。",
      };
    case "actual_result":
      return {
        title: "实际结果：最后到底发生了什么",
        body: "结果不仅是赚亏，还要看是否按计划执行。赚钱但乱来，下一次可能把利润全还回去。",
      };
  }
}

function explainEn(term: TermKey, context: ExplainContext): Explanation {
  const p = context.position;
  const qty = absNumber(p?.quantity, 1);
  const multiplier = absNumber(p?.multiplier, 100);
  if (term === "theta") {
    const theta = finiteNumber(p?.theta ?? context.value);
    const dailyDecay = theta == null ? null : Math.abs(theta * qty * multiplier);
    return {
      title: "Theta: time decay",
      body: "Theta estimates how much option value can decay each day if other inputs stay unchanged.",
      current: dailyDecay == null ? undefined : `Current position estimate: about ${formatUsd(dailyDecay)} per day of time decay.`,
    };
  }
  if (term === "delta") {
    const delta = finiteNumber(p?.delta ?? context.value);
    const dollarMove = delta == null ? null : Math.abs(delta * qty * multiplier);
    return {
      title: "Delta: price sensitivity",
      body: "Delta estimates how much the option changes when the underlying moves by $1.",
      current: dollarMove == null ? undefined : `Current position estimate: about ${formatUsd(dollarMove)} per $1 underlying move.`,
    };
  }
  const zh = explain(term, context, "zh");
  return {
    title: englishTitle(term),
    body: zh.body,
    current: zh.current,
    warning: zh.warning,
  };
}

function englishTitle(term: TermKey) {
  const titles: Record<TermKey, string> = {
    delta: "Delta",
    theta: "Theta",
    iv: "Implied volatility",
    dte: "Days to expiration",
    multiplier: "Option multiplier",
    max_loss: "Maximum loss",
    slippage: "Slippage",
    spread: "Bid/ask spread",
    drawdown: "Drawdown",
    weekly_fuse: "Weekly fuse",
    stop_loss: "Stop loss",
    take_profit: "Take profit",
    position_exposure: "Position exposure",
    risk_to_stop: "Risk to stop",
    cash_buffer: "Cash buffer",
    plan_follow_rate: "Plan follow rate",
    planned_risk: "Planned risk",
    actual_result: "Actual result",
  };
  return titles[term];
}

function finiteNumber(value: unknown) {
  const n = typeof value === "number" ? value : typeof value === "string" ? Number(value) : null;
  return n != null && Number.isFinite(n) ? n : null;
}

function positiveNumber(value: unknown) {
  const n = finiteNumber(value);
  return n != null && n >= 0 ? n : null;
}

function absNumber(value: unknown, fallback: number) {
  const n = finiteNumber(value);
  return n == null ? fallback : Math.abs(n);
}

function daysUntil(date?: string | null) {
  if (!date) return null;
  const time = new Date(date).getTime();
  if (!Number.isFinite(time)) return null;
  return Math.ceil((time - Date.now()) / 86_400_000);
}

function plainLabel(label: ReactNode) {
  return typeof label === "string" || typeof label === "number" ? String(label) : "term";
}
