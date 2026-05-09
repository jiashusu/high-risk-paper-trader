from dataclasses import dataclass
from pathlib import Path

from fastapi import Depends, FastAPI, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from .ai_clients import GeminiAnalysisClient, TranslationClient
from .config import Settings, get_settings, settings_from_env
from .models import AiAnalysisResponse, DashboardPayload, DataCredibilityResponse, ExpertAuditResponse, PlayerCreateRequest, PlayersResponse, PlayerWorkspace, RiskCockpitResponse, StrategyLabResponse, TradeJournalResponse, TranslationRequest, TranslationResponse, UserConfigStatus, UserConfigUpdate, WeeklyReport
from .players import DEFAULT_PLAYER_ID, PlayerManager
from .runtime_config import apply_user_config, build_config_status, build_expert_audit
from .service import TradingResearchService
from .strategies import BUILT_IN_STRATEGIES
from .universe import DEFAULT_UNIVERSE

settings = get_settings()
players = PlayerManager()


@dataclass
class RuntimeBundle:
    player: PlayerWorkspace
    settings: Settings
    service: TradingResearchService
    translator: TranslationClient
    ai_analyzer: GeminiAnalysisClient


runtime_cache: dict[str, RuntimeBundle] = {}


def active_player_id(x_player_id: str | None = Header(default=None), player_id: str | None = Query(default=None)) -> str:
    return player_id or x_player_id or DEFAULT_PLAYER_ID


def runtime_for(player_id: str) -> RuntimeBundle:
    player = players.get(player_id)
    cached = runtime_cache.get(player.player_id)
    config_path = Path(player.config_path)
    ledger_path = Path(player.ledger_path)
    mtime = config_path.stat().st_mtime if config_path.exists() else 0.0
    if cached and getattr(cached, "_config_mtime", None) == mtime:
        return cached
    player_settings = settings_from_env(config_path, ledger_path, Path(player.report_path))
    bundle = RuntimeBundle(
        player=player,
        settings=player_settings,
        service=TradingResearchService(player_settings),
        translator=TranslationClient(player_settings),
        ai_analyzer=GeminiAnalysisClient(player_settings),
    )
    setattr(bundle, "_config_mtime", mtime)
    runtime_cache[player.player_id] = bundle
    return bundle


def rebuild_runtime(player_id: str) -> RuntimeBundle:
    player = players.get(player_id)
    runtime_cache.pop(player.player_id, None)
    return runtime_for(player.player_id)

app = FastAPI(
    title="High-Risk Paper Trading Research API",
    description="Phase 1 paper-only simulator for weekly aggressive trading research.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "mode": "phase_1_paper_only"}


@app.get("/api/players", response_model=PlayersResponse)
async def list_players(player_id: str = Query(default=DEFAULT_PLAYER_ID)) -> PlayersResponse:
    active = players.get(player_id).player_id
    return PlayersResponse(active_player_id=active, players=players.list_players())


@app.post("/api/players", response_model=PlayerWorkspace)
async def create_player(request: PlayerCreateRequest) -> PlayerWorkspace:
    player = players.create(request.display_name, request.player_id, request.initial_cash)
    runtime_cache.pop(player.player_id, None)
    return player


@app.get("/api/user-config", response_model=UserConfigStatus)
async def user_config(player_id: str = Depends(active_player_id)) -> UserConfigStatus:
    bundle = runtime_for(player_id)
    return build_config_status(bundle.settings, bundle.player)


@app.post("/api/user-config", response_model=UserConfigStatus)
async def update_user_config(update: UserConfigUpdate, player_id: str = Depends(active_player_id)) -> UserConfigStatus:
    bundle = runtime_for(player_id)
    changed = apply_user_config(update, Path(bundle.player.config_path))
    if changed:
        bundle = rebuild_runtime(bundle.player.player_id)
        if update.reset_ledger:
            bundle.service.reset_ledger()
    return build_config_status(bundle.settings, bundle.player)


@app.get("/api/expert-audit", response_model=ExpertAuditResponse)
async def expert_audit(player_id: str = Depends(active_player_id)) -> ExpertAuditResponse:
    bundle = runtime_for(player_id)
    dashboard_payload: DashboardPayload | None = None
    try:
        dashboard_payload = await bundle.service.dashboard()
    except Exception:
        dashboard_payload = None
    return build_expert_audit(bundle.settings, dashboard_payload, bundle.player)


@app.post("/api/simulate/week", response_model=DashboardPayload)
async def simulate_week(player_id: str = Depends(active_player_id)) -> DashboardPayload:
    dashboard, _ = await runtime_for(player_id).service.run_cycle()
    return dashboard


@app.post("/api/ledger/tick", response_model=DashboardPayload)
async def ledger_tick(player_id: str = Depends(active_player_id)) -> DashboardPayload:
    dashboard, _ = await runtime_for(player_id).service.run_cycle()
    return dashboard


@app.post("/api/ledger/reset")
async def reset_ledger(player_id: str = Depends(active_player_id)) -> dict[str, str]:
    bundle = runtime_for(player_id)
    bundle.service.reset_ledger()
    return {"status": "reset", "mode": "phase_1_paper_only", "player_id": bundle.player.player_id}


@app.get("/api/dashboard", response_model=DashboardPayload)
async def dashboard(player_id: str = Depends(active_player_id)) -> DashboardPayload:
    return await runtime_for(player_id).service.dashboard()


@app.get("/api/ledger/events")
async def ledger_events(player_id: str = Depends(active_player_id)) -> dict[str, object]:
    bundle = runtime_for(player_id)
    return {"player_id": bundle.player.player_id, "events": bundle.service.ledger.latest_events(limit=100)}


@app.get("/api/order-draft")
async def order_draft(player_id: str = Depends(active_player_id)) -> dict[str, object]:
    dashboard = await runtime_for(player_id).service.dashboard()
    return {"order_draft": dashboard.order_draft, "live_readiness": dashboard.live_readiness}


@app.post("/api/translate", response_model=TranslationResponse)
async def translate_text(request: TranslationRequest, player_id: str = Depends(active_player_id)) -> TranslationResponse:
    return await runtime_for(player_id).translator.translate(request.texts, target=request.target, source=request.source)


@app.get("/api/ai-analysis", response_model=AiAnalysisResponse)
async def ai_analysis(player_id: str = Depends(active_player_id)) -> AiAnalysisResponse:
    bundle = runtime_for(player_id)
    dashboard = await bundle.service.dashboard()
    report = await bundle.service.report()
    risk = await bundle.service.risk_cockpit()
    return await bundle.ai_analyzer.analyze(dashboard, report, risk)


@app.get("/api/report", response_model=WeeklyReport)
async def weekly_report(player_id: str = Depends(active_player_id)) -> WeeklyReport:
    return await runtime_for(player_id).service.report()


@app.get("/api/strategy-lab", response_model=StrategyLabResponse)
async def strategy_lab(player_id: str = Depends(active_player_id)) -> StrategyLabResponse:
    return await runtime_for(player_id).service.strategy_lab()


@app.get("/api/data-credibility", response_model=DataCredibilityResponse)
async def data_credibility(player_id: str = Depends(active_player_id)) -> DataCredibilityResponse:
    return await runtime_for(player_id).service.data_credibility()


@app.get("/api/risk-cockpit", response_model=RiskCockpitResponse)
async def risk_cockpit(player_id: str = Depends(active_player_id)) -> RiskCockpitResponse:
    return await runtime_for(player_id).service.risk_cockpit()


@app.get("/api/trade-journal", response_model=TradeJournalResponse)
async def trade_journal(player_id: str = Depends(active_player_id)) -> TradeJournalResponse:
    return await runtime_for(player_id).service.trade_journal()


@app.get("/api/report.md", response_class=PlainTextResponse)
async def weekly_report_markdown(player_id: str = Depends(active_player_id)) -> str:
    report = await runtime_for(player_id).service.report()
    return report.markdown


@app.get("/api/strategies")
async def strategies() -> dict[str, object]:
    return {
        "mode": "phase_1_paper_only",
        "strategies": [
            {"strategy_id": strategy.strategy_id, "name": strategy.name, "heat": strategy.base_heat, "reliability": strategy.reliability}
            for strategy in BUILT_IN_STRATEGIES
        ],
        "universe": [asset.model_dump() for asset in DEFAULT_UNIVERSE],
    }
