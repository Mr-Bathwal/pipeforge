import openpyxl
import pytest

from pipeforge import llm_assist
from pipeforge.parts import sample_parts
from pipeforge.pipeline import analyze, in_tubebend_domain
from pipeforge.process_sheet import operations, write_excel, write_pdf

SAMPLES = sample_parts()
LP = SAMPLES["PF-LP-2210"]


def test_only_the_tubebend_tube_is_in_the_ml_domain():
    assert in_tubebend_domain(LP)
    assert not any(in_tubebend_domain(p) for k, p in SAMPLES.items() if k != "PF-LP-2210")


def test_ml_mode_outside_its_domain_falls_back_and_says_so():
    a = analyze(SAMPLES["PF-HB-2201"], "ml")
    assert a.springback_model == "physics" and "only for the TubeBEND tube" in a.springback_note


def test_ml_mode_inside_the_domain_scales_with_angle():
    a = analyze(LP, "ml")
    assert a.springback_model == "ml"
    r = a.ybc.rows
    assert r[0].springback == pytest.approx(r[1].springback, rel=1e-4)  # both 47 deg
    assert r[2].springback == pytest.approx(r[0].springback * 60 / 47, rel=1e-4)


def test_no_yield_strength_means_no_physics_number():
    a = analyze(SAMPLES["PF-FT-2541"], "physics")  # STKM11A
    assert a.springback_model == "none" and "no specified yield" in a.springback_note
    assert all(row.springback == 0 for row in a.ybc.rows)


def test_measured_mode_needs_a_value():
    with pytest.raises(ValueError):
        analyze(SAMPLES["PF-FT-2541"], "measured")
    a = analyze(SAMPLES["PF-FT-2541"], "measured", measured_per_90=1.8)
    assert a.ybc.rows[0].springback == pytest.approx(1.8 * a.ybc.rows[0].nominal_A / 90)


def test_process_sheet_carries_the_computed_values(tmp_path):
    a = analyze(LP, "ml")
    path = write_excel(a, tmp_path / "ps.xlsx")
    wb = openpyxl.load_workbook(path)
    assert wb.sheetnames[0] == "工程表 Control plan" and "治具 Fixture" in wb.sheetnames
    text = " ".join(str(c.value) for row in wb.worksheets[0].iter_rows() for c in row if c.value)
    for ja in ("工程", "設備", "管理項目", "検査方法", "頻度", "異常処置"):
        assert ja in text
    assert f"{a.ybc.cut_length:.1f} mm" in text
    for r in a.ybc.rows:
        assert f"C {r.C:.2f} deg" in text
    ybc = wb["曲げ YBC program"]
    assert ybc.max_row == 1 + LP.n_bends


def test_process_sheet_pdf(tmp_path):
    p = write_pdf(analyze(SAMPLES["PF-HB-2201"]), tmp_path / "ps.pdf")
    assert p.read_bytes()[:5] == b"%PDF-"


def test_operations_never_invent_welding_parameters():
    ops = operations(analyze(SAMPLES["PF-HB-2201"]))
    weld = next(o for o in ops if o[0] == "40")
    assert "WPS" in weld[4] and "not defined" in weld[4]


def test_template_summary_is_grounded():
    facts = analyze(LP, "ml").summary()
    text = llm_assist.template_summary(facts)
    assert llm_assist.ungrounded_numbers(text, facts) == []


def test_llm_text_with_an_invented_number_is_rejected():
    facts = analyze(LP, "ml").summary()
    out = llm_assist.summarize(facts, llm=lambda f: "The part has 3 bends and a cycle time of 42.7 s.")
    assert out["source"] == "template" and "42.7" in out["rejected"]


def test_grounded_llm_text_is_kept():
    facts = analyze(LP, "ml").summary()
    good = f"{facts['part_no']} has {facts['n_bends']} bends; the program cut length is {facts['cut_length_program_mm']} mm."
    out = llm_assist.summarize(facts, llm=lambda f: good)
    assert out == {"text": good, "source": "llm", "rejected": None}


def test_llm_failure_falls_back_to_the_template():
    def boom(f):
        raise TimeoutError

    out = llm_assist.summarize(analyze(LP).summary(), llm=boom)
    assert out["source"] == "template" and "TimeoutError" in out["rejected"]


def test_without_a_key_the_feature_is_off(monkeypatch):
    monkeypatch.delenv("PIPEFORGE_LLM_API_KEY", raising=False)
    assert not llm_assist.available()
    assert llm_assist.summarize(analyze(LP).summary())["source"] == "template"
