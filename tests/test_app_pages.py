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
    # render() catches page errors and shows them with st.error, so check for that too.
    assert not app.error, [error.value for error in app.error]
    assert app.sidebar.radio[0].value == page
    assert "recommendation policy evidence" in " ".join(str(item.value).lower() for item in app.sidebar.caption)


def test_welcome_preserves_product_boundaries_and_name_warning() -> None:
    app = AppTest.from_file(APP, default_timeout=90)
    app.run()
    body = "\n".join(str(markdown.value) for markdown in app.markdown)
    assert "one magical recommendation score" in body
    assert "Experiment Signal" in body
    assert "not a trademark opinion" in body


def test_shared_signal_shell_renders_with_name_status() -> None:
    from recommendsignal import __version__

    app = AppTest.from_file(APP, default_timeout=90)
    app.run()
    body = "\n".join(str(item.value) for item in app.markdown)
    sidebar = "\n".join(str(item.value) for item in app.sidebar.markdown)
    sidebar_warnings = "\n".join(str(item.value) for item in app.sidebar.warning)
    assert "REPLAY → COMPARE → CHALLENGE" in body
    assert f"Recommend Signal v{__version__}" in body
    assert "Offline policy evidence—not business lift" in body
    assert "Part of the Signal suite" in body
    assert "AGPL-3.0-or-later" in body
    assert "sg-mast" in body  # the shared Signal masthead
    assert "sg-foot" in body  # the shared Signal footer
    assert "Compare policies before the live test." in sidebar
    assert "sg-side" in sidebar  # the shared Signal sidebar lockup
    assert "Recommend Signal has not received formal trademark clearance" in sidebar_warnings
