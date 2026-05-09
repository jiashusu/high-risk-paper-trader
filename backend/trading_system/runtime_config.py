from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from .config import Settings
from .models import ApiKeyStatus, DashboardPayload, ExpertAuditItem, ExpertAuditResponse, UserConfigStatus, UserConfigUpdate

ENV_PATH = Path(".env.local")

CONFIG_FIELDS = {
    "onboarding_completed": "ONBOARDING_COMPLETED",
    "player_persona": "PLAYER_PERSONA",
    "risk_level": "RISK_LEVEL",
    "allow_options": "ALLOW_OPTIONS",
    "watch_only_mode": "WATCH_ONLY_MODE",
    "paper_initial_cash": "PAPER_INITIAL_CASH",
    "max_single_trade_loss_pct": "MAX_SINGLE_TRADE_LOSS_PCT",
    "max_daily_loss_pct": "MAX_DAILY_LOSS_PCT",
    "max_weekly_loss_pct": "MAX_WEEKLY_LOSS_PCT",
    "max_position_pct": "MAX_POSITION_PCT",
    "max_order_slippage_pct": "MAX_ORDER_SLIPPAGE_PCT",
    "live_min_forward_weeks": "LIVE_MIN_FORWARD_WEEKS",
    "alpaca_paper_api_key": "ALPACA_PAPER_API_KEY",
    "alpaca_paper_secret_key": "ALPACA_PAPER_SECRET_KEY",
    "massive_api_key": "MASSIVE_API_KEY",
    "benzinga_api_key": "BENZINGA_API_KEY",
    "fmp_api_key": "FMP_API_KEY",
    "google_translate_api_key": "GOOGLE_TRANSLATE_API_KEY",
    "gemini_api_key": "GEMINI_API_KEY",
    "gemini_model": "GEMINI_MODEL",
}

RISK_PRESETS = {
    "conservative": {
        "max_single_trade_loss_pct": 10.0,
        "max_daily_loss_pct": 5.0,
        "max_weekly_loss_pct": 10.0,
        "max_position_pct": 20.0,
        "max_order_slippage_pct": 5.0,
        "live_min_forward_weeks": 8,
    },
    "balanced": {
        "max_single_trade_loss_pct": 20.0,
        "max_daily_loss_pct": 10.0,
        "max_weekly_loss_pct": 20.0,
        "max_position_pct": 40.0,
        "max_order_slippage_pct": 8.0,
        "live_min_forward_weeks": 6,
    },
    "aggressive": {
        "max_single_trade_loss_pct": 50.0,
        "max_daily_loss_pct": 20.0,
        "max_weekly_loss_pct": 35.0,
        "max_position_pct": 82.0,
        "max_order_slippage_pct": 15.0,
        "live_min_forward_weeks": 4,
    },
}

PERSONA_DEFAULTS = {
    "beginner": {"risk_level": "conservative", "allow_options": False, "watch_only_mode": True},
    "player": {"risk_level": "balanced", "allow_options": True, "watch_only_mode": False},
    "expert": {"risk_level": "aggressive", "allow_options": True, "watch_only_mode": False},
}


def build_config_status(settings: Settings, player=None) -> UserConfigStatus:
    keys = [
        ApiKeyStatus(name="massive_api_key", label="Massive / Polygon 行情和期权", configured=bool(settings.massive_api_key), required_for="真实行情、期权链、K 线"),
        ApiKeyStatus(name="alpaca_paper_api_key", label="Alpaca Paper", configured=bool(settings.alpaca_paper_api_key and settings.alpaca_paper_secret_key), required_for="模拟券商账户检查"),
        ApiKeyStatus(name="benzinga_api_key", label="Benzinga 新闻", configured=bool(settings.benzinga_api_key), required_for="新闻催化和市场热度"),
        ApiKeyStatus(name="fmp_api_key", label="FMP 财报", configured=bool(settings.fmp_api_key), required_for="财报日历和事件风险"),
        ApiKeyStatus(name="google_translate_api_key", label="Google Translate", configured=bool(settings.google_translate_api_key), required_for="动态中文翻译"),
        ApiKeyStatus(name="gemini_api_key", label="Gemini", configured=bool(settings.gemini_api_key), required_for="AI 模拟盘分析"),
    ]
    blockers: list[str] = []
    if not settings.onboarding_completed:
        blockers.append("还没有完成首次入场向导。")
    if settings.paper_initial_cash < 50:
        blockers.append("初始资金太小，期权模拟会频繁无法建仓。")
    if settings.allow_options and not settings.massive_api_key:
        blockers.append("你已允许期权，但缺少 Massive/Polygon key，期权链和 bid/ask 无法真实模拟。")
    elif not settings.massive_api_key:
        blockers.append("缺少 Massive/Polygon key，外部玩家看到的行情真实性会下降。")
    if not settings.gemini_api_key:
        blockers.append("缺少 Gemini key，AI 分析模块不可用。")
    if settings.max_position_pct > 90:
        blockers.append("单笔最大仓位过高，外部玩家容易误以为系统鼓励满仓赌博。")
    return UserConfigStatus(
        player_id=player.player_id if player else "owner",
        display_name=player.display_name if player else "Owner",
        workspace_path=player.workspace_path if player else "data/workspaces/owner",
        ledger_path=player.ledger_path if player else settings.database_path,
        report_path=player.report_path if player else "data/workspaces/owner/reports",
        onboarding_completed=settings.onboarding_completed,
        player_persona=settings.player_persona,
        risk_level=settings.risk_level,
        allow_options=settings.allow_options,
        watch_only_mode=settings.watch_only_mode,
        advanced_unlocked=settings.player_persona == "expert",
        paper_initial_cash=settings.paper_initial_cash,
        max_single_trade_loss_pct=settings.max_single_trade_loss_pct,
        max_daily_loss_pct=settings.max_daily_loss_pct,
        max_weekly_loss_pct=settings.max_weekly_loss_pct,
        max_position_pct=settings.max_position_pct,
        max_order_slippage_pct=settings.max_order_slippage_pct,
        live_min_forward_weeks=settings.live_min_forward_weeks,
        gemini_model=settings.gemini_model,
        api_keys=keys,
        external_ready=not blockers,
        blockers=blockers,
    )


def apply_user_config(update: UserConfigUpdate, env_path: Path | None = None) -> bool:
    values = _apply_onboarding_presets(update.model_dump(exclude={"reset_ledger"}, exclude_none=True))
    normalized = {CONFIG_FIELDS[key]: _stringify(value).strip() for key, value in values.items() if _stringify(value).strip()}
    if not normalized:
        return False

    target_path = env_path or ENV_PATH
    lines = target_path.read_text(encoding="utf-8").splitlines() if target_path.exists() else []
    seen: set[str] = set()
    next_lines: list[str] = []
    for line in lines:
        if "=" not in line or line.lstrip().startswith("#"):
            next_lines.append(line)
            continue
        name = line.split("=", 1)[0].strip()
        if name in normalized:
            next_lines.append(f"{name}={normalized[name]}")
            seen.add(name)
        else:
            next_lines.append(line)
    for name, value in normalized.items():
        if name not in seen:
            next_lines.append(f"{name}={value}")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text("\n".join(next_lines).rstrip() + "\n", encoding="utf-8")
    return True


def _apply_onboarding_presets(values: dict[str, object]) -> dict[str, object]:
    persona = str(values.get("player_persona") or "").strip()
    if persona in PERSONA_DEFAULTS:
        for key, value in PERSONA_DEFAULTS[persona].items():
            values.setdefault(key, value)
    risk = str(values.get("risk_level") or "").strip()
    if risk in RISK_PRESETS:
        for key, value in RISK_PRESETS[risk].items():
            values.setdefault(key, value)
    return values


def _stringify(value: object) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def build_expert_audit(settings: Settings, dashboard: DashboardPayload | None, player=None) -> ExpertAuditResponse:
    status = build_config_status(settings)
    items: list[ExpertAuditItem] = [
        ExpertAuditItem(
            area="API 与数据",
            status="PASS" if any(key.name == "massive_api_key" and key.configured for key in status.api_keys) else "FIX",
            severity="high",
            finding="外部玩家必须能用自己的行情 key 跑真实 K 线和期权链。",
            recommendation="设置页已支持输入 Massive、Benzinga、FMP、Alpaca、Google Translate、Gemini key。",
        ),
        ExpertAuditItem(
            area="资金配置",
            status="PASS",
            severity="medium",
            finding=f"当前玩家身份为 {settings.player_persona}，风险等级为 {settings.risk_level}，初始资金为 ${settings.paper_initial_cash:,.2f}。",
            recommendation="首次入场向导会让玩家选择身份、资金、风险、期权权限和只看不交易模式；修改金额会重置 forward ledger。",
        ),
        ExpertAuditItem(
            area="新手保护",
            status="PASS" if settings.onboarding_completed else "FIX",
            severity="high",
            finding="首页现在必须先完成首次入场向导，不能直接把小白丢进专业交易台。",
            recommendation="小白模式默认只看不交易且禁用期权；专家模式才开放高级参数和更激进风控。",
        ),
        ExpertAuditItem(
            area="多用户隔离",
            status="PASS" if player else "WATCH",
            severity="critical",
            finding=f"当前玩家工作区为 {player.workspace_path if player else 'legacy global mode'}。",
            recommendation="每个玩家使用自己的 config.env、ledger.duckdb 和 reports 目录；前端通过玩家选择器切换 workspace。",
        ),
        ExpertAuditItem(
            area="真钱安全",
            status="PASS",
            severity="critical",
            finding="系统仍然只生成 order draft，live submission 是硬关闭。",
            recommendation="对外发布前继续保持默认 Phase 1；真钱模式必须另做账号隔离和人工确认。",
        ),
        ExpertAuditItem(
            area="可解释性",
            status="PASS" if settings.gemini_api_key else "FIX",
            severity="medium",
            finding="AI 分析可以把当前模拟盘翻译成中文复盘，但不允许自动下真钱指令。",
            recommendation="Gemini key 配置后，首页会显示中文 AI 模拟盘分析。",
        ),
    ]
    if dashboard:
        weak_sources = [source.name for source in dashboard.realism.source_statuses if source.enabled and not source.healthy]
        items.append(
            ExpertAuditItem(
                area="运行健康",
                status="PASS" if not weak_sources else "WATCH",
                severity="medium",
                finding=f"当前启用数据源异常数：{len(weak_sources)}。",
                recommendation="外部玩家页面要持续显示 source health，异常时宁可空仓。",
            )
        )
    blockers = [item for item in items if item.status == "FIX"]
    return ExpertAuditResponse(
        generated_at=datetime.now(UTC),
        verdict="可以给外部玩家试用，但必须保持 paper-only，且玩家需要配置自己的 API key。" if not blockers else "还不能作为完整外部试玩版，先补齐关键配置。",
        can_share_with_external_players=not blockers,
        items=items,
        next_hardening_steps=[
            "加入登录/本机密码保护，防止别人打开本机页面看到配置状态。",
            "加入配置导入/导出模板，但永远不导出 secret 明文。",
            "对 AI 分析做缓存和速率限制，避免外部玩家频繁刷新烧 API 额度。",
            "为远程部署加入真正账号系统；当前版本是本机多 workspace 隔离，不是互联网登录系统。",
        ],
    )
