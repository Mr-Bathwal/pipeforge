"""Optional engineering summary written by an LLM, grounded in computed values only.

The model receives only the JSON from :meth:`Analysis.summary` and is told
to rephrase it. Its answer is then checked: every number in the text must
appear in that JSON (after rounding), otherwise the answer is rejected and
the deterministic template summary is shown instead. So the assistant can
improve wording but cannot introduce a number.

The feature is off unless ``PIPEFORGE_LLM_API_KEY`` is set (any
OpenAI-compatible endpoint; ``PIPEFORGE_LLM_BASE_URL`` and
``PIPEFORGE_LLM_MODEL`` default to Groq and Llama 3.3 70B). The key is read
from the environment only and never logged or stored.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from collections.abc import Callable

NUMBER = re.compile(r"(?<![A-Za-z0-9.])-?\d+(?:\.\d+)?")  # whole numbers only, not "04" inside "SUS304"
SYSTEM = (
    "You are a manufacturing engineer writing a short summary of a bent-tube part for a process review. "
    "Use ONLY the facts in the JSON you are given. Do not add any number that is not in the JSON, do not "
    "estimate, do not convert units. Write 4 to 6 plain sentences: the part, the bending program and "
    "springback compensation, the manufacturability findings and what to do about them, and the fixture."
)


def _numbers_in(obj) -> set[str]:  # type: ignore[no-untyped-def]
    out: set[str] = set()
    if isinstance(obj, dict):
        for v in obj.values():
            out |= _numbers_in(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out |= _numbers_in(v)
    elif isinstance(obj, bool):
        pass
    elif isinstance(obj, (int, float)):
        out |= _forms(float(obj))
    elif isinstance(obj, str):
        for m in NUMBER.findall(obj):
            out |= _forms(float(m))
    return out


def _forms(x: float) -> set[str]:
    """Spellings of x a writer might use: as given, and rounded to 0, 1 or 2 decimals."""
    forms = {f"{x:g}", f"{x:.0f}", f"{x:.1f}", f"{x:.2f}"}
    if float(x).is_integer():
        forms.add(str(int(x)))
    return {f.rstrip("0").rstrip(".") if "." in f else f for f in forms}


def ungrounded_numbers(text: str, facts: dict) -> list[str]:
    """Numbers in *text* that do not appear in *facts* (empty list = grounded)."""
    allowed = _numbers_in(facts)
    bad = []
    for m in NUMBER.findall(text):
        norm = m.rstrip("0").rstrip(".") if "." in m else m
        if norm not in allowed and m not in allowed:
            bad.append(m)
    return bad


def template_summary(facts: dict) -> str:
    """Deterministic summary from the facts: always grounded, used when no LLM is available."""
    f = facts
    lines = [
        f"{f['part_no']} ({f['name']}) is a {f['material']} tube, OD {f['od_mm']:g} x {f['wall_mm']:g} mm, "
        f"with {f['n_bends']} bends and a programmed cut length of {f['cut_length_program_mm']} mm.",
        f"Springback compensation uses the {f['springback_model']} model; the die angles are "
        + ", ".join(f"{b['C_deg']} deg for bend {b['bend']}" for b in f["bends"]) + ".",
        f"Tooling from the bend die chart: {f['tooling']}. Bend sequence: {f['bend_sequence']}.",
    ]
    if f["dfm_findings"]:
        lines.append("Manufacturability findings: " + " ".join(f["dfm_findings"]))
    else:
        lines.append("All manufacturability checks pass.")
    lines.append(f"The checking fixture has {f['fixture_blocks']} grooved blocks, {f['fixture_clamps']} clamps and "
                 f"{f['fixture_sensors']} sensors.")
    return " ".join(lines)


def _call(facts: dict) -> str:
    key = os.environ.get("PIPEFORGE_LLM_API_KEY")
    if not key:
        raise RuntimeError("no API key set")
    base = os.environ.get("PIPEFORGE_LLM_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
    model = os.environ.get("PIPEFORGE_LLM_MODEL", "llama-3.3-70b-versatile")
    body = json.dumps({"model": model, "temperature": 0.2, "messages": [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": json.dumps(facts, ensure_ascii=False)},
    ]}).encode("utf-8")
    req = urllib.request.Request(f"{base}/chat/completions", data=body, method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return str(data["choices"][0]["message"]["content"]).strip()


def available() -> bool:
    return bool(os.environ.get("PIPEFORGE_LLM_API_KEY"))


def summarize(facts: dict, llm: Callable[[dict], str] | None = None) -> dict:
    """Try the LLM; keep its text only if every number in it is grounded."""
    caller = llm or (_call if available() else None)
    if caller is None:
        return {"text": template_summary(facts), "source": "template", "rejected": None}
    try:
        text = caller(facts)
    except Exception as exc:  # network, quota, malformed reply
        return {"text": template_summary(facts), "source": "template", "rejected": f"LLM call failed: {type(exc).__name__}"}
    bad = ungrounded_numbers(text, facts)
    if bad:
        return {"text": template_summary(facts), "source": "template",
                "rejected": f"LLM text had numbers not in the computed data: {', '.join(bad[:8])}"}
    return {"text": text, "source": "llm", "rejected": None}
