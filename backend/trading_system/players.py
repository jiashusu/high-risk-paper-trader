from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path

from .models import PlayerWorkspace
from .runtime_config import CONFIG_FIELDS

WORKSPACE_ROOT = Path(os.getenv("PAPER_TRADER_WORKSPACE_ROOT") or ("/tmp/high-risk-paper-trader/workspaces" if os.getenv("VERCEL") else "data/workspaces"))
INDEX_PATH = WORKSPACE_ROOT / "players.json"
DEFAULT_PLAYER_ID = "owner"


class PlayerManager:
    def __init__(self, root: Path = WORKSPACE_ROOT, index_path: Path = INDEX_PATH) -> None:
        self.root = root
        self.index_path = index_path
        self.root.mkdir(parents=True, exist_ok=True)
        self._ensure_default_player()

    def list_players(self) -> list[PlayerWorkspace]:
        return [self._workspace_from_record(record) for record in self._read_index()]

    def get(self, player_id: str | None) -> PlayerWorkspace:
        safe_id = sanitize_player_id(player_id or DEFAULT_PLAYER_ID)
        records = self._read_index()
        for record in records:
            if record["player_id"] == safe_id:
                return self._workspace_from_record(record)
        if safe_id == DEFAULT_PLAYER_ID:
            self._ensure_default_player()
            return self.get(DEFAULT_PLAYER_ID)
        raise KeyError(f"Unknown player workspace: {safe_id}")

    def create(self, display_name: str, player_id: str | None = None, initial_cash: float = 500.0) -> PlayerWorkspace:
        safe_id = self._unique_player_id(player_id or display_name)
        now = datetime.now(UTC)
        workspace = self.root / safe_id
        workspace.mkdir(parents=True, exist_ok=False)
        (workspace / "reports").mkdir(parents=True, exist_ok=True)
        env_path = workspace / "config.env"
        env_path.write_text(
            "\n".join(
                [
                    "ONBOARDING_COMPLETED=false",
                    "PLAYER_PERSONA=beginner",
                    "RISK_LEVEL=conservative",
                    "ALLOW_OPTIONS=false",
                    "WATCH_ONLY_MODE=true",
                    f"PAPER_INITIAL_CASH={float(initial_cash)}",
                    "MAX_SINGLE_TRADE_LOSS_PCT=10.0",
                    "MAX_DAILY_LOSS_PCT=5.0",
                    "MAX_WEEKLY_LOSS_PCT=10.0",
                    "MAX_POSITION_PCT=20.0",
                    "MAX_ORDER_SLIPPAGE_PCT=5.0",
                    "LIVE_MIN_FORWARD_WEEKS=8",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        record = {
            "player_id": safe_id,
            "display_name": display_name.strip() or safe_id,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        records = self._read_index()
        records.append(record)
        self._write_index(records)
        return self._workspace_from_record(record)

    def _ensure_default_player(self) -> None:
        if self.index_path.exists() and any(record.get("player_id") == DEFAULT_PLAYER_ID for record in self._read_index()):
            return
        workspace = self.root / DEFAULT_PLAYER_ID
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "reports").mkdir(parents=True, exist_ok=True)
        env_path = workspace / "config.env"
        if not env_path.exists():
            env_path.write_text(_default_player_env(), encoding="utf-8")
        now = datetime.now(UTC).isoformat()
        records = [record for record in self._read_index() if record.get("player_id") != DEFAULT_PLAYER_ID]
        records.insert(
            0,
            {
                "player_id": DEFAULT_PLAYER_ID,
                "display_name": "Owner",
                "created_at": now,
                "updated_at": now,
            },
        )
        self._write_index(records)

    def _unique_player_id(self, seed: str) -> str:
        base = sanitize_player_id(seed)
        existing = {record["player_id"] for record in self._read_index()}
        if base not in existing:
            return base
        suffix = 2
        while f"{base}-{suffix}" in existing:
            suffix += 1
        return f"{base}-{suffix}"

    def _workspace_from_record(self, record: dict) -> PlayerWorkspace:
        player_id = sanitize_player_id(record["player_id"])
        workspace = self.root / player_id
        env_path = workspace / "config.env"
        ledger_path = workspace / "ledger.duckdb"
        report_path = workspace / "reports"
        report_path.mkdir(parents=True, exist_ok=True)
        env_values = _read_env_values(env_path)
        return PlayerWorkspace(
            player_id=player_id,
            display_name=str(record.get("display_name") or player_id),
            workspace_path=str(workspace),
            config_path=str(env_path),
            ledger_path=str(ledger_path),
            report_path=str(report_path),
            created_at=datetime.fromisoformat(record["created_at"]),
            updated_at=datetime.fromisoformat(record["updated_at"]),
            onboarding_completed=_env_bool(env_values.get("ONBOARDING_COMPLETED")),
            initial_cash=float(env_values.get("PAPER_INITIAL_CASH") or 500.0),
        )

    def _read_index(self) -> list[dict]:
        if not self.index_path.exists():
            return []
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        return payload if isinstance(payload, list) else []

    def _write_index(self, records: list[dict]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sanitize_player_id(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower()).strip("-_")
    return slug[:48] or DEFAULT_PLAYER_ID


def _default_player_env() -> str:
    root_values = _read_env_values(Path(".env.local"))
    lines: list[str] = []
    for field, env_name in CONFIG_FIELDS.items():
        if env_name in root_values:
            lines.append(f"{env_name}={root_values[env_name]}")
    if not any(line.startswith("ONBOARDING_COMPLETED=") for line in lines):
        lines.append("ONBOARDING_COMPLETED=false")
    if not any(line.startswith("PLAYER_PERSONA=") for line in lines):
        lines.append("PLAYER_PERSONA=beginner")
    if not any(line.startswith("RISK_LEVEL=") for line in lines):
        lines.append("RISK_LEVEL=conservative")
    if not any(line.startswith("ALLOW_OPTIONS=") for line in lines):
        lines.append("ALLOW_OPTIONS=false")
    if not any(line.startswith("WATCH_ONLY_MODE=") for line in lines):
        lines.append("WATCH_ONLY_MODE=true")
    if not any(line.startswith("PAPER_INITIAL_CASH=") for line in lines):
        lines.append("PAPER_INITIAL_CASH=500.0")
    return "\n".join(lines).rstrip() + "\n"


def _read_env_values(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _env_bool(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}
