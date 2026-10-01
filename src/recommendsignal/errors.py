"""User-facing errors raised by Recommend Signal."""


class DataProblem(ValueError):
    """Raised when uploaded data cannot support the requested evaluation."""
