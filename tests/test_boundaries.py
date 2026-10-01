from pathlib import Path


ROOT = Path(__file__).parents[1]
UI = ROOT / "src" / "recommendsignal" / "ui"


def _product_text() -> str:
    paths = [ROOT / "app.py", UI / "app.py", ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]
    return "\n".join(path.read_text(encoding="utf-8") for path in paths)


def test_exact_product_and_package_name_are_consistent() -> None:
    from recommendsignal import __version__

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "recommendsignal"' in pyproject
    assert f'version = "{__version__}"' in pyproject
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "**Recommend Signal**" in readme
    assert 'description = "Recommend Signal:' in pyproject


def test_name_is_not_presented_as_legally_cleared() -> None:
    text = _product_text().lower()
    assert "not legally cleared" in text or "uncleared working title" in text
    assert "not legal advice" in text or "not a trademark opinion" in text


def test_offline_results_never_become_causal_lift() -> None:
    text = _product_text()
    assert "Offline ranking accuracy does not demonstrate" in text
    assert "Experiment Signal" in text
    assert "No causal" in text or "no causal" in text


def test_no_universal_recommendation_score() -> None:
    text = _product_text().lower()
    assert "does not" in text
    assert "universal recommendation score" in text or "magical recommendation score" in text


def test_originality_boundary_is_explicit() -> None:
    text = (ROOT / "docs" / "sources-and-originality.md").read_text(encoding="utf-8")
    assert "No lecture slide deck" in text
    assert "fictional" in text


def test_app_uses_shared_signal_theme_instead_of_pasted_styles() -> None:
    standalone = (ROOT / "app.py").read_text(encoding="utf-8")
    ui_source = (UI / "app.py").read_text(encoding="utf-8")
    config = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    assert 'st.set_page_config(**sig.page_config("recommend"))' in standalone
    assert "sig.apply(NS)" in ui_source
    for call in ("sig.sidebar_brand(", "sig.masthead(", "sig.footer(", "sig.hero(", "sig.note("):
        assert call in ui_source
    # Every Plotly figure uses the per-app template and is shown through sig.chart (template + theme=None).
    assert ui_source.count("template=sig.template(NS)") == 3
    assert ui_source.count("sig.chart(NS, ") == 3
    assert "st.plotly_chart(" not in ui_source
    assert "<style>" not in standalone + ui_source
    assert not (ROOT / "src" / "recommendsignal" / "suite_brand.py").exists()
    for old_colour in ("#173c3a", "#d95b40", "#83d2b4", "#f2c66d", "#0f766e", "#5b6f91", "#d97706", "#7c3aed"):
        assert old_colour not in (standalone + ui_source).lower()
    assert 'primaryColor = "#aa5d83"' in config  # Customer family 600
    assert "gatherUsageStats = false" in config


def test_readme_follows_the_signal_template() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert '<img src="assets/recommendsignal-banner.png"' in readme
    assert "Signal-Customer-aa5d83" in readme
    assert "assets/recommendsignal-mark-64.png" in readme
    assert "recommendsignal-banner.svg" not in readme
    headings = [
        "## Read this first",
        "## Scope",
        "## Try the demo in three minutes",
        "## Data contract",
        "## Analysis contract",
        "## Methods",
        "## Decision statuses",
        "## Exports",
        "## Run locally",
        "## Privacy",
        "## No install? Give this file to an AI",
        "## Development",
        "## Where this fits in Signal",
        "## References",
        "## Originality and license",
    ]
    positions = [readme.index(heading + "\n") for heading in headings]
    assert positions == sorted(positions)


def test_brand_assets_are_the_synced_signal_files() -> None:
    assets = ROOT / "assets"
    for name in ("banner.png", "social.png", "mark.svg", "mark-32.png", "mark-64.png", "mark-512.png"):
        assert (assets / f"recommendsignal-{name}").exists(), name
    assert not (assets / "recommendsignal-banner.svg").exists()
