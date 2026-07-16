from pathlib import Path


ROOT = Path(__file__).parents[1]


def _product_text() -> str:
    paths = [ROOT / "app.py", ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]
    return "\n".join(path.read_text(encoding="utf-8") for path in paths)


def test_exact_product_and_package_name_are_consistent() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "recommendsignal"' in pyproject
    assert 'version = "1.0.0"' in pyproject
    assert "RecommendSignal" in (ROOT / "README.md").read_text(encoding="utf-8")


def test_name_is_not_presented_as_legally_cleared() -> None:
    text = _product_text().lower()
    assert "not legally cleared" in text or "uncleared working title" in text
    assert "not legal advice" in text or "not a trademark opinion" in text


def test_offline_results_never_become_causal_lift() -> None:
    text = _product_text()
    assert "Offline ranking accuracy does not demonstrate" in text
    assert "ExperimentSignal" in text
    assert "No causal" in text or "no causal" in text


def test_no_universal_recommendation_score() -> None:
    text = _product_text().lower()
    assert "does not" in text
    assert "universal recommendation score" in text or "magical recommendation score" in text


def test_originality_boundary_is_explicit() -> None:
    text = (ROOT / "docs" / "sources-and-originality.md").read_text(encoding="utf-8")
    assert "No lecture slide deck" in text
    assert "fictional" in text


def test_suite_shell_and_readme_contract_are_present() -> None:
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    config = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    assert "apply_suite_theme" in app
    assert "masthead(" in app and "footer(" in app and "sidebar_brand(" in app
    assert "recommendsignal-banner.svg" in readme
    for heading in (
        "## Read this first",
        "## Try it in three minutes",
        "## Evidence pack",
        "## Privacy",
        "## Development checks",
        "## Relationship to the Signal suite",
    ):
        assert heading in readme
    assert "gatherUsageStats = false" in config
