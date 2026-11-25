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


@pytest.mark.slow
def test_switching_language_keeps_the_chosen_part():
    at = AppTest.from_file(APP, default_timeout=180).run()
    box = at.sidebar.selectbox[0]
    box.set_value(next(o for o in box.options if o.startswith("PF-LP-2210"))).run()
    at.sidebar.radio[0].set_value("日本語").run()
    assert not at.exception, at.exception
    assert at.sidebar.selectbox[0].value.startswith("PF-LP-2210")


@pytest.mark.slow
def test_custom_xyz_input_good_and_bad():
    at = AppTest.from_file(APP, default_timeout=180).run()
    at.sidebar.radio[1].set_value("custom").run()
    at.sidebar.text_area[0].set_value("0, 0, 0\n200, 0, 0\n200, 150, 0\n350, 150, 60").run()
    assert not at.exception, at.exception
    assert any("CUSTOM-01" in str(m.value) for m in at.metric)
    at.sidebar.text_area[0].set_value("0, 0, 0\n10, 0, 0\n10, 10, 0").run()  # bends overlap at CLR 60
    assert not at.exception, at.exception
    assert any("Geometry problem" in e.value for e in at.error)
