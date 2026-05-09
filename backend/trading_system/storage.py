from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb


class TradingStore:
    def __init__(self, path: str) -> None:
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = duckdb.connect(path)
        self._init_schema()

    def _init_schema(self) -> None:
        self.connection.execute(
            """
            create table if not exists runs (
              id varchar primary key,
              created_at timestamp,
              payload json
            )
            """
        )

    def save_run(self, run_id: str, payload: dict[str, Any]) -> None:
        self.connection.execute(
            "insert or replace into runs values (?, now(), ?)",
            [run_id, json.dumps(payload, default=str)],
        )

    def latest_run(self) -> dict[str, Any] | None:
        row = self.connection.execute("select payload from runs order by created_at desc limit 1").fetchone()
        if not row:
            return None
        return json.loads(row[0])

