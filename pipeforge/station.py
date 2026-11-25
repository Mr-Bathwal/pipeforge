"""Automated checking station: a PLC-style sequence written as a state machine.

The station is the checking fixture (fixture.py) plus pneumatic toggle
clamps, an inductive proximity sensor under each clamped groove, end-position
sensors at both tube ends, a barcode reader, a label printer, a stack light
(andon) and an NG (reject) bin with its own sensor.

It runs like a PLC: :meth:`Station.scan` is called once per scan cycle with
the input image and returns the output image. The transition table
:data:`TRANSITIONS` is the single source of truth; the Mermaid diagram in
docs/FIXTURE_DESIGN.md and the tests are generated from it.

Poka-yoke interlocks (each has a test):

* PASS is reachable only from CHECK, and only when every seat and end
  sensor is on, the clamps are confirmed closed, and the scanned part number
  matched. The label printer output is energised only in PASS.
* Clamps close only after a correct barcode, so a wrong part is never clamped.
* After a FAIL the station stays locked until the NG-bin sensor sees the
  part go into the reject bin, so a bad part cannot drift back into the flow.
* Sensors must be stable for ``debounce_scans`` cycles before CHECK decides.
* E-stop from any state drops every output; only RESET (with E-stop released)
  returns to IDLE.

The I/O addresses are illustrative (Siemens-style I0.0/Q0.0 notation).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class S(str, Enum):
    IDLE = "IDLE"
    PART_PRESENT = "PART_PRESENT"
    CLAMPING = "CLAMPING"
    CHECK = "CHECK"
    PASS = "PASS"
    FAIL = "FAIL"
    UNCLAMP = "UNCLAMP"
    ESTOP = "ESTOP"


#: (from, to, condition text) for the diagram; the logic in Station.scan implements exactly these.
TRANSITIONS: tuple[tuple[S, S, str], ...] = (
    (S.IDLE, S.PART_PRESENT, "any seat or end sensor ON"),
    (S.PART_PRESENT, S.CLAMPING, "barcode == fixture part no."),
    (S.PART_PRESENT, S.FAIL, "barcode != fixture part no."),
    (S.PART_PRESENT, S.IDLE, "all sensors OFF (part removed)"),
    (S.CLAMPING, S.CHECK, "all clamp-closed switches ON"),
    (S.CLAMPING, S.FAIL, "clamp timeout"),
    (S.CHECK, S.PASS, "all seat + end sensors ON, stable"),
    (S.CHECK, S.FAIL, "any sensor OFF after settle time"),
    (S.PASS, S.UNCLAMP, "label printed"),
    (S.FAIL, S.UNCLAMP, "part detected in NG bin"),
    (S.UNCLAMP, S.IDLE, "clamps open and all sensors OFF"),
    (S.IDLE, S.ESTOP, "E-stop"),
    (S.ESTOP, S.IDLE, "RESET with E-stop released"),
)


@dataclass
class Inputs:
    seat: list[bool]  #: one per clamped block (PX1..)
    end: list[bool]  #: start and end position sensors
    clamp_closed: list[bool]  #: reed switch per clamp
    barcode: str | None = None  #: last scan this cycle, or None
    ng_bin: bool = False
    estop: bool = False  #: True = E-stop pressed
    reset: bool = False
    label_done: bool = False


@dataclass
class Outputs:
    clamp_close: bool = False
    lamp_green: bool = False
    lamp_red: bool = False
    lamp_amber: bool = False
    print_label: bool = False
    buzzer: bool = False


@dataclass
class Station:
    part_no: str
    n_clamps: int
    debounce_scans: int = 3
    settle_scans: int = 20  #: CHECK waits this long for sensors before failing
    clamp_timeout_scans: int = 50  #: e.g. 2.5 s at a 50 ms scan
    state: S = S.IDLE
    timer: int = 0
    stable: int = 0
    reason: str = ""
    passed: int = 0
    failed: int = 0
    history: list[tuple[S, S, str]] = field(default_factory=list)

    def _go(self, new: S, why: str) -> None:
        self.history.append((self.state, new, why))
        self.state = new
        self.timer = 0
        self.stable = 0

    def scan(self, i: Inputs) -> Outputs:
        """One PLC scan: read inputs, step the sequence, write outputs."""
        if len(i.seat) != self.n_clamps or len(i.clamp_closed) != self.n_clamps or len(i.end) != 2:
            raise ValueError("input image does not match the station's I/O list")
        self.timer += 1
        all_sensors = all(i.seat) and all(i.end)
        any_sensor = any(i.seat) or any(i.end)

        if i.estop and self.state is not S.ESTOP:
            self.reason = "E-stop"
            self._go(S.ESTOP, "E-stop")
        elif self.state is S.ESTOP:
            if i.reset and not i.estop:
                self.reason = ""
                self._go(S.IDLE, "RESET with E-stop released")
        elif self.state is S.IDLE:
            if any_sensor:
                self._go(S.PART_PRESENT, "any seat or end sensor ON")
        elif self.state is S.PART_PRESENT:
            if i.barcode is not None:
                if i.barcode.strip() == self.part_no:
                    self._go(S.CLAMPING, "barcode == fixture part no.")
                else:
                    self.reason = f"wrong part: scanned {i.barcode.strip()!r}, fixture is {self.part_no!r}"
                    self.failed += 1
                    self._go(S.FAIL, "barcode != fixture part no.")
            elif not any_sensor:
                self._go(S.IDLE, "all sensors OFF (part removed)")
        elif self.state is S.CLAMPING:
            if all(i.clamp_closed):
                self._go(S.CHECK, "all clamp-closed switches ON")
            elif self.timer > self.clamp_timeout_scans:
                self.reason = "clamp did not close in time"
                self.failed += 1
                self._go(S.FAIL, "clamp timeout")
        elif self.state is S.CHECK:
            ok = all_sensors and all(i.clamp_closed)
            self.stable = self.stable + 1 if ok else 0
            if self.stable >= self.debounce_scans:
                self.passed += 1
                self._go(S.PASS, "all seat + end sensors ON, stable")
            elif self.timer > self.settle_scans:
                off = [f"PX{k + 1}" for k, v in enumerate(i.seat) if not v]
                off += [f"END{k + 1}" for k, v in enumerate(i.end) if not v]
                off += [f"CLAMP{k + 1}" for k, v in enumerate(i.clamp_closed) if not v]
                self.reason = "not seated: " + ", ".join(off)
                self.failed += 1
                self._go(S.FAIL, "any sensor OFF after settle time")
        elif self.state is S.PASS:
            if i.label_done:
                self._go(S.UNCLAMP, "label printed")
        elif self.state is S.FAIL:
            if i.ng_bin:
                self._go(S.UNCLAMP, "part detected in NG bin")
        elif self.state is S.UNCLAMP and not any(i.clamp_closed) and not any_sensor:
            self.reason = ""
            self._go(S.IDLE, "clamps open and all sensors OFF")
        return self.outputs(i)

    def outputs(self, i: Inputs) -> Outputs:
        """Output image for the current state, with the PASS interlock re-checked."""
        st = self.state
        o = Outputs()
        if st is S.ESTOP:
            o.lamp_red = o.buzzer = True
            return o
        o.clamp_close = st in (S.CLAMPING, S.CHECK, S.PASS)
        # On FAIL the clamps open so the operator can move the part to the NG bin;
        # the bin sensor, not the operator, releases the station for the next part.
        o.lamp_green = st is S.PASS
        o.lamp_red = st is S.FAIL
        o.lamp_amber = st in (S.PART_PRESENT, S.CLAMPING, S.CHECK)
        o.print_label = st is S.PASS and all(i.seat) and all(i.end) and all(i.clamp_closed)
        o.buzzer = st is S.FAIL
        return o


def io_list(n_clamps: int) -> list[dict[str, str]]:
    """Illustrative I/O list with PLC-style addresses."""
    rows: list[dict[str, str]] = []
    addr = 0

    def nxt(prefix: str) -> str:
        nonlocal addr
        a = f"{prefix}{addr // 8}.{addr % 8}"
        addr += 1
        return a

    for k in range(n_clamps):
        rows.append({"address": nxt("I"), "tag": f"PX{k + 1}", "type": "DI", "device": "inductive prox. M12, PNP NO",
                     "meaning": f"tube seated in clamped groove {k + 1}"})
    for k, end in enumerate(("start", "end")):
        rows.append({"address": nxt("I"), "tag": f"END{k + 1}", "type": "DI", "device": "inductive prox. M12, PNP NO",
                     "meaning": f"tube {end} end at stop"})
    for k in range(n_clamps):
        rows.append({"address": nxt("I"), "tag": f"CLAMP{k + 1}_CL", "type": "DI", "device": "cylinder reed switch",
                     "meaning": f"clamp {k + 1} closed"})
    for tag, dev, meaning in (
        ("NG_BIN", "photoelectric, diffuse", "part dropped into NG bin"),
        ("ESTOP", "E-stop, NC contact (via safety relay)", "E-stop pressed when OFF"),
        ("RESET", "push button, NO", "reset after E-stop"),
    ):
        rows.append({"address": nxt("I"), "tag": tag, "type": "DI", "device": dev, "meaning": meaning})
    addr = 0
    for tag, dev, meaning in (
        ("CLAMP_SOL", "5/2 solenoid valve", "close all clamps"),
        ("LAMP_G", "stack light green", "PASS"),
        ("LAMP_A", "stack light amber", "cycle running"),
        ("LAMP_R", "stack light red", "FAIL / E-stop (andon)"),
        ("BUZZER", "buzzer", "FAIL / E-stop"),
        ("PRINT", "label printer trigger", "print PASS label"),
    ):
        rows.append({"address": nxt("Q"), "tag": tag, "type": "DO", "device": dev, "meaning": meaning})
    rows.append({"address": "serial", "tag": "BARCODE", "type": "COM", "device": "2D barcode reader",
                 "meaning": "part number on the work-order label"})
    return rows


def mermaid() -> str:
    """State diagram, generated from TRANSITIONS."""
    lines = ["stateDiagram-v2", "    [*] --> IDLE"]
    for a, b, cond in TRANSITIONS:
        lines.append(f"    {a.value} --> {b.value}: {cond}")
    lines.append("    note right of ESTOP: reachable from every state")
    return "\n".join(lines)
