import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pipeforge.station import TRANSITIONS, Inputs, S, Station, io_list, mermaid

N = 3
PART = "PF-HB-2201"


def inp(seat=False, end=False, clamp=False, **kw):
    return Inputs(seat=[seat] * N, end=[end] * 2, clamp_closed=[clamp] * N, **kw)


def run_good_cycle(st: Station):
    st.scan(inp(seat=True))
    assert st.state is S.PART_PRESENT
    st.scan(inp(seat=True, end=True, barcode=PART))
    assert st.state is S.CLAMPING
    st.scan(inp(seat=True, end=True, clamp=True))
    assert st.state is S.CHECK
    for _ in range(st.debounce_scans):
        out = st.scan(inp(seat=True, end=True, clamp=True))
    assert st.state is S.PASS and out.print_label and out.lamp_green
    st.scan(inp(seat=True, end=True, clamp=True, label_done=True))
    assert st.state is S.UNCLAMP
    st.scan(inp())
    assert st.state is S.IDLE


def test_good_part_passes_and_prints_one_label():
    st = Station(PART, N)
    run_good_cycle(st)
    assert (st.passed, st.failed) == (1, 0)


def test_wrong_barcode_fails_without_clamping():
    st = Station(PART, N)
    st.scan(inp(seat=True))
    out = st.scan(inp(seat=True, barcode="PF-FT-2541"))
    assert st.state is S.FAIL and not out.clamp_close and out.lamp_red
    assert "wrong part" in st.reason


def test_unseated_tube_fails_and_names_the_sensor():
    st = Station(PART, N, settle_scans=5)
    st.scan(inp(seat=True))
    st.scan(inp(seat=True, end=True, barcode=PART))
    st.scan(inp(seat=True, end=True, clamp=True))
    bad = Inputs(seat=[True, False, True], end=[True, True], clamp_closed=[True] * N)
    for _ in range(10):
        out = st.scan(bad)
    assert st.state is S.FAIL and not out.print_label
    assert "PX2" in st.reason


def test_fail_stays_locked_until_the_ng_bin_sees_the_part():
    st = Station(PART, N)
    st.scan(inp(seat=True))
    st.scan(inp(seat=True, barcode="WRONG"))
    for _ in range(100):
        st.scan(inp())
    assert st.state is S.FAIL  # removing the part is not enough
    st.scan(inp(ng_bin=True))
    assert st.state is S.UNCLAMP
    st.scan(inp())
    assert st.state is S.IDLE


def test_clamp_timeout_fails():
    st = Station(PART, N, clamp_timeout_scans=4)
    st.scan(inp(seat=True))
    st.scan(inp(seat=True, end=True, barcode=PART))
    for _ in range(6):
        st.scan(inp(seat=True, end=True, clamp=False))
    assert st.state is S.FAIL and "clamp" in st.reason


def test_estop_drops_outputs_and_needs_reset_with_estop_released():
    st = Station(PART, N)
    st.scan(inp(seat=True))
    st.scan(inp(seat=True, end=True, barcode=PART))
    out = st.scan(inp(seat=True, end=True, estop=True))
    assert st.state is S.ESTOP and not out.clamp_close and out.lamp_red
    st.scan(inp(estop=True, reset=True))
    assert st.state is S.ESTOP  # reset ignored while E-stop is still pressed
    st.scan(inp(reset=True))
    assert st.state is S.IDLE


def test_part_removed_before_scan_returns_to_idle():
    st = Station(PART, N)
    st.scan(inp(seat=True))
    st.scan(inp())
    assert st.state is S.IDLE


def test_flicker_shorter_than_debounce_does_not_pass():
    st = Station(PART, N, debounce_scans=3, settle_scans=50)
    st.scan(inp(seat=True))
    st.scan(inp(seat=True, end=True, barcode=PART))
    st.scan(inp(seat=True, end=True, clamp=True))
    for k in range(12):  # sensors good on every other scan only
        st.scan(inp(seat=k % 2 == 0, end=True, clamp=True))
    assert st.state is S.CHECK


def test_io_list_has_every_sensor_and_unique_addresses():
    rows = io_list(N)
    tags = {r["tag"] for r in rows}
    assert {"PX1", "PX2", "PX3", "END1", "END2", "CLAMP_SOL", "PRINT", "LAMP_R"} <= tags
    addrs = [r["address"] for r in rows if r["address"] != "serial"]
    assert len(addrs) == len(set(addrs))


def test_mermaid_lists_every_transition():
    text = mermaid()
    assert text.startswith("stateDiagram-v2")
    for a, b, _ in TRANSITIONS:
        assert f"{a.value} --> {b.value}" in text


def test_every_observed_transition_is_in_the_table():
    st = Station(PART, N, settle_scans=4, clamp_timeout_scans=3)
    run_good_cycle(st)
    st.scan(inp(seat=True))
    st.scan(inp(seat=True, barcode="X"))
    st.scan(inp(ng_bin=True))
    st.scan(inp())
    allowed = {(a, b) for a, b, _ in TRANSITIONS} | {(s, S.ESTOP) for s in S}
    assert all((a, b) in allowed for a, b, _ in st.history)


@st.composite
def input_stream(draw):
    n = draw(st.integers(5, 80))
    out = []
    for _ in range(n):
        out.append(
            Inputs(
                seat=draw(st.lists(st.booleans(), min_size=N, max_size=N)),
                end=draw(st.lists(st.booleans(), min_size=2, max_size=2)),
                clamp_closed=draw(st.lists(st.booleans(), min_size=N, max_size=N)),
                barcode=draw(st.sampled_from([None, None, None, PART, "WRONG"])),
                ng_bin=draw(st.booleans()),
                estop=draw(st.booleans().filter(lambda _: True)) and draw(st.integers(0, 9)) == 0,
                reset=draw(st.booleans()),
                label_done=draw(st.booleans()),
            )
        )
    return out


@settings(max_examples=300, deadline=None)
@given(stream=input_stream())
def test_label_never_prints_unless_every_sensor_and_clamp_is_on(stream):
    st_ = Station(PART, N, debounce_scans=2, settle_scans=6, clamp_timeout_scans=5)
    for i in stream:
        out = st_.scan(i)
        if out.print_label:
            assert all(i.seat) and all(i.end) and all(i.clamp_closed)
            assert st_.state is S.PASS
        if st_.state is S.ESTOP:
            assert not out.clamp_close and not out.print_label


@settings(max_examples=200, deadline=None)
@given(stream=input_stream())
def test_pass_is_only_entered_from_check_after_a_correct_barcode(stream):
    st_ = Station(PART, N, debounce_scans=2, settle_scans=6, clamp_timeout_scans=5)
    for i in stream:
        st_.scan(i)
    for k, (a, b, _) in enumerate(st_.history):
        if b is S.PASS:
            assert a is S.CHECK
            earlier = [h for h in st_.history[:k] if h[1] is S.CLAMPING]
            assert earlier and earlier[-1][2] == "barcode == fixture part no."


def test_wrong_input_image_is_rejected():
    with pytest.raises(ValueError):
        Station(PART, N).scan(Inputs(seat=[True], end=[True, True], clamp_closed=[True] * N))
