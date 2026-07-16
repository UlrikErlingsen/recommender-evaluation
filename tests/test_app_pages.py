from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest


APP = str(Path(__file__).parents[1] / "app.py")
PAGES = [
    "Welcome",
    "1 · Data & temporal contract",
    "2 · Offline leaderboard",
    "3 · Trade-offs & stability",
    "4 · Cold start & subgroups",
    "5 · Evidence pack",
    "Methods & boundaries",
]


@pytest.mark.parametrize("page", PAGES)
def test_every_page_renders_with_fictional_demo(page: str) -> None:
    app = AppTest.from_file(APP, default_timeout=90)
    app.run()
    app.sidebar.radio[0].set_value(page).run()

    assert not app.exception, [error.value for error in app.exception]
    assert app.sidebar.radio[0].value == page
    assert "recommendation policy evidence" in " ".join(str(item.value).lower() for item in app.sidebar.caption)


def test_welcome_preserves_product_boundaries_and_name_warning() -> None:
    app = AppTest.from_file(APP, default_timeout=90)
    app.run()
    body = "\n".join(str(markdown.value) for markdown in app.markdown)
    assert "one magical recommendation score" in body
    assert "ExperimentSignal" in body
    assert "not a trademark opinion" in body
