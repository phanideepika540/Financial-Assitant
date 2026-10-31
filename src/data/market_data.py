from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.core.errors import ProviderError
from src.data.retry import retry_request

logger = logging.getLogger(__name__)


class MarketDataProvider:
    def __init__(self, history_period: str = "5d"):
        self.history_period = history_period

    def snapshot(self, symbol: str) -> str:
        normalized = symbol.strip().upper()
        if not normalized or not normalized.replace(".", "").replace("-", "").isalnum():
            raise ProviderError("Enter a valid ticker symbol to request market data.")
        try:
            import yfinance as yf

            history = retry_request(
                lambda: yf.Ticker(normalized).history(
                    period=self.history_period,
                    interval="1d",
                    timeout=10,
                    auto_adjust=False,
                ),
                is_retryable=lambda exc: not isinstance(exc, ProviderError),
            )
            if history.empty or "Close" not in history:
                raise ProviderError(f"No recent market data was returned for {normalized}.")
            closes = history["Close"].dropna()
            if closes.empty:
                raise ProviderError(f"No recent closing prices were returned for {normalized}.")
            latest = float(closes.iloc[-1])
            previous = float(closes.iloc[-2]) if len(closes) > 1 else None
            lines = [
                f"Provider: Yahoo Finance via yfinance (unofficial; may be delayed).",
                f"Ticker: {normalized}",
                f"Most recent available close: {latest:.2f} {history.index[-1].date()}",
            ]
            if previous is not None:
                lines.append(f"Prior available close: {previous:.2f}")
            lines.append(f"Retrieved at: {datetime.now(timezone.utc).isoformat()}")
            return "\n".join(lines)
        except ProviderError:
            raise
        except Exception as exc:
            logger.exception("Market data request failed for %s", normalized)
            raise ProviderError(
                f"Market data is currently unavailable for {normalized}. Please retry later."
            ) from exc
