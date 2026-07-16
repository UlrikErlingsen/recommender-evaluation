from __future__ import annotations

import pytest

from recommendsignal.analysis import evaluate_policies
from recommendsignal.design import EvaluationConfig, validate_inputs
from recommendsignal.examples import make_demo_catalog, make_demo_events


@pytest.fixture(scope="session")
def demo_events():
    return make_demo_events()


@pytest.fixture(scope="session")
def demo_catalog():
    return make_demo_catalog()


@pytest.fixture(scope="session")
def validated(demo_events, demo_catalog):
    return validate_inputs(demo_events, demo_catalog)


@pytest.fixture(scope="session")
def config():
    return EvaluationConfig(k=10, n_folds=3, bootstrap_repetitions=100)


@pytest.fixture(scope="session")
def result(validated, config):
    return evaluate_policies(validated, config)
