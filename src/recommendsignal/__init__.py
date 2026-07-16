"""RecommendSignal: temporal offline evaluation for recommendation policies."""

from .analysis import EvaluationResult, evaluate_policies
from .design import EvaluationConfig, ValidatedData, validate_inputs
from .errors import DataProblem

__all__ = [
    "DataProblem",
    "EvaluationConfig",
    "EvaluationResult",
    "ValidatedData",
    "evaluate_policies",
    "validate_inputs",
]

__version__ = "1.0.0"
