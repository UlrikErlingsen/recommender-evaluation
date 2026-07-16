"""User-facing errors raised by RecommendSignal."""


class DataProblem(ValueError):
    """Raised when uploaded data cannot support the requested evaluation."""
