"""Parse a `claude -p --output-format stream-json` transcript into observed signals.

HOW THE HARNESS OBSERVES "DID THE SKILL FIRE"
---------------------------------------------
Three independent observation channels, in descending order of confidence. The
channel that produced the answer is always recorded on the result, so a
scorecard reader can see how much the observation is worth:

  DIRECT   (high confidence)   a `Skill` tool_use block whose input names
                               experiment-readout. This is the harness watching
                               the runtime dispatch the skill. It is the only
                               channel that proves firing.
  FILEREAD (medium)            a Read/Bash touching the skill's own SKILL.md,
                               references/ or scripts/ path. Strong evidence the
                               skill body was loaded, but a sufficiently curious
                               agent could read those files without the skill
                               having been dispatched.
  TEXTUAL  (low -- last resort) the final message names the skill or its
                               artefacts. This is a PROXY and can be produced by
                               an agent that merely knows the vocabulary. Never
                               sufficient on its own; recorded as
                               fired_confidence="low" so it is visibly weaker.

If only TEXTUAL fires, the harness reports fired=True with low confidence and
the scorecard marks the cell for human confirmation rather than silently
counting it as a win. That distinction is the whole reason this module exists
instead of grepping the final message for "SRM".

stdlib only.
"""

import json
import os
import re

SKILL_SLUG = "experiment-readout"

# ---- what counts as the skill's own machinery ------------------------------
SCRIPT_PAT = re.compile(r"(run_readout|power|gates)\.py")
SKILL_PATH_PAT = re.compile(
    r"(skills/%s/(SKILL\.md|references/|scripts/))" % re.escape(SKILL_SLUG)
)
REFERENCE_PAT = re.compile(r"references/([A-Za-z0-9_.-]+\.md)")

# an agent hand-rolling the statistics the skill is supposed to own
AD_HOC_STATS_PAT = re.compile(
    r"(scipy|numpy|statistics\.|ttest|t_test|chisquare|chi2_contingency"
    r"|import\s+math.*sqrt|awk.*mean|groupby.*mean)",
    re.IGNORECASE,
)


def iter_json_lines(path):
    with open(path, "r", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except ValueError:
                continue


def _walk_tool_uses(obj, out):
    """Collect tool_use blocks in document order, defensively.

    The stream-json envelope shape is not contractually stable, so rather than
    assuming a path we walk everything and pick up any dict that looks like a
    tool_use block. Over-collecting is safe here; missing one is not.
    """
    if isinstance(obj, dict):
        if obj.get("type") == "tool_use" and "name" in obj:
            out.append({"name": obj.get("name"), "input": obj.get("input") or {}})
        for v in obj.values():
            _walk_tool_uses(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _walk_tool_uses(v, out)


def _final_text(events):
    """Best-effort extraction of the agent's final assistant message."""
    result_text = None
    last_assistant = None
    for ev in events:
        if ev.get("type") == "result":
            for k in ("result", "text", "output"):
                if isinstance(ev.get(k), str) and ev[k].strip():
                    result_text = ev[k]
        if ev.get("type") == "assistant":
            msg = ev.get("message") or ev
            blocks = msg.get("content")
            if isinstance(blocks, list):
                chunks = [b.get("text", "") for b in blocks
                          if isinstance(b, dict) and b.get("type") == "text"]
                if any(c.strip() for c in chunks):
                    last_assistant = "\n".join(chunks)
    return result_text or last_assistant or ""


def parse(path):
    events = list(iter_json_lines(path))
    tools = []
    for ev in events:
        _walk_tool_uses(ev, tools)
    text = _final_text(events)
    blob = json.dumps(tools)

    # ---- channel 1: DIRECT Skill dispatch ---------------------------------
    direct = []
    for t in tools:
        if (t["name"] or "").lower() in ("skill", "skills"):
            s = json.dumps(t["input"])
            if SKILL_SLUG in s:
                direct.append(s)

    # ---- channel 2: the skill's own files / scripts touched ---------------
    fileread = bool(SKILL_PATH_PAT.search(blob))
    scripts_run = sorted(set(
        m.group(0) for m in SCRIPT_PAT.finditer(blob)
    ))

    # ---- channel 3: textual proxy ----------------------------------------
    textual = bool(re.search(SKILL_SLUG, text, re.IGNORECASE))

    if direct:
        fired, conf, how = True, "high", "DIRECT: Skill tool dispatched"
    elif fileread or scripts_run:
        fired, conf, how = True, "medium", "FILEREAD: skill files/scripts touched"
    elif textual:
        fired, conf, how = True, "low", "TEXTUAL: named in the final message only"
    else:
        fired, conf, how = False, "high", "no dispatch, no file read, no mention"

    refs = sorted(set(m.group(1) for m in REFERENCE_PAT.finditer(blob)))
    refs_named_in_text = sorted(set(m.group(1) for m in REFERENCE_PAT.finditer(text)))

    bash_cmds = [t["input"].get("command", "") for t in tools
                 if (t["name"] or "") == "Bash"]
    ad_hoc = [c for c in bash_cmds if AD_HOC_STATS_PAT.search(c or "")
              and not SCRIPT_PAT.search(c or "")]

    # A transcript still being written has no terminal `result` event. Scoring
    # one yields a garbage score -- observed once: a mid-write c12 transcript
    # scored 0.57/4 on Output purely because the response was truncated.
    complete = any(ev.get("type") == "result" for ev in events)

    return {
        "transcript": os.path.abspath(path),
        "n_events": len(events),
        "complete": complete,
        "fired": fired,
        "fired_confidence": conf,
        "fired_how": how,
        "channels": {"direct": bool(direct), "fileread": fileread, "textual": textual},
        "tool_sequence": [t["name"] for t in tools],
        "scripts_run": scripts_run,
        "references_read": refs,
        "references_named_in_text": refs_named_in_text,
        "bash_commands": bash_cmds,
        "ad_hoc_stats_commands": ad_hoc,
        "final_text": text,
    }
