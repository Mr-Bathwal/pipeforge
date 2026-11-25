"""Smoke test: the Streamlit app renders every panel without an exception."""

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py")


@pytest.mark.slow
def test_app_renders_with_the_default_part():
    at = AppTest.from_file(APP, default_timeout=180).run()
    assert not at.exception, at.exception
    assert any("PipeForge" in m.value for m in at.markdown)


@pytest.mark.slow
def test_app_renders_the_tubebend_part_in_japanese():
    at = AppTest.from_file(APP, default_timeout=180).run()
    at.sidebar.radio[0].set_value("日本語").run()
    box = at.sidebar.selectbox[0]
    box.set_value(next(o for o in box.options if o.startswith("PF-LP-2210"))).run()
    assert not at.exception, at.exception
