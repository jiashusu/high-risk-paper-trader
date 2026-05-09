from __future__ import annotations

import httpx

from .config import Settings
from .models import DataSourceStatus


class AlpacaPaperClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def configured(self) -> bool:
        return bool(self.settings.alpaca_paper_api_key and self.settings.alpaca_paper_secret_key)

    def _headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.settings.alpaca_paper_api_key or "",
            "APCA-API-SECRET-KEY": self.settings.alpaca_paper_secret_key or "",
        }

    async def account_status(self) -> DataSourceStatus:
        if not self.configured:
            return DataSourceStatus(
                name="alpaca_paper",
                enabled=False,
                healthy=False,
                detail="Alpaca paper credentials are not configured.",
            )

        base_url = self.settings.alpaca_paper_base_url.rstrip("/")
        async with httpx.AsyncClient(timeout=12, headers=self._headers()) as client:
            try:
                response = await client.get(f"{base_url}/account")
                response.raise_for_status()
                account = response.json()
                status = account.get("status", "unknown")
                buying_power = account.get("buying_power", "unknown")
                portfolio_value = account.get("portfolio_value", "unknown")
                return DataSourceStatus(
                    name="alpaca_paper",
                    enabled=True,
                    healthy=response.status_code == 200,
                    detail=f"Account status={status}, buying_power={buying_power}, portfolio_value={portfolio_value}.",
                )
            except httpx.HTTPError as exc:
                return DataSourceStatus(
                    name="alpaca_paper",
                    enabled=True,
                    healthy=False,
                    detail=f"Account check failed: {exc.__class__.__name__}.",
                )

