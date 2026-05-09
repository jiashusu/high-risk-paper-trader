from __future__ import annotations

import json
from datetime import UTC, datetime
from html import unescape
from typing import Any

import httpx

from .config import Settings
from .models import AiAnalysisResponse, AiRoleAnalysis, DashboardPayload, RiskCockpitResponse, TranslationResponse, WeeklyReport


class TranslationClient:
    def __init__(self, settings: Settings) -> None:
        self.api_key = settings.google_translate_api_key
        self._cache: dict[tuple[str, str, str | None], str] = {}

    async def translate(self, texts: list[str], target: str = "zh-CN", source: str | None = None) -> TranslationResponse:
        clean_texts = [text.strip() for text in texts if text and text.strip()]
        if not clean_texts:
            return TranslationResponse(translations=[], provider="local", enabled=False, warning=None)
        if not self.api_key:
            return TranslationResponse(
                translations=clean_texts,
                provider="local",
                enabled=False,
                warning="GOOGLE_TRANSLATE_API_KEY is not configured.",
            )

        output: list[str | None] = [None] * len(clean_texts)
        missing: list[str] = []
        missing_indexes: list[int] = []
        for index, text in enumerate(clean_texts):
            cached = self._cache.get((target, source, text))
            if cached is None:
                missing.append(text)
                missing_indexes.append(index)
            else:
                output[index] = cached

        if missing:
            try:
                async with httpx.AsyncClient(timeout=12.0) as client:
                    response = await client.post(
                        "https://translation.googleapis.com/language/translate/v2",
                        params={"key": self.api_key},
                        json={"q": missing, "target": target, "source": source, "format": "text"},
                    )
                    response.raise_for_status()
                translations = response.json().get("data", {}).get("translations", [])
                for index, item in zip(missing_indexes, translations, strict=False):
                    translated = unescape(str(item.get("translatedText", clean_texts[index])))
                    self._cache[(target, source, clean_texts[index])] = translated
                    output[index] = translated
            except Exception as exc:
                return TranslationResponse(
                    translations=clean_texts,
                    provider="google_translate",
                    enabled=False,
                    warning=f"Google Translate request failed: {type(exc).__name__}",
                )

        return TranslationResponse(
            translations=[text if text is not None else clean_texts[index] for index, text in enumerate(output)],
            provider="google_translate",
            enabled=True,
        )


class GeminiAnalysisClient:
    def __init__(self, settings: Settings) -> None:
        self.api_key = settings.gemini_api_key
        self.model = settings.gemini_model

    async def analyze(self, dashboard: DashboardPayload, report: WeeklyReport, risk: RiskCockpitResponse | None = None) -> AiAnalysisResponse:
        generated_at = datetime.now(UTC)
        if not self.api_key:
            return self._local_judgement(generated_at, dashboard, report, risk, warning="GEMINI_API_KEY is not configured.")

        prompt = self._build_prompt(dashboard, report, risk)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
                    params={"key": self.api_key},
                    json={
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {
                            "temperature": 0.25,
                            "topP": 0.8,
                            "maxOutputTokens": 1600,
                            "responseMimeType": "application/json",
                        },
                    },
                )
                response.raise_for_status()
            analysis = self._extract_text(response.json())
            if not analysis:
                return self._local_judgement(generated_at, dashboard, report, risk, warning="Gemini returned empty analysis.")
            parsed = self._parse_structured_analysis(analysis)
            if parsed:
                return AiAnalysisResponse(enabled=True, generated_at=generated_at, model=self.model, **parsed)
            return self._local_judgement(generated_at, dashboard, report, risk, warning="Gemini returned non-JSON analysis.")
        except Exception as exc:
            return self._local_judgement(generated_at, dashboard, report, risk, warning=f"Gemini request failed: {type(exc).__name__}")

    def _build_prompt(self, dashboard: DashboardPayload, report: WeeklyReport, risk: RiskCockpitResponse | None) -> str:
        portfolio = dashboard.portfolio
        position = portfolio.positions[0] if portfolio.positions else None
        draft = dashboard.order_draft
        live_gate = dashboard.live_readiness
        recent_trades = [
            {
                "time": trade.timestamp.isoformat(),
                "symbol": trade.symbol,
                "side": trade.side,
                "notional": trade.notional,
                "price": trade.price,
                "instrument_type": trade.instrument_type,
                "reason": trade.reason,
            }
            for trade in dashboard.trades[-5:]
        ]
        payload: dict[str, Any] = {
            "portfolio": {
                "cash": portfolio.cash,
                "equity": portfolio.equity,
                "weekly_return_pct": portfolio.weekly_return_pct,
                "max_drawdown_pct": portfolio.max_drawdown_pct,
            },
            "current_strategy": dashboard.current_strategy.model_dump(mode="json"),
            "position": position.model_dump(mode="json") if position else None,
            "order_draft": draft.model_dump(mode="json") if draft else None,
            "live_gate": live_gate.model_dump(mode="json") if live_gate else None,
            "realism": dashboard.realism.model_dump(mode="json"),
            "warnings": dashboard.warnings,
            "recent_trades": recent_trades,
            "weekly_report_decision": report.decision,
            "forward_pnl": report.forward_pnl,
            "forward_hit_rate": report.forward_hit_rate,
            "risk_cockpit": risk.model_dump(mode="json") if risk else None,
        }
        return (
            "你是一个 AI 三方审判委员会，必须用简体中文审查这个 $500 forward paper 模拟盘。"
            "三位角色必须互相独立：\n"
            "1) 进攻交易员：只关心是否有值得冒险的机会。\n"
            "2) 风控官：只关心账户会不会被打穿。\n"
            "3) 怀疑论者：专门反对系统，找数据、逻辑、过拟合、幻觉和自嗨问题。\n"
            "你不能只总结；必须明确指出可以反对当前策略或系统的理由。"
            "不要给实盘下单指令，不要承诺收益，不要鼓励加杠杆或马丁格尔。"
            "最终动作只能是以下之一：continue, go_flat, reduce_size, switch_strategy, observe_only。"
            "只输出 JSON，不要 markdown。JSON 结构必须是："
            "{"
            '"final_action":"continue|go_flat|reduce_size|switch_strategy|observe_only",'
            '"final_verdict":"一句大白话最终结论",'
            '"analysis":"面向普通玩家的简短总评",'
            '"roles":[{"role":"attack_trader|risk_officer|skeptic","display_name":"中文名","stance":"一句话立场","action":"continue|go_flat|reduce_size|switch_strategy|observe_only","confidence":0到1,"thesis":"核心理由","objections":["反对点"],"must_watch":["必须盯的点"]}]'
            "}。\n\n"
            f"数据如下：{payload}"
        )

    def _extract_text(self, payload: dict[str, Any]) -> str:
        parts: list[str] = []
        for candidate in payload.get("candidates", []):
            content = candidate.get("content", {})
            for part in content.get("parts", []):
                text = part.get("text")
                if text:
                    parts.append(str(text))
        return "\n".join(parts).strip()

    def _parse_structured_analysis(self, text: str) -> dict[str, Any] | None:
        try:
            cleaned = text.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.strip("`")
                cleaned = cleaned.removeprefix("json").strip()
            raw = json.loads(cleaned)
            roles = [AiRoleAnalysis.model_validate(item) for item in raw.get("roles", [])]
            if len(roles) != 3:
                return None
            final_action = raw.get("final_action", "observe_only")
            final_verdict = str(raw.get("final_verdict", ""))
            analysis = str(raw.get("analysis", final_verdict))
            return {
                "analysis": analysis,
                "final_action": final_action,
                "final_verdict": final_verdict,
                "roles": roles,
            }
        except (json.JSONDecodeError, TypeError, ValueError):
            return None

    def _local_judgement(
        self,
        generated_at: datetime,
        dashboard: DashboardPayload,
        report: WeeklyReport,
        risk: RiskCockpitResponse | None,
        warning: str | None,
    ) -> AiAnalysisResponse:
        equity = dashboard.portfolio.equity
        weekly = dashboard.portfolio.weekly_return_pct
        data_ok = dashboard.realism.real_market_data_pct >= 95 and all(
            status.healthy for status in dashboard.realism.source_statuses if status.enabled and status.name in {"massive", "market_freshness", "price_cross_check"}
        )
        risk_level = risk.danger_level if risk else "watch"
        has_draft = bool(dashboard.order_draft and dashboard.order_draft.paper_trade_allowed)
        has_position = bool(dashboard.portfolio.positions)
        action = "observe_only"
        if risk_level == "danger" or weekly <= -20:
            action = "go_flat"
        elif risk_level == "watch":
            action = "reduce_size" if has_position or has_draft else "observe_only"
        elif not data_ok:
            action = "observe_only"
        elif has_draft or has_position:
            action = "continue"

        roles = [
            AiRoleAnalysis(
                role="attack_trader",
                display_name="进攻交易员",
                stance="只有信号、数据和流动性都过关时才值得进攻。",
                action="continue" if has_draft and data_ok and risk_level == "safe" else "observe_only",
                confidence=0.62 if has_draft else 0.48,
                thesis=(
                    f"账户净值 ${equity:.2f}，当前策略是 {dashboard.current_strategy.name}。"
                    f"{'有可执行订单草稿，可以继续观察进攻窗口。' if has_draft else '暂时没有足够强的订单草稿，不急着出手。'}"
                ),
                objections=["没有真实 forward 周期优势时，进攻只是冲动。", "如果价差、数据或流动性不过关，热门策略也不值得做。"],
                must_watch=["订单草稿是否仍允许 paper trade", "行情和期权链是否新鲜", "策略是否连续在 forward ledger 中失效"],
            ),
            AiRoleAnalysis(
                role="risk_officer",
                display_name="风控官",
                stance="先保住 500 美元账户，再谈翻倍。",
                action="go_flat" if risk_level == "danger" else "reduce_size" if risk_level == "watch" else "continue",
                confidence=0.78,
                thesis=(
                    risk.plain_language_summary
                    if risk
                    else f"最大回撤 {dashboard.portfolio.max_drawdown_pct:.2f}%，周收益 {weekly:.2f}%。没有风险驾驶舱时不应放大仓位。"
                ),
                objections=["不能为了翻倍目标放弃熔断。", "连亏后加仓属于马丁格尔倾向，必须禁止。"],
                must_watch=["最大单笔亏损", "剩余周度可亏金额", "连续亏损次数", "止损是否真实可执行"],
            ),
            AiRoleAnalysis(
                role="skeptic",
                display_name="怀疑论者",
                stance="默认系统可能在自我感觉良好，必须找证据反驳。",
                action="observe_only" if not data_ok or not report.forward_hit_rate else "switch_strategy" if report.forward_hit_rate < 0.35 and report.trades else "observe_only",
                confidence=0.74,
                thesis=(
                    f"真实行情占比 {dashboard.realism.real_market_data_pct:.1f}%，forward 命中率 {report.forward_hit_rate:.2f}。"
                    "历史回放、热度和 AI 解释都不能替代真实 forward ledger。"
                ),
                objections=["单次模拟结果样本太小。", "新闻热度可能滞后或为空。", "AI 解释可能事后合理化当前策略。"],
                must_watch=["数据源异常", "策略更换理由", "是否重复刷新导致误判", "是否用回测成绩冒充 forward 成绩"],
            ),
        ]
        final_verdict = self._final_verdict(action, risk_level, data_ok)
        analysis = "\n".join(
            [
                f"统一结论：{final_verdict}",
                f"最终动作：{self._action_label(action)}",
                "三方意见：",
                *[f"- {role.display_name}：{role.stance} 动作={self._action_label(role.action)}。" for role in roles],
                "AI 可以反对系统：如果数据、风控或 forward 证据不足，默认只观察或降仓。",
            ]
        )
        return AiAnalysisResponse(
            enabled=False,
            generated_at=generated_at,
            model=f"{self.model}:local-tribunal",
            analysis=analysis,
            final_action=action,
            final_verdict=final_verdict,
            roles=roles,
            warning=warning,
        )

    def _final_verdict(self, action: str, risk_level: str, data_ok: bool) -> str:
        if action == "go_flat":
            return "风险已经压过机会，先空仓保命。"
        if action == "reduce_size":
            return "可以继续观察，但仓位必须降下来，不能按满风险执行。"
        if action == "switch_strategy":
            return "当前策略证据不足，应该换策略或回到策略实验室重审。"
        if action == "continue":
            return "允许继续模拟，但只限 paper ledger，真钱仍然关闭。"
        if not data_ok:
            return "数据还不够可信，只观察，不交易。"
        if risk_level != "safe":
            return "风险没有完全干净，只观察。"
        return "暂时没有强到必须交易的理由，只观察。"

    def _action_label(self, action: str) -> str:
        return {
            "continue": "继续",
            "go_flat": "空仓",
            "reduce_size": "降低仓位",
            "switch_strategy": "换策略",
            "observe_only": "仅观察",
        }.get(action, "仅观察")
