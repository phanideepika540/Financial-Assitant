import builtins

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
