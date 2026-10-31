class FinanceAssistantError(RuntimeError):
    """Base class for expected application errors safe to report to the user."""


class ProviderError(FinanceAssistantError):
    """Raised when an external data provider cannot return usable data."""
