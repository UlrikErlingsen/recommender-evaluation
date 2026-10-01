"""Recommend Signal user interface: the Signal Hub entry point.

The only package under ``recommendsignal`` that imports Streamlit. ``render()`` draws the whole app on the current
page and never calls ``st.set_page_config``; the standalone ``app.py`` or Signal Hub owns the page config.
"""

from recommendsignal import __version__
from recommendsignal.ui import signal_theme
from recommendsignal.ui.app import render

APP_INFO = {"product": "Recommend Signal", "version": __version__, "repo": "recommender-evaluation", "slug": "recommend"}

__all__ = ["APP_INFO", "render", "signal_theme"]
