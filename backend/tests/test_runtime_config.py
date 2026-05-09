from pathlib import Path

from trading_system.config import Settings
from trading_system.models import UserConfigUpdate
from trading_system.runtime_config import build_config_status, build_expert_audit
import trading_system.runtime_config as runtime_config


def test_config_status_masks_key_values() -> None:
    settings = Settings(
        onboarding_completed=True,
        paper_initial_cash=750,
        massive_api_key="real-key",
        gemini_api_key="gemini-key",
        alpaca_paper_api_key="paper-key",
        alpaca_paper_secret_key="paper-secret",
    )

    status = build_config_status(settings)

    assert status.paper_initial_cash == 750
    assert status.onboarding_completed is True
    assert any(key.name == "massive_api_key" and key.configured for key in status.api_keys)
    dumped = status.model_dump_json()
    assert "real-key" not in dumped
    assert "gemini-key" not in dumped
    assert "paper-secret" not in dumped


def test_apply_user_config_updates_env_file(tmp_path, monkeypatch) -> None:
    env_path = tmp_path / ".env.local"
    env_path.write_text("PAPER_INITIAL_CASH=500\nMASSIVE_API_KEY=old\n", encoding="utf-8")
    monkeypatch.setattr(runtime_config, "ENV_PATH", env_path)

    changed = runtime_config.apply_user_config(UserConfigUpdate(paper_initial_cash=1200, massive_api_key="new-key"))

    assert changed is True
    contents = env_path.read_text(encoding="utf-8")
    assert "PAPER_INITIAL_CASH=1200.0" in contents
    assert "MASSIVE_API_KEY=new-key" in contents


def test_onboarding_persona_applies_safe_presets(tmp_path, monkeypatch) -> None:
    env_path = tmp_path / ".env.local"
    env_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(runtime_config, "ENV_PATH", env_path)

    changed = runtime_config.apply_user_config(
        UserConfigUpdate(onboarding_completed=True, player_persona="beginner", paper_initial_cash=500)
    )

    assert changed is True
    contents = env_path.read_text(encoding="utf-8")
    assert "ONBOARDING_COMPLETED=true" in contents
    assert "PLAYER_PERSONA=beginner" in contents
    assert "RISK_LEVEL=conservative" in contents
    assert "ALLOW_OPTIONS=false" in contents
    assert "WATCH_ONLY_MODE=true" in contents
    assert "MAX_POSITION_PCT=20.0" in contents


def test_expert_audit_blocks_missing_market_key() -> None:
    audit = build_expert_audit(Settings(massive_api_key=None, gemini_api_key="ok"), dashboard=None)

    assert audit.can_share_with_external_players is False
    assert any(item.status == "FIX" for item in audit.items)
