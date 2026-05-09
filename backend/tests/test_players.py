from pathlib import Path

from trading_system.config import settings_from_env
from trading_system.ledger import ForwardLedger
from trading_system.models import UserConfigUpdate
from trading_system.players import PlayerManager
from trading_system.runtime_config import apply_user_config, build_config_status


def test_player_workspaces_have_independent_config_and_ledger(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    manager = PlayerManager(tmp_path / "workspaces", tmp_path / "workspaces" / "players.json")
    owner = manager.get("owner")
    alice = manager.create("Alice Trader", initial_cash=900)

    assert owner.player_id == "owner"
    assert alice.player_id == "alice-trader"
    assert owner.config_path != alice.config_path
    assert owner.ledger_path != alice.ledger_path
    assert owner.report_path != alice.report_path

    changed = apply_user_config(
        UserConfigUpdate(onboarding_completed=True, player_persona="player", paper_initial_cash=900),
        Path(alice.config_path),
    )
    assert changed is True

    owner_settings = settings_from_env(Path(owner.config_path), Path(owner.ledger_path), Path(owner.report_path))
    alice_settings = settings_from_env(Path(alice.config_path), Path(alice.ledger_path), Path(alice.report_path))
    assert build_config_status(owner_settings, owner).onboarding_completed is False
    assert build_config_status(alice_settings, alice).onboarding_completed is True

    owner_ledger = ForwardLedger(owner.ledger_path, owner_settings.paper_initial_cash)
    alice_ledger = ForwardLedger(alice.ledger_path, alice_settings.paper_initial_cash)
    owner_ledger.reset()
    alice_ledger.reset()

    assert owner_ledger.summary()["initial_cash"] == 500
    assert alice_ledger.summary()["initial_cash"] == 900
