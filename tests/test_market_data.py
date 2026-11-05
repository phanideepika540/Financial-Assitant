import builtins
import sys
from types import SimpleNamespace

import pandas as pd

import pytest

from src.core.errors import ProviderError
from src.data.market_data import MarketDataProvider


def test_market_data_dependency_failure_does_not_break_application_imports(monkeypatch):
    original_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        if name == "yfinance":
            raise ImportError("Blocked by application policy")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)

    with pytest.raises(ProviderError, match="Market data is currently unavailable"):
        MarketDataProvider().snapshot("AAPL")


def test_market_snapshot_includes_chartable_closing_prices(monkeypatch):
    class FakeTicker:
        def history(self, **kwargs):
            assert kwargs["period"] == "5d"
            return pd.DataFrame(
                {"Close": [101.25, 103.5, 102.0]},
                index=pd.to_datetime(
                    ["2026-10-28", "2026-10-29", "2026-10-30"]
                ),
            )

    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda _: FakeTicker()))

    snapshot, chart = MarketDataProvider().snapshot_with_chart("aapl")

    assert "Ticker: AAPL" in snapshot
    assert chart["symbol"] == "AAPL"
    assert chart["dates"] == ["2026-10-28", "2026-10-29", "2026-10-30"]
    assert chart["closes"] == [101.25, 103.5, 102.0]
